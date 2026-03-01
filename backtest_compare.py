import random
import json
import statistics
from datetime import datetime
from collections import defaultdict

# Seed for reproducibility
SEED = 42
random.seed(SEED)

# ============================================
# CONFIGURATION (shared)
# ============================================
VIRTUAL_BANKROLL = 500.00
POSITION_SIZE_PCT = 0.05
DEAD_ZONE_LOW = 0.35
DEAD_ZONE_HIGH = 0.65

VELOCITY_THRESHOLDS = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}
VOLUME_MULTIPLIERS = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.8}

COINS = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES = [5, 15]

# ============================================
# SIMULATE THE $195 WINNING TRADE
# ============================================
print("=" * 60)
print("SIMULATING THE $195 WINNING TRADE")
print("=" * 60)
print()
print("Trade Details:")
print("  Market: ETH 15m")
print("  Side: YES")
print("  Entry Price: 0.025")
print("  Amount: $5.00")
print("  Outcome: WIN (+3900%)")
print()

# Production bot check
print("Production Bot (v4_production):")
prod_price_ok = 0.025 >= 0.15 and 0.025 <= 0.85  # Production price bounds
print(f"  Price check (0.15-0.85): {'PASS' if prod_price_ok else 'FAIL'}")
print(f"  Dead zone check: N/A (no zone filter)")
print(f"  Result: {'WOULD TAKE TRADE' if prod_price_ok else 'BLOCKED'}")
print()

# Zoned bot check
print("Zoned Bot (v4_zoned):")
zone_price_ok = 0.025 >= 0.15 and 0.025 <= 0.85
in_dead_zone = 0.35 <= 0.025 <= 0.65
print(f"  Price check (0.15-0.85): {'PASS' if zone_price_ok else 'FAIL'}")
print(f"  Dead zone [0.35-0.65]: {'BLOCKED' if in_dead_zone else 'PASS (outside zone)'}")
print(f"  Result: {'WOULD TAKE TRADE' if (zone_price_ok and not in_dead_zone) else 'BLOCKED'}")
print()

print("=" * 60)
print("BACKTEST RESULTS (50,000 potential trades)")
print("=" * 60)
print()

def run_backtest(name, use_zone_filter=False, n_samples=50000):
    """Run comprehensive backtest"""
    bankroll = 500.0
    initial = bankroll
    trades = []
    blocked_by_zone = []
    blocked_by_price = []
    blocked_by_volume = []
    blocked_by_sentiment = []
    
    volume_emas = {coin: 0.0 for coin in COINS}
    alpha = 2 / 21
    
    wins = 0
    losses = 0
    
    for i in range(n_samples):
        coin = random.choice(COINS)
        
        # Generate realistic market data based on coin characteristics
        if coin == 'SOL':
            yes_price = random.uniform(0.20, 0.70)
            velocity = random.uniform(-0.60, 0.60)
        elif coin == 'XRP':
            yes_price = random.uniform(0.25, 0.68)
            velocity = random.uniform(-0.30, 0.30)
        elif coin == 'BTC':
            yes_price = random.uniform(0.28, 0.62)
            velocity = random.uniform(-0.35, 0.35)
        else:  # ETH
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
        
        # Price bounds check (both versions)
        if yes_price < 0.15 or yes_price > 0.85:
            blocked_by_price.append({'coin': coin, 'price': yes_price})
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
        
        # ZONE FILTER (Zoned version only)
        if use_zone_filter:
            effective_price = yes_price if side == "YES" else (1.0 - yes_price)
            if DEAD_ZONE_LOW <= effective_price <= DEAD_ZONE_HIGH:
                blocked_by_zone.append({'coin': coin, 'side': side, 'price': yes_price})
                continue
        
        # Volume filter (both)
        if volume_emas[coin] > 0 and volume < volume_emas[coin] * VOLUME_MULTIPLIERS[coin]:
            blocked_by_volume.append({'coin': coin})
            continue
        
        # Sentiment filter (both)
        if side == 'YES':
            if fng > 80:
                blocked_by_sentiment.append({'coin': coin, 'reason': 'fng>80'})
                continue
            size_mult = 1.5 if fng <= 20 else (1.0 if fng <= 60 else 0.5)
        else:
            if fng < 20:
                blocked_by_sentiment.append({'coin': coin, 'reason': 'fng<20'})
                continue
            size_mult = 1.5 if fng >= 80 else (1.0 if fng >= 40 else 0.5)
        
        # Execute trade
        position_size = bankroll * POSITION_SIZE_PCT * size_mult
        
        # Simulate outcome (realistic win rate based on edge)
        # Outside dead zone = better edge
        effective_price = yes_price if side == "YES" else (1.0 - yes_price)
        edge = abs(0.5 - effective_price) * 2  # 0 to 1
        win_prob = 0.5 + (edge * 0.15)  # Base 50% + edge bonus
        
        won = random.random() < win_prob
        
        if won:
            payout = position_size / effective_price  # Shares * 1.0
            pnl = payout - position_size
            wins += 1
        else:
            pnl = -position_size
            losses += 1
        
        bankroll += pnl
        trades.append({
            'coin': coin,
            'side': side,
            'entry': effective_price,
            'size': position_size,
            'pnl': pnl,
            'won': won
        })
    
    return {
        'name': name,
        'final_bankroll': bankroll,
        'total_return': (bankroll - initial) / initial * 100,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate': wins / len(trades) * 100 if trades else 0,
        'avg_trade': statistics.mean([t['pnl'] for t in trades]) if trades else 0,
        'blocked_zone': len(blocked_by_zone),
        'blocked_price': len(blocked_by_price),
        'blocked_volume': len(blocked_by_volume),
        'blocked_sentiment': len(blocked_sentiment)
    }

