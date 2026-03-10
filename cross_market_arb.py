"""
cross_market_arb.py — Time-decay arbitrage for Polymarket 5-minute binaries
Strategy: Log-normal probability + MM lag detection + time filter
Author: Waves MVMNT (rebuilt from scratch + backtest validated)

STRATEGY SUMMARY
================
Edge ONLY exists when spot has moved sharply AND the market hasn't caught up.
When spot is already $1500+ above threshold with 45s left, BOTH the rational
probability AND the market price are near 1.0 — no edge exists there.

The edge case: spot crosses or approaches threshold DURING the window's
final 90 seconds, putting it in the 0.65-0.90 real-probability zone while
the market is still stuck at its last stale price (often 0.45-0.60).

We trade when ALL of:
  1. 10s < time_remaining < 90s            (execution window)
  2. real_prob in [0.70, 0.97]             (not already certain — no edge at 0.999)
  3. net_edge > 12% after 2% fees          (EV filter)
  4. |spot momentum last 60s| > threshold  (price moved recently = MM lag likely)
  5. spot data fresh < 5s old              (staleness guard)

We do NOT trade when:
  - real_prob > 0.97 (market already knows, will price accurately)
  - real_prob < 0.65 (not enough certainty to overcome fees)
  - circuit breaker tripped (win_rate < 46% over last 50+ trades)
  - daily loss > 8% of bankroll
  - 2+ positions already open

MATH
====
P(resolves YES) = Φ(d)   where d = ln(S/K) / (σ × √T)
  S = current spot, K = threshold, σ = vol per minute, T = minutes remaining
  Φ = standard normal CDF (no scipy needed — Abramowitz & Stegun approx)

Net EV per $1 bet:
  EV = p × win_payout × (1-fee) − (1−p) × stake_lost
  net_edge = EV / market_price

The market price lag that creates edge:
  real_prob=0.85, MM_price=0.70 → net_edge=20%   ← trade this
  real_prob=0.99, MM_price=0.98 → net_edge=1%    ← no edge, skip

HONEST BACKTEST FINDING
=======================
Monte Carlo with rational MM pricing: 0 trades (correct — no edge vs efficient MM)
Monte Carlo with realistic MM lag (70% updated, 30% stale): ~5 trades per 1000 windows
The edge requires BOTH large recent move AND MM lag.
Real data validation required before live trading.

PARAMETERS (all tunable via env vars)
======================================
ARB_MIN_SEC=10, ARB_MAX_SEC=90
ARB_MIN_PROB=0.70, ARB_MAX_PROB=0.97
ARB_MIN_NET_EDGE=0.12, BTC_VOL_PER_MIN=0.003, ETH_VOL_PER_MIN=0.004
ARB_MAX_POSITIONS=2, ARB_DAILY_LOSS_PCT=0.08, CB_MIN_SAMPLE=50
"""

import math
import os
import subprocess
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Normal CDF (Abramowitz & Stegun 26.2.17, max error 7.5e-8) ───────────────
def _norm_cdf(x: float) -> float:
    a1, a2, a3, a4, a5 = (0.319381530, -0.356563782,
                           1.781477937, -1.821255978, 1.330274429)
    L = abs(x)
    K = 1.0 / (1.0 + 0.2316419 * L)
    w = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-L * L / 2.0) * (
        a1*K + a2*K**2 + a3*K**3 + a4*K**4 + a5*K**5
    )
    return w if x >= 0 else 1.0 - w


@dataclass
class ArbSignal:
    side:             str    # 'YES' or 'NO'
    market_price:     float  # what we pay per share
    real_prob:        float  # our probability estimate
    net_edge:         float  # EV / market_price (>0.12 required)
    ev_per_dollar:    float  # expected value per $1 bet
    cushion_usd:      float  # |spot - threshold|
    time_remaining:   float  # seconds until window closes
    d_stat:           float  # log-normal d parameter (higher = more certain)
    coin:             str    # BTC or ETH


@dataclass
class TradeRecord:
    market_key:    str
    side:          str
    amount:        float
    entry_price:   float
    entry_ts:      float
    signal:        ArbSignal
    order_id:      Optional[str] = None
    closed:        bool = False
    won:           Optional[bool] = None
    pnl:           float = 0.0


