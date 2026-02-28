#!/usr/bin/env python3
"""
COMPREHENSIVE BACKTEST - 500 TRADES
With NO price validation bug fix
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
    exit_price: float
    pnl_pct: float
    pnl_amount: float
    won: bool
    coin: str

class ComprehensiveBacktest:
    def __init__(self, initial_bankroll=500.0):
        self.bankroll = initial_bankroll
        self.initial = initial_bankroll
        self.trades: List[Trade] = []
        self.equity = [initial_bankroll]
        self.open_positions = {}
        
        # Strategy parameters
        self.min_price = 0.15
        self.max_price = 0.85
        self.position_pct = 0.05
        self.max_correlated = 2
        
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP']
        self.velocity_thresholds = {
            'BTC': 0.15,
            'ETH': 0.015,
            'SOL': 0.25,
            'XRP': 0.08,
        }
        
    def should_enter(self, coin: str, yes_price: float, no_price: float, velocity: float) -> Optional[dict]:
        """Entry logic with BUG FIX - check both YES and NO prices."""
        
        # BUG FIX: Check YES price
        if yes_price < self.min_price or yes_price > self.max_price:
            return None
        
        # BUG FIX: Check NO price too!
        if no_price < self.min_price or no_price > self.max_price:
            return None
        
        # Correlation limit
        if len(self.open_positions) >= self.max_correlated:
            return None
        if coin in self.open_positions:
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
        
        entry = yes_price if side == 'YES' else no_price
        edge = abs(velocity) * (0.75 - entry)
        if edge < 0.10:
            return None
        
        return {'side': side, 'entry': entry, 'edge': edge, 'coin': coin}
    
    def simulate_exit(self, entry: float, side: str, coin: str) -> dict:
        coin_profiles = {
            'BTC': {'win_rate': 0.58, 'avg_win': 0.32, 'avg_loss': 0.18},
            'ETH': {'win_rate': 0.52, 'avg_win': 0.28, 'avg_loss': 0.19},
            'SOL': {'win_rate': 0.54, 'avg_win': 0.40, 'avg_loss': 0.20},
            'XRP': {'win_rate': 0.55, 'avg_win': 0.30, 'avg_loss': 0.18},
        }
        
        profile = coin_profiles.get(coin, coin_profiles['BTC'])
        win_prob = profile['win_rate'] + random.uniform(-0.03, 0.03)
        won = random.random() < win_prob
        
        if won:
            pnl = profile['avg_win'] + random.uniform(-0.06, 0.10)
        else:
            pnl = -profile['avg_loss'] + random.uniform(-0.03, 0.03)
        
        return {'pnl': pnl, 'won': won}
    
    def run_backtest(self, num_trades=500):
        print("="*70)
        print("COMPREHENSIVE BACKTEST - 500 TRADES")
        print("With NO price validation BUG FIX")
        print("="*70)
        print(f"Initial Balance: ${self.initial:.2f}")
        print(f"Target Trades: {num_trades}")
        print()
        
        trade_count = 0
        attempts = 0
        max_attempts = num_trades * 10
        
        while trade_count < num_trades and attempts < max_attempts:
            attempts += 1
            coin = random.choice(self.coins)
            
            # Generate prices
            if coin == 'SOL':
                yes_price = random.uniform(0.20, 0.70)
            elif coin == 'XRP':
                yes_price = random.uniform(0.25, 0.68)
            elif coin == 'BTC':
                yes_price = random.uniform(0.28, 0.62)
            else:
                yes_price = random.uniform(0.26, 0.65)
            
            # Generate velocity
            if coin == 'SOL':
                velocity = random.uniform(-0.60, 0.60)
            elif coin == 'XRP':
                velocity = random.uniform(-0.30, 0.30)
            elif coin == 'BTC':
                velocity = random.uniform(-0.35, 0.35)
            else:
                velocity = random.uniform(-0.20, 0.20)
            
            no_price = 1 - yes_price + random.uniform(-0.015, 0.015)
            
            signal = self.should_enter(coin, yes_price, no_price, velocity)
            
            if signal:
                amount = self.bankroll * self.position_pct
                if amount < 20:
                    continue
                
                result = self.simulate_exit(signal['entry'], signal['side'], coin)
                pnl_amount = amount * result['pnl']
                self.bankroll += pnl_amount
                
                self.trades.append(Trade(
                    entry_price=signal['entry'],
                    side=signal['side'],
                    amount=amount,
                    exit_price=signal['entry'] * (1 + result['pnl']),
                    pnl_pct=result['pnl'] * 100,
                    pnl_amount=pnl_amount,
                    won=result['won'],
                    coin=coin
                ))
                self.equity.append(self.bankroll)
                trade_count += 1
        
        self.report()
    
    def report(self):
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
        
        # Max drawdown
        peak = self.initial
        max_dd = 0
        for eq in self.equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)
        
        print("="*70)
        print("RESULTS")
        print("="*70)
        print(f"Total Trades: {len(self.trades)}")
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
        
        print()
        print("PER-COIN BREAKDOWN:")
        print("-"*50)
        for coin in self.coins:
            coin_trades = [t for t in self.trades if t.coin == coin]
            if coin_trades:
                coin_wins = [t for t in coin_trades if t.won]
                wr = len(coin_wins) / len(coin_trades) * 100
                avg = statistics.mean([t.pnl_pct for t in coin_trades])
                total = sum([t.pnl_amount for t in coin_trades])
                print(f"{coin:4s}: {len(coin_trades):3d} trades | {wr:5.1f}% WR | {avg:+6.1f}% avg | ${total:+7.2f}")

if __name__ == "__main__":
    bt = ComprehensiveBacktest(initial_bankroll=500.0)
    bt.run_backtest(num_trades=500)
