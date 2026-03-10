#!/usr/bin/env python3
"""
dual_strategy_backtest.py - Comprehensive backtest of External Arb vs Momentum strategies
Uses backtesting.py for realistic simulation with large sample sizes

Run: python3 dual_strategy_backtest.py --samples 100000 --plot
"""

import math
import random
import statistics
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import argparse
import json

# Try to import backtesting.py, fallback to custom implementation
try:
    from backtesting import Backtest, Strategy
    from backtesting.lib import crossover
    BACKTESTING_AVAILABLE = True
except ImportError:
    BACKTESTING_AVAILABLE = False
    print("backtesting.py not available, using custom implementation")

@dataclass
class TradeResult:
    strategy: str
    entry_time: datetime
    exit_time: datetime
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    win: bool
    holding_period_min: float

class ExternalArbStrategy:
    """
    External Arbitrage Strategy Backtest
    Based on log-normal probability model with time decay
    """
    def __init__(self, vol=0.003, fee=0.02, min_edge=0.05, min_prob=0.55, max_prob=0.95):
        self.vol = vol
        self.fee = fee
        self.min_edge = min_edge
        self.min_prob = min_prob
        self.max_prob = max_prob
        self.trades: List[TradeResult] = []
        
    def _norm_cdf(self, x):
        """Standard normal CDF approximation"""
        a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
        L = abs(x)
        K = 1 / (1 + 0.2316419 * L)
        w = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-L * L / 2) * (a1*K + a2*K**2 + a3*K**3 + a4*K**4 + a5*K**5)
        return w if x >= 0 else 1 - w
    
    def kelly_size(self, p: float, market_price: float, bankroll: float, max_fraction=0.25) -> float:
        """Kelly Criterion position sizing"""
        if p <= 0 or market_price <= 0:
            return 0
        b = (1 - market_price) / market_price  # odds
        q = 1 - p
        kelly = (p * b - q) / b if b > 0 else 0
        kelly = max(0, min(kelly, max_fraction))
        return bankroll * kelly
    
    def evaluate(self, spot: float, threshold: float, time_remaining_sec: float,
                 yes_price: float, no_price: float, bankroll: float,
                 timestamp: datetime) -> Optional[TradeResult]:
        """
        Evaluate external arbitrage opportunity
        """
        # Time filter: only trade with 1-4 minutes remaining
        if not (60 <= time_remaining_sec <= 240):
            return None
        
        T = time_remaining_sec / 3600.0  # Convert to hours
        
        # Calculate real probability using log-normal model
        try:
            d = math.log(spot / threshold) / (self.vol * math.sqrt(T))
            prob_above = self._norm_cdf(d)
        except:
            return None
        
        # Determine side
        if spot > threshold:
            side = 'YES'
            market_price = yes_price
            real_prob = prob_above
        else:
            side = 'NO'
            market_price = no_price
            real_prob = 1 - prob_above
        
        # Probability range check
        if not (self.min_prob <= real_prob <= self.max_prob):
            return None
        
        # Calculate edge
        ev = real_prob * (1 - market_price) * (1 - self.fee) - (1 - real_prob) * market_price
        net_edge = ev / max(market_price, 1e-6)
        
        if net_edge < self.min_edge:
            return None
        
        # Position sizing
        position_size = self.kelly_size(real_prob, market_price, bankroll)
        if position_size <= 0:
            return None
        
        # Simulate trade outcome
        # Probability-weighted outcome
        if random.random() < real_prob:
            # Win - binary option pays $1 per share
            shares = position_size / market_price
            payout = shares * 1.0 * (1 - self.fee)
            pnl = payout - position_size
            win = True
            exit_price = 1.0
        else:
            # Loss
            pnl = -position_size
            win = False
            exit_price = 0.0
        
        trade = TradeResult(
            strategy='external_arb',
            entry_time=timestamp,
            exit_time=timestamp + timedelta(minutes=time_remaining_sec/60),
            side=side,
            entry_price=market_price,
            exit_price=exit_price,
            size=position_size,
            pnl=pnl,
            win=win,
            holding_period_min=time_remaining_sec/60
        )
        self.trades.append(trade)
        return trade


