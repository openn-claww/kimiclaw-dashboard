#!/usr/bin/env python3
"""Check actual token balances for winning positions"""
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
account = w3.eth.account.from_key(private_key)
address = account.address

CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
CTF_ABI = [{'inputs': [{'name': '_owner', 'type': 'address'}, {'name': '_id', 'type': 'uint256'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    positions = json.load(f)

print('AUTO-REDEEM CHECK: Wednesday, February 25th, 2026 — 11:07 PM (Asia/Shanghai)')
print(f'Wallet: {address}')
print('='*70)

unredeemed = []

for pos in positions:
    market_id = pos.get('market_id')
    token_id = pos.get('token_id', '')
    
    if not market_id or not token_id:
        continue
    
    try:
        # Check token balance
        token_int = int(token_id)
        balance = ctf.functions.balanceOf(address, token_int).call()
        
        if balance == 0:
            continue  # Already redeemed or never held
        
        # Check market status
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=10)
        if resp.status_code != 200:
            continue
        
        market = resp.json()
        is_closed = market.get('closed', False)
        is_resolved = market.get('resolved', False) or market.get('umaResolutionStatus') == 'resolved'
        outcome_prices_str = market.get('outcomePrices', '')
        question = market.get('question', 'Unknown')[:60]
        outcomes_str = market.get('outcomes', '["Yes","No"]')
        
        if not (is_closed or is_resolved):
            continue
        
        # Determine winner
        winner = None
        try:
            outcome_prices = json.loads(outcome_prices_str)
            outcomes = json.loads(outcomes_str)
            if outcome_prices[0] == "1":
                winner = outcomes[0]
            elif outcome_prices[1] == "1":
                winner = outcomes[1]
        except:
            continue
        
        if not winner:
            continue
        
        pos_side = pos.get('position', '').upper()
        winner_upper = winner.upper()
        
        # Check if this is a winning position
        is_winner = (pos_side == 'YES' and 'YES' in winner_upper) or \
                    (pos_side == 'NO' and 'NO' in winner_upper) or \
                    (pos_side == winner_upper)
        
        if is_winner:
            print(f"🎯 UNREDEEMED WINNER!")
            print(f"   {question}")
            print(f"   Market ID: {market_id}")
            print(f"   Position: {pos_side} (won - {winner})")
            print(f"   Token Balance: {balance / 1e6:.4f} shares")
            print(f"   Entry Amount: ${pos.get('entry_amount', 0)}")
            print()
            unredeemed.append({
                'market_id': market_id,
                'question': market.get('question', 'Unknown'),
                'position': pos_side,
                'balance': balance / 1e6,
                'token_id': token_id,
                'condition_id': market.get('conditionId', '')
            })
            
    except Exception as e:
        pass

print('='*70)
print(f"UNREDEEMED WINNING POSITIONS: {len(unredeemed)}")

if unredeemed:
    total = sum(u['balance'] for u in unredeemed)
    print(f"Total value: ${total:.2f}")
    for u in unredeemed:
        print(f"   • {u['question'][:50]}... | {u['position']} | ${u['balance']:.2f}")
else:
    print("\nNo unredeemed winning positions found.")
    print("All winning positions have been redeemed or settled.")