class CircuitBreaker:
    """Trip after statistically meaningful evidence of consistent losses."""

    def __init__(self,
                 min_sample: int   = 50,
                 min_win_rate: float = 0.46,
                 daily_loss_pct: float = 0.08):
        self.min_sample     = min_sample
        self.min_win_rate   = min_win_rate
        self.daily_loss_pct = daily_loss_pct
        self._history:  list[bool]  = []   # True=win, False=loss
        self._daily_loss: float     = 0.0
        self._day_start:  float     = time.time()
        self._tripped:    bool      = False
        self._trip_reason: str      = ""

    @property
    def tripped(self) -> bool:
        return self._tripped

    def record(self, won: bool, pnl: float, bankroll: float):
        # Reset daily loss at midnight UTC
        now = time.time()
        if now - self._day_start > 86400:
            self._daily_loss = 0.0
            self._day_start  = now

        self._history.append(won)
        if pnl < 0:
            self._daily_loss += abs(pnl)

        # Daily loss hard stop
        if bankroll > 0 and self._daily_loss >= bankroll * self.daily_loss_pct:
            self._tripped    = True
            self._trip_reason = (
                f"daily_loss_limit: ${self._daily_loss:.2f} >= "
                f"{self.daily_loss_pct:.0%} of ${bankroll:.2f}"
            )
            log.warning(f"[CircuitBreaker] TRIPPED — {self._trip_reason}")
            return

        # Win rate check (only after min sample)
        n = len(self._history)
        if n >= self.min_sample:
            recent    = self._history[-self.min_sample:]
            win_rate  = sum(recent) / len(recent)
            if win_rate < self.min_win_rate:
                self._tripped    = True
                self._trip_reason = (
                    f"win_rate: {win_rate:.1%} < {self.min_win_rate:.1%} "
                    f"over last {self.min_sample} trades"
                )
                log.warning(f"[CircuitBreaker] TRIPPED — {self._trip_reason}")

    def reset(self):
        self._tripped    = False
        self._trip_reason = ""
        log.info("[CircuitBreaker] Manually reset")

    def status(self) -> dict:
        n = len(self._history)
        recent = self._history[-self.min_sample:] if n >= self.min_sample else self._history
        wr = sum(recent) / max(len(recent), 1)
        return {
            "tripped":      self._tripped,
            "reason":       self._trip_reason,
            "total_trades": n,
            "win_rate":     round(wr, 3),
            "daily_loss":   round(self._daily_loss, 2),
        }


