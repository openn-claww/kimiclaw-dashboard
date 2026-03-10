#!/usr/bin/env python3
"""
auto_redeem.py — Automatic Redemption of Resolved Polymarket Positions
[FIX-2] Monitor positions for resolution (every 5 minutes)
[FIX-3] Auto-redeem winning positions via CTF / CLOB API
[FIX-4] Full P&L tracking on redemption
[FIX-5] Retry with backoff + alert after 3 failures
"""

import os, json, time, logging, threading, requests
from typing import Optional, Dict, List, Callable
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

log = logging.getLogger('auto_redeem')

WORKSPACE             = os.getenv('BOT_WORKSPACE', '/root/.openclaw/workspace')
GAMMA_API             = os.getenv('GAMMA_API', 'https://gamma-api.polymarket.com')
CLOB_BASE_URL         = os.getenv('CLOB_BASE_URL', 'https://clob.polymarket.com')
REDEEM_POLL_INTERVAL  = int(os.getenv('REDEEM_POLL_INTERVAL', '300'))
REDEEM_MAX_RETRIES    = int(os.getenv('REDEEM_MAX_RETRIES', '3'))
REDEEM_BACKOFF_BASE   = float(os.getenv('REDEEM_BACKOFF_BASE', '30.0'))
REDEEM_STATE_FILE     = f'{WORKSPACE}/redemption_state.json'
REDEEM_LOG_FILE       = f'{WORKSPACE}/redemption_log.json'


class RedemptionStatus(Enum):
    PENDING_CHECK     = 'pending_check'
    RESOLVED_WIN      = 'resolved_win'
    RESOLVED_LOSS     = 'resolved_loss'
    PENDING_REDEEM    = 'pending_redeem'
    REDEEMING         = 'redeeming'
    REDEEMED          = 'redeemed'
    REDEEM_FAILED     = 'redeem_failed'
    REDEEM_ABANDONED  = 'redeem_abandoned'


