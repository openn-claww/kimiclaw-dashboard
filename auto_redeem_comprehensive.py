#!/usr/bin/env python3
"""
Comprehensive auto-redeem check for all Polymarket positions
Checks positions.json for open positions and attempts redemption if resolved
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load environment
env_path = Path('/root/.openclaw/skills/polyclaw') / '.env'
load_dotenv(env_path)
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

if not private_key or not rpc_url:
    print('ERROR: Missing POLYCLAW_PRIVATE_KEY or CHAINSTACK_NODE')
    exit(1)

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
    {'inputs': [{'name': '_owner', 'type': 'address'}, {'name': '_id', 'type': 'uint256'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'},
    {'inputs': [{'name': 'collateralToken', 'type': 'address'}, {'name': 'parentCollectionId', 'type': 'bytes32'}, {'name': 'conditionId', 'type': 'bytes32'}, {'name': 'indexSets', 'type': 'uint256[]'}], 'name': 'redeemPositions', 'outputs': [], 'type': 'function'},
]

ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

# Load positions
positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
with open(positions_file) as f:
    all_positions = json.load(f)

# Filter open positions
open_positions = [p for p in all_positions if p.get('status') == 'open']

print(f'AUTO-REDEMPTION CHECK - March 1, 2026')
print(f'Wallet: {address}')
print(f'Open positions to check: {len(open_positions)}')
print('='*70)

redeemed = []
already_redeemed = []
not_resolved = []
losing_positions = []
errors = []

for pos in open_positions:
    market_id = pos.get('market_id')
    question = pos.get('question', 'Unknown')
    position_side = pos.get('position', '').upper()
    token_id = pos.get('token_id', '')
    
    print(f'\n📊 {question[:60]}...')
    print(f'   Market ID: {market_id} | Position: {position_side}')
    
    try:
        # Fetch market data
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=15)
        if resp.status_code != 200:
            print(f'   ⚠️ API error: {resp.status_code}')
            errors.append({'market': market_id, 'error': f'API error {resp.status_code}'})
            continue
        
        market_data = resp.json()
        is_closed = market_data.get('closed', False)
        is_resolved = market_data.get('resolved', False)
        uma_status = market_data.get('umaResolutionStatus', '')
        outcome = market_data.get('outcome')
        outcome_prices_str = market_data.get('outcomePrices', '')
        condition_id = market_data.get('conditionId', '')
        
        # Check if resolved
        resolved = is_resolved or uma_status == 'resolved' or (is_closed and outcome)
        
        if not resolved:
            print(f'   ⏳ Not yet resolved (closed={is_closed}, resolved={is_resolved})')
            not_resolved.append({'market': market_id, 'question': question})
            continue
        
        print(f'   ✅ Market RESOLVED')
        
        # Determine winner from outcomePrices
        winner = None
        try:
            outcome_prices = json.loads(outcome_prices_str)
            if outcome_prices[0] == "1":
                winner = "YES"
            elif outcome_prices[1] == "1":
                winner = "NO"
        except:
            pass
        
        # Also check outcome field
        if not winner and outcome:
            winner = outcome.upper()
        
        if not winner:
            print(f'   ⏳ Outcome not yet determined')
            not_resolved.append({'market': market_id, 'question': question})
            continue
        
        print(f'   🏆 Winner: {winner}')
        
        # Check if we won
        if position_side != winner:
            print(f'   ❌ Losing position ({position_side} vs {winner})')
            losing_positions.append({'market': market_id, 'question': question, 'position': position_side, 'winner': winner})
            continue
        
        print(f'   🎉 WINNING POSITION!')
        
        # Check token balance
        if not token_id:
            print(f'   ⚠️ No token ID')
            errors.append({'market': market_id, 'error': 'No token ID'})
            continue
        
        try:
            balance = ctf.functions.balanceOf(address, int(token_id)).call()
            print(f'   Token Balance: {balance / 1e6:.4f} shares')
        except Exception as e:
            print(f'   ⚠️ Balance check error: {e}')
            errors.append({'market': market_id, 'error': f'Balance check: {e}'})
            continue
        
        if balance == 0:
            print(f'   ✅ Already redeemed (zero balance)')
            already_redeemed.append({'market': market_id, 'question': question})
            continue
        
        # Attempt redemption
        print(f'   🔄 Attempting redemption...')
        
        if not condition_id:
            print(f'   ⚠️ No condition ID')
            errors.append({'market': market_id, 'error': 'No condition ID'})
            continue
        
        try:
            condition_bytes = bytes.fromhex(condition_id.replace('0x', ''))
            index_set = 1 if winner == 'YES' else 2
            
            # Get USDC balance before
            USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
            usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_E), abi=USDC_ABI)
            usdc_before = usdc.functions.balanceOf(address).call()
            
            tx = ctf.functions.redeemPositions(
                w3.to_checksum_address(USDC_E),
                bytes(32),
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
                usdc_after = usdc.functions.balanceOf(address).call()
                profit = (usdc_after - usdc_before) / 1e6
                
                print(f'   ✅ REDEEMED!')
                print(f'   💰 Profit: ${profit:+.2f} USDC')
                print(f'   🔗 TX: https://polygonscan.com/tx/{tx_hash.hex()}')
                
                redeemed.append({
                    'market_id': market_id,
                    'question': question,
                    'position': position_side,
                    'profit': profit,
                    'tx_hash': tx_hash.hex()
                })
            else:
                print(f'   ❌ Transaction failed')
                errors.append({'market': market_id, 'error': 'Transaction failed'})
                
        except Exception as e:
            print(f'   ❌ Redemption error: {e}')
            errors.append({'market': market_id, 'error': str(e)})
            
    except Exception as e:
        print(f'   ❌ Error: {e}')
        errors.append({'market': market_id, 'error': str(e)})

# Summary
print(f'\n{"="*70}')
print(f'SUMMARY')
print(f'{"="*70}')

if redeemed:
    total_profit = sum(r['profit'] for r in redeemed)
    print(f'\n✅ REDEEMED: {len(redeemed)} position(s) - Total: ${total_profit:+.2f} USDC')
    for r in redeemed:
        print(f'   • {r["question"][:50]}...')
        print(f'     Position: {r["position"]} | Profit: ${r["profit"]:+.2f}')
        print(f'     TX: {r["tx_hash"]}')
else:
    print(f'\nℹ️  No positions redeemed this run')

if already_redeemed:
    print(f'\n✓ Already redeemed: {len(already_redeemed)} position(s)')

if not_resolved:
    print(f'\n⏳ Not resolved yet: {len(not_resolved)} position(s)')
    for nr in not_resolved:
        print(f'   • {nr["question"][:50]}...')

if losing_positions:
    print(f'\n❌ Losing positions: {len(losing_positions)}')

if errors:
    print(f'\n⚠️  Errors: {len(errors)}')
    for e in errors[:3]:
        print(f'   • {e["market"]}: {e["error"]}')

print(f'\n--- END OF REPORT ---')