# Run backtests
print("Running Production Bot backtest...")
prod_results = run_backtest("Production (No Zone)", use_zone_filter=False, n_samples=50000)

print("Running Zoned Bot backtest...")
zoned_results = run_backtest("Zoned (Dead Zone Filter)", use_zone_filter=True, n_samples=50000)

# Display results
print()
print("RESULTS COMPARISON:")
print("-" * 80)
print(f"{'Metric':<30} {'Production':<20} {'Zoned':<20} {'Winner':<10}")
print("-" * 80)

metrics = [
    ('Final Bankroll', f"${prod_results['final_bankroll']:.2f}", f"${zoned_results['final_bankroll']:.2f}"),
    ('Total Return', f"{prod_results['total_return']:.1f}%", f"{zoned_results['total_return']:.1f}%"),
    ('Trades Taken', str(prod_results['trades']), str(zoned_results['trades'])),
    ('Win Rate', f"{prod_results['win_rate']:.1f}%", f"{zoned_results['win_rate']:.1f}%"),
    ('Wins/Losses', f"{prod_results['wins']}/{prod_results['losses']}", f"{zoned_results['wins']}/{zoned_results['losses']}"),
    ('Avg Trade PnL', f"${prod_results['avg_trade']:.2f}", f"${zoned_results['avg_trade']:.2f}"),
]

for metric, prod_val, zoned_val in metrics:
    if metric == 'Final Bankroll':
        winner = 'ZONED' if zoned_results['final_bankroll'] > prod_results['final_bankroll'] else 'PROD'
    elif metric == 'Total Return':
        winner = 'ZONED' if zoned_results['total_return'] > prod_results['total_return'] else 'PROD'
    elif metric == 'Win Rate':
        winner = 'ZONED' if zoned_results['win_rate'] > prod_results['win_rate'] else 'PROD'
    else:
        winner = '-'
    print(f"{metric:<30} {prod_val:<20} {zoned_val:<20} {winner:<10}")

print("-" * 80)
print()
print("BLOCKED TRADES:")
print(f"  Production - Price bounds: {prod_results['blocked_price']:,}")
print(f"  Zoned - Price bounds: {zoned_results['blocked_price']:,}")
print(f"  Zoned - Dead zone filter: {zoned_results['blocked_zone']:,}")
print(f"  Both - Volume filter: {prod_results['blocked_volume']:,}")
print(f"  Both - Sentiment filter: {prod_results['blocked_sentiment']:,}")
print()

# Calculate opportunity cost of zone filter
zone_block_rate = zoned_results['blocked_zone'] / 50000 * 100
print(f"Zone filter blocked {zone_block_rate:.1f}% of potential trades")
print()

# Recommendation
if zoned_results['final_bankroll'] > prod_results['final_bankroll']:
    winner = "ZONED"
    diff = zoned_results['final_bankroll'] - prod_results['final_bankroll']
    reason = "Higher win rate from better trade selection"
else:
    winner = "PRODUCTION"
    diff = prod_results['final_bankroll'] - zoned_results['final_bankroll']
    reason = "More trades = more opportunities"

print("=" * 60)
print(f"RECOMMENDATION: {winner} performs better")
print(f"Difference: ${diff:.2f}")
print(f"Reason: {reason}")
print("=" * 60)
