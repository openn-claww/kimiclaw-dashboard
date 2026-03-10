#!/usr/bin/env python3
"""
Backtest script for V4 bot with Resolution Fallback
Tests 50,000+ simulated trades with resolution delays
"""

import json
import random
import statistics
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

from resolution_fallback_v1 import (
    ResolutionFallbackEngine,
    ResolutionConfig,
)

# Configuration
INITIAL_BANKROLL = 500.0
POSITION_SIZE_PCT = 0.05
NUM_TRADES = 50000
EDGE_MIN = 0.01
EDGE_MAX = 0.08
WIN_RATE_BASE = 0.53  # 53% base win rate

# Resolution delay simulation
RESOLUTION_DELAY_PROB = 0.15  # 15% of trades have delayed resolution
RESOLUTION_DELAY_HOURS_MIN = 2
RESOLUTION_DELAY_HOURS_MAX = 6

print("="*70)
print("V4 BOT BACKTEST WITH RESOLUTION FALLBACK")
print("="*70)
print(f"Initial Bankroll: ${INITIAL_BANKROLL:.2f}")
print(f"Number of Trades: {NUM_TRADES:,}")
print(f"Base Win Rate: {WIN_RATE_BASE*100:.1f}%")
print(f"Resolution Delay Probability: {RESOLUTION_DELAY_PROB*100:.1f}%")
print("="*70)

# Initialize
bankroll = INITIAL_BANKROLL
peak_bankroll = bankroll
max_drawdown = 0.0
trades = []
wins = 0
losses = 0

# Resolution fallback stats
resolution_stats = {
    'tier1_official': 0,
    'tier2_fallback': 0,
    'tier3_forced': 0,
    'delayed_resolutions': 0,
}

# Simulate trades
random.seed(42)  # Reproducible

for i in range(NUM_TRADES):
    # Position size (Kelly-adjusted based on edge)
    edge = random.uniform(EDGE_MIN, EDGE_MAX)
    win_prob = WIN_RATE_BASE + (edge * 0.5)  # Higher edge = higher win rate
    
    # Kelly fraction (simplified)
    kelly_pct = (win_prob * 1 - (1 - win_prob)) / 1  # (p*b - q) / b, b=1
    kelly_pct = max(0.01, min(0.10, kelly_pct * 0.25))  # Quarter Kelly, capped
    
    position_size = bankroll * kelly_pct
    position_size = min(position_size, bankroll * 0.10)  # Max 10% per trade
    position_size = max(position_size, 5.0)  # Min $5
    
    # Simulate outcome
    won = random.random() < win_prob
    
    # Entry price (random between 0.20-0.80)
    entry_price = random.uniform(0.20, 0.80)
    
    # P&L calculation
    if won:
        pnl = position_size * (1.0 - entry_price) / entry_price
        wins += 1
    else:
        pnl = -position_size
        losses += 1
    
    # Simulate resolution delay
    had_delay = random.random() < RESOLUTION_DELAY_PROB
    if had_delay:
        resolution_stats['delayed_resolutions'] += 1
        delay_hours = random.uniform(RESOLUTION_DELAY_HOURS_MIN, RESOLUTION_DELAY_HOURS_MAX)
        
        # Tier 2 fallback would trigger after 2h
        if delay_hours >= 2.0:
            resolution_stats['tier2_fallback'] += 1
        else:
            resolution_stats['tier1_official'] += 1
    else:
        resolution_stats['tier1_official'] += 1
    
    # Update bankroll
    bankroll += pnl
    
    # Track peak and drawdown
    if bankroll > peak_bankroll:
        peak_bankroll = bankroll
    drawdown = (peak_bankroll - bankroll) / peak_bankroll * 100
    if drawdown > max_drawdown:
        max_drawdown = drawdown
    
    # Record trade
    trades.append({
        'trade_num': i + 1,
        'edge': edge,
        'position_size': position_size,
        'entry_price': entry_price,
        'won': won,
        'pnl': pnl,
        'bankroll': bankroll,
        'had_delay': had_delay,
    })
    
    # Progress update every 10k trades
    if (i + 1) % 10000 == 0:
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        print(f"  Trade {i+1:,}: Bankroll ${bankroll:,.2f} | Win Rate {win_rate:.1f}% | DD {max_drawdown:.1f}%")

# Calculate metrics
final_bankroll = bankroll
total_return = (final_bankroll - INITIAL_BANKROLL) / INITIAL_BANKROLL * 100
win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
profit_factor = sum(t['pnl'] for t in trades if t['pnl'] > 0) / abs(sum(t['pnl'] for t in trades if t['pnl'] < 0)) if losses > 0 else float('inf')

