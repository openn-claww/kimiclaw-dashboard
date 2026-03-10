#!/usr/bin/env python3
"""
Realistic backtest for V4 bot with Resolution Fallback
Uses fixed position sizes and realistic market conditions
"""

import json
import random
import statistics
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

# Configuration - MORE REALISTIC
INITIAL_BANKROLL = 500.0
POSITION_SIZE = 25.0  # Fixed $25 per trade (5% of $500)
NUM_TRADES = 10000    # Fewer trades for realism
WIN_RATE_BASE = 0.535  # 53.5% win rate (realistic for edge)
EDGE_MEAN = 0.03       # 3% average edge
EDGE_STD = 0.02        # 2% std dev

# Resolution delay simulation
RESOLUTION_DELAY_PROB = 0.20  # 20% of trades have delayed resolution
RESOLUTION_DELAY_HOURS = 4    # Average 4h delay

# Market conditions
FEE_PCT = 0.002  # 0.2% fee per trade (Polymarket spread)
SLIPPAGE_PCT = 0.001  # 0.1% slippage

print("="*70)
print("V4 BOT REALISTIC BACKTEST WITH RESOLUTION FALLBACK")
print("="*70)
print(f"Initial Bankroll: ${INITIAL_BANKROLL:.2f}")
print(f"Position Size: ${POSITION_SIZE:.2f} per trade")
print(f"Number of Trades: {NUM_TRADES:,}")
print(f"Base Win Rate: {WIN_RATE_BASE*100:.1f}%")
print(f"Avg Edge: {EDGE_MEAN*100:.1f}%")
print(f"Fees: {FEE_PCT*100:.2f}% per trade")
print("="*70)

# Initialize
bankroll = INITIAL_BANKROLL
peak_bankroll = bankroll
max_drawdown = 0.0
trades = []
wins = 0
losses = 0
consecutive_losses = 0
max_consecutive_losses = 0

# Resolution fallback stats
resolution_stats = {
    'tier1_official': 0,
    'tier2_fallback': 0,
    'tier3_forced': 0,
    'delayed_resolutions': 0,
}

# Simulate trades
random.seed(42)

for i in range(NUM_TRADES):
    # Check if we have enough bankroll
    if bankroll < POSITION_SIZE:
        print(f"  Trade {i+1}: BANKRUPT - Insufficient funds")
        break
    
    # Calculate edge for this trade
    edge = random.gauss(EDGE_MEAN, EDGE_STD)
    edge = max(0.005, min(0.10, edge))  # Clamp between 0.5% and 10%
    
    # Win probability based on edge
    win_prob = 0.50 + edge
    
    # Entry price (realistic distribution)
    entry_price = random.uniform(0.25, 0.75)
    
    # Simulate outcome
    won = random.random() < win_prob
    
    # Calculate gross P&L
    if won:
        gross_pnl = POSITION_SIZE * ((1.0 - entry_price) / entry_price)
    else:
        gross_pnl = -POSITION_SIZE
    
    # Subtract fees
    fee = POSITION_SIZE * FEE_PCT
    net_pnl = gross_pnl - fee
    
    # Update stats
    if won:
        wins += 1
        consecutive_losses = 0
    else:
        losses += 1
        consecutive_losses += 1
        if consecutive_losses > max_consecutive_losses:
            max_consecutive_losses = consecutive_losses
    
    # Simulate resolution delay
    had_delay = random.random() < RESOLUTION_DELAY_PROB
    if had_delay:
        resolution_stats['delayed_resolutions'] += 1
        # Tier 2 fallback triggers after 2h
        resolution_stats['tier2_fallback'] += 1
    else:
        resolution_stats['tier1_official'] += 1
    
    # Update bankroll
    bankroll += net_pnl
    
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
        'entry_price': entry_price,
        'won': won,
        'gross_pnl': gross_pnl,
        'net_pnl': net_pnl,
        'bankroll': bankroll,
        'had_delay': had_delay,
    })
    
    # Progress update every 2k trades
    if (i + 1) % 2000 == 0:
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        print(f"  Trade {i+1:,}: Bankroll ${bankroll:,.2f} | WR {win_rate:.1f}% | DD {max_drawdown:.1f}%")

# Calculate final metrics
final_bankroll = bankroll
total_return = (final_bankroll - INITIAL_BANKROLL) / INITIAL_BANKROLL * 100
total_trades = wins + losses
win_rate = wins / total_trades * 100 if total_trades > 0 else 0

# Profit factor
gross_profit = sum(t['gross_pnl'] for t in trades if t['gross_pnl'] > 0)
gross_loss = abs(sum(t['gross_pnl'] for t in trades if t['gross_pnl'] < 0))
profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

# Sharpe ratio (daily returns)
daily_returns = []
for i in range(0, len(trades), 100):  # Approximate 100 trades per day
    day_trades = trades[i:i+100]
    if day_trades:
        day_pnl = sum(t['net_pnl'] for t in day_trades)
        day_return = day_pnl / INITIAL_BANKROLL
        daily_returns.append(day_return)

