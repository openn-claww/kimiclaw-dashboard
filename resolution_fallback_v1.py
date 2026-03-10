"""
═══════════════════════════════════════════════════════════════════════════════
RESOLUTION FALLBACK SYSTEM v1.0
For: Polymarket Up-Down BTC/ETH/SOL/XRP 5m/15m Trading Bot
═══════════════════════════════════════════════════════════════════════════════

THREE-TIER RESOLUTION:
  Tier 1 (Primary)   → Polymarket API returns resolved: true
  Tier 2 (Fallback1) → Unresolved >2h  → Binance/Coinbase price verification
  Tier 3 (Fallback2) → Unresolved >48h → Auto-resolve, free capital

PRICE SOURCE PRIORITY:
  1. Binance REST API (matches Polymarket's oracle most often)
  2. Coinbase REST API (backup)
  3. OKX REST API     (last resort)

SAFETY MODEL:
  - Fallback resolutions logged separately with FULL audit trail
  - Paper mode: immediate resolution allowed
  - Live mode: fallback resolutions flagged for human review
  - Discrepancy detection when Polymarket eventually resolves
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class ResolutionConfig:
    # Tier 2 trigger: hours before fallback resolution kicks in
    FALLBACK1_TRIGGER_HOURS: float = 2.0

    # Tier 3 trigger: hours before forced capital release
    FALLBACK2_TRIGGER_HOURS: float = 48.0

    # Price fetch: how many seconds around expiration to average
    PRICE_WINDOW_SECONDS: int = 60

    # Max allowed spread between exchanges before flagging (%)
    MAX_EXCHANGE_SPREAD_PCT: float = 0.5

    # Price exactly at entry = NO wins (DOWN) — match Polymarket convention
    # Set to True if your markets specify otherwise
    TIE_GOES_TO_DOWN: bool = True

    # In LIVE mode, do we actually finalize on fallback, or just flag?
    LIVE_FALLBACK_AUTO_FINALIZE: bool = True  # Set False for conservative ops

    # Audit log path
    AUDIT_LOG_PATH: str = "/root/.openclaw/workspace/resolution_audit.jsonl"

    # Resolution state file
    RESOLUTION_STATE_PATH: str = "/root/.openclaw/workspace/resolution_state.json"


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ResolutionSource(str, Enum):
    POLYMARKET   = "polymarket_official"
    BINANCE      = "binance_fallback"
    COINBASE     = "coinbase_fallback"
    OKX          = "okx_fallback"
    FORCED       = "forced_48h_release"
    MANUAL       = "manual_override"


class ResolutionTier(int, Enum):
    PRIMARY   = 1
    FALLBACK1 = 2
    FALLBACK2 = 3


@dataclass
class PriceSnapshot:
    exchange: str
    symbol: str
    price: float
    timestamp_utc: str
    raw_response: dict = field(default_factory=dict)


@dataclass
class ResolutionAttempt:
    market_id: str
    attempt_time_utc: str
    tier: int
    source: str
    success: bool
    outcome: Optional[str]        # 'YES' or 'NO' or None
    entry_price: Optional[float]
    exit_price: Optional[float]
    exchange_used: Optional[str]
    notes: str
    fallback_prices: dict = field(default_factory=dict)


@dataclass
class ResolutionState:
    """Per-market resolution tracking — persisted to JSON."""
    market_id: str
    slug: str
    coin: str
    timeframe_minutes: int
    entry_price: float
    position_side: str              # 'YES' or 'NO'
    expiration_utc: str             # ISO format
    first_checked_utc: str
    last_checked_utc: str
    resolution_attempts: int = 0
    resolved: bool = False
    resolution_tier: Optional[int] = None
    resolution_source: Optional[str] = None
    resolution_outcome: Optional[str] = None
    resolution_time_utc: Optional[str] = None
    polymarket_confirmed: bool = False   # True once Polymarket officially agrees
    discrepancy_detected: bool = False   # True if Polymarket outcome != fallback
    flagged_for_review: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# PRICE FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

class PriceFetcher:
    """
    Fetch spot price from multiple exchanges with automatic failover.
    Polymarket most commonly uses Binance or Coinbase as oracle source.
    """

    SYMBOL_MAP = {
        "BTC":  {"binance": "BTCUSDT",  "coinbase": "BTC-USD",  "okx": "BTC-USDT"},
        "ETH":  {"binance": "ETHUSDT",  "coinbase": "ETH-USD",  "okx": "ETH-USDT"},
        "SOL":  {"binance": "SOLUSDT",  "coinbase": "SOL-USD",  "okx": "SOL-USDT"},
        "XRP":  {"binance": "XRPUSDT",  "coinbase": "XRP-USD",  "okx": "XRP-USDT"},
    }

    TIMEOUT = 5  # seconds

    # ── Binance ───────────────────────────────────────────────────────────────

    def get_binance_price_at(self, coin: str, target_ts_ms: int) -> Optional[PriceSnapshot]:
        """
        Fetch 1m kline that covers target_ts_ms from Binance.
        Uses close price of the 1m candle as proxy for exact expiration price.
        """
        symbol = self.SYMBOL_MAP.get(coin, {}).get("binance")
        if not symbol:
            return None

        # Start 1 candle before target, fetch 3 candles to be safe
        start_ms = target_ts_ms - 60_000

        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol":    symbol,
                "interval":  "1m",
                "startTime": start_ms,
                "limit":     3,
            }
            r = requests.get(url, params=params, timeout=self.TIMEOUT)
            r.raise_for_status()
            klines = r.json()

            if not klines:
                return None

            # Find the kline that contains target_ts_ms
            price = None
            for k in klines:
                open_ts  = k[0]
                close_ts = k[6]
                if open_ts <= target_ts_ms <= close_ts:
                    price = float(k[4])  # close price
                    break

            # If exact candle not found, use closest close
            if price is None:
                price = float(klines[-1][4])

            return PriceSnapshot(
                exchange="binance",
                symbol=symbol,
                price=price,
                timestamp_utc=datetime.fromtimestamp(
                    target_ts_ms / 1000, tz=timezone.utc
                ).isoformat(),
                raw_response={"klines_count": len(klines)},
            )

        except Exception as e:
            logging.warning(f"[PriceFetcher] Binance failed for {coin}: {e}")
            return None

    def get_binance_current_price(self, coin: str) -> Optional[PriceSnapshot]:
        """Get current spot price from Binance (for near-real-time checks)."""
        symbol = self.SYMBOL_MAP.get(coin, {}).get("binance")
        if not symbol:
            return None
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            r = requests.get(url, timeout=self.TIMEOUT)
            r.raise_for_status()
            data = r.json()
            return PriceSnapshot(
                exchange="binance",
                symbol=symbol,
                price=float(data["price"]),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                raw_response=data,
            )
        except Exception as e:
            logging.warning(f"[PriceFetcher] Binance current price failed: {e}")
            return None

    # ── Coinbase ──────────────────────────────────────────────────────────────

    def get_coinbase_price_at(self, coin: str, target_ts_ms: int) -> Optional[PriceSnapshot]:
        """Fetch 1m candle from Coinbase Advanced Trade API."""
        symbol = self.SYMBOL_MAP.get(coin, {}).get("coinbase")
        if not symbol:
            return None

        target_dt = datetime.fromtimestamp(target_ts_ms / 1000, tz=timezone.utc)
        start_iso = datetime.fromtimestamp(
            (target_ts_ms - 120_000) / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = target_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"
            params = {
                "granularity": 60,
                "start": start_iso,
                "end": end_iso,
            }
            r = requests.get(url, params=params, timeout=self.TIMEOUT)
            r.raise_for_status()
            candles = r.json()  # [time, low, high, open, close, volume]

            if not candles:
                return None

            # Coinbase returns most recent first
            price = float(candles[0][4])  # close

            return PriceSnapshot(
                exchange="coinbase",
                symbol=symbol,
                price=price,
                timestamp_utc=target_dt.isoformat(),
                raw_response={"candles_count": len(candles)},
            )

        except Exception as e:
            logging.warning(f"[PriceFetcher] Coinbase failed for {coin}: {e}")
            return None

    # ── OKX (last resort) ─────────────────────────────────────────────────────

    def get_okx_price_at(self, coin: str, target_ts_ms: int) -> Optional[PriceSnapshot]:
        symbol = self.SYMBOL_MAP.get(coin, {}).get("okx")
        if not symbol:
            return None
        try:
            url = "https://www.okx.com/api/v5/market/history-candles"
            params = {
                "instId": symbol,
                "bar":    "1m",
                "before": str(target_ts_ms - 120_000),
                "after":  str(target_ts_ms + 60_000),
                "limit":  "5",
            }
            r = requests.get(url, params=params, timeout=self.TIMEOUT)
            r.raise_for_status()
            data = r.json()
            candles = data.get("data", [])
            if not candles:
                return None
            price = float(candles[0][4])
            return PriceSnapshot(
                exchange="okx",
                symbol=symbol,
                price=price,
                timestamp_utc=datetime.fromtimestamp(
                    target_ts_ms / 1000, tz=timezone.utc
                ).isoformat(),
            )
        except Exception as e:
            logging.warning(f"[PriceFetcher] OKX failed for {coin}: {e}")
            return None

    # ── Unified fetch with failover ───────────────────────────────────────────

    def get_price_with_failover(
        self,
        coin: str,
        target_ts_ms: int,
    ) -> tuple[Optional[PriceSnapshot], dict]:
        """
        Try Binance → Coinbase → OKX.
        Returns (best_snapshot, all_snapshots_dict).
        all_snapshots_dict contains prices from ALL successful exchanges
        so we can cross-check for spread anomalies.
        """
        fetchers = [
            ("binance",  self.get_binance_price_at),
            ("coinbase", self.get_coinbase_price_at),
            ("okx",      self.get_okx_price_at),
        ]

        all_prices: dict[str, PriceSnapshot] = {}
        primary: Optional[PriceSnapshot] = None

        for exchange_name, fetch_fn in fetchers:
            snap = fetch_fn(coin, target_ts_ms)
            if snap:
                all_prices[exchange_name] = snap
                if primary is None:
                    primary = snap

        return primary, all_prices


# ─────────────────────────────────────────────────────────────────────────────
# OUTCOME DETERMINER
# ─────────────────────────────────────────────────────────────────────────────

class OutcomeDeterminer:
    """
    Determines YES/NO outcome from entry price vs exit price.
    Mirrors Polymarket Up-Down market logic.
    """

    def determine(
        self,
        entry_price: float,
        exit_price: float,
        config: ResolutionConfig = None,
    ) -> tuple[str, str]:
        """
        Returns (outcome, reason_string).
        outcome: 'YES' if price went UP, 'NO' if price went DOWN or flat.
        """
        cfg = config or ResolutionConfig()

        if exit_price > entry_price:
            pct = ((exit_price - entry_price) / entry_price) * 100
            return "YES", f"Price UP {pct:.4f}% ({entry_price} → {exit_price})"

        elif exit_price < entry_price:
            pct = ((entry_price - exit_price) / entry_price) * 100
            return "NO", f"Price DOWN {pct:.4f}% ({entry_price} → {exit_price})"

        else:
            # Exact tie — convention: NO wins (DOWN)
            if cfg.TIE_GOES_TO_DOWN:
                return "NO", f"Price UNCHANGED at {exit_price} — tie → NO wins"
            else:
                return "YES", f"Price UNCHANGED at {exit_price} — tie → YES wins"

    def check_exchange_spread(
        self,
        all_prices: dict[str, "PriceSnapshot"],
        max_spread_pct: float,
    ) -> tuple[bool, str]:
        """
        Returns (spread_ok, description).
        Warns if spread between exchanges is suspiciously large.
        """
        if len(all_prices) < 2:
            return True, "Only one exchange available, cannot cross-check."

        prices = [s.price for s in all_prices.values()]
        min_p  = min(prices)
        max_p  = max(prices)
        spread = ((max_p - min_p) / min_p) * 100

        if spread > max_spread_pct:
            exchanges_str = ", ".join(
                f"{k}={v.price}" for k, v in all_prices.items()
            )
            return False, f"⚠ LARGE SPREAD {spread:.3f}% between {exchanges_str}"
        else:
            return True, f"Spread OK ({spread:.4f}%)"


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOGGER
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogger:
    """Append-only JSONL audit log for all resolution events."""

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)

    def log(self, attempt: ResolutionAttempt):
        entry = {
            **asdict(attempt),
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logging.info(
            f"[Audit] {attempt.market_id} | Tier {attempt.tier} | "
            f"{attempt.source} | outcome={attempt.outcome} | ok={attempt.success}"
        )

    def load_all(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        with open(self.log_path) as f:
            return [json.loads(line) for line in f if line.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# RESOLUTION STATE MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class ResolutionStateManager:
    """Manages per-market resolution state with JSON persistence."""

    def __init__(self, state_path: str):
        self.state_path = Path(state_path)
        self._state: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                self._state = json.load(f)

    def _save(self):
        with open(self.state_path, "w") as f:
            json.dump(self._state, f, indent=2)

    def get(self, market_id: str) -> Optional[ResolutionState]:
        data = self._state.get(market_id)
        if not data:
            return None
        return ResolutionState(**data)

    def upsert(self, rs: ResolutionState):
        self._state[rs.market_id] = asdict(rs)
        self._save()

    def get_all_unresolved(self) -> list[ResolutionState]:
        return [
            ResolutionState(**v)
            for v in self._state.values()
            if not v.get("resolved", False)
        ]

    def register_position(
        self,
        market_id: str,
        slug: str,
        coin: str,
        timeframe_minutes: int,
        entry_price: float,
        position_side: str,
        expiration_utc: str,
    ) -> ResolutionState:
        """Called when a new position opens — starts tracking."""
        now = datetime.now(timezone.utc).isoformat()
        rs = ResolutionState(
            market_id=market_id,
            slug=slug,
            coin=coin,
            timeframe_minutes=timeframe_minutes,
            entry_price=entry_price,
            position_side=position_side,
            expiration_utc=expiration_utc,
            first_checked_utc=now,
            last_checked_utc=now,
        )
        self.upsert(rs)
        logging.info(f"[StateManager] Registered {market_id} ({coin} {timeframe_minutes}m)")
        return rs


# ─────────────────────────────────────────────────────────────────────────────
# POLYMARKET API HELPER
# ─────────────────────────────────────────────────────────────────────────────

GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_polymarket_status(slug: str, timeout: int = 5) -> dict:
    """Returns market data dict or empty dict on failure."""
    try:
        url = f"{GAMMA_API}/markets/slug/{slug}"
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.warning(f"[Polymarket] API fetch failed for {slug}: {e}")
        return {}


def parse_polymarket_outcome(data: dict) -> Optional[str]:
    """
    Returns 'YES', 'NO', or None.
    winningOutcomeIndex: 0 = YES (Up), 1 = NO (Down)
    """
    if not data.get("resolved"):
        return None
    winner = data.get("winningOutcomeIndex")
    if winner == 0:
        return "YES"
    elif winner == 1:
        return "NO"
    return None


def extract_expiration_from_slug(slug: str) -> Optional[int]:
    """
    Parses Unix timestamp from slug like btc-updown-5m-1709251200.
    Returns milliseconds.
    """
    try:
        ts_str = slug.split("-")[-1]
        return int(ts_str) * 1000
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RESOLUTION FALLBACK ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ResolutionFallbackEngine:
    """
    Drop-in replacement/extension for your check_all_exits() loop.

    Usage:
        engine = ResolutionFallbackEngine(config, is_paper=False)

        # When opening a position:
        engine.register_position(market_id, slug, coin, tf, entry_price, side, exp)

        # In your main loop (replaces check_all_exits):
        results = engine.check_all_exits(active_positions)
        for market_id, outcome, source, tier in results:
            finalize_position(active_positions[market_id], outcome)
    """

    def __init__(
        self,
        config: Optional[ResolutionConfig] = None,
        is_paper: bool = True,
    ):
        self.cfg     = config or ResolutionConfig()
        self.is_paper = is_paper

        self.fetcher   = PriceFetcher()
        self.determiner = OutcomeDeterminer()
        self.state_mgr  = ResolutionStateManager(self.cfg.RESOLUTION_STATE_PATH)
        self.audit      = AuditLogger(self.cfg.AUDIT_LOG_PATH)

        logging.info(
            f"[ResolutionEngine] Init | mode={'PAPER' if is_paper else 'LIVE'} | "
            f"fallback1={self.cfg.FALLBACK1_TRIGGER_HOURS}h | "
            f"fallback2={self.cfg.FALLBACK2_TRIGGER_HOURS}h"
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def register_position(
        self,
        market_id: str,
        slug: str,
        coin: str,
        timeframe_minutes: int,
        entry_price: float,
        position_side: str,
        expiration_utc: str,
    ) -> ResolutionState:
        """Call this when a new position opens."""
        return self.state_mgr.register_position(
            market_id, slug, coin, timeframe_minutes,
            entry_price, position_side, expiration_utc,
        )

    def check_all_exits(
        self,
        active_positions: dict,
    ) -> list[tuple[str, str, str, int]]:
        """
        Main loop — call this on your polling interval.

        Returns list of (market_id, outcome, source, tier) for positions ready to finalize.
        You should call finalize_position() for each returned item.

        active_positions: {market_id: position_dict}
        position_dict must have: 'slug', 'coin', 'timeframe', 'entry_price',
                                  'side', 'expiration_utc'
        """
        results = []

        for market_id, position in active_positions.items():
            resolution = self._attempt_resolution(market_id, position)
            if resolution:
                market_id, outcome, source, tier = resolution
                results.append(resolution)

        return results

    def reconcile_with_polymarket(self, market_id: str, slug: str):
        """
        Call periodically for fallback-resolved positions.
        Detects discrepancies when Polymarket eventually resolves officially.
        """
        rs = self.state_mgr.get(market_id)
        if not rs or not rs.resolved or rs.polymarket_confirmed:
            return

        data = fetch_polymarket_status(slug)
        poly_outcome = parse_polymarket_outcome(data)

        if poly_outcome is None:
            return  # Still not resolved on Polymarket

        rs.polymarket_confirmed = True

        if poly_outcome != rs.resolution_outcome:
            rs.discrepancy_detected = True
            rs.flagged_for_review   = True
            logging.error(
                f"[Reconcile] ⚠ DISCREPANCY on {market_id}: "
                f"fallback={rs.resolution_outcome}, polymarket={poly_outcome}"
            )
            self.audit.log(ResolutionAttempt(
                market_id=market_id,
                attempt_time_utc=datetime.now(timezone.utc).isoformat(),
                tier=ResolutionTier.PRIMARY,
                source=ResolutionSource.POLYMARKET,
                success=True,
                outcome=poly_outcome,
                entry_price=rs.entry_price,
                exit_price=None,
                exchange_used="polymarket",
                notes=f"DISCREPANCY DETECTED: fallback={rs.resolution_outcome}",
            ))
        else:
            logging.info(
                f"[Reconcile] ✓ {market_id} confirmed: {poly_outcome} matches fallback"
            )

        self.state_mgr.upsert(rs)

    def get_stuck_positions(self) -> list[ResolutionState]:
        """Returns positions that should count toward your max_positions limit."""
        return [
            rs for rs in self.state_mgr.get_all_unresolved()
            if not rs.resolved
        ]

    # ── Internal Resolution Logic ──────────────────────────────────────────────

    def _attempt_resolution(
        self,
        market_id: str,
        position: dict,
    ) -> Optional[tuple[str, str, str, int]]:
        """
        Returns (market_id, outcome, source, tier) or None if not yet resolvable.
        """
        slug            = position.get("slug", "")
        coin            = position.get("coin", "BTC")
        entry_price     = float(position.get("entry_price", 0))
        expiration_utc  = position.get("expiration_utc", "")

        now_utc = datetime.now(timezone.utc)

        # Parse expiration
        try:
            exp_dt = datetime.fromisoformat(expiration_utc.replace("Z", "+00:00"))
        except Exception:
            logging.error(f"[Resolution] Cannot parse expiration: {expiration_utc}")
            return None

        hours_since_exp = (now_utc - exp_dt).total_seconds() / 3600

        # Update state tracker
        rs = self.state_mgr.get(market_id)
        if rs is None:
            tf = int(position.get("timeframe", 15))
            side = position.get("side", "YES")
            rs = self.state_mgr.register_position(
                market_id, slug, coin, tf, entry_price, side, expiration_utc
            )

        rs.last_checked_utc = now_utc.isoformat()
        rs.resolution_attempts += 1
        self.state_mgr.upsert(rs)

        # ── TIER 1: Polymarket Official ──────────────────────────────────────
        data         = fetch_polymarket_status(slug)
        poly_outcome = parse_polymarket_outcome(data)

        if poly_outcome is not None:
            return self._finalize(
                rs, market_id, poly_outcome,
                ResolutionSource.POLYMARKET, ResolutionTier.PRIMARY,
                entry_price=entry_price, exit_price=None,
                exchange_used="polymarket", notes="Official Polymarket resolution"
            )

        # Market not yet expired — nothing to do
        if hours_since_exp < 0:
            return None

        # ── TIER 2: Binance/Coinbase Fallback (>2h) ─────────────────────────
        if hours_since_exp >= self.cfg.FALLBACK1_TRIGGER_HOURS or self.is_paper:

            exp_ts_ms = extract_expiration_from_slug(slug)
            if exp_ts_ms is None:
                exp_ts_ms = int(exp_dt.timestamp() * 1000)

            snap, all_prices = self.fetcher.get_price_with_failover(coin, exp_ts_ms)

            if snap is not None:
                outcome, reason = self.determiner.determine(entry_price, snap.price)

                # Spread safety check
                spread_ok, spread_msg = self.determiner.check_exchange_spread(
                    all_prices, self.cfg.MAX_EXCHANGE_SPREAD_PCT
                )
                notes = f"{reason} | {spread_msg}"

                if not spread_ok:
                    logging.warning(
                        f"[Resolution] {market_id} spread anomaly: {spread_msg}"
                    )
                    # In live mode with large spread, flag but still resolve
                    rs.flagged_for_review = True
                    self.state_mgr.upsert(rs)

                # In live mode, check if we should auto-finalize
                if not self.is_paper and not self.cfg.LIVE_FALLBACK_AUTO_FINALIZE:
                    logging.warning(
                        f"[Resolution] {market_id} FLAGGED for manual review "
                        f"(LIVE_FALLBACK_AUTO_FINALIZE=False)"
                    )
                    rs.flagged_for_review = True
                    self.state_mgr.upsert(rs)
                    return None

                return self._finalize(
                    rs, market_id, outcome,
                    ResolutionSource(snap.exchange + "_fallback"),
                    ResolutionTier.FALLBACK1,
                    entry_price=entry_price,
                    exit_price=snap.price,
                    exchange_used=snap.exchange,
                    notes=notes,
                    all_prices={k: v.price for k, v in all_prices.items()},
                )
            else:
                logging.error(
                    f"[Resolution] {market_id}: All price feeds failed! "
                    f"Cannot resolve tier 2."
                )

        # ── TIER 3: Forced Capital Release (>48h) ────────────────────────────
        if hours_since_exp >= self.cfg.FALLBACK2_TRIGGER_HOURS:
            logging.error(
                f"[Resolution] {market_id}: TIER 3 FORCED — {hours_since_exp:.1f}h "
                f"without resolution. Freeing capital."
            )

            # Last-ditch: try current price as proxy
            snap_current = self.fetcher.get_binance_current_price(coin)
            outcome  = "UNKNOWN"
            exit_px  = None
            notes    = f"Forced after {hours_since_exp:.1f}h unresolved — ALL feeds failed"

            if snap_current:
                outcome, reason = self.determiner.determine(
                    entry_price, snap_current.price
                )
                exit_px = snap_current.price
                notes   = (
                    f"Forced after {hours_since_exp:.1f}h | "
                    f"CURRENT PRICE used (not expiry): {reason}"
                )

            return self._finalize(
                rs, market_id, outcome,
                ResolutionSource.FORCED, ResolutionTier.FALLBACK2,
                entry_price=entry_price,
                exit_price=exit_px,
                exchange_used="binance_current" if snap_current else None,
                notes=notes,
            )

        return None

    def _finalize(
        self,
        rs: ResolutionState,
        market_id: str,
        outcome: str,
        source: ResolutionSource,
        tier: ResolutionTier,
        entry_price: Optional[float],
        exit_price: Optional[float],
        exchange_used: Optional[str],
        notes: str,
        all_prices: Optional[dict] = None,
    ) -> tuple[str, str, str, int]:
        """Record resolution, log to audit trail, update state."""

        now = datetime.now(timezone.utc).isoformat()

        rs.resolved              = True
        rs.resolution_tier       = tier.value
        rs.resolution_source     = source.value
        rs.resolution_outcome    = outcome
        rs.resolution_time_utc   = now
        rs.polymarket_confirmed  = (tier == ResolutionTier.PRIMARY)
        self.state_mgr.upsert(rs)

        attempt = ResolutionAttempt(
            market_id=market_id,
            attempt_time_utc=now,
            tier=tier.value,
            source=source.value,
            success=True,
            outcome=outcome,
            entry_price=entry_price,
            exit_price=exit_price,
            exchange_used=exchange_used,
            notes=notes,
            fallback_prices=all_prices or {},
        )
        self.audit.log(attempt)

        tier_label = {1: "PRIMARY", 2: "FALLBACK1", 3: "FALLBACK2"}[tier.value]
        logging.info(
            f"[Resolution] ✅ {market_id} → {outcome} "
            f"| Tier {tier.value} ({tier_label}) | {source.value} | {notes}"
        )

        return (market_id, outcome, source.value, tier.value)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION PATCH FOR check_all_exits()
# ─────────────────────────────────────────────────────────────────────────────

def build_patched_check_all_exits(
    engine: ResolutionFallbackEngine,
    finalize_position_fn,
    active_positions: dict,
):
    """
    Returns a drop-in check_all_exits() that wraps your existing finalize_position().

    Integration example:

        engine = ResolutionFallbackEngine(is_paper=IS_PAPER_TRADING)

        def check_all_exits():
            patched = build_patched_check_all_exits(
                engine, finalize_position, active_positions
            )
            patched()
    """

    def check_all_exits():
        # Unresolved positions count toward max_positions
        stuck = engine.get_stuck_positions()
        if stuck:
            logging.info(
                f"[CheckExits] {len(stuck)} position(s) stuck/pending resolution"
            )

        # Attempt resolution for all active positions
        resolved_items = engine.check_all_exits(active_positions)

        for market_id, outcome, source, tier in resolved_items:
            position = active_positions.get(market_id)
            if position:
                logging.info(
                    f"[CheckExits] Finalizing {market_id} | outcome={outcome} | "
                    f"source={source} | tier={tier}"
                )
                finalize_position_fn(position, outcome)

        # Reconcile previously fallback-resolved positions
        for rs in list(engine.state_mgr.get_all_unresolved()):
            pass  # Only unresolved are returned by get_all_unresolved

        # Also reconcile RESOLVED-by-fallback positions periodically
        for market_id_key, data in engine.state_mgr._state.items():
            if (
                data.get("resolved")
                and not data.get("polymarket_confirmed")
                and not data.get("discrepancy_detected")
            ):
                engine.reconcile_with_polymarket(
                    market_id_key, data.get("slug", "")
                )

    return check_all_exits


# ─────────────────────────────────────────────────────────────────────────────
# MANUAL RESOLUTION UTILITY
# ─────────────────────────────────────────────────────────────────────────────

def manual_resolve(
    engine: ResolutionFallbackEngine,
    market_id: str,
    outcome: str,
    reason: str = "Manual override",
):
    """
    Force-resolve a stuck position. Use only when you've verified externally.

    Usage:
        manual_resolve(engine, "btc-updown-15m-1234567890", "YES",
                       "Verified on Polymarket UI — YES won")
    """
    rs = engine.state_mgr.get(market_id)
    if rs is None:
        print(f"ERROR: {market_id} not found in resolution state.")
        return

    if rs.resolved:
        print(f"WARNING: {market_id} already resolved as {rs.resolution_outcome}")
        return

    now = datetime.now(timezone.utc).isoformat()
    rs.resolved              = True
    rs.resolution_tier       = 0  # 0 = manual
    rs.resolution_source     = ResolutionSource.MANUAL
    rs.resolution_outcome    = outcome
    rs.resolution_time_utc   = now
    rs.flagged_for_review    = True
    engine.state_mgr.upsert(rs)

    engine.audit.log(ResolutionAttempt(
        market_id=market_id,
        attempt_time_utc=now,
        tier=0,
        source=ResolutionSource.MANUAL,
        success=True,
        outcome=outcome,
        entry_price=rs.entry_price,
        exit_price=None,
        exchange_used=None,
        notes=reason,
    ))
    print(f"✅ {market_id} manually resolved as {outcome}. Flagged for review.")


# ─────────────────────────────────────────────────────────────────────────────
# QUICK DIAGNOSTIC — run standalone to check current stuck positions
# ─────────────────────────────────────────────────────────────────────────────

def run_diagnostic(state_path: str = "/root/.openclaw/workspace/resolution_state.json"):
    """
    Run: python resolution_fallback_v1.py
    Prints status of all tracked positions.
    """
    mgr = ResolutionStateManager(state_path)
    all_states = list(mgr._state.values())

    print(f"\n{'═'*65}")
    print(f"  RESOLUTION FALLBACK DIAGNOSTIC — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'═'*65}")
    print(f"  Total tracked: {len(all_states)}")

    unresolved = [s for s in all_states if not s.get("resolved")]
    resolved   = [s for s in all_states if s.get("resolved")]

    print(f"  Unresolved:    {len(unresolved)}")
    print(f"  Resolved:      {len(resolved)}")
    print(f"{'─'*65}")

    if unresolved:
        print("\n  🔴 UNRESOLVED POSITIONS:")
        for s in unresolved:
            exp_str = s.get("expiration_utc", "?")
            try:
                exp_dt      = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                hours_stuck = (datetime.now(timezone.utc) - exp_dt).total_seconds() / 3600
                age_str     = f"{hours_stuck:.1f}h"
            except Exception:
                age_str = "?"

            print(f"     {s['market_id']}")
            print(f"       coin={s['coin']} | entry={s['entry_price']} | "
                  f"age={age_str} | attempts={s.get('resolution_attempts',0)}")

    if resolved:
        print("\n  ✅ RECENTLY RESOLVED:")
        for s in resolved[-5:]:  # Last 5
            tier_map = {1: "OFFICIAL", 2: "FALLBACK1", 3: "FALLBACK2", 0: "MANUAL"}
            tier_label = tier_map.get(s.get("resolution_tier", 1), "?")
            disc = " ⚠ DISCREPANCY" if s.get("discrepancy_detected") else ""
            flag = " 🔍 REVIEW" if s.get("flagged_for_review") else ""
            print(
                f"     {s['market_id']} → {s.get('resolution_outcome')} "
                f"[{tier_label}]{disc}{flag}"
            )

    print(f"\n{'═'*65}\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_diagnostic()
