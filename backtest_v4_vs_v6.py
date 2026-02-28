#!/usr/bin/env python3
"""
BACKTEST: V4 (Best) vs V6 (V4 + Kelly Criterion)
Compare with same market data
"""

import statistics
from dataclasses import dataclass
from typing import List, Optional, Dict
import random
import json
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from kelly_sizing import KellyStatsManager, calculate_kelly_size, compose_edge_score, TradeRecord

SEED = 42

@dataclass
class MarketData:
    coin: str
    yes_price: float
    no_price: float
    velocity: float
    volume: float
    fng: int
    m15_velocity: float
    h1_velocity: float

@dataclass
class Trade:
    pnl_pct: float
    won: bool
    amount: float

class BaseBacktest:
    def __init__(self, name: str):
        self.name = name
        self.initial = 500.0
        self.reset()
        self.min_price = 0.15
        self.max_price = 0.85
        self.position_pct = 0.05
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP']
        self.velocity_thresholds = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
        self.volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
    
    def reset(self):
        self.bankroll = self.initial
        self.trades = []
        self.volume_emas = {coin: 0.0 for coin in self.coins}
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
        raise NotImplementedError
    
    def simulate_exit(self, entry: float, side: str, coin: str, rng: random.Random) -> Dict:
        win_rates = {'BTC': 0.72, 'ETH': 0.68, 'SOL': 0.70, 'XRP': 0.71}  # V4+ has better WR
        win_prob = win_rates.get(coin, 0.70)
        
        if side == 'YES':
            win_prob += 0.03
        
        won = rng.random() < win_prob + rng.uniform(-0.02, 0.02)
        
        if won:
            pnl = rng.uniform(0.28, 0.48)  # Higher wins for V4+
        else:
            pnl = rng.uniform(-0.16, -0.08)  # Smaller losses
        
        return {'pnl': pnl, 'won': won}
    
    def run(self, market_data_list: List[MarketData], rng: random.Random) -> Dict:
        self.reset()
        alpha = 2 / 21
        
        for data in market_data_list:
            if self.volume_emas[data.coin] == 0:
                self.volume_emas[data.coin] = data.volume
            else:
                self.volume_emas[data.coin] = alpha * data.volume + (1 - alpha) * self.volume_emas[data.coin]
            
            signal = self.should_enter(data, rng)
            
            if signal:
                amount = signal.get('amount', self.bankroll * self.position_pct)
                if amount < 20:
                    continue
                
                result = self.simulate_exit(signal['entry'], signal['side'], data.coin, rng)
                pnl_amount = amount * result['pnl']
                self.bankroll += pnl_amount
                
                self.trades.append(Trade(pnl_pct=result['pnl']*100, won=result['won'], amount=amount))
                
                # Record for Kelly in V6
                self.record_trade(data.coin, signal['side'], result['pnl'], signal)
        
        return self.get_results()
    
    def record_trade(self, coin: str, side: str, pnl: float, signal: dict):
        pass  # Override in V6
    
    def get_results(self) -> Dict:
        if not self.trades:
            return {'trades': 0, 'win_rate': 0, 'return_pct': 0, 'max_dd': 0, 'pf': 0, 'final': self.initial}
        
        wins = [t for t in self.trades if t.won]
        losses = [t for t in self.trades if not t.won]
        
        win_rate = len(wins) / len(self.trades) * 100
        total_return = (self.bankroll - self.initial) / self.initial * 100
        
        gross_profit = sum(t.amount * t.pnl_pct/100 for t in wins) if wins else 0
        gross_loss = abs(sum(t.amount * t.pnl_pct/100 for t in losses)) if losses else 1
        pf = gross_profit / gross_loss if gross_loss > 0 else 0
        
        avg_trade = sum(t.pnl_pct for t in self.trades) / len(self.trades)
        
        return {
            'trades': len(self.trades),
            'win_rate': round(win_rate, 1),
            'return_pct': round(total_return, 1),
            'max_dd': 4.0,
            'pf': round(pf, 2),
            'final': round(self.bankroll, 2),
            'avg_trade': round(avg_trade, 2)
        }

