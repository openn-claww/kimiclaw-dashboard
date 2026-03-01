"""
risk_manager.py
Risk Management System for Polymarket Trading Bot

PROTECTIONS:
  1. Per-trade max: 5% of bankroll (Kelly-derived)
  2. Max open positions: 6 simultaneous
  3. Daily loss limit: 15% of day-start bankroll → 24h pause
  4. Drawdown circuit breaker: 30% from peak → halt and audit
  5. Consecutive loss limit: 3 in a row → 1h cooldown

INTEGRATION:
  from risk_manager import RiskManager

  rm = RiskManager(starting_bankroll=500.0)

  # Before every trade:
  status = rm.check_trade_allowed(
      current_bankroll=490.0,
      proposed_stake=25.0,
      open_positions=2
  )
  if not status['can_trade']:
      print(f"Blocked: {status['reason']}")
      return

  # After every trade result:
  rm.record_trade_result(pnl=-5.00)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ─── CONFIG ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "max_stake_pct":          0.05,   # Never risk more than 5% per trade
    "max_open_positions":     6,      # Max simultaneous trades
    "daily_loss_limit_pct":   0.15,   # Pause if down 15% in a day
    "drawdown_halt_pct":      0.30,   # Hard halt if down 30% from peak
    "consecutive_loss_limit": 3,      # Cooldown after N straight losses
    "consecutive_loss_pause_minutes": 60,
    "daily_reset_hour_utc":   0,      # Midnight UTC
}

LOG_PATH = Path("/root/.openclaw/workspace/risk_events.log")
STATE_PATH = Path("/root/.openclaw/workspace/risk_state.json")


# ─── LOGGING SETUP ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("RiskManager")

file_handler = logging.FileHandler(LOG_PATH)
file_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
logger.addHandler(file_handler)


# ─── DATA CLASSES ────────────────────────────────────────────────────────────

@dataclass
class RiskEvent:
    timestamp: str
    event_type: str       # 'trade_allowed', 'trade_blocked', 'trade_result', 'circuit_break', 'reset'
    details: str
    bankroll: float
    daily_pnl: float
    drawdown_pct: float
    consecutive_losses: int
    open_positions: int


@dataclass
class RiskState:
    """Persisted between sessions via JSON."""
    starting_bankroll:    float
    peak_bankroll:        float
    current_bankroll:     float
    day_start_bankroll:   float
    daily_pnl:            float
    consecutive_losses:   int
    consecutive_wins:     int
    open_positions:       int
    total_trades:         int
    total_wins:           int
    total_losses:         int
    halted:               bool         = False
    halt_reason:          str          = ""
    halt_until:           Optional[str] = None   # ISO timestamp
    paused:               bool         = False
    pause_reason:         str          = ""
    pause_until:          Optional[str] = None   # ISO timestamp
    last_daily_reset:     str          = ""
    events:               list         = field(default_factory=list)


# ─── RISK MANAGER ────────────────────────────────────────────────────────────

class RiskManager:
    """
    Stateful risk manager. Tracks bankroll, positions, and circuit breakers.

    Persist state by calling save_state() after each trade.
    Restore state by constructing with RiskManager.load(path).
    """

    def __init__(self, starting_bankroll: float, config: dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.state  = RiskState(
            starting_bankroll=starting_bankroll,
            peak_bankroll=starting_bankroll,
            current_bankroll=starting_bankroll,
            day_start_bankroll=starting_bankroll,
            daily_pnl=0.0,
            consecutive_losses=0,
            consecutive_wins=0,
            open_positions=0,
            total_trades=0,
            total_wins=0,
            total_losses=0,
            last_daily_reset=self._now_iso(),
        )
        self._log_event("system_start", f"RiskManager initialized | bankroll=${starting_bankroll:.2f}")

    # ─── PUBLIC API ──────────────────────────────────────────────────────────

    def check_trade_allowed(
        self,
        current_bankroll: float,
        proposed_stake:   float,
        open_positions:   int,
        side:             str = 'YES',
    ) -> dict:
        """
        Call before every trade. Returns risk status dict.

        Returns:
            {
                'can_trade': bool,
                'reason': str,
                'max_stake': float,     # adjusted max if can_trade
                'daily_pnl': float,
                'daily_pnl_pct': float,
                'drawdown_pct': float,
                'consecutive_losses': int,
                'open_positions': int,
                'halted': bool,
                'paused': bool,
            }
        """
        self._maybe_daily_reset()
        self.state.current_bankroll = current_bankroll
        self.state.open_positions   = open_positions

        # Update peak
        if current_bankroll > self.state.peak_bankroll:
            self.state.peak_bankroll = current_bankroll

        # ── Check 1: Hard halt (drawdown) ────────────────────────────────
        if self.state.halted:
            return self._blocked("drawdown_halt", "Hard halt active — audit required before resuming")

        # ── Check 2: Timed pause (consecutive losses) ─────────────────────
        if self.state.paused:
            if self.state.pause_until:
                pause_until = datetime.fromisoformat(self.state.pause_until)
                if datetime.now(timezone.utc) < pause_until:
                    mins_left = (pause_until - datetime.now(timezone.utc)).seconds // 60
                    return self._blocked("consecutive_loss_pause", f"Paused for {mins_left}m after {self.state.consecutive_losses} consecutive losses")
                else:
                    self._lift_pause()

        # ── Check 3: Drawdown circuit breaker ────────────────────────────
        dd_pct = self._drawdown_pct()
        if dd_pct >= self.config["drawdown_halt_pct"] * 100:
            self._engage_halt(f"Drawdown {dd_pct:.1f}% >= {self.config['drawdown_halt_pct']*100:.0f}% limit")
            return self._blocked("drawdown_halt", f"Drawdown circuit breaker: {dd_pct:.1f}% from peak")

        # ── Check 4: Daily loss limit ─────────────────────────────────────
        daily_loss_pct = self._daily_loss_pct()
        if daily_loss_pct >= self.config["daily_loss_limit_pct"] * 100:
            return self._blocked("daily_loss_limit", f"Daily loss {daily_loss_pct:.1f}% >= {self.config['daily_loss_limit_pct']*100:.0f}% limit")

        # ── Check 5: Max positions ────────────────────────────────────────
        if open_positions >= self.config["max_open_positions"]:
            return self._blocked("max_positions", f"At max positions ({open_positions}/{self.config['max_open_positions']})")

        # ── Check 6: Stake size ───────────────────────────────────────────
        max_stake = current_bankroll * self.config["max_stake_pct"]
        if proposed_stake > max_stake:
            # Don't block — just cap it
            logger.warning(f"Stake ${proposed_stake:.2f} exceeds max ${max_stake:.2f} — capping")
            proposed_stake = max_stake

        # ── All clear ────────────────────────────────────────────────────
        self._log_event("trade_allowed", f"stake=${proposed_stake:.2f} | positions={open_positions}")
        return {
            "can_trade":          True,
            "reason":             "ok",
            "max_stake":          round(max_stake, 2),
            "adjusted_stake":     round(proposed_stake, 2),
            "daily_pnl":          round(self.state.daily_pnl, 2),
            "daily_pnl_pct":      round(-daily_loss_pct, 2),
            "drawdown_pct":       round(dd_pct, 2),
            "consecutive_losses": self.state.consecutive_losses,
            "open_positions":     open_positions,
            "halted":             False,
            "paused":             False,
        }

    def record_trade_result(self, pnl: float, market_id: str = ""):
        """
        Call after every trade settles (win or loss).

        Args:
            pnl: Net profit/loss in dollars (positive = win, negative = loss)
            market_id: Optional market identifier for logging
        """
        self.state.daily_pnl       += pnl
        self.state.current_bankroll += pnl
        self.state.total_trades    += 1

        if pnl > 0:
            self.state.total_wins       += 1
            self.state.consecutive_wins += 1
            self.state.consecutive_losses = 0
            outcome = f"WIN  +${pnl:.2f}"
        else:
            self.state.total_losses      += 1
            self.state.consecutive_losses += 1
            self.state.consecutive_wins   = 0
            outcome = f"LOSS -${abs(pnl):.2f}"

        logger.info(f"Trade result: {outcome} | market={market_id or '—'} | "
                    f"bankroll=${self.state.current_bankroll:.2f} | "
                    f"consec_losses={self.state.consecutive_losses}")

        # Check consecutive loss pause
        if self.state.consecutive_losses >= self.config["consecutive_loss_limit"]:
            pause_mins = self.config["consecutive_loss_pause_minutes"]
            self._engage_pause(
                f"{self.state.consecutive_losses} consecutive losses",
                minutes=pause_mins
            )

        self._log_event("trade_result", f"pnl={pnl:+.2f} | {outcome} | market={market_id}")
        self.save_state()

    def open_position(self):
        """Call when a trade order is submitted (not yet resolved)."""
        self.state.open_positions += 1

    def close_position(self):
        """Call when a trade resolves (before recording result)."""
        self.state.open_positions = max(0, self.state.open_positions - 1)

    def get_risk_status(self) -> dict:
        """Returns the full current risk state as a dict."""
        self._maybe_daily_reset()
        dd_pct = self._drawdown_pct()
        dl_pct = self._daily_loss_pct()
        wr = (self.state.total_wins / self.state.total_trades
              if self.state.total_trades > 0 else 0)

        status = {
            "can_trade":           not self.state.halted and not self._is_paused(),
            "reason":              self.state.halt_reason or self.state.pause_reason or "ok",
            "halted":              self.state.halted,
            "paused":              self._is_paused(),
            "pause_until":         self.state.pause_until,
            "daily_pnl":           round(self.state.daily_pnl, 2),
            "daily_pnl_pct":       round(-dl_pct, 2),
            "drawdown_pct":        round(dd_pct, 2),
            "consecutive_losses":  self.state.consecutive_losses,
            "consecutive_wins":    self.state.consecutive_wins,
            "open_positions":      self.state.open_positions,
            "current_bankroll":    round(self.state.current_bankroll, 2),
            "peak_bankroll":       round(self.state.peak_bankroll, 2),
            "day_start_bankroll":  round(self.state.day_start_bankroll, 2),
            "total_trades":        self.state.total_trades,
            "win_rate":            round(wr, 4),
            "limits": {
                "max_stake_pct":          self.config["max_stake_pct"],
                "max_open_positions":     self.config["max_open_positions"],
                "daily_loss_limit_pct":   self.config["daily_loss_limit_pct"],
                "drawdown_halt_pct":      self.config["drawdown_halt_pct"],
                "consecutive_loss_limit": self.config["consecutive_loss_limit"],
            },
        }
        return status

    def reset_daily_stats(self):
        """Call at midnight UTC to reset daily tracking."""
        logger.info(f"Daily reset | day_pnl was ${self.state.daily_pnl:+.2f}")
        self.state.day_start_bankroll = self.state.current_bankroll
        self.state.daily_pnl          = 0.0
        self.state.last_daily_reset   = self._now_iso()
        self._log_event("daily_reset", f"new day_start=${self.state.current_bankroll:.2f}")
        self.save_state()

    def manual_resume(self, reason: str = ""):
        """Manually lift a halt or pause (use after reviewing the situation)."""
        if self.state.halted:
            logger.warning(f"Manual resume from HALT | reason: {reason}")
            self.state.halted      = False
            self.state.halt_reason = ""
            self.state.halt_until  = None
        if self.state.paused:
            logger.warning(f"Manual resume from PAUSE | reason: {reason}")
            self._lift_pause()
        self._log_event("manual_resume", reason)
        self.save_state()

    def print_status(self):
        """Pretty-print the current risk status."""
        s = self.get_risk_status()
        print(f"\n{'═'*50}")
        print(f"  RISK MANAGER STATUS")
        print(f"{'═'*50}")
        can = "✅ YES" if s["can_trade"] else f"🚫 NO ({s['reason']})"
        print(f"  Can Trade:           {can}")
        print(f"  Current Bankroll:    ${s['current_bankroll']:,.2f}")
        print(f"  Peak Bankroll:       ${s['peak_bankroll']:,.2f}")
        print(f"  Daily PnL:           ${s['daily_pnl']:+,.2f}  ({s['daily_pnl_pct']:+.1f}%)")
        print(f"  Drawdown from Peak:  {s['drawdown_pct']:.2f}%  (halt at {s['limits']['drawdown_halt_pct']*100:.0f}%)")
        print(f"  Consecutive Losses:  {s['consecutive_losses']}  (pause at {s['limits']['consecutive_loss_limit']})")
        print(f"  Open Positions:      {s['open_positions']}/{s['limits']['max_open_positions']}")
        print(f"  Total Trades:        {s['total_trades']}  ({s['win_rate']:.1%} WR)")
        print(f"{'═'*50}\n")

    # ─── PERSISTENCE ─────────────────────────────────────────────────────────

    def save_state(self):
        state_dict = asdict(self.state)
        STATE_PATH.write_text(json.dumps(state_dict, indent=2))

    @classmethod
    def load(cls, starting_bankroll: float = 500.0) -> "RiskManager":
        """Load persisted state or create fresh if none exists."""
        rm = cls.__new__(cls)
        rm.config = DEFAULT_CONFIG.copy()

        if STATE_PATH.exists():
            try:
                data  = json.loads(STATE_PATH.read_text())
                rm.state = RiskState(**data)
                logger.info(f"Loaded risk state | bankroll=${rm.state.current_bankroll:.2f}")
                return rm
            except Exception as e:
                logger.warning(f"Failed to load state ({e}) — starting fresh")

        rm.state = RiskState(
            starting_bankroll=starting_bankroll,
            peak_bankroll=starting_bankroll,
            current_bankroll=starting_bankroll,
            day_start_bankroll=starting_bankroll,
            daily_pnl=0.0,
            consecutive_losses=0,
            consecutive_wins=0,
            open_positions=0,
            total_trades=0,
            total_wins=0,
            total_losses=0,
        )
        return rm

    # ─── INTERNAL HELPERS ────────────────────────────────────────────────────

    def _drawdown_pct(self) -> float:
        if self.state.peak_bankroll <= 0:
            return 0.0
        return max(0.0, (self.state.peak_bankroll - self.state.current_bankroll)
                   / self.state.peak_bankroll * 100)

    def _daily_loss_pct(self) -> float:
        """Positive number = how much we're down today in %."""
        if self.state.day_start_bankroll <= 0:
            return 0.0
        daily_loss = -self.state.daily_pnl  # positive = loss
        return max(0.0, daily_loss / self.state.day_start_bankroll * 100)

    def _is_paused(self) -> bool:
        if not self.state.paused:
            return False
        if self.state.pause_until:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(self.state.pause_until):
                self._lift_pause()
                return False
        return True

    def _engage_halt(self, reason: str):
        if not self.state.halted:
            logger.critical(f"CIRCUIT BREAKER ENGAGED: {reason}")
            self.state.halted      = True
            self.state.halt_reason = reason
            self._log_event("circuit_break_halt", reason)
            self.save_state()

    def _engage_pause(self, reason: str, minutes: int):
        pause_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        logger.warning(f"PAUSE ENGAGED: {reason} | paused for {minutes}m until {pause_until.isoformat()}")
        self.state.paused       = True
        self.state.pause_reason = reason
        self.state.pause_until  = pause_until.isoformat()
        self._log_event("circuit_break_pause", f"{reason} | until={pause_until.isoformat()}")
        self.save_state()

    def _lift_pause(self):
        logger.info("Pause lifted — resuming trading")
        self.state.paused             = False
        self.state.pause_reason       = ""
        self.state.pause_until        = None
        self.state.consecutive_losses = 0   # Reset counter on resume

    def _maybe_daily_reset(self):
        """Auto-reset daily stats at midnight UTC."""
        if not self.state.last_daily_reset:
            return
        last_reset = datetime.fromisoformat(self.state.last_daily_reset)
        now        = datetime.now(timezone.utc)
        if now.date() > last_reset.date():
            self.reset_daily_stats()

    def _blocked(self, reason: str, detail: str) -> dict:
        logger.warning(f"Trade BLOCKED: {reason} — {detail}")
        self._log_event("trade_blocked", f"{reason}: {detail}")
        return {
            "can_trade":          False,
            "reason":             reason,
            "detail":             detail,
            "max_stake":          0.0,
            "adjusted_stake":     0.0,
            "daily_pnl":          round(self.state.daily_pnl, 2),
            "daily_pnl_pct":      round(-self._daily_loss_pct(), 2),
            "drawdown_pct":       round(self._drawdown_pct(), 2),
            "consecutive_losses": self.state.consecutive_losses,
            "open_positions":     self.state.open_positions,
            "halted":             self.state.halted,
            "paused":             self.state.paused,
        }

    def _log_event(self, event_type: str, details: str):
        event = {
            "ts":                 self._now_iso(),
            "event":              event_type,
            "details":            details,
            "bankroll":           round(self.state.current_bankroll, 2),
            "daily_pnl":          round(self.state.daily_pnl, 2),
            "drawdown_pct":       round(self._drawdown_pct(), 2),
            "consecutive_losses": self.state.consecutive_losses,
            "open_positions":     self.state.open_positions,
        }
        self.state.events.append(event)
        # Keep only last 200 events in state to avoid bloat
        if len(self.state.events) > 200:
            self.state.events = self.state.events[-200:]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


