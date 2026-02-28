# adaptive_exit.py - Adaptive exit strategy based on regime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import deque
import time

# ── Regime Definitions ────────────────────────────────────────────────────────
class Regime(Enum):
    TREND_UP   = "trend_up"
    TREND_DOWN = "trend_down"
    CHOPPY     = "choppy"
    HIGH_VOL   = "high_vol"

class ExitReason(Enum):
    STOP_LOSS      = "stop_loss"
    TAKE_PROFIT    = "take_profit"
    PARTIAL_TARGET = "partial_target"
    TRAILING_STOP  = "trailing_stop"
    TIME_STOP      = "time_stop"
    REGIME_CHANGE  = "regime_change"

@dataclass
class ExitParams:
    stop_loss:        float
    take_profit:      float
    partial_target:   float
    trail_pct:        Optional[float]
    trail_activate:   float
    time_stop_min:    int

# Regime-based exit parameters
REGIME_EXITS = {
    Regime.TREND_UP:   ExitParams(0.30, 0.60, 0.25, 0.20, 0.10, 180),
    Regime.TREND_DOWN: ExitParams(0.15, 0.25, 0.12, 0.10, 0.05,  60),
    Regime.CHOPPY:     ExitParams(0.10, 0.20, 0.10, None, 0.00,  45),
    Regime.HIGH_VOL:   ExitParams(0.35, 0.70, 0.30, 0.25, 0.12, 240),
}

@dataclass
class ExitSignal:
    should_exit:   bool
    reason:        Optional[ExitReason]
    exit_shares:   float
    debug:         dict

@dataclass
class AdaptivePosition:
    market_id:    str
    side:         str
    entry_price:  float
    shares:       float
    entry_regime: Regime
    entry_time:   float = field(default_factory=time.time)
    
    params: ExitParams = field(init=False)
    peak_price:          float = field(init=False)
    trailing_stop_price: Optional[float] = None
    trailing_active:     bool  = False
    partial_taken:       bool  = False
    remaining_shares:    float = field(init=False)
    current_regime:      Regime = field(init=False)
    
    def __post_init__(self):
        self.params           = REGIME_EXITS[self.entry_regime]
        self.peak_price       = self.entry_price
        self.remaining_shares = self.shares
        self.current_regime   = self.entry_regime

def check_exits(pos: AdaptivePosition, current_price: float,
                current_regime: Regime) -> ExitSignal:
    """Master exit check - call on every price tick."""
    p      = pos.params
    pnl    = (current_price - pos.entry_price) / pos.entry_price
    elapsed = (time.time() - pos.entry_time) / 60
    
    debug = {
        "market":       pos.market_id,
        "entry":        pos.entry_price,
        "current":      current_price,
        "pnl_pct":      f"{pnl:+.2%}",
        "elapsed_min":  f"{elapsed:.1f}",
        "regime":       pos.current_regime.value,
        "trailing_on":  pos.trailing_active,
        "partial_done": pos.partial_taken,
    }
    
    def _signal(reason, shares):
        debug["exit_reason"] = reason.value
        return ExitSignal(True, reason, shares, debug)
    
    def _hold():
        debug["exit_reason"] = "hold"
        return ExitSignal(False, None, 0.0, debug)
    
    # 1. Regime change exit
    if current_regime != pos.current_regime:
        old, new = pos.current_regime, current_regime
        pos.current_regime = new
        pos.params = REGIME_EXITS[new]
        
        should_exit = _should_exit_on_regime_change(old, new, pnl)
        debug["regime_change"] = f"{old.value} → {new.value}"
        
        if should_exit:
            return _signal(ExitReason.REGIME_CHANGE, pos.remaining_shares)
    
    # 2. Hard stop loss
    if pnl <= -p.stop_loss:
        return _signal(ExitReason.STOP_LOSS, pos.remaining_shares)
    
    # 3. Time stop
    if elapsed >= p.time_stop_min:
        return _signal(ExitReason.TIME_STOP, pos.remaining_shares)
    
    # 4. Partial exit at first target
    if not pos.partial_taken and pnl >= p.partial_target:
        partial_shares = pos.shares * 0.5
        pos.remaining_shares -= partial_shares
        pos.partial_taken = True
        return _signal(ExitReason.PARTIAL_TARGET, partial_shares)
    
    # 5. Full take profit
    if pnl >= p.take_profit:
        return _signal(ExitReason.TAKE_PROFIT, pos.remaining_shares)
    
    # 6. Trailing stop
    if p.trail_pct is not None:
        _update_trailing_stop(pos, current_price, pnl, p)
        if pos.trailing_active and current_price <= pos.trailing_stop_price:
            return _signal(ExitReason.TRAILING_STOP, pos.remaining_shares)
    
    return _hold()

def _update_trailing_stop(pos: AdaptivePosition, current_price: float,
                           pnl: float, p: ExitParams):
    """Ratchet trailing stop upward only."""
    if not pos.trailing_active and pnl >= p.trail_activate:
        pos.trailing_active = True
        pos.trailing_stop_price = current_price * (1 - p.trail_pct)
        return
    
    if pos.trailing_active and current_price > pos.peak_price:
        pos.peak_price = current_price
        new_stop = current_price * (1 - p.trail_pct)
        if new_stop > pos.trailing_stop_price:
            pos.trailing_stop_price = new_stop

def _should_exit_on_regime_change(old: Regime, new: Regime, pnl: float) -> bool:
    """Exit rules on regime change."""
    if new == Regime.CHOPPY:
        return True
    if old == Regime.TREND_UP and new == Regime.TREND_DOWN:
        return True
    if old == Regime.TREND_DOWN and new == Regime.TREND_UP:
        return True
    if new == Regime.HIGH_VOL and pnl < 0:
        return True
    return False

# ATR Calculator for dynamic stops
@dataclass
class ATRState:
    period: int = 14
    values: deque = field(default_factory=lambda: deque(maxlen=14))
    prev_close: Optional[float] = None
    current_atr: float = 0.0

def update_atr(state: ATRState, high: float, low: float, close: float) -> float:
    """Update ATR with new candle data."""
    if state.prev_close is None:
        state.prev_close = close
        return 0.0
    
    tr = max(high - low, abs(high - state.prev_close), abs(low - state.prev_close))
    state.values.append(tr)
    state.prev_close = close
    
    if len(state.values) >= state.period:
        state.current_atr = sum(state.values) / len(state.values)
    
    return state.current_atr

def atr_adjusted_stop(base_stop_pct: float, entry_price: float,
                       atr: float, multiplier: float = 2.0) -> float:
    """Blend regime stop with ATR-based stop."""
    if atr <= 0 or entry_price <= 0:
        return base_stop_pct
    
    atr_stop_pct = (atr * multiplier) / entry_price
    return max(base_stop_pct, atr_stop_pct)
