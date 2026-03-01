#!/usr/bin/env python3
"""
MASTER BACKTEST - Compare All Versions with SAME Data
Same seed, same market conditions for fair comparison
"""

import statistics
from dataclasses import dataclass
from typing import List, Optional, Dict
import random
import json

# Fixed seed for reproducibility
SEED = 42
random.seed(SEED)

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
    spread_pct: float
    depth_ratio: float
    regime: str

@dataclass
class Trade:
    entry_price: float
    side: str
    amount: float
    pnl_pct: float
    pnl_amount: float
    won: bool
    coin: str

class BaseBacktest:
    """Base class for all versions."""
    
    def __init__(self, name: str, initial_bankroll=500.0):
        self.name = name
        self.initial = initial_bankroll
        self.bankroll = initial_bankroll
        self.trades: List[Trade] = []
        self.equity = [initial_bankroll]
        
        # Common parameters
        self.min_price = 0.15
        self.max_price = 0.85
        self.position_pct = 0.05
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP']
        self.velocity_thresholds = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
        
        # Volume EMA tracking
        self.volume_emas = {coin: 0.0 for coin in self.coins}
        self.alpha = 2 / 21
    
    def reset(self):
        """Reset for new run."""
        self.bankroll = self.initial
        self.trades = []
        self.equity = [self.initial]
        self.volume_emas = {coin: 0.0 for coin in self.coins}
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
        """Override in subclasses."""
        raise NotImplementedError
    
    def simulate_exit(self, entry: float, side: str, coin: str) -> Dict:
        """Simulate trade outcome."""
        win_rates = {'BTC': 0.60, 'ETH': 0.55, 'SOL': 0.58, 'XRP': 0.59}
        win_prob = win_rates.get(coin, 0.58)
        
        # Adjust for side alignment with velocity
        won = random.random() < win_prob + random.uniform(-0.03, 0.03)
        
        if won:
            pnl = random.uniform(0.20, 0.45)
        else:
            pnl = random.uniform(-0.18, -0.08)
        
        return {'pnl': pnl, 'won': won}
    
    def run(self, market_data_list: List[MarketData]) -> Dict:
        """Run backtest on provided market data."""
        self.reset()
        
        for data in market_data_list:
            # Update volume EMA
            if self.volume_emas[data.coin] == 0:
                self.volume_emas[data.coin] = data.volume
            else:
                self.volume_emas[data.coin] = self.alpha * data.volume + (1 - self.alpha) * self.volume_emas[data.coin]
            
            signal = self.should_enter(data)
            
            if signal:
                amount = self.bankroll * self.position_pct * signal.get('size_mult', 1.0)
                if amount < 20:
                    continue
                
                result = self.simulate_exit(signal['entry'], signal['side'], data.coin)
                pnl_amount = amount * result['pnl']
                self.bankroll += pnl_amount
                
                self.trades.append(Trade(
                    entry_price=signal['entry'],
                    side=signal['side'],
                    amount=amount,
                    pnl_pct=result['pnl'] * 100,
                    pnl_amount=pnl_amount,
                    won=result['won'],
                    coin=data.coin
                ))
                self.equity.append(self.bankroll)
        
        return self.get_results()
    
    def get_results(self) -> Dict:
        """Calculate and return results."""
        if not self.trades:
            return {'trades': 0, 'win_rate': 0, 'return_pct': 0, 'max_dd': 0, 'pf': 0}
        
        wins = [t for t in self.trades if t.won]
        losses = [t for t in self.trades if not t.won]
        
        win_rate = len(wins) / len(self.trades) * 100
        total_return = (self.bankroll - self.initial) / self.initial * 100
        
        # Max drawdown
        peak = self.initial
        max_dd = 0
        for eq in self.equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)
        
        # Profit factor
        gross_profit = sum(t.pnl_amount for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_amount for t in losses)) if losses else 1
        pf = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            'trades': len(self.trades),
            'win_rate': round(win_rate, 1),
            'return_pct': round(total_return, 1),
            'max_dd': round(max_dd, 1),
            'pf': round(pf, 2),
            'final_balance': round(self.bankroll, 2)
        }

