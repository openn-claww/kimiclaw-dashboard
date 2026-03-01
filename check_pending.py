#!/usr/bin/env python3
"""Check pending markets that haven't resolved yet"""
import json
import requests
from pathlib import Path
from datetime import datetime

positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    positions = json.load(f)

print('AUTO-REDEEM CHECK: Wednesday, February 25th, 2026 — 11:07 PM (Asia/Shanghai)')
print('='*70)

# Get unique markets
market_ids = set()
for pos in positions:
    if pos.get('market_id'):
        market_ids.add(pos['market_id'])

print(f"Checking {len(market_ids)} markets...\n")

pending = []
resolved = []

for market_id in market_ids:
    try:
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=15)
        if resp.status_code != 200:
            continue
        
        market = resp.json()
        is_closed = market.get('closed', False)
        is_resolved = market.get('resolved', False) or market.get('umaResolutionStatus') == 'resolved'
        question = market.get('question', 'Unknown')[:65]
        end_date = market.get('endDate', 'Unknown')
        
        # Get total position value for this market
        total_value = sum(p.get('entry_amount', 0) for p in positions if p.get('market_id') == market_id)
        
        if is_closed or is_resolved:
            # Parse outcome prices
            outcome_prices_str = market.get('outcomePrices', '')
            winner = None
            try:
                outcome_prices = json.loads(outcome_prices_str)
                outcomes = json.loads(market.get('outcomes', '["Yes","No"]'))
                if outcome_prices[0] == "1":
                    winner = outcomes[0]
                elif outcome_prices[1] == "1":
                    winner = outcomes[1]
            except:
                pass
            
            resolved.append({
                'market_id': market_id,
                'question': question,
                'winner': winner,
                'value': total_value
            })
        else:
            pending.append({
                'market_id': market_id,
                'question': question,
                'end_date': end_date,
                'value': total_value
            })
    except Exception as e:
        print(f"Error checking {market_id}: {e}")

print(f"✅ RESOLVED MARKETS ({len(resolved)}):")
for r in resolved:
    status = f"→ Winner: {r['winner']}" if r['winner'] else "→ Outcome pending"
    print(f"   • {r['question']}...")
    print(f"     {status} | ${r['value']:.2f} at stake")

print(f"\n⏳ PENDING MARKETS ({len(pending)}):")
for p in pending:
    print(f"   • {p['question']}...")
    print(f"     Resolves: {p['end_date'][:10] if len(p['end_date']) > 10 else p['end_date']} | ${p['value']:.2f} at stake")

print('\n' + '='*70)
print("SUMMARY:")
print(f"   Resolved markets: {len(resolved)}")
print(f"   Pending markets: {len(pending)}")
print(f"   Total at stake in pending: ${sum(p['value'] for p in pending):.2f}")

# Check if any pending markets resolve soon
print("\n   Markets resolving within 48 hours:")
found_upcoming = False
for p in pending:
    try:
        end = datetime.fromisoformat(p['end_date'].replace('Z', '+00:00'))
        now = datetime.now(end.tzinfo)
        hours_until = (end - now).total_seconds() / 3600
        if 0 < hours_until < 48:
            print(f"      ⚠️  {p['question'][:40]}... in {hours_until:.1f}h")
            found_upcoming = True
    except:
        pass

if not found_upcoming:
    print("      None")
