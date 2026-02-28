# kelly_sizing.py - Kelly Criterion position sizing
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from enum import Enum
import time
import json
import os

# Configuration
KELLY_FRACTION = 0.5        # Half-Kelly
MAX_POSITION_PCT = 0.10     # Hard cap at 10%
MIN_POSITION_PCT = 0.005    # Floor at 0.5%
MIN_TRADES = 15             # Minimum trades before Kelly valid
ROLLING_WINDOW = 20         # Rolling window for stats
MIN_WIN_RATE = 0.40
MIN_REWARD_RATIO = 0.80
PERSIST_PATH = "/root/.openclaw/workspace/kelly_stats.json"

class TradeOutcome(Enum):
    WIN = "win"
    LOSS = "loss"
    SCRATCH = "scratch"

@dataclass
class TradeRecord:
    coin: str
    side: str
    pnl_pct: float
    timestamp: float = field(default_factory=time.time)
    edge_score: float = 0.0
    regime: str = ""
    
    @property
    def outcome(self) -> TradeOutcome:
        if abs(self.pnl_pct) < 0.005:
            return TradeOutcome.SCRATCH
        return TradeOutcome.WIN if self.pnl_pct > 0 else TradeOutcome.LOSS

@dataclass
class KellyStats:
    coin: str
    trades: deque = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    reward_ratio: float = 0.0
    kelly_f: float = 0.0
    sample_size: int = 0
    last_computed: float = 0.0
    
    def add_trade(self, record: TradeRecord):
        if record.outcome != TradeOutcome.SCRATCH:
            self.trades.append(record)
    
    def compute(self) -> "KellyStats":
        active = [t for t in self.trades if t.outcome != TradeOutcome.SCRATCH]
        self.sample_size = len(active)
        self.last_computed = time.time()
        
        if self.sample_size < MIN_TRADES:
            self.kelly_f = 0.0
            return self
        
        wins = [t for t in active if t.outcome == TradeOutcome.WIN]
        losses = [t for t in active if t.outcome == TradeOutcome.LOSS]
        
        if not wins or not losses:
            self.kelly_f = 0.0
            return self
        
        self.win_rate = len(wins) / self.sample_size
        self.avg_win = sum(t.pnl_pct for t in wins) / len(wins)
        self.avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses))
        self.reward_ratio = self.avg_win / self.avg_loss if self.avg_loss > 0 else 0.0
        
        p, q, b = self.win_rate, 1 - self.win_rate, self.reward_ratio
        
        if b <= MIN_REWARD_RATIO or p <= MIN_WIN_RATE:
            self.kelly_f = 0.0
        else:
            self.kelly_f = max(0.0, (p * b - q) / b)
        
        return self
    
    @property
    def is_ready(self) -> bool:
        return self.sample_size >= MIN_TRADES and self.kelly_f > 0

@dataclass
class KellyVerdict:
    allowed: bool
    position_pct: float
    position_dollars: float
    kelly_f: float
    fractional_kelly: float
    edge_adjusted: float
    capped: bool
    stats_source: str
    sample_size: int
    block_reason: Optional[str]

class KellyStatsManager:
    def __init__(self):
        self.per_coin: dict[str, KellyStats] = {}
        self.global_pool = KellyStats(coin="__global__")
        self._load()
    
    def record_trade(self, record: TradeRecord):
        if record.coin not in self.per_coin:
            self.per_coin[record.coin] = KellyStats(coin=record.coin)
        self.per_coin[record.coin].add_trade(record)
        self.global_pool.add_trade(record)
        self._save()
    
    def get_stats(self, coin: str) -> tuple[KellyStats, str]:
        coin_stats = self.per_coin.get(coin)
        if coin_stats and coin_stats.compute().is_ready:
            return coin_stats, "per_coin"
        self.global_pool.compute()
        return self.global_pool, "global"
    
    def _save(self):
        try:
            os.makedirs(os.path.dirname(PERSIST_PATH), exist_ok=True)
            data = {
                "global": self._stats_to_dict(self.global_pool),
                "coins": {k: self._stats_to_dict(v) for k, v in self.per_coin.items()}
            }
            with open(PERSIST_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[KELLY] Save failed: {e}")
    
    def _load(self):
        try:
            if not os.path.exists(PERSIST_PATH):
                return
            with open(PERSIST_PATH) as f:
                data = json.load(f)
            for coin, d in data.get("coins", {}).items():
                self.per_coin[coin] = self._dict_to_stats(coin, d)
            if "global" in data:
                self.global_pool = self._dict_to_stats("__global__", data["global"])
        except Exception as e:
            print(f"[KELLY] Load failed: {e}")
    
    @staticmethod
    def _stats_to_dict(s: KellyStats) -> dict:
        return {"trades": [{"coin": t.coin, "side": t.side, "pnl_pct": t.pnl_pct,
                "timestamp": t.timestamp, "edge_score": t.edge_score, "regime": t.regime}
                for t in s.trades]}
    
    @staticmethod
    def _dict_to_stats(coin: str, d: dict) -> KellyStats:
        stats = KellyStats(coin=coin)
        for t in d.get("trades", []):
            stats.add_trade(TradeRecord(**t))
        return stats

def calculate_kelly_size(coin: str, bankroll: float, edge_score: float,
                         stats_manager: KellyStatsManager,
                         kelly_fraction: float = KELLY_FRACTION) -> KellyVerdict:
    def _block(reason: str) -> KellyVerdict:
        return KellyVerdict(False, 0.0, 0.0, 0.0, 0.0, 0.0, False, "none", 0, reason)
    
    if bankroll <= 0:
        return _block("bankroll is zero")
    if edge_score <= 0:
        return _block("edge_score is zero")
    
    stats, source = stats_manager.get_stats(coin)
    
    if not stats.is_ready:
        bootstrap_pct = 0.02
        return KellyVerdict(True, bootstrap_pct, round(bankroll * bootstrap_pct, 2),
                           0.0, 0.0, bootstrap_pct, False, f"{source}_bootstrap",
                           stats.sample_size, None)
    
    if stats.kelly_f == 0.0:
        return _block(f"Kelly=0 | WR={stats.win_rate:.0%} b={stats.reward_ratio:.2f}")
    
    fractional = stats.kelly_f * kelly_fraction
    edge_adjusted = fractional * edge_score
    capped = edge_adjusted > MAX_POSITION_PCT
    final_pct = min(edge_adjusted, MAX_POSITION_PCT)
    
    if final_pct < MIN_POSITION_PCT:
        return _block(f"Position {final_pct:.2%} below minimum")
    
    return KellyVerdict(True, round(final_pct, 4), round(bankroll * final_pct, 2),
                       stats.kelly_f, fractional, edge_adjusted, capped, source,
                       stats.sample_size, None)

def compose_edge_score(velocity: float, velocity_max: float,
                       mtf_confidence: float, book_confidence: float,
                       sentiment_mult: float, volume_ratio: float) -> float:
    vel_norm = min(1.0, abs(velocity) / max(velocity_max, 1e-9))
    vol_norm = min(1.0, max(0.0, (volume_ratio - 1.0) / 2.0))
    sent_norm = min(1.0, max(0.0, (sentiment_mult - 0.5)))
    
    score = vel_norm * 0.20 + vol_norm * 0.15 + mtf_confidence * 0.30 + \
            book_confidence * 0.25 + sent_norm * 0.10
    return round(min(1.0, max(0.0, score)), 4)
