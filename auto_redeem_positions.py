#!/usr/bin/env python3
"""
Auto-redeem resolved market positions
Check all positions and redeem winning positions
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load environment
load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))
account = w3.eth.account.from_key(private_key)
address = account.address

# Contract addresses
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
POLYGON_CHAIN_ID = 137

# CTF ABI
CTF_ABI = [
    {
        'inputs': [
            {'name': '_owner', 'type': 'address'},
            {'name': '_id', 'type': 'uint256'},
        ],
        'name': 'balanceOf',
        'outputs': [{'name': '', 'type': 'uint256'}],
        'type': 'function',
    },
    {
        'inputs': [
            {'name': 'collateralToken', 'type': 'address'},
            {'name': 'parentCollectionId', 'type': 'bytes32'},
            {'name': 'conditionId', 'type': 'bytes32'},
            {'name': 'indexSets', 'type': 'uint256[]'},
        ],
        'name': 'redeemPositions',
        'outputs': [],
        'type': 'function',
    },
]

ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    positions = json.load(f)

print(f'Auto-Redeem Check for {address}')
print(f'Time: Wednesday, February 25th, 2026 — 6:57 AM (Asia/Shanghai)')
print('='*70)

redeemed = []
errors = []

for pos in positions:
    market_id = pos.get('market_id')
    token_id = pos.get('token_id', '')
    position_side = pos.get('position', '').upper()
    
    if not market_id or not token_id:
        continue
    
    try:
        # Check token balance
        token_int = int(token_id)
        balance = ctf.functions.balanceOf(address, token_int).call()
        if balance == 0:
            continue
        
        # Check market status
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=10)
        if resp.status_code != 200:
            continue
        
        market_data = resp.json()
        is_closed = market_data.get('closed', False)
        is_resolved = market_data.get('umaResolutionStatus') == 'resolved'
        outcome_prices_str = market_data.get('outcomePrices', '')
        condition_id = market_data.get('conditionId', '')
        question = market_data.get('question', pos.get('question', 'Unknown'))
        
        if not (is_closed and is_resolved):
            continue
        
        # Parse outcome prices to determine winner
        # outcomePrices: ["1", "0"] means first outcome won (YES)
        # outcomePrices: ["0", "1"] means second outcome won (NO)
        try:
            outcome_prices = json.loads(outcome_prices_str)
            if outcome_prices[0] == "1":
                winning_outcome = 0  # First outcome (YES)
                winning_name = market_data.get('outcomes', '["Yes", "No"]').split(',')[0].strip('["')
            elif outcome_prices[1] == "1":
                winning_outcome = 1  # Second outcome (NO)
                winning_name = market_data.get('outcomes', '["Yes", "No"]').split(',')[1].strip('"]')
            else:
                continue  # No clear winner
        except:
            continue
        
        # Map position side to outcome index
        # For binary markets: YES = 0, NO = 1
        if position_side == 'YES':
            position_index = 0
        elif position_side == 'NO':
            position_index = 1
        else:
            continue
        
        # Check if this is a winning position
        if position_index == winning_outcome:
            print(f"\n🎯 WINNING POSITION FOUND!")
            print(f"   Market: {question}")
            print(f"   Market ID: {market_id}")
            print(f"   Position: {position_side} (won)")
            print(f"   Token Balance: {balance / 1e6:.4f} shares")
            print(f"   Entry Amount: ${pos.get('entry_amount', 0)}")
            
            # Attempt redemption
            try:
                condition_bytes = bytes.fromhex(condition_id[2:])
                index_set = position_index + 1  # Index sets are 1-based (1=YES, 2=NO)
                
                tx = ctf.functions.redeemPositions(
                    w3.to_checksum_address(USDC_E),
                    bytes(32),  # parentCollectionId (empty)
                    condition_bytes,
                    [index_set]
                ).build_transaction({
                    'from': address,
                    'nonce': w3.eth.get_transaction_count(address),
                    'gas': 300000,
                    'gasPrice': w3.eth.gas_price,
                    'chainId': POLYGON_CHAIN_ID,
                })
                
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                
                if receipt['status'] == 1:
                    print(f"   ✅ REDEEMED!")
                    print(f"   TX: https://polygonscan.com/tx/{tx_hash.hex()}")
                    redeemed.append({
                        'market_id': market_id,
                        'question': question,
                        'position': position_side,
                        'amount': balance / 1e6,
                        'tx_hash': tx_hash.hex()
                    })
                else:
                    print(f"   ❌ Redeem failed")
                    errors.append({'market': market_id, 'error': 'Transaction failed'})
                    
            except Exception as e:
                print(f"   ❌ Redeem error: {e}")
                errors.append({'market': market_id, 'error': str(e)})
        else:
            # Losing position - can still redeem for collateral but no profit
            pass
            
    except Exception as e:
        pass

# Summary
print(f"\n{'='*70}")
print(f"REDEEMED: {len(redeemed)} positions")
if redeemed:
    for r in redeemed:
        print(f"   ✅ {r['question']}: ${r['amount']:.2f} redeemed")
        print(f"      TX: {r['tx_hash']}")

if errors:
    print(f"\nERRORS: {len(errors)}")
    for e in errors:
        print(f"   ❌ {e['market']}: {e['error']}")

if not redeemed and not errors:
    print("No winning positions ready for redemption at this time.")