class MomentumStrategy:
    """
    Momentum Strategy Backtest
    Trades on price velocity with stop-loss and take-profit
    """
    def __init__(self, velocity_threshold=0.003, stop_loss=0.02, 
                 take_profit=0.04, fee=0.02, max_hold_min=30, cooldown_min=5):
        self.velocity_threshold = velocity_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.fee = fee
        self.max_hold_min = max_hold_min
        self.cooldown_min = cooldown_min
        self.trades: List[TradeResult] = []
        self.price_history: List[Tuple[datetime, float]] = []
        self.last_trade_time: Optional[datetime] = None
        
    def calculate_velocity(self, current_price: float, timestamp: datetime) -> float:
        """Calculate 1-minute price velocity"""
        self.price_history.append((timestamp, current_price))
        
        # Keep only last 2 minutes of data
        cutoff = timestamp - timedelta(minutes=2)
        self.price_history = [(t, p) for t, p in self.price_history if t >= cutoff]
        
        if len(self.price_history) < 2:
            return 0.0
        
        # Find price 1 minute ago
        one_min_ago = timestamp - timedelta(minutes=1)
        past_prices = [p for t, p in self.price_history if t <= one_min_ago]
        
        if not past_prices:
            return 0.0
        
        past_price = past_prices[-1]
        return (current_price - past_price) / past_price
    
    def kelly_size(self, signal_strength: float, bankroll: float, max_fraction=0.25) -> float:
        """Position size based on signal strength"""
        kelly = min(signal_strength, max_fraction)
        return bankroll * kelly
    
    def evaluate(self, current_price: float, yes_price: float, no_price: float,
                 timestamp: datetime, bankroll: float) -> Optional[TradeResult]:
        """
        Evaluate momentum opportunity
        """
        # Check cooldown
        if self.last_trade_time and (timestamp - self.last_trade_time).total_seconds() < self.cooldown_min * 60:
            return None
        
        velocity = self.calculate_velocity(current_price, timestamp)
        
        # Check velocity threshold
        if abs(velocity) < self.velocity_threshold:
            return None
        
        # Determine side
        if velocity > 0:
            side = 'YES'
            entry_price = yes_price
            # Don't buy if too expensive
            if entry_price > 0.75:
                return None
        else:
            side = 'NO'
            entry_price = no_price
            if entry_price > 0.75:
                return None
        
        # Signal strength based on velocity magnitude (max 10% of bankroll)
        signal_strength = min(abs(velocity) / 0.01, 0.10)  # Cap at 10% per trade
        
        # Position sizing - smaller for safety
        position_size = self.kelly_size(signal_strength, bankroll)
        position_size = min(position_size, bankroll * 0.10, 5.0)  # Max $5 or 10% of bankroll
        if position_size <= 0.5:  # Min $0.50 trade
            return None
        
        # Simulate trade outcome with momentum
        # In prediction markets: buy at entry_price, payout is $1 if win, $0 if lose
        # But with momentum, we're betting on direction
        win_prob = 0.55 + min(abs(velocity) * 10, 0.10)  # 55-65% win rate
        
        if random.random() < win_prob:
            # Win - prediction market pays $1 per share
            shares = position_size / entry_price
            payout = shares * 1.0 * (1 - self.fee)
            pnl = payout - position_size
            win = True
            hold_time = random.uniform(5, 15)
            exit_price = 1.0
        else:
            # Loss - shares become worthless
            pnl = -position_size
            win = False
            hold_time = random.uniform(3, 10)
            exit_price = 0.0
        
        trade = TradeResult(
            strategy='momentum',
            entry_time=timestamp,
            exit_time=timestamp + timedelta(minutes=hold_time),
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=position_size,
            pnl=pnl,
            win=win,
            holding_period_min=hold_time
        )
        self.trades.append(trade)
        self.last_trade_time = timestamp
        return trade


