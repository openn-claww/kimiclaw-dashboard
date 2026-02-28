# mtf_confirmation.py - Multi-timeframe confirmation module
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
from typing import Optional
import time

class TF(Enum):
    M5  = "5m"
    M15 = "15m"
    H1  = "1h"

class Alignment(Enum):
    ALIGNED  = "aligned"
    NEUTRAL  = "neutral"
    AGAINST  = "against"

TF_SECONDS = {TF.M5: 300, TF.M15: 900, TF.H1: 3600}
TF_AGGREGATION = {TF.M15: 3, TF.H1: 12}
TF_EMA_PERIODS = {TF.M5: 5, TF.M15: 8, TF.H1: 12}

# Size matrix: (M15_alignment, H1_alignment) → size multiplier
SIZE_MATRIX = {
    (Alignment.ALIGNED,  Alignment.ALIGNED):  1.00,
    (Alignment.ALIGNED,  Alignment.NEUTRAL):  0.50,
    (Alignment.ALIGNED,  Alignment.AGAINST):  0.25,
    (Alignment.NEUTRAL,  Alignment.ALIGNED):  0.25,
    (Alignment.NEUTRAL,  Alignment.NEUTRAL):  0.00,
    (Alignment.NEUTRAL,  Alignment.AGAINST):  0.00,
    (Alignment.AGAINST,  Alignment.ALIGNED):  0.00,
    (Alignment.AGAINST,  Alignment.NEUTRAL):  0.00,
    (Alignment.AGAINST,  Alignment.AGAINST):  0.00,
}

@dataclass
class TFSignal:
    tf: TF
    velocity: float
    alignment: Alignment
    updated_at: float = field(default_factory=time.time)
    stale: bool = False
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.updated_at

@dataclass
class CandleBuffer:
    tf: TF
    candle_size: int
    prices: deque = field(init=False)
    completed: list = field(default_factory=list)
    max_candles: int = 50
    
    def __post_init__(self):
        self.prices = deque(maxlen=self.candle_size)
    
    def push(self, price: float) -> Optional[float]:
        self.prices.append(price)
        if len(self.prices) == self.candle_size:
            close = price
            self.completed.append(close)
            if len(self.completed) > self.max_candles:
                self.completed.pop(0)
            self.prices.clear()
            return close
        return None

@dataclass
class VelocityEMA:
    period: int
    ema: float = 0.0
    prev_price: Optional[float] = None
    count: int = 0
    _alpha: float = field(init=False)
    
    def __post_init__(self):
        self._alpha = 2 / (self.period + 1)
    
    def update(self, price: float) -> float:
        if self.prev_price is None or self.prev_price == 0:
            self.prev_price = price
            return 0.0
        
        raw_velocity = (price - self.prev_price) / self.prev_price
        self.prev_price = price
        self.count += 1
        
        if self.count == 1:
            self.ema = raw_velocity
        else:
            self.ema = self._alpha * raw_velocity + (1 - self._alpha) * self.ema
        
        return self.ema

class MTFTracker:
    NEUTRAL_BAND = 0.002
    
    def __init__(self, coin: str):
        self.coin = coin
        self.velocity = {
            TF.M5: VelocityEMA(TF_EMA_PERIODS[TF.M5]),
            TF.M15: VelocityEMA(TF_EMA_PERIODS[TF.M15]),
            TF.H1: VelocityEMA(TF_EMA_PERIODS[TF.H1]),
        }
        self.buffers = {
            TF.M15: CandleBuffer(TF.M15, TF_AGGREGATION[TF.M15]),
            TF.H1: CandleBuffer(TF.H1, TF_AGGREGATION[TF.H1]),
        }
        self.signals = {TF.M5: None, TF.M15: None, TF.H1: None}
    
    def push_price(self, price: float, timestamp: float) -> dict[TF, Optional[TFSignal]]:
        v5 = self.velocity[TF.M5].update(price)
        self.signals[TF.M5] = self._make_signal(TF.M5, v5, timestamp)
        
        m15_close = self.buffers[TF.M15].push(price)
        if m15_close is not None:
            v15 = self.velocity[TF.M15].update(m15_close)
            self.signals[TF.M15] = self._make_signal(TF.M15, v15, timestamp)
        
        h1_close = self.buffers[TF.H1].push(price)
        if h1_close is not None:
            v1h = self.velocity[TF.H1].update(h1_close)
            self.signals[TF.H1] = self._make_signal(TF.H1, v1h, timestamp)
        
        self._check_staleness(timestamp)
        return self.signals
    
    def _make_signal(self, tf: TF, velocity: float, timestamp: float) -> TFSignal:
        if abs(velocity) <= self.NEUTRAL_BAND:
            alignment = Alignment.NEUTRAL
        elif velocity > 0:
            alignment = Alignment.ALIGNED
        else:
            alignment = Alignment.AGAINST
        return TFSignal(tf=tf, velocity=velocity, alignment=alignment, updated_at=timestamp)
    
    def _check_staleness(self, now: float):
        for tf, signal in self.signals.items():
            if signal is None:
                continue
            max_age = TF_SECONDS[tf] * 2
            signal.stale = (now - signal.updated_at) > max_age

@dataclass
class MTFVerdict:
    allowed: bool
    size_multiplier: float
    primary_side: str
    m5_velocity: float
    m15_alignment: Alignment
    h1_alignment: Alignment
    block_reason: Optional[str]
    confidence_score: float

def evaluate_mtf(signals: dict[TF, Optional[TFSignal]], primary_side: str) -> MTFVerdict:
    def _block(reason):
        return MTFVerdict(False, 0.0, primary_side, 0.0,
                          Alignment.NEUTRAL, Alignment.NEUTRAL, reason, 0.0)
    
    for tf in [TF.M5, TF.M15, TF.H1]:
        sig = signals.get(tf)
        if sig is None:
            return _block(f"{tf.value} signal missing")
        if sig.stale:
            return _block(f"{tf.value} signal stale")
    
    m5 = signals[TF.M5]
    m15 = signals[TF.M15]
    h1 = signals[TF.H1]
    
    def _align_for_side(sig: TFSignal) -> Alignment:
        if sig.alignment == Alignment.NEUTRAL:
            return Alignment.NEUTRAL
        if primary_side == "YES":
            return sig.alignment
        return Alignment.ALIGNED if sig.alignment == Alignment.AGAINST else Alignment.AGAINST
    
    m15_aligned = _align_for_side(m15)
    h1_aligned = _align_for_side(h1)
    
    multiplier = SIZE_MATRIX.get((m15_aligned, h1_aligned), 0.0)
    allowed = multiplier > 0.0
    
    block_reason = None if allowed else f"M15={m15_aligned.value}, H1={h1_aligned.value}"
    
    alignment_score = {Alignment.ALIGNED: 1.0, Alignment.NEUTRAL: 0.5, Alignment.AGAINST: 0.0}
    m5_score = alignment_score[_align_for_side(m5)]
    m15_score = alignment_score[m15_aligned]
    h1_score = alignment_score[h1_aligned]
    confidence = (0.2 * m5_score) + (0.3 * m15_score) + (0.5 * h1_score)
    
    return MTFVerdict(
        allowed=allowed,
        size_multiplier=multiplier,
        primary_side=primary_side,
        m5_velocity=m5.velocity,
        m15_alignment=m15_aligned,
        h1_alignment=h1_aligned,
        block_reason=block_reason,
        confidence_score=confidence,
    )
