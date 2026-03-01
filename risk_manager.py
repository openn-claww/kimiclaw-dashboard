"""
risk_manager.py — OpenClaw Unified Risk Manager
================================================
Single import that wires CircuitBreaker + CorrelationLimiter together.
This is the ONLY risk interface your bot should call.

All trade entries go through here. All trade results come back here.

Usage:
    from risk_manager import RiskManager

    rm = RiskManager(starting_balance=453.08)

    # ── Before every entry ──
    ok, reason = rm.pre_trade_check(coin="BTC", side="YES", size_usd=22.65)
    if not ok:
        logger.warning("Trade blocked: %s", reason)
        return

    order = place_order(...)   # your exchange call

    # ── After entry confirmed ──
    position_id = rm.on_trade_opened(coin="BTC", side="YES",
                                     size_usd=22.65, market_id=order.id)

    # ── After position resolves ──
    rm.on_trade_closed(position_id=position_id, won=True, pnl=+4.50)

    # ── Heartbeat: log snapshot to memory.db ──
    rm.heartbeat()
"""

import logging
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from circuit_breaker    import CircuitBreaker,     CircuitBreakerConfig
from correlation_limiter import CorrelationLimiter, CorrelationConfig

# Optional memory integration
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory.memory import log_memory, log_conversation
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Unified risk gate. One instance, lives for the whole session.

    Args:
        starting_balance:  Portfolio value at session start (USD)
        cb_config:         Override CircuitBreaker thresholds
        cl_config:         Override CorrelationLimiter thresholds
        enable_memory:     Write status snapshots to memory.db
    """

    def __init__(
        self,
        starting_balance:  float,
        cb_config:         Optional[CircuitBreakerConfig]  = None,
        cl_config:         Optional[CorrelationConfig]     = None,
        enable_memory:     bool = True,
    ):
        self.starting_balance = starting_balance
        self.cb = CircuitBreaker(starting_balance, cb_config)
        self.cl = CorrelationLimiter(starting_balance, cl_config)
        self._enable_memory = enable_memory and MEMORY_AVAILABLE
        self._trade_count   = 0

        logger.info("RiskManager initialized | balance=$%.2f | memory=%s",
                    starting_balance, "ON" if self._enable_memory else "OFF")

    # ── Pre-trade gate (call this before EVERY order) ─────────────────────────

    def pre_trade_check(
        self,
        coin:     str,
        side:     str,
        size_usd: float,
    ) -> tuple[bool, str]:
        """
        Unified check: circuit breaker + correlation limiter.
        Returns (True, "OK") or (False, reason).
        """
        # 1. Circuit breaker first — if tripped, nothing goes through
        cb_ok, cb_reason = self.cb.allow_trade()
        if not cb_ok:
            return False, f"[CircuitBreaker] {cb_reason}"

        # 2. Correlation limiter
        cl_ok, cl_reason = self.cl.can_enter(coin, side, size_usd)
        if not cl_ok:
            return False, f"[CorrelationLimiter] {cl_reason}"

        logger.info("✅ pre_trade_check PASSED | %s %s $%.2f", side, coin, size_usd)
        return True, "OK"

    # ── Post-entry registration ───────────────────────────────────────────────

    def on_trade_opened(
        self,
        coin:      str,
        side:      str,
        size_usd:  float,
        market_id: str = "",
    ) -> str:
        """
        Call AFTER order is confirmed by the exchange.
        Returns position_id — store this to call on_trade_closed() later.
        """
        pos = self.cl.open_position(coin, side, size_usd, market_id)
        self._trade_count += 1

        if self._enable_memory:
            log_conversation(
                role    = "system",
                content = f"TRADE OPENED: {side} {coin} ${size_usd:.2f} | market={market_id} | pos_id={pos.id}",
                topic   = "trades",
            )
        return pos.id

    # ── Post-resolution update ────────────────────────────────────────────────

    def on_trade_closed(
        self,
        position_id: str,
        won:         bool,
        pnl:         float,
        coin:        str = "",   # optional, used if position_id lookup fails
    ) -> None:
        """
        Call AFTER position resolves (win or loss).
        Updates both circuit breaker and correlation limiter.
        """
        # Close in correlation limiter
        pos = self.cl.close_position(position_id, pnl)
        if pos is None and coin:
            pos = self.cl.close_by_coin(coin, pnl)

        # Report to circuit breaker
        coin_label = pos.coin if pos else coin
        self.cb.record_trade(won=won, pnl=pnl, coin=coin_label)

        # Update correlation limiter's portfolio value
        new_balance = self.starting_balance + self.cb._session_pnl
        self.cl.update_portfolio_value(new_balance)

        if self._enable_memory:
            log_conversation(
                role    = "system",
                content = (f"TRADE CLOSED: {'WIN' if won else 'LOSS'} {coin_label} "
                           f"pnl={pnl:+.2f} | pos_id={position_id}"),
                topic   = "trades",
            )

    # ── Manual controls ───────────────────────────────────────────────────────

    def halt(self, reason: str = "") -> None:
        """Operator-triggered halt."""
        self.cb.record_manual_halt(reason)

    def resume(self, reason: str = "") -> None:
        """Operator-triggered resume after reviewing logs."""
        self.cb.reset(reason)
        logger.info("RiskManager RESUMED by operator: %s", reason)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def heartbeat(self) -> dict:
        """
        Snapshot of full risk state.
        Call periodically (every 5 min) and log to memory.db.
        Returns the snapshot dict.
        """
        snap = {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "circuit_breaker": self.cb.status(),
            "correlation":     self.cl.status(),
            "trade_count":     self._trade_count,
        }

        logger.info("Heartbeat | tripped=%s | open_pos=%d | session_pnl=$%.2f",
                    snap["circuit_breaker"]["tripped"],
                    snap["correlation"]["open_positions"],
                    snap["circuit_breaker"]["session_pnl"])

        if self._enable_memory:
            log_memory(
                topic   = "risk_heartbeat",
                content = json.dumps(snap, indent=2),
                tags    = "heartbeat,risk,circuit_breaker,correlation",
                source  = "heartbeat",
            )

        return snap

    def print_status(self) -> None:
        """Pretty-print current risk state to stdout."""
        cb   = self.cb.status()
        print("\n══ Risk Manager Status ══════════════════")
        print(f"  Circuit Breaker : {'🔴 TRIPPED' if cb['tripped'] else '🟢 OK'}")
        if cb["tripped"]:
            print(f"  Trip reason     : {cb['trip_reason']}")
            print(f"  Trip message    : {cb['trip_message']}")
        print(f"  Consecutive loss: {cb['consecutive_losses']}")
        print(f"  Session P&L     : ${cb['session_pnl']:+.2f} ({cb['session_loss_pct']:.1%})")
        print(f"  Balance         : ${cb['current_balance']:.2f} (started ${cb['starting_balance']:.2f})")
        print(f"  Win rate        : {cb['win_rate']:.0%} over {cb['total_trades']} trades")
        print(f"\n{self.cl.risk_report()}")
        print("════════════════════════════════════════\n")


# ─── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n=== RiskManager Integration Test: $47 Loss Scenario ===\n")

    rm = RiskManager(starting_balance=500.00, enable_memory=False)

    # Replay the session that caused the $47 loss
    session = [
        # (coin,  side,  size,   won,    pnl,    label)
        ("BTC",  "YES", 20.00,  False,  -8.50,  "Entry 1 — bad market"),
        ("ETH",  "YES", 20.00,  False, -12.00,  "Entry 2 — bad market"),
        ("BTC",  "YES", 20.00,  False,  -9.25,  "Entry 3 — consecutive loss #3 → TRIP"),
        ("ETH",  "NO",  15.00,  True,   +5.00,  "Entry 4 — should be BLOCKED by circuit breaker"),
        ("SOL",  "YES", 10.00,  True,   +3.00,  "Entry 5 — should also be BLOCKED"),
    ]

    position_ids = {}

    for coin, side, size, won, pnl, label in session:
        print(f"\n  ── {label}")
        ok, reason = rm.pre_trade_check(coin=coin, side=side, size_usd=size)
        if not ok:
            print(f"     BLOCKED ✓ → {reason}")
            continue
        pos_id = rm.on_trade_opened(coin=coin, side=side, size_usd=size)
        position_ids[coin] = pos_id
        print(f"     Entered {side} {coin} ${size:.2f} | pos_id={pos_id}")
        rm.on_trade_closed(position_id=pos_id, won=won, pnl=pnl, coin=coin)
        print(f"     Closed: {'WIN' if won else 'LOSS'} ${pnl:+.2f}")

    print()
    rm.print_status()

    print("Calling heartbeat()...")
    snap = rm.heartbeat()
    print(f"Snapshot keys: {list(snap.keys())}")
