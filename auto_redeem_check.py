#!/usr/bin/env python3
"""Check and execute redemptions for resolved Polymarket positions"""
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load env from polyclaw skill
load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))
account = w3.eth.account.from_key(private_key)
address = account.address

# Contracts
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'

CTF_ABI = [
    {'inputs': [{'name': '_owner', 'type': 'address'}, {'name': '_id', 'type': 'uint256'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'},
    {'inputs': [{'name': 'collateralToken', 'type': 'address'}, {'name': 'parentCollectionId', 'type': 'bytes32'}, {'name': 'conditionId', 'type': 'bytes32'}, {'name': 'partition', 'type': 'uint256[]'}, {'name': 'amount', 'type': 'uint256'}], 'name': 'mergePositions', 'outputs': [], 'type': 'function'},
    {'inputs': [{'name': 'collateralToken', 'type': 'address'}, {'name': 'parentCollectionId', 'type': 'bytes32'}, {'name': 'conditionId', 'type': 'bytes32'}, {'name': 'indexSets', 'type': 'uint256[]'}], 'name': 'redeemPositions', 'outputs': [], 'type': 'function'},
]

ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    data = json.load(f)

print(f'Auto-Redemption Check - {address}')
print('='*70)

redeemable = []
resolved_but_no_outcome = []

for pos in data:
    market_id = pos.get('market_id')
    token_id = pos.get('token_id', '')
    
    if not market_id or not token_id:
        continue
    
    try:
        token_int = int(token_id)
        balance = ctf.functions.balanceOf(address, token_int).call()
        if balance == 0:
            continue
    except:
        continue
    
    # Check market status
    try:
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=10)
        if resp.status_code != 200:
            continue
        
        market = resp.json()
        is_closed = market.get('closed', False)
        is_resolved = market.get('resolved', False)
        uma_status = market.get('umaResolutionStatus', '')
        outcome = market.get('outcome')
        question = market.get('question', pos.get('question', 'Unknown'))
        outcome_prices = market.get('outcomePrices', '[]')
        
        # Parse outcome prices to determine winner
        winner = None
        try:
            prices = json.loads(outcome_prices)
            outcomes = json.loads(market.get('outcomes', '[]'))
            if prices and outcomes:
                for i, p in enumerate(prices):
                    if float(p) >= 0.99:  # Winner has price ~1
                        winner = outcomes[i]
                        break
        except:
            pass
        
        if is_closed or is_resolved or uma_status == 'resolved':
            position_side = pos.get('position', '').upper()
            
            # Check if we have a confirmed outcome
            if outcome:
                # Direct outcome match
                if position_side == outcome.upper():
                    redeemable.append({
                        'pos': pos,
                        'market': market,
                        'balance': balance,
                        'winner': outcome,
                        'confirmed': True
                    })
            elif winner:
                # Winner determined from outcomePrices
                if position_side == winner.upper():
                    redeemable.append({
                        'pos': pos,
                        'market': market,
                        'balance': balance,
                        'winner': winner,
                        'confirmed': True
                    })
                else:
                    # Losing position
                    pass
            else:
                # Resolved but no clear outcome yet
                resolved_but_no_outcome.append({
                    'pos': pos,
                    'market': market,
                    'balance': balance
                })
        
    except Exception as e:
        print(f"Error: {market_id} - {e}")

# Report results
print(f"\n✅ CONFIRMED REDEEMABLE: {len(redeemable)}")
for r in redeemable:
    pos = r['pos']
    print(f"  • {pos.get('question', 'Unknown')}")
    print(f"    Market: {pos.get('market_id')} | Position: {pos.get('position')}")
    print(f"    Balance: {r['balance']/1e6:.4f} tokens | Winner: {r['winner']}")

print(f"\n⏳ RESOLVED (outcome pending): {len(resolved_but_no_outcome)}")
for r in resolved_but_no_outcome:
    pos = r['pos']
    market = r['market']
    print(f"  • {pos.get('question', 'Unknown')}")
    print(f"    Market: {pos.get('market_id')} | Position: {pos.get('position')}")
    print(f"    Balance: {r['balance']/1e6:.4f} tokens")
    # Show outcome prices hint
    try:
        prices = json.loads(market.get('outcomePrices', '[]'))
        outcomes = json.loads(market.get('outcomes', '[]'))
        if prices and outcomes:
            print(f"    Outcome prices: {list(zip(outcomes, prices))}")
    except:
        pass

print(f"\n{'='*70}")
if redeemable:
    print("REDEMPTION RECOMMENDED for confirmed winning positions.")
else:
    print("No confirmed winning positions ready for redemption.")