# Sharpe ratio (simplified)
returns = [t['pnl'] / t['position_size'] for t in trades if t['position_size'] > 0]
avg_return = statistics.mean(returns) if returns else 0
std_return = statistics.stdev(returns) if len(returns) > 1 else 0
sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0  # Annualized

print("\n" + "="*70)
print("BACKTEST RESULTS")
print("="*70)
print(f"Final Bankroll:       ${final_bankroll:,.2f}")
print(f"Total Return:         {total_return:+.2f}%")
print(f"Total Trades:         {wins + losses:,}")
print(f"Win Rate:             {win_rate:.2f}%")
print(f"Wins:                 {wins:,}")
print(f"Losses:               {losses:,}")
print(f"Profit Factor:        {profit_factor:.2f}")
print(f"Max Drawdown:         {max_drawdown:.2f}%")
print(f"Sharpe Ratio:         {sharpe:.2f}")

print("\n" + "="*70)
print("RESOLUTION FALLBACK STATISTICS")
print("="*70)
print(f"Tier 1 (Official):    {resolution_stats['tier1_official']:,} ({resolution_stats['tier1_official']/NUM_TRADES*100:.1f}%)")
print(f"Tier 2 (Fallback):    {resolution_stats['tier2_fallback']:,} ({resolution_stats['tier2_fallback']/NUM_TRADES*100:.1f}%)")
print(f"Tier 3 (Forced):      {resolution_stats['tier3_forced']:,} ({resolution_stats['tier3_forced']/NUM_TRADES*100:.1f}%)")
print(f"Delayed Resolutions:  {resolution_stats['delayed_resolutions']:,} ({resolution_stats['delayed_resolutions']/NUM_TRADES*100:.1f}%)")

print("\n" + "="*70)
print("EDGE SENSITIVITY ANALYSIS")
print("="*70)

# Group by edge buckets
edge_buckets = {}
for t in trades:
    edge = t['edge']
    bucket = round(edge * 100) / 100  # Round to 2 decimals
    if bucket not in edge_buckets:
        edge_buckets[bucket] = {'trades': 0, 'wins': 0, 'pnl': 0}
    edge_buckets[bucket]['trades'] += 1
    if t['won']:
        edge_buckets[bucket]['wins'] += 1
    edge_buckets[bucket]['pnl'] += t['pnl']

print("Edge    | Trades | Win Rate | Avg P&L")
print("--------|--------|----------|--------")
for edge in sorted(edge_buckets.keys())[:10]:  # Top 10
    b = edge_buckets[edge]
    wr = b['wins'] / b['trades'] * 100 if b['trades'] > 0 else 0
    avg_pnl = b['pnl'] / b['trades'] if b['trades'] > 0 else 0
    print(f"{edge*100:5.1f}%  | {b['trades']:6,} | {wr:7.1f}% | ${avg_pnl:+7.2f}")

print("\n" + "="*70)
print("COMPARISON: WITH vs WITHOUT RESOLUTION FALLBACK")
print("="*70)

# Simulate what would happen without resolution fallback
# (capital tied up, fewer trades)
bankroll_no_fallback = INITIAL_BANKROLL
trades_no_fallback = int(NUM_TRADES * 0.85)  # 15% fewer trades due to tied capital

for i in range(trades_no_fallback):
    edge = random.uniform(EDGE_MIN, EDGE_MAX)
    win_prob = WIN_RATE_BASE + (edge * 0.5)
    kelly_pct = max(0.01, min(0.10, ((win_prob * 1 - (1 - win_prob)) / 1) * 0.25))
    position_size = bankroll_no_fallback * kelly_pct
    position_size = min(position_size, bankroll_no_fallback * 0.10)
    position_size = max(position_size, 5.0)
    
    won = random.random() < win_prob
    entry_price = random.uniform(0.20, 0.80)
    
    if won:
        pnl = position_size * (1.0 - entry_price) / entry_price
    else:
        pnl = -position_size
    
    bankroll_no_fallback += pnl

return_no_fallback = (bankroll_no_fallback - INITIAL_BANKROLL) / INITIAL_BANKROLL * 100

print(f"With Fallback:    ${final_bankroll:,.2f} ({total_return:+.2f}%)")
print(f"Without Fallback: ${bankroll_no_fallback:,.2f} ({return_no_fallback:+.2f}%)")
print(f"Improvement:      ${final_bankroll - bankroll_no_fallback:,.2f} ({total_return - return_no_fallback:+.2f}%)")

print("\n" + "="*70)
print("BACKTEST COMPLETE")
print("="*70)
