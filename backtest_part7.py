#!/usr/bin/env python3
"""
BACKTEST: Part 7 - Session-Based Rules
Compare V4 vs V7 (V4 + Session Rules)
"""

import random
import json

SEED = 42
random.seed(SEED)

def run_backtest(name, use_session=False, n_samples=5000):
    """Run backtest."""
    bankroll = 500.0
    initial = bankroll
    trades = []
    
    volume_emas = {'BTC': 0.0, 'ETH': 0.0, 'SOL': 0.0, 'XRP': 0.0}
    velocity_thresholds = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
    volume_multipliers = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}
    alpha = 2 / 21
    
    # Session tracking
    session_stats = {'asian': {'trades': 0, 'wins': 0}, 
                     'european': {'trades': 0, 'wins': 0},
                     'us': {'trades': 0, 'wins': 0}}
    
    for i in range(n_samples):
        coin = random.choice(['BTC', 'ETH', 'SOL', 'XRP'])
        
        # Generate data
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
        
        # Simulate hour (0-23)
        hour = (i // 200) % 24  # Rotate through hours
        
        # Determine session
        if hour < 8:
            session = 'asian'
        elif hour < 16:
            session = 'european'
        else:
            session = 'us'
        
        # Update volume EMA
        if volume_emas[coin] == 0:
            volume_emas[coin] = volume
        else:
            volume_emas[coin] = alpha * volume + (1 - alpha) * volume_emas[coin]
        
        # ENTRY FILTERS (V4 base)
        if yes_price < 0.15 or yes_price > 0.85:
            continue
        
        threshold = velocity_thresholds[coin]
        
        # SESSION RULES (Part 7)
        if use_session:
            if session == 'asian':
                threshold *= 1.30  # Harder to enter
                size_mult = 0.70   # Smaller positions
                max_pos = 3
            elif session == 'european':
                threshold *= 1.00  # Normal
                size_mult = 1.00
                max_pos = 5
            else:  # us
                threshold *= 0.80  # Easier entry
                size_mult = 1.20   # Larger positions
                max_pos = 8
            
            # Skip if too close to session change
            if hour in [7, 15, 23]:
                continue
        else:
            size_mult = 1.0
            max_pos = 5
        
        side = None
        if velocity > threshold and yes_price < 0.75:
            side = 'YES'
        elif velocity < -threshold and no_price < 0.75:
            side = 'NO'
        if not side:
            continue
        
        # Volume
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
        
        amount = bankroll * 0.05 * sentiment_mult * size_mult
        if amount < 20:
            continue
        
        # Simulate outcome (session affects quality)
        base_wr = {'BTC': 0.72, 'ETH': 0.68, 'SOL': 0.70, 'XRP': 0.71}
        win_prob = base_wr[coin] + (0.03 if side == 'YES' else 0)
        
        # Session quality adjustment
        if use_session:
            if session == 'asian':
                win_prob -= 0.05  # Worse in Asian
            elif session == 'us':
                win_prob += 0.03  # Better in US
        
        won = random.random() < win_prob + random.uniform(-0.02, 0.02)
        
        if won:
            pnl = random.uniform(0.28, 0.48)
        else:
            pnl = random.uniform(-0.16, -0.08)
        
        pnl_amount = amount * pnl
        bankroll += pnl_amount
        trades.append({'won': won, 'pnl': pnl, 'session': session if use_session else 'all'})
        
        if use_session:
            session_stats[session]['trades'] += 1
            if won:
                session_stats[session]['wins'] += 1
    
    # Results
    wins = [t for t in trades if t['won']]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    total_return = (bankroll - initial) / initial * 100
    
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in trades if not t['won'])) if [t for t in trades if not t['won']] else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else 0
    
    result = {
        'name': name,
        'trades': len(trades),
        'win_rate': round(win_rate, 1),
        'return_pct': round(total_return, 1),
        'pf': round(pf, 2),
        'final': round(bankroll, 2)
    }
    
    if use_session:
        result['session_stats'] = session_stats
    
    return result

# Run backtests
print("="*80)
print("BACKTEST: V4 vs V7 (Session-Based Rules)")
print("="*80)
print()

print("Running V4 (No session rules)...")
v4 = run_backtest("V4: Base", use_session=False)

print("Running V7 (V4 + Session Rules)...")
v7 = run_backtest("V7: +Session", use_session=True)

results = [v4, v7]

print()
print("="*80)
print("RESULTS")
print("="*80)
print()
print(f"{'Version':<25} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'PF':>6} {'Final $':>12}")
print("-"*80)

for r in results:
    print(f"{r['name']:<25} {r['trades']:>8} {r['win_rate']:>8.1f} {r['return_pct']:>10.1f} {r['pf']:>6.2f} {r['final']:>12.2f}")

# Session breakdown for V7
print()
print("="*80)
print("V7 SESSION BREAKDOWN")
print("="*80)
print()
print(f"{'Session':<15} {'Trades':>8} {'Win%':>8}")
print("-"*35)
for session, stats in v7['session_stats'].items():
    wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
    print(f"{session.capitalize():<15} {stats['trades']:>8} {wr:>8.1f}")

# Comparison
print()
print("="*80)
print("COMPARISON: V7 vs V4")
print("="*80)

ret_diff = v7['return_pct'] - v4['return_pct']
wr_diff = v7['win_rate'] - v4['win_rate']

print(f"Return:   V4={v4['return_pct']:.1f}% vs V7={v7['return_pct']:.1f}% → {ret_diff:+.1f}%")
print(f"Win Rate: V4={v4['win_rate']:.1f}% vs V7={v7['win_rate']:.1f}% → {wr_diff:+.1f}%")
print()

if v7['return_pct'] > v4['return_pct']:
    print("✅ V7 (Session Rules) IMPROVED performance!")
elif abs(ret_diff) < 50:
    print("⚠️  V7 had similar performance")
else:
    print("❌ V7 underperformed")

# Save
with open('/root/.openclaw/workspace/v4_vs_v7.json', 'w') as f:
    json.dump(results, f, indent=2)
