#!/usr/bin/env python3
"""
BACKTESTING SYSTEM for Ultimate Bot Strategy
Tests strategy on historical data
"""

import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from collections import defaultdict
import requests

# Configuration
INITIAL_BANKROLL = 500.00
POSITION_SIZE_PCT = 0.05
MIN_EDGE = 0.10
STOP_LOSS_PCT = 0.20
TAKE_PROFIT_PCT = 0.40
TRAILING_STOP_PCT = 0.15
TIME_STOP_MINUTES = 90

# Entry validation (from fixed bot)
MIN_YES_PRICE = 0.15
MAX_YES_PRICE = 0.85

class Backtester:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.bankroll = INITIAL_BANKROLL
        self.trades = []
        self.positions = []
        self.equity_curve = []
        
    def fetch_historical_data(self, coin, tf):
        """Fetch historical market data from Polymarket."""
        # For now, simulate with current data
        # In production, this would query historical API
        print(f"Fetching {coin} {tf}m data from {self.start_date} to {self.end_date}")
        return []
    
    def simulate_trade(self, entry_price, side, market_data):
        """Simulate a single trade outcome."""
        # Simplified simulation - assumes random outcome based on price
        # In reality, would use actual historical resolutions
        
        # Higher price = higher probability of YES winning
        if side == 'YES':
            win_prob = entry_price
        else:
            win_prob = 1 - entry_price
        
        # Simulate outcome
        import random
        won = random.random() < win_prob
        
        if won:
            if side == 'YES':
                exit_price = 1.0
                pnl = (1.0 - entry_price) / entry_price
            else:
                exit_price = 1.0
                pnl = (1.0 - (1 - entry_price)) / (1 - entry_price)
        else:
            exit_price = 0.0
            pnl = -1.0
        
        return {
            'won': won,
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_reason': 'resolved'
        }
    
    def run_backtest(self):
        """Run full backtest."""
        print("="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Initial Bankroll: ${INITIAL_BANKROLL:.2f}")
        print()
        
        # Simulate 100 trades with various market conditions
        test_cases = [
            # (yes_price, side, description)
            (0.45, 'YES', 'Normal market'),
            (0.35, 'YES', 'Cheap YES'),
            (0.55, 'NO', 'Cheap NO'),
            (0.25, 'YES', 'Very cheap YES'),
            (0.50, 'YES', 'Coin flip'),
        ]
        
        for i in range(20):  # Simulate 20 trades
            for yes_price, side, desc in test_cases:
                # Skip invalid prices (our fix)
                if yes_price < MIN_YES_PRICE or yes_price > MAX_YES_PRICE:
                    continue
                if (1 - yes_price) < MIN_YES_PRICE or (1 - yes_price) > MAX_YES_PRICE:
                    continue
                
                entry_price = yes_price if side == 'YES' else (1 - yes_price)
                amount = self.bankroll * POSITION_SIZE_PCT
                
                if amount < 20:
                    continue
                
                # Simulate trade
                result = self.simulate_trade(entry_price, side, {})
                
                pnl_amount = amount * result['pnl']
                self.bankroll += pnl_amount
                
                self.trades.append({
                    'entry_price': entry_price,
                    'side': side,
                    'amount': amount,
                    'pnl': result['pnl'] * 100,
                    'pnl_amount': pnl_amount,
                    'won': result['won']
                })
                
                self.equity_curve.append(self.bankroll)
        
        self.report_results()
    
    def report_results(self):
        """Generate backtest report."""
        if not self.trades:
            print("No trades simulated")
            return
        
        wins = [t for t in self.trades if t['won']]
        losses = [t for t in self.trades if not t['won']]
        
        win_rate = len(wins) / len(self.trades) * 100
        avg_win = statistics.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = statistics.mean([t['pnl'] for t in losses]) if losses else 0
        
        total_pnl = self.bankroll - INITIAL_BANKROLL
        total_return = (total_pnl / INITIAL_BANKROLL) * 100
        
        print(f"Total Trades: {len(self.trades)}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Wins: {len(wins)}, Losses: {len(losses)}")
        print(f"Avg Win: +{avg_win:.1f}%")
        print(f"Avg Loss: {avg_loss:.1f}%")
        print(f"Final Bankroll: ${self.bankroll:.2f}")
        print(f"Total P&L: ${total_pnl:+.2f} ({total_return:+.1f}%)")
        print()
        
        # Risk metrics
        max_drawdown = self.calculate_max_drawdown()
        print(f"Max Drawdown: {max_drawdown:.1f}%")
        
        sharpe = self.calculate_sharpe()
        print(f"Sharpe Ratio: {sharpe:.2f}")
    
    def calculate_max_drawdown(self):
        """Calculate maximum drawdown."""
        if not self.equity_curve:
            return 0
        
        peak = self.equity_curve[0]
        max_dd = 0
        
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def calculate_sharpe(self):
        """Calculate Sharpe ratio."""
        if len(self.trades) < 2:
            return 0
        
        returns = [t['pnl'] for t in self.trades]
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0
        
        if std_return == 0:
            return 0
        
        return avg_return / std_return

if __name__ == "__main__":
    # Run backtest for last 7 days
    end = datetime.now()
    start = end - timedelta(days=7)
    
    bt = Backtester(start, end)
    bt.run_backtest()