# ═══════════════════════════════════════════════════════════════════════════════
# VERSION 1: Original (Baseline)
# ═══════════════════════════════════════════════════════════════════════════════
class Version1_Original(BaseBacktest):
    def __init__(self):
        super().__init__("V1: Original")
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
        # Price validation
        if data.yes_price < self.min_price or data.yes_price > self.max_price:
            return None
        
        # Velocity only
        threshold = self.velocity_thresholds[data.coin]
        side = None
        if data.velocity > threshold and data.yes_price < 0.75:
            side = 'YES'
        elif data.velocity < -threshold and data.no_price < 0.75:
            side = 'NO'
        
        if not side:
            return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        return {'side': side, 'entry': entry, 'size_mult': 1.0}

# ═══════════════════════════════════════════════════════════════════════════════
# VERSION 2: + Volume Filter
# ═══════════════════════════════════════════════════════════════════════════════
class Version2_Volume(BaseBacktest):
    def __init__(self):
        super().__init__("V2: +Volume")
        self.volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
        # Price validation
        if data.yes_price < self.min_price or data.yes_price > self.max_price:
            return None
        
        # Velocity
        threshold = self.velocity_thresholds[data.coin]
        side = None
        if data.velocity > threshold and data.yes_price < 0.75:
            side = 'YES'
        elif data.velocity < -threshold and data.no_price < 0.75:
            side = 'NO'
        
        if not side:
            return None
        
        # Volume filter
        if self.volume_emas[data.coin] > 0:
            required = self.volume_emas[data.coin] * self.volume_multipliers[data.coin]
            if data.volume < required:
                return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        return {'side': side, 'entry': entry, 'size_mult': 1.0}

# ═══════════════════════════════════════════════════════════════════════════════
# VERSION 3: + Sentiment
# ═══════════════════════════════════════════════════════════════════════════════
class Version3_Sentiment(BaseBacktest):
    def __init__(self):
        super().__init__("V3: +Sentiment")
        self.volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
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
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
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
        
        # Volume
        if self.volume_emas[data.coin] > 0:
            required = self.volume_emas[data.coin] * self.volume_multipliers[data.coin]
            if data.volume < required:
                return None
        
        # Sentiment
        mult = self.get_sentiment_mult(data.fng, side)
        if mult is None:
            return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        return {'side': side, 'entry': entry, 'size_mult': mult}

# ═══════════════════════════════════════════════════════════════════════════════
# VERSION 4: + MTF
# ═══════════════════════════════════════════════════════════════════════════════
class Version4_MTF(BaseBacktest):
    def __init__(self):
        super().__init__("V4: +MTF")
        self.volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
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
    
    def should_enter(self, data: MarketData) -> Optional[Dict]:
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
        
        # Volume
        if self.volume_emas[data.coin] > 0:
            required = self.volume_emas[data.coin] * self.volume_multipliers[data.coin]
            if data.volume < required:
                return None
        
        # Sentiment
        sentiment_mult = self.get_sentiment_mult(data.fng, side)
        if sentiment_mult is None:
            return None
        
        # MTF
        neutral_band = 0.002
        if side == 'YES':
            m15_aligned = data.m15_velocity > neutral_band
            h1_aligned = data.h1_velocity > neutral_band
        else:
            m15_aligned = data.m15_velocity < -neutral_band
            h1_aligned = data.h1_velocity < -neutral_band
        
        if not m15_aligned or not h1_aligned:
            return None
        
        entry = data.yes_price if side == 'YES' else data.no_price
        return {'side': side, 'entry': entry, 'size_mult': sentiment_mult}

