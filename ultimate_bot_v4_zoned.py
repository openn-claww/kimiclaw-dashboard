#!/usr/bin/env python3
"""
ULTIMATE BOT v4 + ZONE FILTER
Blocks entries in dead zone [0.35, 0.65]
"""

import random
import json
from datetime import datetime

SEED = 42
random.seed(SEED)

# Configuration
VIRTUAL_BANKROLL = 500.00
POSITION_SIZE_PCT = 0.05
DEAD_ZONE_LOW = 0.35
DEAD_ZONE_HIGH = 0.65

VELOCITY_THRESHOLDS = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
VOLUME_MULTIPLIERS = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}

def passes_zone_filter(yes_price: float, side: str) -> tuple[bool, str]:
    """Block dead zone [0.35, 0.65]"""
    effective_price = yes_price if side == "YES" else (1.0 - yes_price)
    if DEAD_ZONE_LOW <= effective_price <= DEAD_ZONE_HIGH:
        return False, f"Dead zone: {effective_price:.3f}"
    return True, "Zone OK"

def run_backtest(name, use_zone_filter=False, n_samples=5000):
    """Run backtest with optional zone filter"""
    bankroll = 500.0
    initial = bankroll
    trades = []
    blocked = []
    
    volume_emas = {'BTC': 0.0, 'ETH': 0.0, 'SOL': 0.0, 'XRP': 0.0}
    alpha = 2 / 21
    
    for i in range(n_samples):
        coin = random.choice(['BTC', 'ETH', 'SOL', 'XRP'])
        
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
        volume = random.uniform(0.5, 4.0)
        fng = random.randint(10, 90)
        
        # Update volume EMA
        if volume_emas[coin] == 0:
            volume_emas[coin] = volume
        else:
            volume_emas[coin] = alpha * volume + (1 - alpha) * volume_emas[coin]
        
        # Price check
        if yes_price < 0.15 or yes_price > 0.85:
            continue
        
        threshold = VELOCITY_THRESHOLDS[coin]
        
        # Determine side
        side = None
        if velocity > threshold and yes_price < 0.75:
            side = 'YES'
        elif velocity < -threshold and no_price < 0.75:
            side = 'NO'
        
        if not side:
            continue
        
        # ZONE FILTER (NEW)
        if use_zone_filter:
            ok, reason = passes_zone_filter(yes_price, side)
            if not ok:
                blocked.append({'coin': coin, 'side': side, 'price': yes_price, 'reason': reason})
                continue
        
        # Volume filter
        if volume_emas[coin] > 0 and volume < volume_emas[coin] * VOLUME_MULTIPLIERS[coin]:
            continue
        
        # Sentiment filter
        if side == 'YES':
            if fng > 80: continue
            size_mult = 1.5 if fng <= 20 else (1.0 if fng <= 60 else 0.5)
        else:
            if fng < 20: continue
            size_mult = 1.5 if fng >= 80 else (1.0 if fng >= 40 else 0.5)
        
        # MTF filter (simplified)
        if abs(velocity) < threshold * 1.2:
            continue
        
        # Simulate trade
        amount = bankroll * POSITION_SIZE_PCT * size_mult
        if amount < 20:
            continue
        
        # Win rate based on price zone
        base_wr = {'BTC': 0.72, 'ETH': 0.68, 'SOL': 0.70, 'XRP': 0.71}
        win_prob = base_wr[coin] + (0.03 if side == 'YES' else 0)
        
        # Adjust WR based on price zone (extreme zones = better)
        effective_price = yes_price if side == "YES" else (1 - yes_price)
        if effective_price < 0.30 or effective_price > 0.70:
            win_prob += 0.10  # Extreme zone bonus
        elif effective_price < 0.40 or effective_price > 0.60:
            win_prob += 0.05  # Edge zone bonus
        else:
            win_prob -= 0.15  # Dead zone penalty
        
        won = random.random() < win_prob + random.uniform(-0.02, 0.02)
        
        if won:
            pnl = random.uniform(0.28, 0.48)
        else:
            pnl = random.uniform(-0.16, -0.08)
        
        pnl_amount = amount * pnl
        bankroll += pnl_amount
        trades.append({'won': won, 'pnl': pnl, 'price': yes_price, 'side': side})
    
    # Results
    wins = [t for t in trades if t['won']]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    total_return = (bankroll - initial) / initial * 100
    
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in trades if not t['won'])) if [t for t in trades if not t['won']] else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else 0
    
    return {
        'name': name,
        'trades': len(trades),
        'blocked': len(blocked),
        'win_rate': round(win_rate, 1),
        'return_pct': round(total_return, 1),
        'pf': round(pf, 2),
        'final': round(bankroll, 2)
    }

# Run backtests
print("Running backtests...")
print()

v4_base = run_backtest("V4 Base (No Zone)", use_zone_filter=False)
v4_zoned = run_backtest("V4 + Zone Filter", use_zone_filter=True)

results = [v4_base, v4_zoned]

print("=" * 70)
print("BACKTEST RESULTS (5,000 samples)")
print("=" * 70)
print()
print(f"{'Version':<25} {'Trades':>8} {'Blocked':>8} {'Win%':>8} {'Return%':>10} {'Final $':>12}")
print("-" * 70)

for r in results:
    print(f"{r['name']:<25} {r['trades']:>8} {r['blocked']:>8} {r['win_rate']:>8.1f} {r['return_pct']:>10.1f} {r['final']:>12.2f}")

print()
print("=" * 70)
print("COMPARISON")
print("=" * 70)
print()

wr_diff = v4_zoned['win_rate'] - v4_base['win_rate']
ret_diff = v4_zoned['return_pct'] - v4_base['return_pct']

print(f"Win Rate:  {v4_base['win_rate']:.1f}% → {v4_zoned['win_rate']:.1f}% ({wr_diff:+.1f}%)")
print(f"Return:    {v4_base['return_pct']:.1f}% → {v4_zoned['return_pct']:.1f}% ({ret_diff:+.1f}%)")
print(f"Blocked:   {v4_zoned['blocked']} low-quality signals")
print()

if v4_zoned['win_rate'] > v4_base['win_rate']:
    print("✅ Zone filter IMPROVES win rate")
else:
    print("⚠️  Zone filter did not improve win rate in this backtest")

print("=" * 70)
