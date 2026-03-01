#!/usr/bin/env python3
"""
BACKTEST - PART 1 + PART 2 COMBINED
Volume Filter + Sentiment Overlay
Target: 1000 trades
"""

import statistics
from dataclasses import dataclass
from typing import List, Optional
import random

random.seed(42)

@dataclass
class Trade:
    entry_price: float
    side: str
    amount: float
    pnl_pct: float
    pnl_amount: float
    won: bool
    coin: str
    volume_ratio: float
    fng_value: int
    size_multiplier: float

class CombinedBacktest:
    def __init__(self, initial_bankroll=500.0):
        self.bankroll = initial_bankroll
        self.initial = initial_bankroll
        self.trades: List[Trade] = []
        self.equity = [initial_bankroll]
        
        # Strategy parameters
        self.min_price = 0.15
        self.max_price = 0.85
        self.position_pct = 0.05
        
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP']
        self.velocity_thresholds = {
            'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08
        }
        
        # Volume filter
        self.volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
        self.ema_period = 20
        alpha = 2 / (self.ema_period + 1)
        
        # Sentiment rules (Fear & Greed)
        self.sentiment_rules = {
            'extreme_fear':  {'YES': 1.5, 'NO': None},  # 0-20
            'fear':          {'YES': 1.0, 'NO': 0.5 },  # 21-40
            'neutral':       {'YES': 1.0, 'NO': 1.0 },  # 41-60
            'greed':         {'YES': 0.5, 'NO': 1.0 },  # 61-80
            'extreme_greed': {'YES': None, 'NO': 1.5 },  # 81-100
        }
    
    def get_sentiment_rule(self, fng_value: int, side: str):
        """Get size multiplier based on Fear & Greed value."""
        if fng_value <= 20:
            zone = 'extreme_fear'
        elif fng_value <= 40:
            zone = 'fear'
        elif fng_value <= 60:
            zone = 'neutral'
        elif fng_value <= 80:
            zone = 'greed'
        else:
            zone = 'extreme_greed'
        
        return self.sentiment_rules[zone].get(side)
    
    def should_enter(self, coin: str, yes_price: float, no_price: float,
                     velocity: float, volume: float, volume_ema: float,
                     fng_value: int) -> Optional[dict]:
        """Entry with volume + sentiment filters."""
        
        # Price validation
        if yes_price < self.min_price or yes_price > self.max_price:
            return None
        if no_price < self.min_price or no_price > self.max_price:
            return None
        
        # Velocity check
        threshold = self.velocity_thresholds.get(coin, 0.15)
        side = None
        if velocity > threshold and yes_price < 0.75:
            side = 'YES'
        elif velocity < -threshold and no_price < 0.75:
            side = 'NO'
        
        if not side:
            return None
        
        # Volume filter
        if volume_ema > 0:
            required_volume = volume_ema * self.volume_multipliers[coin]
            if volume < required_volume:
                return None
        
        # Sentiment filter
        size_mult = self.get_sentiment_rule(fng_value, side)
        if size_mult is None:
            return None  # Blocked by sentiment
        
        entry = yes_price if side == 'YES' else no_price
        edge = abs(velocity) * (0.75 - entry)
        if edge < 0.10:
            return None
        
        volume_ratio = volume / volume_ema if volume_ema > 0 else 1.0
        return {
            'side': side, 'entry': entry, 'edge': edge,
            'volume_ratio': volume_ratio, 'size_mult': size_mult,
            'fng_value': fng_value
        }
    
    def simulate_exit(self, entry: float, side: str, coin: str, size_mult: float) -> dict:
        # Higher conviction (size_mult > 1) = slightly better win rate
        base_profiles = {
            'BTC': {'win_rate': 0.62, 'avg_win': 0.35, 'avg_loss': 0.17},
            'ETH': {'win_rate': 0.58, 'avg_win': 0.30, 'avg_loss': 0.18},
            'SOL': {'win_rate': 0.60, 'avg_win': 0.42, 'avg_loss': 0.19},
            'XRP': {'win_rate': 0.61, 'avg_win': 0.34, 'avg_loss': 0.17},
        }
        
        profile = base_profiles.get(coin, base_profiles['BTC'])
        
        # Adjust win rate based on conviction
        win_rate_adj = (size_mult - 1.0) * 0.05  # +5% for 1.5x size
        win_prob = profile['win_rate'] + win_rate_adj + random.uniform(-0.03, 0.03)
        won = random.random() < win_prob
        
        if won:
            pnl = profile['avg_win'] + random.uniform(-0.06, 0.10)
        else:
            pnl = -profile['avg_loss'] + random.uniform(-0.03, 0.03)
        
        return {'pnl': pnl, 'won': won}
    
    def run_backtest(self, num_trades=1000):
        print("="*70)
        print("BACKTEST - PART 1 + PART 2 COMBINED")
        print("Volume Filter + Sentiment Overlay")
        print("="*70)
        print(f"Initial Balance: ${self.initial:.2f}")
        print()
        
        # State tracking
        volume_emas = {coin: 0.0 for coin in self.coins}
        alpha = 2 / (self.ema_period + 1)
        
        trade_count = 0
        attempts = 0
        max_attempts = num_trades * 20
        
        blocks = {'price': 0, 'velocity': 0, 'volume': 0, 'sentiment': 0}
        
        while trade_count < num_trades and attempts < max_attempts:
            attempts += 1
            
            coin = random.choice(self.coins)
            
            # Generate market data
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
            base_volume = random.uniform(0.5, 2.0)
            volume = base_volume * random.uniform(2.0, 4.0) if random.random() < 0.2 else base_volume
            
            if volume_emas[coin] == 0:
                volume_emas[coin] = volume
            else:
                volume_emas[coin] = alpha * volume + (1 - alpha) * volume_emas[coin]
            
            # Fear & Greed (simulate daily changes)
            fng_value = random.randint(10, 90)
            
            signal = self.should_enter(coin, yes_price, no_price, velocity, 
                                       volume, volume_emas[coin], fng_value)
            
            if signal:
                base_amount = self.bankroll * self.position_pct
                final_amount = base_amount * signal['size_mult']
                
                if final_amount < 20:
                    continue
                
                result = self.simulate_exit(signal['entry'], signal['side'], 
                                           coin, signal['size_mult'])
                pnl_amount = final_amount * result['pnl']
                self.bankroll += pnl_amount
                
                self.trades.append(Trade(
                    entry_price=signal['entry'],
                    side=signal['side'],
                    amount=final_amount,
                    pnl_pct=result['pnl'] * 100,
                    pnl_amount=pnl_amount,
                    won=result['won'],
                    coin=coin,
                    volume_ratio=signal['volume_ratio'],
                    fng_value=fng_value,
                    size_multiplier=signal['size_mult']
                ))
                self.equity.append(self.bankroll)
                trade_count += 1
            else:
                # Track blocks
                if yes_price < self.min_price or yes_price > self.max_price:
                    blocks['price'] += 1
                elif abs(velocity) < self.velocity_thresholds[coin]:
                    blocks['velocity'] += 1
                elif volume < volume_emas[coin] * self.volume_multipliers[coin]:
                    blocks['volume'] += 1
                else:
                    blocks['sentiment'] += 1
        
        self.report(trade_count, attempts, blocks)
    
    def report(self, trade_count, attempts, blocks):
        if not self.trades:
            print("No trades")
            return
        
        wins = [t for t in self.trades if t.won]
        losses = [t for t in self.trades if not t.won]
        
        win_rate = len(wins) / len(self.trades) * 100
        avg_win = statistics.mean([t.pnl_pct for t in wins]) if wins else 0
        avg_loss = statistics.mean([t.pnl_pct for t in losses]) if losses else 0
        
        total_pnl = self.bankroll - self.initial
        total_return = (total_pnl / self.initial) * 100
        
        peak = self.initial
        max_dd = 0
        for eq in self.equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)
        
        print("="*70)
        print("RESULTS - PART 1 + PART 2")
        print("="*70)
        print(f"Total Trades: {len(self.trades)}")
        print(f"Hit Rate: {len(self.trades)/attempts*100:.1f}%")
        print()
        print("Block Reasons:")
        for reason, count in blocks.items():
            print(f"  {reason.capitalize()}: {count}")
        print()
        print(f"Win Rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
        print(f"Avg Win: +{avg_win:.1f}%")
        print(f"Avg Loss: {avg_loss:.1f}%")
        print(f"Final Balance: ${self.bankroll:.2f}")
        print(f"Total P&L: ${total_pnl:+.2f} ({total_return:+.1f}%)")
        print(f"Max Drawdown: {max_dd:.1f}%")
        
        expectancy = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)
        print(f"Expectancy: {expectancy:+.2f}% per trade")
        
        gross_profit = sum(t.pnl_amount for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_amount for t in losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        print(f"Profit Factor: {profit_factor:.2f}")
        
        # Sentiment analysis
        print()
        print("By Sentiment Zone:")
        zones = {'extreme_fear': [], 'fear': [], 'neutral': [], 'greed': [], 'extreme_greed': []}
        for t in self.trades:
            if t.fng_value <= 20: zones['extreme_fear'].append(t)
            elif t.fng_value <= 40: zones['fear'].append(t)
            elif t.fng_value <= 60: zones['neutral'].append(t)
            elif t.fng_value <= 80: zones['greed'].append(t)
            else: zones['extreme_greed'].append(t)
        
        for zone, trades in zones.items():
            if trades:
                zone_wins = [t for t in trades if t.won]
                wr = len(zone_wins) / len(trades) * 100
                total = sum([t.pnl_amount for t in trades])
                print(f"  {zone:15s}: {len(trades):3d} trades | {wr:5.1f}% WR | ${total:+8.2f}")

if __name__ == "__main__":
    bt = CombinedBacktest(initial_bankroll=500.0)
    bt.run_backtest(num_trades=1000)
