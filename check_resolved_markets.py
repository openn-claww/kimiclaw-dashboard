#!/usr/bin/env python3
"""Check which markets have resolved and can be redeemed"""
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))
account = w3.eth.account.from_key(private_key)
address = account.address

# CTF contract
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
CTF_ABI = [
    {'inputs': [{'name': '_owner', 'type': 'address'}, {'name': '_id', 'type': 'uint256'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'},
]
ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    data = json.load(f)

print(f'Checking resolved markets for redemption')
print(f'Wallet: {address}')
print('='*70)

redeemable_positions = []

for pos in data:
    market_id = pos.get('market_id')
    token_id = pos.get('token_id', '')
    
    if not market_id or not token_id:
        continue
    
    # Check token balance
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
        
        market_data = resp.json()
        is_closed = market_data.get('closed', False)
        is_resolved = market_data.get('resolved', False)
        outcome = market_data.get('outcome')
        question = market_data.get('question', pos.get('question', 'Unknown'))
        
        if is_closed or is_resolved:
            print(f"\n🎯 {question}")
            print(f"   Market ID: {market_id}")
            print(f"   Status: CLOSED/RESOLVED")
            print(f"   Outcome: {outcome}")
            print(f"   Your Position: {pos.get('position', 'Unknown')}")
            print(f"   Token Balance: {balance / 1e6:.4f} CTF tokens")
            print(f"   Entry Amount: ${pos.get('entry_amount', 0)}")
            
            # Check if position matches outcome
            position_side = pos.get('position', '').upper()
            if outcome and position_side == outcome.upper():
                print(f"   ✅ WINNING POSITION - Can redeem!")
                redeemable_positions.append({
                    'position': pos,
                    'market_data': market_data,
                    'balance': balance / 1e6
                })
            elif outcome:
                print(f"   ❌ Losing position")
            else:
                print(f"   ⏳ Outcome not yet determined")
        
    except Exception as e:
        print(f"Error checking market {market_id}: {e}")

print(f"\n{'='*70}")
print(f"REDEEMABLE POSITIONS: {len(redeemable_positions)}")

if redeemable_positions:
    for rp in redeemable_positions:
        pos = rp['position']
        print(f"\n   • {pos.get('question', 'Unknown')}")
        print(f"     Market: {pos.get('market_id')}")
        print(f"     Position: {pos.get('position')} | Balance: {rp['balance']:.4f} tokens")
else:
    print("\nNo positions ready for redemption at this time.")