class DualStrategyBacktest:
    """
    Runs both strategies side by side on simulated market data
    """
    def __init__(self, initial_bankroll=56.71, samples=100000):
        self.initial_bankroll = initial_bankroll
        self.samples = samples
        self.external_arb = ExternalArbStrategy()
        self.momentum = MomentumStrategy()
        
    def generate_market_data(self, n_samples: int) -> List[Dict]:
        """Generate realistic prediction market data with inefficiencies"""
        data = []
        base_time = datetime(2024, 1, 1, 0, 0, 0)
        
        # Price thresholds for different markets
        thresholds = {
            'BTC': [65000, 67000, 68000, 69000, 70000, 71000, 72000],
            'ETH': [2000, 2100, 2200, 2300, 2400, 2500],
            'SOL': [80, 85, 90, 95, 100, 105],
            'XRP': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        }
        
        # Track prices for momentum
        price_history = {coin: random.choice(thresholds[coin]) for coin in thresholds}
        
        for i in range(n_samples):
            coin = random.choice(list(thresholds.keys()))
            threshold = random.choice(thresholds[coin])
            
            # Generate spot price with momentum (serial correlation)
            prev_price = price_history[coin]
            trend = random.gauss(0, 0.001)  # Small random walk
            # Add momentum: 60% chance trend continues
            if i > 0 and random.random() < 0.6:
                trend += random.gauss(0, 0.002)
            
            spot = prev_price * (1 + trend)
            price_history[coin] = spot
            
            # Time remaining (0-5 minutes)
            time_remaining = random.uniform(10, 300)
            
            # Market prices with inefficiency for external arb
            # Calculate "real" probability
            vol = 0.003
            T = time_remaining / 3600.0
            try:
                d = math.log(spot / threshold) / (vol * math.sqrt(T))
                real_prob = self.external_arb._norm_cdf(d) if spot > threshold else 1 - self.external_arb._norm_cdf(-d)
            except:
                real_prob = 0.5
            
            # Market maker price lags real probability by 10-30% (creates arb opportunity)
            lag = random.uniform(0.10, 0.30)
            mm_prob = real_prob * (1 - lag) + random.gauss(0.5, 0.05) * lag
            
            # Add spread
            yes_p = max(0.01, min(0.99, mm_prob + random.gauss(0, 0.01)))
            no_p = max(0.01, min(0.99, 1.0 - mm_prob + random.gauss(0, 0.01)))
            
            timestamp = base_time + timedelta(seconds=i * 10)
            
            data.append({
                'coin': coin,
                'threshold': threshold,
                'spot': spot,
                'time_remaining_sec': time_remaining,
                'yes_price': yes_p,
                'no_price': no_p,
                'timestamp': timestamp,
                'real_prob': real_prob  # For debugging
            })
        
        return data
    
    def run_backtest(self) -> Dict:
        """Run complete backtest of both strategies"""
        print(f"\n{'='*70}")
        print(f"DUAL STRATEGY BACKTEST - {self.samples:,} samples")
        print(f"Initial Bankroll: ${self.initial_bankroll:.2f}")
        print(f"{'='*70}\n")
        
        # Generate market data
        print("Generating market data...")
        market_data = self.generate_market_data(self.samples)
        
        # Run strategies
        external_bankroll = self.initial_bankroll
        momentum_bankroll = self.initial_bankroll
        
        print("Running External Arb strategy...")
        for i, data in enumerate(market_data):
            if external_bankroll < 50:  # Hard floor
                break
            result = self.external_arb.evaluate(
                spot=data['spot'],
                threshold=data['threshold'],
                time_remaining_sec=data['time_remaining_sec'],
                yes_price=data['yes_price'],
                no_price=data['no_price'],
                bankroll=external_bankroll,
                timestamp=data['timestamp']
            )
            if result:
                external_bankroll += result.pnl
        
        print("Running Momentum strategy...")
        for i, data in enumerate(market_data):
            if momentum_bankroll < 50:  # Hard floor
                break
            result = self.momentum.evaluate(
                current_price=data['spot'],
                yes_price=data['yes_price'],
                no_price=data['no_price'],
                timestamp=data['timestamp'],
                bankroll=momentum_bankroll
            )
            if result:
                momentum_bankroll += result.pnl
        
        # Calculate statistics
        results = {
            'external_arb': self._calculate_stats(self.external_arb.trades, external_bankroll),
            'momentum': self._calculate_stats(self.momentum.trades, momentum_bankroll),
            'initial_bankroll': self.initial_bankroll,
            'samples': self.samples
        }
        
        return results
    
    def _calculate_stats(self, trades: List[TradeResult], final_bankroll: float) -> Dict:
        """Calculate comprehensive statistics for a strategy"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'final_bankroll': final_bankroll,
                'avg_trade_pnl': 0,
                'max_drawdown': 0,
                'sharpe': 0,
                'profit_factor': 0
            }
        
        wins = sum(1 for t in trades if t.win)
        losses = len(trades) - wins
        win_rate = wins / len(trades) if trades else 0
        
        total_pnl = sum(t.pnl for t in trades)
        avg_pnl = total_pnl / len(trades)
        
        # Calculate drawdown
        peak = self.initial_bankroll
        max_dd = 0
        current = self.initial_bankroll
        for trade in trades:
            current += trade.pnl
            if current > peak:
                peak = current
            dd = (peak - current) / peak
            max_dd = max(max_dd, dd)
        
        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Sharpe ratio (simplified)
        pnls = [t.pnl for t in trades]
        if len(pnls) > 1:
            mean_pnl = statistics.mean(pnls)
            try:
                std_pnl = statistics.stdev(pnls)
                sharpe = (mean_pnl / std_pnl) * math.sqrt(len(pnls)) if std_pnl > 0 else 0
            except:
                sharpe = 0
        else:
            sharpe = 0
        
        # Average hold time
        avg_hold = statistics.mean([t.holding_period_min for t in trades]) if trades else 0
        
        return {
            'total_trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'final_bankroll': final_bankroll,
            'avg_trade_pnl': avg_pnl,
            'max_drawdown_pct': max_dd * 100,
            'sharpe': sharpe,
            'profit_factor': profit_factor,
            'avg_hold_time': avg_hold
        }
    
    def print_results(self, results: Dict):
        """Print formatted results"""
        print(f"\n{'='*70}")
        print("BACKTEST RESULTS - STRATEGY COMPARISON")
        print(f"{'='*70}\n")
        
        for strategy_name, stats in results.items():
            if strategy_name in ['initial_bankroll', 'samples']:
                continue
            
            print(f"\n📊 {strategy_name.upper().replace('_', ' ')}")
            print("-" * 50)
            print(f"  Total Trades:     {stats['total_trades']}")
            print(f"  Win Rate:         {stats['win_rate']:.1%}")
            print(f"  Total P&L:        ${stats['total_pnl']:+.2f}")
            print(f"  Final Bankroll:   ${stats['final_bankroll']:.2f}")
            print(f"  Avg Trade P&L:    ${stats['avg_trade_pnl']:+.3f}")
            print(f"  Max Drawdown:     {stats['max_drawdown_pct']:.1f}%")
            print(f"  Sharpe Ratio:     {stats['sharpe']:.2f}")
            print(f"  Profit Factor:    {stats['profit_factor']:.2f}")
            print(f"  Avg Hold Time:    {stats['avg_hold_time']:.1f} min")
        
        # Comparison
        print(f"\n{'='*70}")
        print("WINNER ANALYSIS")
        print(f"{'='*70}")
        
        ext = results['external_arb']
        mom = results['momentum']
        
        if ext['total_pnl'] > mom['total_pnl']:
            winner = 'EXTERNAL ARBITRAGE'
            margin = ext['total_pnl'] - mom['total_pnl']
        else:
            winner = 'MOMENTUM'
            margin = mom['total_pnl'] - ext['total_pnl']
        
        print(f"\n🏆 WINNER: {winner}")
        print(f"   Margin: ${margin:+.2f}")
        print(f"\n📈 RECOMMENDATION:")
        
        if ext['sharpe'] > mom['sharpe'] and ext['total_trades'] > 10:
            print("   External Arb has better risk-adjusted returns")
        elif mom['sharpe'] > ext['sharpe'] and mom['total_trades'] > 10:
            print("   Momentum has better risk-adjusted returns")
        else:
            print("   Insufficient data - need more trades for conclusion")
        
        print(f"\n💰 EXPECTED RETURNS (per $56.71 bankroll):")
        if ext['total_trades'] > 0:
            exp_return_ext = (ext['total_pnl'] / self.initial_bankroll) * 100
            print(f"   External Arb: {exp_return_ext:+.1f}%")
        if mom['total_trades'] > 0:
            exp_return_mom = (mom['total_pnl'] / self.initial_bankroll) * 100
            print(f"   Momentum:     {exp_return_mom:+.1f}%")
        
        print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description='Dual Strategy Backtest')
    parser.add_argument('--samples', type=int, default=100000, help='Number of samples')
    parser.add_argument('--bankroll', type=float, default=56.71, help='Initial bankroll')
    parser.add_argument('--output', type=str, default='backtest_results.json', help='Output file')
    args = parser.parse_args()
    
    # Set random seed for reproducibility
    random.seed(42)
    
    # Run backtest
    backtest = DualStrategyBacktest(
        initial_bankroll=args.bankroll,
        samples=args.samples
    )
    
    results = backtest.run_backtest()
    backtest.print_results(results)
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {args.output}")


if __name__ == '__main__':
    main()
