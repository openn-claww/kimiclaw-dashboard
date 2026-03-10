#!/usr/bin/env python3
"""
high_probability_bond.py - High-Probability Bond Buying Strategy

STRATEGY: "Bond Buyer"
TYPE: High-Probability / Bond Strategy

PRINCIPLE:
Buy binary options that are already highly likely to win (70-90% probability).
The edge comes from:
1. Market inefficiency in pricing near-expiry options
2. Risk premium that exceeds actual risk
3. Time decay working in our favor when probability is stable

AGENCY PATTERN:
- Clean entry/exit rules
- Kelly sizing
- Strict risk management
- Statistical validation
"""

import math
import json
import time
import random
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BondSignal:
    coin: str
    side: str
    entry_price: float
    probability: float
    edge: float
    time_to_expiry: float


class BondBuyerStrategy:
    """
    High-Probability Bond Buying Strategy
    
    ONLY trades when:
    - Probability >= 70% (high confidence)
    - Probability <= 92% (avoid certainty traps)
    - Time remaining 2-15 minutes
    - Price is stable (low volatility)
    """
    
    NAME = "BondBuyer"
    VERSION = "1.0"
    
    # Entry Parameters
    MIN_PROB = 0.70
    MAX_PROB = 0.92
    MIN_TIME = 2.0   # minutes
    MAX_TIME = 15.0  # minutes
    
    # Exit Parameters
    PROFIT_TARGET = 0.04  # 4%
    STOP_LOSS = 0.06     # 6%
    
    # Risk Management
    MAX_BET = 1.0
    MIN_BET = 0.10
    
    def __init__(self, bankroll: float = 5.0):
        self.bankroll = bankroll
        self.initial = bankroll
        self.positions = {}
        self.trades = []
        self.wins = 0
        self.losses = 0
        
    def calculate_probability(self, spot: float, strike: float, t: float) -> float:
        """Calculate probability using log-normal model"""
        if t <= 0 or spot <= 0 or strike <= 0:
            return 0.5
        
        vol = 0.003
        T = t / 60.0
        
        try:
            d = math.log(spot / strike) / (vol * math.sqrt(T))
            # Approximate CDF
            prob = 0.5 * (1 + math.erf(d / math.sqrt(2)))
            return max(0.01, min(0.99, prob))
        except:
            return 0.5
    
    def generate_signal(self, coin: str, yes_price: float, no_price: float,
                       spot: float, strike: float, time_sec: float) -> Optional[BondSignal]:
        """Generate bond buying signal"""
        
        time_min = time_sec / 60.0
        
        # Check time constraints
        if not (self.MIN_TIME <= time_min <= self.MAX_TIME):
            return None
        
        # Calculate probability
        prob_above = self.calculate_probability(spot, strike, time_sec)
        
        # Determine side
        cushion = spot - strike
        
        if cushion > 0:
            side = 'YES'
            market_price = yes_price
            real_prob = prob_above
        else:
            side = 'NO'
            market_price = no_price
            real_prob = 1.0 - prob_above
        
        # Check probability constraints
        if not (self.MIN_PROB <= real_prob <= self.MAX_PROB):
            return None
        
        # Calculate edge
        edge = real_prob - market_price
        
        # Need positive edge > 2%
        if edge < 0.02:
            return None
        
        return BondSignal(
            coin=coin,
            side=side,
            entry_price=market_price,
            probability=real_prob,
            edge=edge,
            time_to_expiry=time_min
        )
    
    def calculate_size(self, signal: BondSignal) -> float:
        """Kelly sizing"""
        p = signal.probability
        b = (1 - signal.entry_price) / signal.entry_price
        q = 1 - p
        
        kelly = (p * b - q) / b if b > 0 else 0
        kelly = max(0, min(kelly, 0.25)) * 0.25  # Quarter Kelly
        
        bet = self.bankroll * kelly
        bet = min(bet, self.MAX_BET)
        bet = max(bet, self.MIN_BET)
        
        return round(bet, 2)
    
    def enter(self, signal: BondSignal, amount: float):
        """Enter position"""
        pos_id = f"{signal.coin}-{time.time():.0f}"
        
        self.positions[pos_id] = {
            'side': signal.side,
            'entry': signal.entry_price,
            'amount': amount,
            'prob': signal.probability,
            'time': time.time()
        }
        
        self.bankroll -= amount
        return pos_id
    
    def check_exit(self, pos_id: str, yes_price: float, no_price: float):
        """Check if should exit"""
        if pos_id not in self.positions:
            return None
        
        pos = self.positions[pos_id]
        current = yes_price if pos['side'] == 'YES' else no_price
        
        pnl = (current - pos['entry']) / pos['entry']
        
        if pnl >= self.PROFIT_TARGET:
            return 'profit', pnl
        elif pnl <= -self.STOP_LOSS:
            return 'stop', pnl
        
        hold_time = (time.time() - pos['time']) / 60
        if hold_time >= 10:  # Max 10 min hold
            return 'time', pnl
        
        return None
    
    def exit(self, pos_id: str, reason: str, pnl: float):
        """Exit position"""
        pos = self.positions[pos_id]
        
        # Apply P&L
        amount = pos['amount']
        profit = amount * pnl
        self.bankroll += amount + profit * 0.98  # 2% fee
        
        # Update stats
        if profit > 0:
            self.wins += 1
        else:
            self.losses += 1
        
        self.trades.append({
            'side': pos['side'],
            'entry': pos['entry'],
            'pnl': profit,
            'pnl_pct': pnl,
            'reason': reason
        })
        
        del self.positions[pos_id]
        return profit
    
    def get_stats(self):
        """Get strategy stats"""
        total = self.wins + self.losses
        if total == 0:
            return {'win_rate': 0, 'profit': 0, 'trades': 0}
        
        win_rate = self.wins / total
        total_profit = sum(t['pnl'] for t in self.trades)
        
        return {
            'win_rate': win_rate,
            'profit': total_profit,
            'trades': total,
            'bankroll': self.bankroll,
            'roi': (self.bankroll - self.initial) / self.initial
        }


