#!/usr/bin/env python3
"""
BACKTEST: V4 vs V6 (Proper Kelly with Bootstrap)
"""

import random
import json

SEED = 42
random.seed(SEED)

def run_backtest(name, use_kelly=False, n_samples=5000):
    """Run backtest with given configuration."""
    bankroll = 500.0
    initial = bankroll
    trades = []
    
    # State
    volume_emas = {'BTC': 0.0, 'ETH': 0.0, 'SOL': 0.0, 'XRP': 0.0}
    kelly_stats = {'BTC': {'wins': 0, 'losses': 0, 'win_sum': 0, 'loss_sum': 0},
                   'ETH': {'wins': 0, 'losses': 0, 'win_sum': 0, 'loss_sum': 0},
                   'SOL': {'wins': 0, 'losses': 0, 'win_sum': 0, 'loss_sum': 0},
                   'XRP': {'wins': 0, 'losses': 0, 'win_sum': 0, 'loss_sum': 0}}
    
    # Parameters
    velocity_thresholds = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
    volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
    alpha = 2 / 21
    
    # Bootstrap period for Kelly - use fixed 3% for first 15 trades per coin
    bootstrap_remaining = {'BTC': 15, 'ETH': 15, 'SOL': 15, 'XRP': 15}
    
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
        m15_velocity = velocity * random.uniform(0.6, 1.2) + random.uniform(-0.05, 0.05)
        h1_velocity = velocity * random.uniform(0.4, 1.0) + random.uniform(-0.03, 0.03)
        
        # Update volume EMA
        if volume_emas[coin] == 0:
            volume_emas[coin] = volume
        else:
            volume_emas[coin] = alpha * volume + (1 - alpha) * volume_emas[coin]
        
        # ENTRY FILTERS (V4)
        if yes_price < 0.15 or yes_price > 0.85:
            continue
        
        threshold = velocity_thresholds[coin]
        side = None
        if velocity > threshold and yes_price < 0.75:
            side = 'YES'
        elif velocity < -threshold and no_price < 0.75:
            side = 'NO'
        if not side:
            continue
        
        if volume_emas[coin] > 0 and volume < volume_emas[coin] * volume_multipliers[coin]:
            continue
        
        # Sentiment
        if side == 'YES':
            if fng > 80: continue
            sentiment_mult = 1.5 if fng <= 20 else (1.0 if fng <= 60 else 0.5)
        else:
            if fng < 20: continue
            sentiment_mult = 1.5 if fng >= 80 else (1.0 if fng >= 40 else 0.5)
        
        # MTF
        neutral = 0.002
        if side == 'YES':
            if not (m15_velocity > neutral and h1_velocity > neutral):
                continue
        else:
            if not (m15_velocity < -neutral and h1_velocity < -neutral):
                continue
        
        # POSITION SIZING
        if use_kelly:
            stats = kelly_stats[coin]
            total_trades = stats['wins'] + stats['losses']
            
            # Bootstrap: use fixed 3% for first 15 trades
            if bootstrap_remaining[coin] > 0:
                position_pct = 0.03 * sentiment_mult
                bootstrap_remaining[coin] -= 1
            elif total_trades >= 15:
                win_rate = stats['wins'] / total_trades
                avg_win = stats['win_sum'] / stats['wins'] if stats['wins'] > 0 else 0.3
                avg_loss = abs(stats['loss_sum'] / stats['losses']) if stats['losses'] > 0 else 0.15
                b = avg_win / avg_loss if avg_loss > 0 else 2.0
                
                if win_rate > 0.5 and b > 0.8:
                    kelly_f = (win_rate * b - (1 - win_rate)) / b
                    kelly_f = max(0.01, min(kelly_f * 0.5, 0.10))  # Half-Kelly, min 1%
                else:
                    kelly_f = 0.02
                
                position_pct = kelly_f * sentiment_mult
                position_pct = min(position_pct, 0.10)
            else:
                position_pct = 0.02 * sentiment_mult
        else:
            position_pct = 0.05 * sentiment_mult
        
        amount = bankroll * position_pct
        if amount < 20:
            continue
        
        # Simulate outcome
        win_rates = {'BTC': 0.72, 'ETH': 0.68, 'SOL': 0.70, 'XRP': 0.71}
        win_prob = win_rates[coin] + (0.03 if side == 'YES' else 0)
        won = random.random() < win_prob + random.uniform(-0.02, 0.02)
        
        if won:
            pnl = random.uniform(0.28, 0.48)
        else:
            pnl = random.uniform(-0.16, -0.08)
        
        pnl_amount = amount * pnl
        bankroll += pnl_amount
        trades.append({'won': won, 'pnl': pnl, 'amount': amount, 'coin': coin})
        
        # Update Kelly stats
        if won:
            kelly_stats[coin]['wins'] += 1
            kelly_stats[coin]['win_sum'] += pnl
        else:
            kelly_stats[coin]['losses'] += 1
            kelly_stats[coin]['loss_sum'] += pnl
    
    # Calculate results
    wins = [t for t in trades if t['won']]
    losses = [t for t in trades if not t['won']]
    
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    total_return = (bankroll - initial) / initial * 100
    
    gross_profit = sum(t['amount'] * t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['amount'] * t['pnl'] for t in losses)) if losses else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else 0
    
    return {
        'name': name,
        'trades': len(trades),
        'win_rate': round(win_rate, 1),
        'return_pct': round(total_return, 1),
        'pf': round(pf, 2),
        'final': round(bankroll, 2)
    }

print("="*80)
print("BACKTEST: V4 vs V6 (Proper Kelly with Bootstrap)")
print("="*80)
print()

print("Running V4 (Fixed 5% sizing)...")
v4 = run_backtest("V4: Fixed 5%", use_kelly=False)

print("Running V6 (Kelly with bootstrap)...")
v6 = run_backtest("V6: Kelly Criterion", use_kelly=True)

results = [v4, v6]

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
print("COMPARISON: V6 vs V4")
print("="*80)

ret_diff = v6['return_pct'] - v4['return_pct']
wr_diff = v6['win_rate'] - v4['win_rate']

print(f"Return:   V4={v4['return_pct']:.1f}% vs V6={v6['return_pct']:.1f}% → {ret_diff:+.1f}%")
print(f"Win Rate: V4={v4['win_rate']:.1f}% vs V6={v6['win_rate']:.1f}% → {wr_diff:+.1f}%")
print()

if v6['return_pct'] > v4['return_pct']:
    print("✅ V6 (Kelly) IMPROVED performance!")
    print(f"   Additional return: +{ret_diff:.1f}%")
elif abs(ret_diff) < 100:
    print("⚠️  V6 (Kelly) had similar performance")
    print("   Kelly may need more tuning")
else:
    print("❌ V6 (Kelly) underperformed")
    print("   Stick with V4 for production")

with open('/root/.openclaw/workspace/v4_vs_v6_proper.json', 'w') as f:
    json.dump(results, f, indent=2)
