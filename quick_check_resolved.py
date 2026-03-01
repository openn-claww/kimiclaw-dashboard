#!/usr/bin/env python3
"""Quick check for resolved markets - for cron job"""
import json
import requests
from pathlib import Path

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    positions = json.load(f)

print('AUTO-REDEEM CHECK: Wednesday, February 25th, 2026 — 11:07 PM (Asia/Shanghai)')
print('='*70)

# Track unique market IDs to check
market_ids = set()
for pos in positions:
    if pos.get('market_id'):
        market_ids.add(pos['market_id'])

print(f"Checking {len(market_ids)} unique markets...")
print()

resolved_count = 0
redeemable = []

for market_id in market_ids:
    try:
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=15)
        if resp.status_code != 200:
            continue
        
        market = resp.json()
        is_closed = market.get('closed', False)
        is_resolved = market.get('resolved', False) or market.get('umaResolutionStatus') == 'resolved'
        outcome = market.get('outcome')
        question = market.get('question', 'Unknown')
        
        if is_closed or is_resolved:
            resolved_count += 1
            print(f"📊 {question[:60]}...")
            print(f"   Market ID: {market_id}")
            print(f"   Status: {'RESOLVED' if is_resolved else 'CLOSED'}")
            print(f"   Outcome: {outcome or 'Pending'}")
            
            # Check if any of our positions match the winning outcome
            for pos in positions:
                if pos.get('market_id') == market_id:
                    pos_side = pos.get('position', '').upper()
                    if outcome and pos_side == outcome.upper():
                        print(f"   ✅ WINNING POSITION: {pos_side}")
                        redeemable.append({
                            'market_id': market_id,
                            'question': question,
                            'position': pos_side,
                            'amount': pos.get('entry_amount', 0)
                        })
                    elif outcome:
                        print(f"   ❌ Losing position: {pos_side}")
            print()
            
    except Exception as e:
        print(f"   Error checking {market_id}: {e}")

print('='*70)
print(f"SUMMARY: {resolved_count} resolved markets found, {len(redeemable)} redeemable positions")

if redeemable:
    print("\n🎯 REDEEMABLE POSITIONS:")
    for r in redeemable:
        print(f"   • {r['question'][:50]}...")
        print(f"     Position: {r['position']} | Amount: ${r['amount']}")
else:
    print("\nNo winning positions ready for redemption at this time.")
