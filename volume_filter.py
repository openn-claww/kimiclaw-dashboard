# volume_filter.py - Volume confirmation filter for trading bot
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import time

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_EMA_PERIOD     = 20
DEFAULT_MULTIPLIER     = 1.5
MIN_TRADES_TO_ACTIVATE = 10   # Don't signal until EMA is warmed up
STALE_VOLUME_SECONDS   = 5    # Ignore volume older than this
ZERO_VOLUME_SENTINEL   = 1e-9 # Treat volumes below this as zero

# Per-coin volatility profiles
COIN_VOLUME_PROFILES = {
    "BTC": (1.5, 20),   # Liquid, standard
    "ETH": (1.5, 20),   # Similar to BTC
    "SOL": (1.8, 15),   # More volatile, shorter memory
    "XRP": (1.6, 18),   # Medium volatility
}
DEFAULT_PROFILE = (1.5, 20)

@dataclass
class VolumeState:
    coin: str
    ema_period: int = DEFAULT_EMA_PERIOD
    multiplier: float = DEFAULT_MULTIPLIER
    
    # Runtime state
    volume_ema: float = 0.0
    last_volume: float = 0.0
    last_update: float = field(default_factory=time.time)
    trade_count: int = 0
    _alpha: float = field(init=False)
    
    def __post_init__(self):
        self._alpha = 2 / (self.ema_period + 1)

def parse_binance_trade(msg: dict) -> tuple[float, float, float]:
    """Extract (price, volume, timestamp) from Binance trade message."""
    try:
        price = float(msg.get("p", 0))
        volume = float(msg.get("q", 0))
        timestamp = msg.get("T", 0) / 1000.0  # ms to seconds
        
        if volume < ZERO_VOLUME_SENTINEL:
            volume = ZERO_VOLUME_SENTINEL
        
        return price, volume, timestamp
    except (KeyError, ValueError) as e:
        return 0.0, ZERO_VOLUME_SENTINEL, time.time()

def update_volume_ema(state: VolumeState, raw_volume: float, timestamp: float) -> float:
    """Update volume EMA with new trade volume."""
    # Stale data guard
    if time.time() - timestamp > STALE_VOLUME_SECONDS:
        return state.volume_ema
    
    state.last_volume = raw_volume
    state.last_update = timestamp
    state.trade_count += 1
    
    if state.volume_ema == 0.0:
        state.volume_ema = raw_volume  # Seed on first trade
    else:
        state.volume_ema = (
            state._alpha * raw_volume
            + (1 - state._alpha) * state.volume_ema
        )
    
    return state.volume_ema

def is_volume_confirmed(state: VolumeState, current_volume: float) -> tuple[bool, dict]:
    """Check if volume confirms the trade signal."""
    debug = {
        "coin": state.coin,
        "current_volume": current_volume,
        "volume_ema": state.volume_ema,
        "multiplier": state.multiplier,
        "required": state.volume_ema * state.multiplier,
        "trade_count": state.trade_count,
        "warmed_up": state.trade_count >= MIN_TRADES_TO_ACTIVATE,
        "confirmed": False,
        "block_reason": None,
    }
    
    # Block: Not warmed up
    if state.trade_count < MIN_TRADES_TO_ACTIVATE:
        debug["block_reason"] = f"warming up ({state.trade_count}/{MIN_TRADES_TO_ACTIVATE})"
        return False, debug
    
    # Block: Zero EMA
    if state.volume_ema < ZERO_VOLUME_SENTINEL:
        debug["block_reason"] = "volume_ema is zero"
        return False, debug
    
    # Block: Zero volume
    if current_volume < ZERO_VOLUME_SENTINEL:
        debug["block_reason"] = "current volume is zero"
        return False, debug
    
    # Core check
    threshold = state.volume_ema * state.multiplier
    if current_volume >= threshold:
        debug["confirmed"] = True
        debug["volume_ratio"] = current_volume / state.volume_ema
    else:
        debug["block_reason"] = (
            f"volume {current_volume:.4f} < required {threshold:.4f} "
            f"({current_volume/state.volume_ema:.2f}x vs {state.multiplier}x needed)"
        )
    
    return debug["confirmed"], debug

def make_volume_state(coin: str) -> VolumeState:
    """Create VolumeState with coin-appropriate parameters."""
    multiplier, period = COIN_VOLUME_PROFILES.get(coin, DEFAULT_PROFILE)
    return VolumeState(coin=coin, ema_period=period, multiplier=multiplier)