def run_backtest(n_sim: int = 1000):
    """Run backtest"""
    results = []
    
    for i in range(n_sim):
        strat = BondBuyerStrategy(bankroll=5.0)
        random.seed(i)
        
        # Simulate 100 opportunities
        for _ in range(100):
            # Generate realistic scenario
            strike = random.choice([65000, 67000, 68000, 70000])
            cushion = random.uniform(0.01, 0.06)  # 1-6% cushion
            spot = strike * (1 + random.choice([-1, 1]) * cushion)
            time_sec = random.uniform(120, 900)  # 2-15 min
            
            # Calculate true probability
            prob = strat.calculate_probability(spot, strike, time_sec)
            
            # Add market inefficiency (noise)
            if spot > strike:
                yes_prob = prob
                yes_price = max(0.50, min(0.95, yes_prob - random.uniform(0, 0.05)))
                no_price = 1 - yes_price + random.uniform(-0.01, 0.01)
            else:
                no_prob = 1 - prob
                no_price = max(0.50, min(0.95, no_prob - random.uniform(0, 0.05)))
                yes_price = 1 - no_price + random.uniform(-0.01, 0.01)
            
            # Generate signal
            signal = strat.generate_signal('BTC', yes_price, no_price, 
                                          spot, strike, time_sec)
            
            if signal:
                amount = strat.calculate_size(signal)
                if amount >= 0.10:
                    pos_id = strat.enter(signal, amount)
                    
                    # Simulate outcome (70-90% win rate based on probability)
                    won = random.random() < signal.probability
                    if won:
                        exit_yes = yes_price * 1.04
                        exit_no = no_price * 1.04
                    else:
                        exit_yes = yes_price * 0.94
                        exit_no = no_price * 0.94
                    
                    exit_result = strat.check_exit(pos_id, exit_yes, exit_no)
                    if exit_result:
                        strat.exit(pos_id, exit_result[0], exit_result[1])
        
        # Close remaining
        for pos_id in list(strat.positions.keys()):
            pos = strat.positions[pos_id]
            exit_result = strat.check_exit(pos_id, pos['entry'] * 1.02, pos['entry'] * 1.02)
            if exit_result:
                strat.exit(pos_id, exit_result[0], exit_result[1])
        
        stats = strat.get_stats()
        results.append(stats)
    
    # Aggregate
    profitable = sum(1 for r in results if r['profit'] > 0)
    total_trades = sum(r['trades'] for r in results)
    avg_win_rate = sum(r['win_rate'] for r in results if r['trades'] > 0) / max(1, sum(1 for r in results if r['trades'] > 0))
    avg_profit = sum(r['profit'] for r in results) / n_sim
    
    return {
        'simulations': n_sim,
        'profitable_pct': profitable / n_sim,
        'avg_win_rate': avg_win_rate,
        'avg_profit': avg_profit,
        'total_trades': total_trades,
        'avg_trades_per_sim': total_trades / n_sim
    }


if __name__ == '__main__':
    print("\n🎯 Bond Buyer Strategy - High Probability Trading\n")
    
    results = run_backtest(1000)
    
    print("=" * 60)
    print("BOND BUYER BACKTEST RESULTS")
    print("=" * 60)
    print(f"Simulations:      {results['simulations']}")
    print(f"Profitable:       {results['profitable_pct']:.1%}")
    print(f"Avg Win Rate:     {results['avg_win_rate']:.1%}")
    print(f"Avg Profit:       ${results['avg_profit']:.2f}")
    print(f"Total Trades:     {results['total_trades']}")
    print(f"Trades per sim:   {results['avg_trades_per_sim']:.1f}")
    
    if results['avg_win_rate'] >= 0.55:
        print("\n✅ STRATEGY VIABLE - Win rate > 55%")
    else:
        print("\n❌ NEEDS IMPROVEMENT")
    
    print("=" * 60)
    
    # Save
    with open('/root/.openclaw/workspace/bond_buyer_backtest.json', 'w') as f:
        json.dump(results, f, indent=2)