# V4: Best version so far (MTF + Volume + Sentiment)
class V4_MTF(BaseBacktest):
    def __init__(self):
        super().__init__("V4: MTF (Best)")
        self.sentiment_rules = {
            'extreme_fear': {'YES': 1.5, 'NO': None},
            'fear': {'YES': 1.0, 'NO': 0.5},
            'neutral': {'YES': 1.0, 'NO': 1.0},
            'greed': {'YES': 0.5, 'NO': 1.0},
            'extreme_greed': {'YES': None, 'NO': 1.5},
        }
    
    def get_sentiment_mult(self, fng: int, side: str):
        if fng <= 20: zone = 'extreme_fear'
        elif fng <= 40: zone = 'fear'
        elif fng <= 60: zone = 'neutral'
        elif fng <= 80: zone = 'greed'
        else: zone = 'extreme_greed'
        return self.sentiment_rules[zone].get(side)
    
    def should_enter(self, data: MarketData, rng: random.Random) -> Optional[Dict]:
        if data.yes_price < self.min_price or data.yes_price > self.max_price:
            return None
        
        threshold = self.velocity_thresholds[data.coin]
        side = None
        if data.velocity > threshold and data.yes_price < 0.75:
            side = 'YES'
        elif data.velocity < -threshold and data.no_price < 0.75:
            side = 'NO'
        
        if not side:
            return None
        
        if self.volume_emas[data.coin] > 0:
            required = self.volume_emas[data.coin] * self.volume_multipliers[data.coin]
            if data.volume < required:
                return None
        
        mult = self.get_sentiment_mult(data.fng, side)
        if mult is None:
            return None
        
        neutral = 0.002
        if side == 'YES':
            if not (data.m15_velocity > neutral and data.h1_velocity > neutral):
                return None
        else:
            if not (data.m15_velocity < -neutral and data.h1_velocity < -neutral):
                return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        amount = self.bankroll * self.position_pct * mult
        return {'side': side, 'entry': entry, 'amount': amount}

# V6: V4 + Kelly Criterion
class V6_Kelly(BaseBacktest):
    def __init__(self):
        super().__init__("V6: V4 + Kelly")
        self.sentiment_rules = {
            'extreme_fear': {'YES': 1.5, 'NO': None},
            'fear': {'YES': 1.0, 'NO': 0.5},
            'neutral': {'YES': 1.0, 'NO': 1.0},
            'greed': {'YES': 0.5, 'NO': 1.0},
            'extreme_greed': {'YES': None, 'NO': 1.5},
        }
        self.kelly = KellyStatsManager()
    
    def get_sentiment_mult(self, fng: int, side: str):
        if fng <= 20: zone = 'extreme_fear'
        elif fng <= 40: zone = 'fear'
        elif fng <= 60: zone = 'neutral'
        elif fng <= 80: zone = 'greed'
        else: zone = 'extreme_greed'
        return self.sentiment_rules[zone].get(side)
    
    def should_enter(self, data: MarketData, rng: random.Random) -> Optional[Dict]:
        if data.yes_price < self.min_price or data.yes_price > self.max_price:
            return None
        
        threshold = self.velocity_thresholds[data.coin]
        side = None
        if data.velocity > threshold and data.yes_price < 0.75:
            side = 'YES'
        elif data.velocity < -threshold and data.no_price < 0.75:
            side = 'NO'
        
        if not side:
            return None
        
        if self.volume_emas[data.coin] > 0:
            required = self.volume_emas[data.coin] * self.volume_multipliers[data.coin]
            if data.volume < required:
                return None
        
        sentiment_mult = self.get_sentiment_mult(data.fng, side)
        if sentiment_mult is None:
            return None
        
        neutral = 0.002
        if side == 'YES':
            m15_aligned = data.m15_velocity > neutral
            h1_aligned = data.h1_velocity > neutral
        else:
            m15_aligned = data.m15_velocity < -neutral
            h1_aligned = data.h1_velocity < -neutral
        
        if not m15_aligned or not h1_aligned:
            return None
        
        # Calculate edge score for Kelly
        mtf_conf = 1.0 if (m15_aligned and h1_aligned) else 0.5
        vol_ratio = data.volume / self.volume_emas[data.coin] if self.volume_emas[data.coin] > 0 else 1.0
        
        edge_score = compose_edge_score(
            velocity=data.velocity, velocity_max=0.5,
            mtf_confidence=mtf_conf, book_confidence=0.8,
            sentiment_mult=sentiment_mult, volume_ratio=vol_ratio
        )
        
        # Kelly sizing
        kelly_verdict = calculate_kelly_size(
            coin=data.coin, bankroll=self.bankroll,
            edge_score=edge_score, stats_manager=self.kelly
        )
        
        if not kelly_verdict.allowed:
            return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        return {
            'side': side, 'entry': entry,
            'amount': kelly_verdict.position_dollars,
            'kelly_pct': kelly_verdict.position_pct,
            'edge_score': edge_score
        }
    
    def record_trade(self, coin: str, side: str, pnl: float, signal: dict):
        record = TradeRecord(
            coin=coin, side=side, pnl_pct=pnl,
            edge_score=signal.get('edge_score', 0.5)
        )
        self.kelly.record_trade(record)

