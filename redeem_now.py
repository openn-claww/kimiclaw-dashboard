#!/usr/bin/env python3
"""Auto-redeem resolved market positions"""

import sqlite3
import requests
import json
import os
import time
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

# CTF ABI (minimal for redemption)
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

conn = sqlite3.connect('positions.db')
cursor = conn.cursor()

# Get all open positions
cursor.execute('SELECT id, market_slug, side, entry_price, size, condition_id, asset_id FROM positions WHERE status="open"')
rows = cursor.fetchall()

print(f'Auto-Redeem Check for {address}')
print(f'Time: Sunday, March 1st, 2026 — 9:07 AM (Asia/Shanghai)')
print('='*70)

redeemed = []
errors = []

for row in rows:
    pos_id, market_slug, side, entry_price, size, condition_id, asset_id = row
    
    try:
        # Get market info
        resp = requests.get(f'https://gamma-api.polymarket.com/markets?slug={market_slug}', timeout=10)
        if resp.status_code != 200:
            continue
        
        markets = resp.json()
        if not markets:
            continue
        
        market = markets[0]
        is_closed = market.get('closed', False)
        uma_status = market.get('umaResolutionStatus', 'unknown')
        outcome_prices_str = market.get('outcomePrices', '')
        question = market.get('question', market_slug)
        
        if not (is_closed and uma_status == 'resolved'):
            continue
        
        # Parse outcome prices
        try:
            outcome_prices = json.loads(outcome_prices_str)
            if outcome_prices[0] == '1':
                winning_outcome = 0  # YES
            elif outcome_prices[1] == '1':
                winning_outcome = 1  # NO
            else:
                continue
        except:
            continue
        
        # Check if position is winner
        position_index = 0 if side == 'YES' else 1
        if position_index != winning_outcome:
            continue  # Losing position
        
        # Check token balance
        if not asset_id:
            continue
        try:
            token_int = int(asset_id)
            balance = ctf.functions.balanceOf(address, token_int).call()
            if balance == 0:
                continue
        except Exception as e:
            errors.append({'market': market_slug, 'error': f'Balance check failed: {e}'})
            continue
        
        print(f'\n🎯 WINNING POSITION: {question}')
        print(f'   Market: {market_slug}')
        print(f'   Position: {side} (won)')
        print(f'   Token Balance: {balance / 1e6:.4f} shares')
        print(f'   Condition ID: {condition_id}')
        
        # Attempt redemption
        try:
            if not condition_id:
                errors.append({'market': market_slug, 'error': 'Missing condition_id'})
                continue
            
            condition_bytes = bytes.fromhex(condition_id.replace('0x', ''))
            index_set = position_index + 1  # Index sets are 1-based
            
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
                print(f'   ✅ REDEEMED!')
                print(f'   TX: https://polygonscan.com/tx/{tx_hash.hex()}')
                redeemed.append({
                    'market_slug': market_slug,
                    'question': question,
                    'side': side,
                    'amount': balance / 1e6,
                    'tx_hash': tx_hash.hex()
                })
                # Update position status in DB
                pnl = (balance/1e6) - (size * entry_price)
                cursor.execute('UPDATE positions SET status="redeemed", resolved_outcome=?, resolved_time=?, pnl=? WHERE id=?',
                    (side, time.time(), pnl, pos_id))
                conn.commit()
            else:
                print(f'   ❌ Transaction failed')
                errors.append({'market': market_slug, 'error': 'Transaction failed'})
        except Exception as e:
            print(f'   ❌ Redeem error: {e}')
            errors.append({'market': market_slug, 'error': str(e)})
            
    except Exception as e:
        errors.append({'market': market_slug, 'error': str(e)})

# Summary
print(f'\n{"="*70}')
print(f'REDEEMED: {len(redeemed)} positions')
for r in redeemed:
    print(f'   ✅ {r["question"]}: ${r["amount"]:.2f} redeemed')
    print(f'      TX: {r["tx_hash"]}')

if errors:
    print(f'\nERRORS: {len(errors)}')
    for e in errors[:5]:  # Show first 5 errors
        print(f'   ❌ {e["market"]}: {e["error"]}')

conn.close()

# Output summary for reporting
if redeemed:
    print(f'\n--- REPORT TO #winnings ---')
    total = sum(r['amount'] for r in redeemed)
    print(f'Redeemed {len(redeemed)} positions for ${total:.2f} USDC')