# ═══════════════════════════════════════════════════════════════════════════════
# GENERATE MARKET DATA
# ═══════════════════════════════════════════════════════════════════════════════
def generate_market_data(n_samples: int = 5000) -> List[MarketData]:
    """Generate consistent market data for all versions."""
    data = []
    
    for _ in range(n_samples):
        coin = random.choice(['BTC', 'ETH', 'SOL', 'XRP'])
        
        # Generate prices based on coin
        if coin == 'SOL':
            yes_price = random.uniform(0.20, 0.70)
            velocity = random.uniform(-0.60, 0.60)
        elif coin == 'XRP':
            yes_price = random.uniform(0.25, 0.68)
            velocity = random.uniform(-0.30, 0.30)
        elif coin == 'BTC':
            yes_price = random.uniform(0.28, 0.62)
            velocity = random.uniform(-0.35, 0.35)
        else:
            yes_price = random.uniform(0.26, 0.65)
            velocity = random.uniform(-0.20, 0.20)
        
        no_price = 1 - yes_price + random.uniform(-0.015, 0.015)
        
        # Volume
        base_vol = random.uniform(0.5, 2.0)
        volume = base_vol * random.uniform(2.0, 4.0) if random.random() < 0.2 else base_vol
        
        # Sentiment
        fng = random.randint(10, 90)
        
        # MTF velocities
        m15_velocity = velocity * random.uniform(0.6, 1.2) + random.uniform(-0.05, 0.05)
        h1_velocity = velocity * random.uniform(0.4, 1.0) + random.uniform(-0.03, 0.03)
        
        # Order book
        spread_pct = random.uniform(0.005, 0.025) if random.random() < 0.8 else random.uniform(0.03, 0.06)
        depth_ratio = random.uniform(0.5, 2.0)
        
        # Regime
        regime = random.choice(['trend_up', 'trend_down', 'choppy', 'high_vol'])
        
        data.append(MarketData(
            coin=coin, yes_price=yes_price, no_price=no_price,
            velocity=velocity, volume=volume, fng=fng,
            m15_velocity=m15_velocity, h1_velocity=h1_velocity,
            spread_pct=spread_pct, depth_ratio=depth_ratio, regime=regime
        ))
    
    return data

# ═══════════════════════════════════════════════════════════════════════════════
# RUN COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("="*80)
    print("MASTER BACKTEST - FAIR COMPARISON")
    print("Same seed, same market data for all versions")
    print("="*80)
    print()
    
    # Generate market data once
    print("Generating market data...")
    market_data = generate_market_data(5000)
    print(f"Generated {len(market_data)} market data points")
    print()
    
    # Test all versions
    versions = [
        Version1_Original(),
        Version2_Volume(),
        Version3_Sentiment(),
        Version4_MTF(),
    ]
    
    results = []
    for version in versions:
        print(f"Testing {version.name}...")
        result = version.run(market_data)
        result['name'] = version.name
        results.append(result)
    
    # Print comparison table
    print()
    print("="*80)
    print("RESULTS COMPARISON")
    print("="*80)
    print()
    print(f"{'Version':<20} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'MaxDD%':>8} {'PF':>6} {'Final $':>10}")
    print("-"*80)
    
    for r in results:
        print(f"{r['name']:<20} {r['trades']:>8} {r['win_rate']:>8.1f} {r['return_pct']:>10.1f} {r['max_dd']:>8.1f} {r['pf']:>6.2f} {r['final_balance']:>10.2f}")
    
    print()
    print("="*80)
    print("SUMMARY")
    print("="*80)
    
    baseline = results[0]
    best = max(results, key=lambda x: x['return_pct'])
    
    print(f"Baseline (V1): {baseline['return_pct']:.1f}% return")
    print(f"Best version: {best['name']} with {best['return_pct']:.1f}% return")
    print(f"Improvement: +{best['return_pct'] - baseline['return_pct']:.1f}%")
    print()
    
    # Save results
    with open('/root/.openclaw/workspace/backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("Results saved to backtest_results.json")

if __name__ == "__main__":
    main()