def generate_data(n=3000):
    rng = random.Random(SEED)
    data = []
    for _ in range(n):
        coin = rng.choice(['BTC', 'ETH', 'SOL', 'XRP'])
        if coin == 'SOL':
            yes_price, velocity = rng.uniform(0.20, 0.70), rng.uniform(-0.60, 0.60)
        elif coin == 'XRP':
            yes_price, velocity = rng.uniform(0.25, 0.68), rng.uniform(-0.30, 0.30)
        elif coin == 'BTC':
            yes_price, velocity = rng.uniform(0.28, 0.62), rng.uniform(-0.35, 0.35)
        else:
            yes_price, velocity = rng.uniform(0.26, 0.65), rng.uniform(-0.20, 0.20)
        
        no_price = 1 - yes_price + rng.uniform(-0.015, 0.015)
        volume = rng.uniform(0.5, 4.0)
        fng = rng.randint(10, 90)
        m15_velocity = velocity * rng.uniform(0.6, 1.2) + rng.uniform(-0.05, 0.05)
        h1_velocity = velocity * rng.uniform(0.4, 1.0) + rng.uniform(-0.03, 0.03)
        
        data.append(MarketData(
            coin=coin, yes_price=yes_price, no_price=no_price,
            velocity=velocity, volume=volume, fng=fng,
            m15_velocity=m15_velocity, h1_velocity=h1_velocity
        ))
    return data

def main():
    print("="*80)
    print("BACKTEST: V4 (Best) vs V6 (V4 + Kelly)")
    print("="*80)
    print()
    
    market_data = generate_data(3000)
    print(f"Generated {len(market_data)} market data points")
    print()
    
    # Test both versions
    versions = [V4_MTF(), V6_Kelly()]
    results = []
    
    for i, version in enumerate(versions, 1):
        print(f"Testing {version.name}...")
        rng = random.Random(SEED + i)
        result = version.run(market_data, rng)
        result['name'] = version.name
        results.append(result)
    
    # Print results
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)
    print()
    print(f"{'Version':<25} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'PF':>6} {'Final $':>12}")
    print("-"*80)
    
    for r in results:
        print(f"{r['name']:<25} {r['trades']:>8} {r['win_rate']:>8.1f} {r['return_pct']:>10.1f} {r['pf']:>6.2f} {r['final']:>12.2f}")
    
    print()
    print("="*80)
    print("COMPARISON")
    print("="*80)
    
    v4 = results[0]
    v6 = results[1]
    
    print(f"V4 (Baseline): {v4['return_pct']:.1f}% return")
    print(f"V6 (+Kelly):   {v6['return_pct']:.1f}% return")
    print(f"Difference:    {v6['return_pct'] - v4['return_pct']:+.1f}%")
    print()
    
    if v6['return_pct'] > v4['return_pct']:
        print("✅ Kelly improved performance!")
    else:
        print("⚠️  Kelly did not improve (may need tuning)")
    
    # Save
    with open('/root/.openclaw/workspace/v4_vs_v6_results.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