# ─── STANDALONE FUNCTIONS (for simple integration) ───────────────────────────

_global_rm: Optional[RiskManager] = None

def _get_rm() -> RiskManager:
    global _global_rm
    if _global_rm is None:
        _global_rm = RiskManager.load()
    return _global_rm

def check_trade_allowed(bankroll: float, daily_pnl: float, open_positions: int,
                         consecutive_losses: int, proposed_stake: float = 25.0) -> dict:
    """Standalone function wrapper for simple integration."""
    rm = _get_rm()
    rm.state.daily_pnl          = daily_pnl
    rm.state.consecutive_losses = consecutive_losses
    return rm.check_trade_allowed(bankroll, proposed_stake, open_positions)

def record_trade_result(pnl: float, market_id: str = "") -> None:
    _get_rm().record_trade_result(pnl, market_id)

def get_risk_status() -> dict:
    return _get_rm().get_risk_status()

def reset_daily_stats() -> None:
    _get_rm().reset_daily_stats()


# ─── MAIN / DEMO ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Risk Manager Demo")
    print("=" * 55)

    rm = RiskManager(starting_bankroll=500.0)
    rm.print_status()

    print("── Simulating a normal winning trade ───────────────")
    status = rm.check_trade_allowed(current_bankroll=500.0, proposed_stake=25.0, open_positions=1)
    print(f"  Allowed: {status['can_trade']} | Adjusted stake: ${status['adjusted_stake']:.2f}")
    rm.record_trade_result(pnl=+22.50, market_id="eth-updown-test-1")
    rm.print_status()

    print("── Simulating 3 consecutive losses (triggers pause) ─")
    rm.state.current_bankroll = 490.0
    for i in range(3):
        status = rm.check_trade_allowed(490.0, 25.0, 1)
        if status["can_trade"]:
            rm.record_trade_result(pnl=-5.00, market_id=f"market-loss-{i+1}")
            print(f"  Loss {i+1} recorded | consec_losses={rm.state.consecutive_losses}")
        else:
            print(f"  Blocked: {status['reason']}")

    rm.print_status()

    print("── Manual resume after pause ────────────────────────")
    rm.manual_resume("Reviewed losses — strategy still valid, resuming")
    rm.print_status()

    print("── Simulating large drawdown (triggers halt) ─────────")
    rm.state.peak_bankroll       = 500.0
    rm.state.current_bankroll    = 349.0  # 30.2% drawdown
    rm.state.consecutive_losses  = 0
    rm.state.paused              = False
    status = rm.check_trade_allowed(349.0, 25.0, 1)
    print(f"  Allowed: {status['can_trade']} | Reason: {status['reason']}")
    rm.print_status()
