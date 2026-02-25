#!/usr/bin/env python3
"""Check resolved markets with outcome prices"""
import json
import requests
from pathlib import Path

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    positions = json.load(f)

print('AUTO-REDEEM CHECK: Wednesday, February 25th, 2026 — 11:07 PM (Asia/Shanghai)')
print('='*70)

# Build position lookup
position_map = {}
for pos in positions:
    mid = pos.get('market_id')
    if mid:
        if mid not in position_map:
            position_map[mid] = []
        position_map[mid].append(pos)

market_ids = list(position_map.keys())
print(f"Checking {len(market_ids)} unique markets...")
print()

redeemable = []
losing = []

for market_id in market_ids:
    try:
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=15)
        if resp.status_code != 200:
            continue
        
        market = resp.json()
        is_closed = market.get('closed', False)
        is_resolved = market.get('resolved', False) or market.get('umaResolutionStatus') == 'resolved'
        outcome_prices_str = market.get('outcomePrices', '')
        question = market.get('question', 'Unknown')[:70]
        outcomes_str = market.get('outcomes', '["Yes","No"]')
        
        if not (is_closed or is_resolved):
            continue
        
        # Parse outcome prices to determine winner
        # ["1","0"] = first outcome won, ["0","1"] = second outcome won
        winner = None
        try:
            outcome_prices = json.loads(outcome_prices_str)
            outcomes = json.loads(outcomes_str)
            if outcome_prices[0] == "1":
                winner = outcomes[0]  # First outcome won
            elif outcome_prices[1] == "1":
                winner = outcomes[1]  # Second outcome won
        except:
            pass
        
        if not winner:
            continue
        
        print(f"📊 {question}")
        print(f"   Market ID: {market_id}")
        print(f"   Winner: {winner}")
        
        for pos in position_map[market_id]:
            pos_side = pos.get('position', '').upper()
            entry = pos.get('entry_amount', 0)
            
            # Normalize winner name
            winner_upper = winner.upper()
            if winner_upper in ['YES', 'NO']:
                pass
            elif 'YES' in winner_upper:
                winner_upper = 'YES'
            elif 'NO' in winner_upper:
                winner_upper = 'NO'
            
            if pos_side == winner_upper:
                print(f"   ✅ WIN: {pos_side} position worth ${entry}")
                redeemable.append({
                    'market_id': market_id,
                    'question': market.get('question', 'Unknown'),
                    'position': pos_side,
                    'amount': entry
                })
            else:
                print(f"   ❌ LOSS: {pos_side} position (lost ${entry})")
                losing.append({
                    'market_id': market_id,
                    'position': pos_side,
                    'amount': entry
                })
        print()
            
    except Exception as e:
        print(f"   Error: {e}")

print('='*70)
print(f"SUMMARY: {len(redeemable)} winning positions, {len(losing)} losing positions")

if redeemable:
    print("\n🎯 WINNING POSITIONS (can redeem):")
    total = 0
    for r in redeemable:
        print(f"   • {r['question'][:55]}...")
        print(f"     {r['position']} | ${r['amount']:.2f}")
        total += r['amount']
    print(f"\n   Total redeemable: ${total:.2f}")
else:
    print("\nNo winning positions ready for redemption at this time.")

if losing:
    total_loss = sum(l['amount'] for l in losing)
    print(f"\n📉 Total at risk in losing positions: ${total_loss:.2f}")