@dataclass
class RedemptionRecord:
    market_id:       str
    slug:            str
    side:            str
    entry_price:     float
    shares:          float
    token_id:        str
    expiration_utc:  str
    status:          str             = 'pending_check'
    resolved_at:     Optional[str]  = None
    winning_side:    Optional[str]  = None
    resolution_src:  Optional[str]  = None
    redeem_attempts: int            = 0
    redeem_tx_hash:  Optional[str]  = None
    redeemed_at:     Optional[str]  = None
    redeem_error:    Optional[str]  = None
    exit_price:      Optional[float] = None
    pnl_usd:         Optional[float] = None
    pnl_pct:         Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'RedemptionRecord':
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class ResolutionChecker:
    """[FIX-2] Polls Gamma API for market resolution status."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'MasterBotV6/1.0', 'Accept': 'application/json'})

    def check(self, slug: str) -> Optional[dict]:
        for endpoint in (f"{GAMMA_API}/events/slug/{slug}", f"{GAMMA_API}/markets/slug/{slug}"):
            try:
                r = self._session.get(endpoint, timeout=8)
                if r.status_code == 200:
                    return self._parse(r.json())
            except Exception as e:
                log.debug(f"[ResolutionChecker] {endpoint}: {e}")
        return None

    def _parse(self, data: dict) -> dict:
        mkt = data.get('markets', [data])[0] if 'markets' in data else data
        resolved = bool(mkt.get('resolved') or mkt.get('closed'))
        winning_side = None
        if resolved:
            try:
                prices = json.loads(mkt.get('outcomePrices', '[]')) if isinstance(mkt.get('outcomePrices'), str) else mkt.get('outcomePrices', [])
                if len(prices) >= 2:
                    winning_side = 'YES' if float(prices[0]) >= 0.99 else 'NO'
            except Exception:
                pass
            if winning_side is None:
                raw = mkt.get('winner') or mkt.get('winning_outcome')
                if raw:
                    winning_side = str(raw).upper()
        return {'resolved': resolved, 'winning_side': winning_side}


class CTFRedeemer:
    """[FIX-3] Redeems winning positions via PolyClaw wallet or CLOB API."""

    def __init__(self, wallet_manager=None, contract_manager=None):
        self._wallet = wallet_manager
        self._contracts = contract_manager

    def redeem(self, record: RedemptionRecord) -> dict:
        log.info(f"[CTFRedeemer] Redeeming {record.market_id} side={record.side} shares={record.shares:.4f}")

        # Method 1: PolyClaw contracts
        if self._contracts or self._wallet:
            res = self._via_polyclaw(record)
            if res['success']:
                return res
            log.warning(f"[CTFRedeemer] PolyClaw failed: {res['error']}")

        # Method 2: CLOB REST API
        res = self._via_clob_api(record)
        if res['success']:
            return res
        log.warning(f"[CTFRedeemer] CLOB API failed: {res['error']}")

        return {'success': False, 'tx_hash': None, 'error': 'all_methods_failed'}

    def _via_polyclaw(self, record: RedemptionRecord) -> dict:
        for obj in (self._contracts, self._wallet):
            if obj is None:
                continue
            for name in ('merge_position', 'mergePosition', 'redeem_position', 'redeemPosition', 'redeem'):
                fn = getattr(obj, name, None)
                if callable(fn):
                    try:
                        result = fn(token_id=record.token_id, amount=record.shares, market_id=record.market_id)
                        if isinstance(result, dict):
                            tx = result.get('tx_hash') or result.get('transactionHash', '')
                            return {'success': bool(tx or result.get('success')), 'tx_hash': tx, 'error': result.get('error')}
                        if isinstance(result, str) and len(result) > 10:
                            return {'success': True, 'tx_hash': result, 'error': None}
                    except Exception as e:
                        log.debug(f"[CTFRedeemer] {name}: {e}")
        return {'success': False, 'tx_hash': None, 'error': 'no_polyclaw_method'}

    def _via_clob_api(self, record: RedemptionRecord) -> dict:
        api_key = os.getenv('CLOB_API_KEY', '')
        if not api_key:
            return {'success': False, 'tx_hash': None, 'error': 'no_clob_api_key'}
        try:
            r = requests.post(
                f"{CLOB_BASE_URL}/redeem",
                json={'token_id': record.token_id, 'amount': str(record.shares), 'market_id': record.market_id},
                headers={'CLOB-API-KEY': api_key, 'CLOB-API-SECRET': os.getenv('CLOB_API_SECRET', ''), 'Content-Type': 'application/json'},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                return {'success': True, 'tx_hash': data.get('tx_hash', ''), 'error': None}
            return {'success': False, 'tx_hash': None, 'error': f"HTTP {r.status_code}: {r.text[:100]}"}
        except Exception as e:
            return {'success': False, 'tx_hash': None, 'error': str(e)}


class AutoRedeemEngine:
    """
    [FIX-2][FIX-3][FIX-4][FIX-5] Main redemption orchestrator.
    Runs as a daemon thread inside master bot.
    """

    def __init__(self, wallet_manager=None, contract_manager=None,
                 alert_fn=None, emergency_stop_fn=None):
        self._records:  Dict[str, RedemptionRecord] = {}
        self._lock      = threading.Lock()
        self._checker   = ResolutionChecker()
        self._redeemer  = CTFRedeemer(wallet_manager, contract_manager)
        self._alert     = alert_fn or (lambda lvl, msg: log.critical(f"[ALERT-{lvl}] {msg}"))
        self._estop     = emergency_stop_fn or (lambda: False)
        self._running   = False
        self._thread    = None
        self._last_poll = 0.0
        Path(WORKSPACE).mkdir(parents=True, exist_ok=True)
        self._load_state()

    # ── State I/O ──────────────────────────────────────────────────────────

    def _load_state(self):
        try:
            with open(REDEEM_STATE_FILE) as f:
                raw = json.load(f)
            with self._lock:
                for mid, d in raw.items():
                    try:
                        self._records[mid] = RedemptionRecord.from_dict(d)
                    except Exception as e:
                        log.warning(f"[AutoRedeem] Bad record {mid}: {e}")
            log.info(f"[AutoRedeem] Loaded {len(self._records)} records from state")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_state(self):
        with self._lock:
            data = {mid: r.to_dict() for mid, r in self._records.items()}
        try:
            tmp = REDEEM_STATE_FILE + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            Path(tmp).replace(REDEEM_STATE_FILE)
        except Exception as e:
            log.error(f"[AutoRedeem] State save failed: {e}")

    def _log_final(self, record: RedemptionRecord):
        """[FIX-4] Append final P&L record to log file."""
        try:
            existing = []
            if Path(REDEEM_LOG_FILE).exists():
                with open(REDEEM_LOG_FILE) as f:
                    existing = json.load(f)
            existing.append({**record.to_dict(), 'logged_at': datetime.now(tz=timezone.utc).isoformat()})
            tmp = REDEEM_LOG_FILE + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(existing, f, indent=2)
            Path(tmp).replace(REDEEM_LOG_FILE)
        except Exception as e:
            log.error(f"[AutoRedeem] Log write failed: {e}")

    # ── Public API ─────────────────────────────────────────────────────────

    def register_position(self, market_id: str, slug: str, side: str,
                          entry_price: float, shares: float,
                          token_id: str, expiration_utc: str):
        with self._lock:
            if market_id in self._records:
                return
            self._records[market_id] = RedemptionRecord(
                market_id=market_id, slug=slug, side=side,
                entry_price=entry_price, shares=shares,
                token_id=token_id, expiration_utc=expiration_utc,
            )
        log.info(f"[AutoRedeem] Registered {market_id} side={side} shares={shares:.4f}")
        self._save_state()

    def deregister_position(self, market_id: str):
        with self._lock:
            self._records.pop(market_id, None)
        self._save_state()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, name='AutoRedeemPoller', daemon=True)
        self._thread.start()
        log.info(f"[AutoRedeem] Poller started (every {REDEEM_POLL_INTERVAL}s)")

    def stop(self):
        self._running = False

    def force_poll(self):
        """Trigger immediate check — useful for testing."""
        threading.Thread(target=self._process_all, daemon=True).start()

    # ── Background loop ────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                if self._estop():
                    log.warning("[AutoRedeem] Emergency stop active — pausing 30s")
                    time.sleep(30)
                    continue
                now = time.time()
                if now - self._last_poll >= REDEEM_POLL_INTERVAL:
                    self._last_poll = now
                    self._process_all()
            except Exception as e:
                log.error(f"[AutoRedeem] Loop error: {e}", exc_info=True)
            time.sleep(10)

    def _process_all(self):
        with self._lock:
            mids = list(self._records.keys())
        log.debug(f"[AutoRedeem] Polling {len(mids)} positions")
        for mid in mids:
            if self._estop():
                break
            try:
                self._process_one(mid)
            except Exception as e:
                log.error(f"[AutoRedeem] Error on {mid}: {e}", exc_info=True)

    def _process_one(self, mid: str):
        with self._lock:
            record = self._records.get(mid)
        if record is None:
            return

        s = RedemptionStatus(record.status)

        if s in (RedemptionStatus.REDEEMED, RedemptionStatus.REDEEM_ABANDONED):
            return  # done

        # [FIX-2] Check resolution
        if s == RedemptionStatus.PENDING_CHECK:
            self._check_resolution(record)
            return

        # Loss — just finalise
        if s == RedemptionStatus.RESOLVED_LOSS:
            self._finalise_loss(record)
            return

        # [FIX-3][FIX-5] Win — attempt redemption
        if s in (RedemptionStatus.PENDING_REDEEM, RedemptionStatus.REDEEM_FAILED):
            self._attempt_redeem(record)
            return

    # ── Resolution ─────────────────────────────────────────────────────────

    def _check_resolution(self, record: RedemptionRecord):
        """[FIX-2] Query Gamma API and update record."""
        result = self._checker.check(record.slug)
        if result is None or not result['resolved']:
            return

        won          = result['winning_side'] == record.side
        new_status   = (RedemptionStatus.PENDING_REDEEM if won
                        else RedemptionStatus.RESOLVED_LOSS)

        with self._lock:
            record.resolved_at  = datetime.now(tz=timezone.utc).isoformat()
            record.winning_side = result['winning_side']
            record.status       = new_status.value

        outcome = 'WIN' if won else 'LOSS'
        log.info(f"[AutoRedeem] {record.market_id} RESOLVED → {outcome} "
                 f"(winner={result['winning_side']} us={record.side})")
        self._save_state()

        if not won:
            self._finalise_loss(record)

    # ── Loss finalise ──────────────────────────────────────────────────────

    def _finalise_loss(self, record: RedemptionRecord):
        """[FIX-4] P&L for a loss — tokens are worth 0."""
        with self._lock:
            record.exit_price  = 0.0
            record.pnl_usd     = round(record.shares * -record.entry_price, 4)
            record.pnl_pct     = round(-record.entry_price / record.entry_price * 100, 2)
            record.status      = RedemptionStatus.REDEEMED.value
            record.redeemed_at = datetime.now(tz=timezone.utc).isoformat()
        log.info(f"[AutoRedeem] {record.market_id} LOSS settled | "
                 f"pnl=${record.pnl_usd:.2f} ({record.pnl_pct:.1f}%)")
        self._save_state()
        self._log_final(record)

    # ── Redemption attempt ─────────────────────────────────────────────────

    def _attempt_redeem(self, record: RedemptionRecord):
        """[FIX-3][FIX-5] Attempt CTF redeem with exponential backoff."""
        if self._estop():
            return

        if record.redeem_attempts >= REDEEM_MAX_RETRIES:
            self._abandon(record)
            return

        # Exponential backoff on retries
        if record.redeem_attempts > 0:
            wait = REDEEM_BACKOFF_BASE * (2 ** (record.redeem_attempts - 1))
            log.info(f"[AutoRedeem] {record.market_id} retry "
                     f"{record.redeem_attempts}/{REDEEM_MAX_RETRIES} in {wait:.0f}s")
            time.sleep(wait)

        with self._lock:
            record.status          = RedemptionStatus.REDEEMING.value
            record.redeem_attempts += 1

        log.info(f"[AutoRedeem] Attempting redeem {record.market_id} "
                 f"(attempt {record.redeem_attempts}/{REDEEM_MAX_RETRIES})")

        result = self._redeemer.redeem(record)

        if result['success']:
            self._complete(record, result['tx_hash'])
        else:
            with self._lock:
                record.status      = RedemptionStatus.REDEEM_FAILED.value
                record.redeem_error = result.get('error', 'unknown')
            log.warning(f"[AutoRedeem] {record.market_id} attempt {record.redeem_attempts} failed: {record.redeem_error}")
            if record.redeem_attempts >= REDEEM_MAX_RETRIES:
                self._abandon(record)
            else:
                self._save_state()

    def _complete(self, record: RedemptionRecord, tx_hash: Optional[str]):
        """[FIX-4] Mark redeemed and log P&L."""
        with self._lock:
            record.exit_price     = 1.0
            record.pnl_usd        = round(record.shares * (1.0 - record.entry_price), 4)
            record.pnl_pct        = round((1.0 - record.entry_price) / record.entry_price * 100, 2)
            record.status         = RedemptionStatus.REDEEMED.value
            record.redeemed_at    = datetime.now(tz=timezone.utc).isoformat()
            record.redeem_tx_hash = tx_hash
            record.redeem_error   = None
        log.info(f"[AutoRedeem] ✓ {record.market_id} REDEEMED | "
                 f"tx={tx_hash} pnl=${record.pnl_usd:.2f} ({record.pnl_pct:.1f}%)")
        self._save_state()
        self._log_final(record)

    def _abandon(self, record: RedemptionRecord):
        """[FIX-5] Give up after max retries — alert user."""
        with self._lock:
            record.status = RedemptionStatus.REDEEM_ABANDONED.value
        msg = (f"REDEMPTION ABANDONED after {record.redeem_attempts} attempts — "
               f"MANUAL ACTION REQUIRED | market={record.market_id} "
               f"token={record.token_id} shares={record.shares:.4f} "
               f"last_error={record.redeem_error}")
        log.critical(f"[AutoRedeem] 🚨 {msg}")
        self._alert('CRITICAL', msg)
        self._save_state()
        self._log_final(record)

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            records = list(self._records.values())
        counts: dict = {}
        for r in records:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {
            'total':        len(records),
            'by_status':    counts,
            'poll_interval': REDEEM_POLL_INTERVAL,
            'running':      self._running,
        }

    def get_pending(self) -> List[dict]:
        active = {RedemptionStatus.PENDING_CHECK.value,
                  RedemptionStatus.PENDING_REDEEM.value,
                  RedemptionStatus.REDEEM_FAILED.value}
        with self._lock:
            return [r.to_dict() for r in self._records.values() if r.status in active]
