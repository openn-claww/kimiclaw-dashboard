"""
circuit_breaker.py — OpenClaw Trading Circuit Breaker
======================================================
Halts the bot automatically when loss patterns indicate something is wrong.

Two independent trip conditions (either one halts trading):
  1. CONSECUTIVE LOSSES  — N losses in a row, regardless of size
  2. SESSION DRAWDOWN    — total session loss exceeds X% of starting balance

Usage:
    from circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(starting_balance=453.08)

    # After every trade result:
    cb.record_trade(won=False, pnl=-12.50)

    # Before every new entry:
    if not cb.allow_trade():
        return  # halted — do not enter

    # Manual resume after you've reviewed logs:
    cb.reset(reason="Reviewed logs, bug fixed")
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class CircuitBreakerConfig:
    # Consecutive loss trip
    max_consecutive_losses: int   = 3       # halt after 3 losses in a row
    cooldown_minutes: int         = 30      # auto-resume after N minutes

    # Session drawdown trip
    max_session_loss_pct: float   = 0.05    # halt if session down >5%
    max_single_loss_pct:  float   = 0.03    # halt if any single trade >3% loss

    # Warning thresholds (log warning but don't halt)
    warn_consecutive_losses: int  = 2       # warn after 2 in a row
    warn_session_loss_pct:   float = 0.03   # warn at 3% drawdown


class TripReason(Enum):
    CONSECUTIVE_LOSSES = "consecutive_losses"
    SESSION_DRAWDOWN   = "session_drawdown"
    SINGLE_LOSS        = "single_loss_too_large"
    MANUAL             = "manual_halt"


# ─── Trade Record ─────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    timestamp:  datetime
    won:        bool
    pnl:        float          # positive = profit, negative = loss
    coin:       str  = ""
    market_id:  str  = ""
    note:       str  = ""


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Stateful circuit breaker. One instance per bot session.
    Thread-safe for single-threaded async bots; add a Lock for multi-threaded.
    """

    def __init__(
        self,
        starting_balance: float,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.starting_balance   = starting_balance
        self.config             = config or CircuitBreakerConfig()

        # State
        self._tripped:          bool              = False
        self._trip_reason:      Optional[TripReason] = None
        self._trip_time:        Optional[datetime]   = None
        self._trip_message:     str               = ""

        self._consecutive_losses: int             = 0
        self._session_pnl:        float           = 0.0
        self._trades:             list[TradeRecord] = []
        self._halts:              list[dict]      = []   # audit log

    # ── Public API ────────────────────────────────────────────────────────────

    def allow_trade(self) -> tuple[bool, str]:
        """
        Call BEFORE every trade entry.
        Returns (True, "OK") or (False, reason_string).
        Auto-clears cooldown-based trips if cooldown has expired.
        """
        if not self._tripped:
            return True, "OK"

        # Check if cooldown has expired (only for non-manual trips)
        if self._trip_reason != TripReason.MANUAL and self._trip_time:
            elapsed = (datetime.now(timezone.utc) - self._trip_time).total_seconds() / 60
            if elapsed >= self.config.cooldown_minutes:
                self._auto_reset(elapsed)
                return True, "OK"

        msg = (
            f"Circuit breaker TRIPPED [{self._trip_reason.value}]: {self._trip_message} "
            f"| Tripped at {self._trip_time.strftime('%H:%M:%S') if self._trip_time else '?'}"
        )
        return False, msg

    def record_trade(
        self,
        won:       bool,
        pnl:       float,
        coin:      str = "",
        market_id: str = "",
        note:      str = "",
    ) -> None:
        """
        Call AFTER every trade resolves (win or loss).
        Updates internal state and trips the breaker if thresholds are crossed.
        """
        record = TradeRecord(
            timestamp = datetime.now(timezone.utc),
            won       = won,
            pnl       = pnl,
            coin      = coin,
            market_id = market_id,
            note      = note,
        )
        self._trades.append(record)
        self._session_pnl += pnl

        if won:
            self._consecutive_losses = 0
            logger.info("✓ Trade WIN  | pnl=+$%.2f | session=%.2f%% | streak=0 losses",
                        pnl, self._session_loss_pct())
        else:
            self._consecutive_losses += 1
            logger.warning("✗ Trade LOSS | pnl=-$%.2f | session=%.2f%% | streak=%d losses",
                           abs(pnl), self._session_loss_pct(), self._consecutive_losses)
            self._check_trips(pnl)

    def record_manual_halt(self, reason: str = "") -> None:
        """Force-halt the bot from external code or operator."""
        self._trip(TripReason.MANUAL, reason or "Manual halt requested")

    def reset(self, reason: str = "") -> None:
        """
        Manual reset — requires explicit call after reviewing logs.
        Does NOT reset session P&L (that's intentional: drawdown is real).
        """
        logger.info("Circuit breaker RESET by operator. Reason: %s | Session P&L: $%.2f",
                    reason or "none given", self._session_pnl)
        self._tripped              = False
        self._trip_reason          = None
        self._trip_time            = None
        self._trip_message         = ""
        self._consecutive_losses   = 0   # reset streak only, not session P&L
        self._halts.append({
            "type":      "manual_reset",
            "reason":    reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_pnl_at_reset": self._session_pnl,
        })

    # ── Status / Reporting ────────────────────────────────────────────────────

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    def status(self) -> dict:
        """Full status snapshot — log this to memory.db via heartbeat."""
        total_trades   = len(self._trades)
        winning_trades = sum(1 for t in self._trades if t.won)
        return {
            "tripped":            self._tripped,
            "trip_reason":        self._trip_reason.value if self._trip_reason else None,
            "trip_message":       self._trip_message,
            "trip_time":          self._trip_time.isoformat() if self._trip_time else None,
            "consecutive_losses": self._consecutive_losses,
            "session_pnl":        round(self._session_pnl, 2),
            "session_loss_pct":   round(self._session_loss_pct(), 4),
            "starting_balance":   self.starting_balance,
            "current_balance":    round(self.starting_balance + self._session_pnl, 2),
            "total_trades":       total_trades,
            "win_rate":           round(winning_trades / total_trades, 3) if total_trades else 0,
            "halt_count":         len(self._halts),
        }

    def recent_trades(self, n: int = 10) -> list[dict]:
        return [
            {
                "time":  t.timestamp.strftime("%H:%M:%S"),
                "won":   t.won,
                "pnl":   t.pnl,
                "coin":  t.coin,
            }
            for t in self._trades[-n:]
        ]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _session_loss_pct(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return self._session_pnl / self.starting_balance  # negative when losing

    def _check_trips(self, last_pnl: float) -> None:
        cfg = self.config

        # Warning thresholds (don't halt, just alert)
        if self._consecutive_losses >= cfg.warn_consecutive_losses:
            logger.warning("⚠ WARNING: %d consecutive losses — approaching circuit breaker",
                           self._consecutive_losses)
        if self._session_loss_pct() <= -cfg.warn_session_loss_pct:
            logger.warning("⚠ WARNING: Session down %.1f%% — approaching drawdown limit",
                           abs(self._session_loss_pct()) * 100)

        # Trip: single loss too large
        if self.starting_balance > 0:
            single_loss_pct = abs(last_pnl) / self.starting_balance
            if single_loss_pct >= cfg.max_single_loss_pct:
                self._trip(
                    TripReason.SINGLE_LOSS,
                    f"Single trade loss ${abs(last_pnl):.2f} = {single_loss_pct:.1%} of balance "
                    f"(max={cfg.max_single_loss_pct:.1%})"
                )
                return

        # Trip: consecutive losses
        if self._consecutive_losses >= cfg.max_consecutive_losses:
            self._trip(
                TripReason.CONSECUTIVE_LOSSES,
                f"{self._consecutive_losses} consecutive losses "
                f"(max={cfg.max_consecutive_losses})"
            )
            return

        # Trip: session drawdown
        if self._session_loss_pct() <= -cfg.max_session_loss_pct:
            self._trip(
                TripReason.SESSION_DRAWDOWN,
                f"Session loss {self._session_loss_pct():.1%} "
                f"(max={-cfg.max_session_loss_pct:.1%}) | "
                f"${abs(self._session_pnl):.2f} lost from ${self.starting_balance:.2f}"
            )

    def _trip(self, reason: TripReason, message: str) -> None:
        if self._tripped:
            return  # already tripped, don't overwrite first reason
        self._tripped       = True
        self._trip_reason   = reason
        self._trip_time     = datetime.now(timezone.utc)
        self._trip_message  = message
        self._halts.append({
            "type":              "trip",
            "reason":            reason.value,
            "message":           message,
            "timestamp":         self._trip_time.isoformat(),
            "consecutive_losses": self._consecutive_losses,
            "session_pnl":       self._session_pnl,
        })
        logger.error("🔴 CIRCUIT BREAKER TRIPPED [%s]: %s", reason.value, message)
        logger.error("🔴 Bot is HALTED. Call cb.reset(reason=...) after reviewing logs.")

    def _auto_reset(self, elapsed_minutes: float) -> None:
        logger.info("⏱ Circuit breaker auto-reset after %.1f min cooldown.", elapsed_minutes)
        self._tripped             = False
        self._trip_reason         = None
        self._trip_time           = None
        self._trip_message        = ""
        self._consecutive_losses  = 0
        self._halts.append({
            "type":      "auto_reset",
            "elapsed_minutes": elapsed_minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ─── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n=== Circuit Breaker Smoke Test ===\n")

    cb = CircuitBreaker(starting_balance=453.08)

    # Simulate the $47 disaster scenario
    trades = [
        (False, -8.50,  "BTC",  "bad entry #1"),
        (False, -12.00, "ETH",  "bad entry #2"),
        (False, -9.25,  "BTC",  "bad entry #3"),   # ← should trip here
        (True,   5.00,  "ETH",  "this should NOT execute — bot should be halted"),
    ]

    for won, pnl, coin, note in trades:
        allowed, reason = cb.allow_trade()
        if not allowed:
            print(f"\n  BLOCKED: {reason}")
            print(f"  Trade '{note}' was NOT entered. ✓")
            continue
        print(f"  {'WIN ' if won else 'LOSS'} ${pnl:+.2f} | {coin} | {note}")
        cb.record_trade(won=won, pnl=pnl, coin=coin, note=note)

    import json
    print("\n--- Status ---")
    print(json.dumps(cb.status(), indent=2))