if len(daily_returns) > 1:
    avg_daily_return = statistics.mean(daily_returns)
    std_daily_return = statistics.stdev(daily_returns)
    sharpe = (avg_daily_return / std_daily_return) * (365 ** 0.5) if std_daily_return > 0 else 0
else:
    sharpe = 0

# Expectancy
avg_win = gross_profit / wins if wins > 0 else 0
avg_loss = gross_loss / losses if losses > 0 else 0
expectancy = (win_rate/100 * avg_win) - ((1-win_rate/100) * avg_loss)

print("\n" + "="*70)
print("BACKTEST RESULTS")
print("="*70)
print(f"Final Bankroll:       ${final_bankroll:,.2f}")
print(f"Total Return:         {total_return:+.2f}%")
print(f"Total Trades:         {total_trades:,}")
print(f"Win Rate:             {win_rate:.2f}%")
print(f"Wins:                 {wins:,}")
print(f"Losses:               {losses:,}")
print(f"Profit Factor:        {profit_factor:.2f}")
print(f"Expectancy:           ${expectancy:+.2f} per trade")
print(f"Max Drawdown:         {max_drawdown:.2f}%")
print(f"Max Consec. Losses:   {max_consecutive_losses}")
print(f"Sharpe Ratio:         {sharpe:.2f}")

print("\n" + "="*70)
print("RESOLUTION FALLBACK STATISTICS")
print("="*70)
total_resolved = resolution_stats['tier1_official'] + resolution_stats['tier2_fallback']
print(f"Tier 1 (Official):    {resolution_stats['tier1_official']:,} ({resolution_stats['tier1_official']/total_trades*100:.1f}%)")
print(f"Tier 2 (Fallback):    {resolution_stats['tier2_fallback']:,} ({resolution_stats['tier2_fallback']/total_trades*100:.1f}%)")
print(f"Tier 3 (Forced):      {resolution_stats['tier3_forced']:,} ({resolution_stats['tier3_forced']/total_trades*100:.1f}%)")
print(f"Delayed Resolutions:  {resolution_stats['delayed_resolutions']:,} ({resolution_stats['delayed_resolutions']/total_trades*100:.1f}%)")

# Calculate capital efficiency gain
delayed_pnl = sum(t['net_pnl'] for t in trades if t['had_delay'])
print(f"\nCapital Efficiency:")
print(f"  Delayed trades P&L: ${delayed_pnl:,.2f}")
print(f"  Without fallback, this capital would be tied up")
print(f"  Fallback unlocks capital for ~{resolution_stats['tier2_fallback'] * 2} hours of additional trading")

print("\n" + "="*70)
print("EDGE ANALYSIS")
print("="*70)

# Group by edge buckets
edge_buckets = {}
for t in trades:
    edge = round(t['edge'] * 100) / 100
    if edge not in edge_buckets:
        edge_buckets[edge] = {'trades': 0, 'wins': 0, 'pnl': 0}
    edge_buckets[edge]['trades'] += 1
    if t['won']:
        edge_buckets[edge]['wins'] += 1
    edge_buckets[edge]['pnl'] += t['net_pnl']

print("Edge    | Trades | Win Rate | Total P&L")
print("--------|--------|----------|------------")
for edge in sorted(edge_buckets.keys()):
    b = edge_buckets[edge]
    if b['trades'] >= 50:  # Only show buckets with enough samples
        wr = b['wins'] / b['trades'] * 100
        print(f"{edge*100:5.1f}%  | {b['trades']:6,} | {wr:7.1f}% | ${b['pnl']:>+10,.2f}")

print("\n" + "="*70)
print("MONTHLY PROJECTION (based on backtest)")
print("="*70)
trades_per_month = 300  # ~10 trades/day
monthly_expectancy = expectancy * trades_per_month
monthly_return = (monthly_expectancy / INITIAL_BANKROLL) * 100
annual_return = monthly_return * 12

print(f"Trades/month:         {trades_per_month}")
print(f"Expected P&L/month:   ${monthly_expectancy:,.2f}")
print(f"Expected return/month: {monthly_return:+.2f}%")
print(f"Projected annual return: {annual_return:+.2f}%")

print("\n" + "="*70)
print("BACKTEST COMPLETE")
print("="*70)

# Save results
results = {
    'timestamp': datetime.now().isoformat(),
    'initial_bankroll': INITIAL_BANKROLL,
    'final_bankroll': final_bankroll,
    'total_return_pct': total_return,
    'total_trades': total_trades,
    'win_rate': win_rate,
    'profit_factor': profit_factor,
    'max_drawdown': max_drawdown,
    'sharpe_ratio': sharpe,
    'resolution_stats': resolution_stats,
    'monthly_projection': {
        'trades': trades_per_month,
        'expected_pnl': monthly_expectancy,
        'expected_return_pct': monthly_return,
    }
}

with open('/root/.openclaw/workspace/backtest_results_resolution.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\nResults saved to backtest_results_resolution.json")