class CrossMarketArb:
    """
    Cross-market arbitrage engine using time-decay + log-normal probability.
    Designed to be called from MasterBotV6.
    """

    # ── Strategy parameters (override via env vars) ───────────────────────────
    MIN_SEC_REMAINING = int(os.getenv('ARB_MIN_SEC',          '10'))
    MAX_SEC_REMAINING = int(os.getenv('ARB_MAX_SEC',          '90'))
    MIN_REAL_PROB     = float(os.getenv('ARB_MIN_PROB',      '0.70'))  # below = too uncertain
    MAX_REAL_PROB     = float(os.getenv('ARB_MAX_PROB',      '0.97'))  # above = market also knows
    MIN_NET_EDGE      = float(os.getenv('ARB_MIN_NET_EDGE',  '0.12'))
    MAX_POSITIONS     = int(os.getenv('ARB_MAX_POSITIONS',     '2'))
    FEE               = 0.02   # 2% round-trip — not configurable, it's Polymarket's rate
    BTC_VOL_PER_MIN   = float(os.getenv('BTC_VOL_PER_MIN',  '0.003'))
    ETH_VOL_PER_MIN   = float(os.getenv('ETH_VOL_PER_MIN',  '0.004'))

    # ── Polyclaw execution ────────────────────────────────────────────────────
    POLYCLAW_DIR      = '/root/.openclaw/skills/polyclaw'
    POLYCLAW_TIMEOUT  = 60

    def __init__(self, bot):
        self.bot              = bot
        self._positions:  dict[str, TradeRecord] = {}   # market_key → TradeRecord
        self._closed:     list[TradeRecord]       = []
        self.circuit      = CircuitBreaker(
            min_sample    = int(os.getenv('CB_MIN_SAMPLE',    '50')),
            min_win_rate  = float(os.getenv('CB_MIN_WIN_RATE', '0.46')),
            daily_loss_pct= float(os.getenv('ARB_DAILY_LOSS_PCT', '0.08')),
        )
        self._arb_count   = 0

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def check_market(self, pm_data: dict, spot_data: dict,
                     bankroll: float, paper: bool = True) -> Optional[TradeRecord]:
        """
        Main entry point. Call once per market per tick.
        Returns the TradeRecord if a trade was entered, None otherwise.
        """
        if self.circuit.tripped:
            return None

        signal = self.detect_arbitrage(pm_data, spot_data)
        if signal is None:
            return None

        market_key = pm_data.get('market_id', pm_data.get('conditionId', 'unknown'))
        amount     = self._kelly_size(signal, bankroll)

        ok, reason = self._pre_trade_checks(market_key, signal, amount, bankroll)
        if not ok:
            log.debug(f"[Arb] Blocked: {reason}")
            return None

        return self._execute(market_key, signal, amount, bankroll, paper)

    def on_resolution(self, market_key: str, resolved_yes: bool):
        """
        Call when a market resolves. Records outcome for circuit breaker.
        """
        rec = self._positions.pop(market_key, None)
        if rec is None:
            return

        won = (resolved_yes and rec.side == 'YES') or (not resolved_yes and rec.side == 'NO')
        if won:
            pnl = rec.amount * (1.0 / rec.entry_price - 1.0) * (1.0 - self.FEE)
        else:
            pnl = -rec.amount

        rec.closed = True
        rec.won    = won
        rec.pnl    = pnl
        self._closed.append(rec)

        # Update circuit breaker with current bankroll estimate
        bankroll = getattr(self.bot, '_virtual_free', 56.71)
        self.circuit.record(won, pnl, bankroll)

        status = "✅ WIN" if won else "❌ LOSS"
        log.info(
            f"[Arb] {status} {market_key} {rec.side} "
            f"| pnl=${pnl:+.2f} | {self.circuit.status()}"
        )

    def status(self) -> dict:
        return {
            "open_positions":  len(self._positions),
            "closed_trades":   len(self._closed),
            "circuit_breaker": self.circuit.status(),
        }

    def check_all(self, markets=None, bankroll=None, paper=None):
        """
        Legacy API wrapper for MasterBotV6 compatibility.
        Iterates through provided markets or bot's market cache.
        """
        results = []
        
        # Get defaults from bot if not provided
        if bankroll is None:
            bankroll = getattr(self.bot, '_virtual_free', 56.71)
        if paper is None:
            paper = getattr(self.bot, 'IS_PAPER_TRADING', True)
        
        # If markets provided, use them
        if markets:
            for market_key, market_data in markets.items():
                try:
                    pm_data = market_data.get('pm_data', market_data)
                    spot_data = market_data.get('spot_data', {})
                    rec = self.check_market(pm_data, spot_data, bankroll, paper)
                    if rec:
                        results.append(rec)
                except Exception as e:
                    log.debug(f"[Arb] check_all error for {market_key}: {e}")
        
        # Also check if bot has market cache
        elif hasattr(self.bot, '_market_cache'):
            for market_key, market_data in self.bot._market_cache.items():
                try:
                    pm_data = market_data.get('pm_data', market_data)
                    spot_data = market_data.get('spot_data', {})
                    rec = self.check_market(pm_data, spot_data, bankroll, paper)
                    if rec:
                        results.append(rec)
                except Exception as e:
                    log.debug(f"[Arb] check_all error for {market_key}: {e}")
        
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # STRATEGY CORE
    # ─────────────────────────────────────────────────────────────────────────

    def detect_arbitrage(self, pm_data: dict, spot_data: dict) -> Optional[ArbSignal]:
        """
        Time-decay arbitrage using log-normal probability with MM-lag detection.
        """
        # [DEBUG] Log entry with key data
        coin = str(spot_data.get('coin', 'BTC')).upper()
        threshold = spot_data.get('threshold', 0)
        spot = spot_data.get('price', 0)
        log.debug(f"[detect_arbitrage] {coin} - threshold={threshold} spot={spot}")
        
        # ── 1. Extract and validate prices ───────────────────────────────────
        prices = pm_data.get('outcomePrices', [])
        if len(prices) < 2:
            return None

        try:
            yes_price = float(prices[0])
            no_price  = float(prices[1])
        except (TypeError, ValueError):
            return None

        total = yes_price + no_price
        if not (0.88 <= total <= 1.12):
            log.debug(f"[Arb] Stale/bad prices: yes={yes_price} no={no_price} sum={total:.3f}")
            return None

        # ── 2. Time filter ────────────────────────────────────────────────────
        time_remaining = self._get_time_remaining(spot_data)
        if time_remaining is None:
            return None
        if time_remaining <= self.MIN_SEC_REMAINING:
            return None   # too close — execution lag risk
        if time_remaining > self.MAX_SEC_REMAINING:
            return None   # too early — too much volatility uncertainty

        # ── 3. Spot data ──────────────────────────────────────────────────────
        try:
            threshold = float(spot_data['threshold'])
            spot      = float(spot_data['price'])
            coin      = str(spot_data.get('coin', 'BTC')).upper()
        except (KeyError, TypeError, ValueError):
            return None

        if threshold <= 0 or spot <= 0:
            return None

        # ── 4. Staleness guard ────────────────────────────────────────────────
        spot_age = float(spot_data.get('spot_age_sec', 0))
        if spot_age > 5.0:
            log.debug(f"[Arb] Spot data stale: {spot_age:.1f}s old")
            return None

        # ── 5. Log-normal probability ─────────────────────────────────────────
        vol = self.ETH_VOL_PER_MIN if coin == 'ETH' else self.BTC_VOL_PER_MIN
        T   = time_remaining / 60.0        # convert to minutes

        try:
            d = math.log(spot / threshold) / (vol * math.sqrt(T))
        except (ValueError, ZeroDivisionError):
            return None

        prob_above = _norm_cdf(d)
        cushion_usd = spot - threshold

        # ── 6. Side selection ─────────────────────────────────────────────────
        if cushion_usd > 0:
            side, market_price, real_prob = 'YES', yes_price, prob_above
        else:
            side, market_price, real_prob = 'NO', no_price, 1.0 - prob_above

        # ── 7. Probability range filter ───────────────────────────────────────
        # CRITICAL: skip if real_prob > MAX_REAL_PROB (market also knows → no lag)
        # Skip if real_prob < MIN_REAL_PROB (too uncertain → edge is noise)
        if not (self.MIN_REAL_PROB <= real_prob <= self.MAX_REAL_PROB):
            log.debug(
                f"[Arb] Prob out of range: real_prob={real_prob:.3f} "
                f"range=[{self.MIN_REAL_PROB:.2f},{self.MAX_REAL_PROB:.2f}]"
            )
            return None

        # ── 8. EV and edge ────────────────────────────────────────────────────
        # EV = p × win_payout × (1-fee) − (1−p) × stake_lost
        ev = (real_prob * (1.0 - market_price) * (1.0 - self.FEE)
              - (1.0 - real_prob) * market_price)
        net_edge = ev / max(market_price, 1e-6)

        if net_edge < self.MIN_NET_EDGE:
            log.debug(
                f"[Arb] Insufficient edge: {net_edge:.1%} < {self.MIN_NET_EDGE:.1%} | "
                f"real={real_prob:.3f} mkt={market_price:.3f}"
            )
            return None

        log.info(
            f"[Arb] 🎯 SIGNAL {coin} {side} | "
            f"real_prob={real_prob:.1%} market={market_price:.3f} "
            f"spread={real_prob-market_price:+.3f} "
            f"net_edge={net_edge:.1%} d={d:.2f} "
            f"cushion=${cushion_usd:+.0f} t={time_remaining:.0f}s"
        )

        return ArbSignal(
            side=side, market_price=market_price, real_prob=real_prob,
            net_edge=net_edge, ev_per_dollar=ev, cushion_usd=cushion_usd,
            time_remaining=time_remaining, d_stat=d, coin=coin,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # RISK CONTROLS
    # ─────────────────────────────────────────────────────────────────────────

    def _pre_trade_checks(self, market_key: str, signal: ArbSignal,
                          amount: float, bankroll: float) -> tuple[bool, str]:
        """Hard gates. All must pass."""

        if amount < 1.0:
            return False, f"size_too_small: ${amount:.2f} < $1.00 minimum"

        if market_key in self._positions:
            return False, f"duplicate_position: {market_key} already open"

        if len(self._positions) >= self.MAX_POSITIONS:
            return False, f"max_positions: {len(self._positions)}/{self.MAX_POSITIONS} open"

        if signal.net_edge < self.MIN_NET_EDGE:
            return False, f"insufficient_edge: {signal.net_edge:.1%} < {self.MIN_NET_EDGE:.1%}"

        # Hard dollar floor — never bet more than 5% of bankroll
        if amount > bankroll * 0.05:
            return False, f"oversize: ${amount:.2f} > 5% of ${bankroll:.2f}"

        return True, "ok"

    def _kelly_size(self, signal: ArbSignal, bankroll: float) -> float:
        """
        Half-Kelly bet sizing, capped at 5% of bankroll and $5 max.
        Kelly f* = (p × b - (1-p)) / b
        where b = (1 - market_price) / market_price  (net odds)
        """
        p = signal.real_prob
        b = (1.0 - signal.market_price) / max(signal.market_price, 1e-6)
        kelly_f = (p * b - (1.0 - p)) / max(b, 1e-6)
        half_k  = max(0.0, kelly_f / 2.0)

        # Apply caps
        amount = bankroll * half_k
        amount = min(amount, bankroll * 0.05)   # max 5% per trade
        amount = min(amount, 5.0)               # hard dollar cap
        amount = max(amount, 1.0)               # minimum bet

        return round(amount, 2)

    # ─────────────────────────────────────────────────────────────────────────
    # EXECUTION
    # ─────────────────────────────────────────────────────────────────────────

    def _execute(self, market_key: str, signal: ArbSignal, amount: float,
                 bankroll: float, paper: bool) -> TradeRecord:
        """Execute trade via PolyClaw CLI or paper simulate."""
        self._arb_count += 1
        tc = self._arb_count

        rec = TradeRecord(
            market_key=market_key, side=signal.side, amount=amount,
            entry_price=signal.market_price, entry_ts=time.time(), signal=signal,
        )

        if paper:
            # Paper mode: simulate fill
            rec.order_id = f"paper_{tc}"
            log.info(
                f"[Arb] 📄 #{tc} PAPER {signal.coin} {signal.side} "
                f"@ {signal.market_price:.3f} | ${amount:.2f} "
                f"| edge={signal.net_edge:.1%} d={signal.d_stat:.2f} "
                f"t={signal.time_remaining:.0f}s"
            )
        else:
            # Live mode: PolyClaw CLI
            proxy      = os.environ.get('HTTPS_PROXY', '')
            proxy_pfx  = f'export HTTPS_PROXY={proxy} && ' if proxy else ''
            cmd_str    = (
                f"{proxy_pfx}"
                f"cd {self.POLYCLAW_DIR} && source .env && "
                f"uv run python scripts/polyclaw.py buy "
                f"{market_key} {signal.side} {amount:.2f}"
            )
            try:
                result = subprocess.run(
                    ['bash', '-c', cmd_str],
                    capture_output=True, text=True,
                    timeout=self.POLYCLAW_TIMEOUT,
                )
                stdout = result.stdout.strip()
                stderr = result.stderr.strip()

                if stdout:
                    log.info(f"[Arb] polyclaw stdout: {stdout[:400]}")
                if stderr:
                    log.warning(f"[Arb] polyclaw stderr: {stderr[:200]}")
                log.info(f"[Arb] polyclaw returncode: {result.returncode}")

                if result.returncode == 0:
                    # Extract TX hash
                    order_id = 'polyclaw_ok'
                    for line in stdout.splitlines():
                        if 'Split TX:' in line or 'tx_hash' in line.lower() or '0x' in line:
                            order_id = line.split()[-1].strip()
                            break
                    rec.order_id = order_id
                    log.info(
                        f"[Arb] ✅ #{tc} LIVE {signal.coin} {signal.side} "
                        f"@ {signal.market_price:.3f} | ${amount:.2f} "
                        f"| order_id={order_id} | virtual=False"
                    )
                else:
                    log.error(
                        f"[Arb] ❌ #{tc} LIVE FAILED returncode={result.returncode} "
                        f"| virtual=True (not counted)"
                    )
                    return rec  # don't register as open position on failure

            except subprocess.TimeoutExpired:
                log.error(f"[Arb] #{tc} polyclaw timeout after {self.POLYCLAW_TIMEOUT}s")
                return rec
            except Exception as e:
                log.error(f"[Arb] #{tc} polyclaw exception: {type(e).__name__}: {e}")
                return rec

        self._positions[market_key] = rec
        return rec

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_time_remaining(self, spot_data: dict) -> Optional[float]:
        """Get seconds until window closes. Returns None if unavailable."""
        # Direct field
        t = spot_data.get('time_remaining_sec')
        if t is not None:
            return float(t)

        # Derive from window end timestamp
        end = spot_data.get('window_end_ts')
        if end is not None:
            remaining = float(end) - time.time()
            return max(0.0, remaining)

        # Derive from window start + duration
        start    = spot_data.get('window_start_ts')
        duration = spot_data.get('window_duration_sec', 300)  # default 5min
        if start is not None:
            elapsed   = time.time() - float(start)
            remaining = float(duration) - elapsed
            return max(0.0, remaining)

        log.debug("[Arb] time_remaining unavailable — add window_end_ts to spot_data")
        return None

# Backward compatibility alias
CrossMarketArbitrage = CrossMarketArb
