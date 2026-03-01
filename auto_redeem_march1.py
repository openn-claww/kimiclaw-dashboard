#!/usr/bin/env python3
"""
Auto-redeem script for resolved markets
Markets: 1303400 (BTC $55K dip) and 1345641 (BTC $75K reach)
Both resolved NO - winning positions
"""

import os
import sys
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

print(f'Auto-Redemption Check - March 1, 2026')
print(f'Wallet: {address}')
print('='*70)

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

# USDC for balance check
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_E), abi=USDC_ABI)

# Markets to check
MARKETS = [
    {'market_id': '1303400', 'name': 'Will Bitcoin dip to $55,000 in February?'},
    {'market_id': '1345641', 'name': 'Will Bitcoin reach $75,000 in February?'},
]

redeemed = []
errors = []

for market in MARKETS:
    market_id = market['market_id']
    print(f"\n📊 {market['name']}")
    print(f"   Market ID: {market_id}")
    
    try:
        # Fetch market data from API
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=10)
        if resp.status_code != 200:
            print(f"   ⚠️  API error: {resp.status_code}")
            continue
        
        data = resp.json()
        condition_id = data.get('conditionId', '')
        outcome_prices_str = data.get('outcomePrices', '')
        
        if not condition_id:
            print(f"   ⚠️  No condition ID found")
            continue
        
        # Determine winner
        winner = None
        try:
            outcome_prices = json.loads(outcome_prices_str)
            if outcome_prices[0] == "1":
                winner = "Yes"
            elif outcome_prices[1] == "1":
                winner = "No"
        except:
            pass
        
        if not winner:
            print(f"   ⏳ Outcome not yet determined")
            continue
        
        print(f"   Outcome: {winner} (resolved)")
        
        # Get token IDs from positions file
        positions_file = Path.home() / '.openclaw' / 'polyclaw' / 'positions.json'
        with open(positions_file) as f:
            positions = json.load(f)
        
        # Find our position
        our_position = None
        for pos in positions:
            if pos.get('market_id') == market_id:
                our_position = pos
                break
        
        if not our_position:
            print(f"   ⚠️  Position not found in records")
            continue
        
        position_side = our_position.get('position', '').upper()
        token_id = our_position.get('token_id', '')
        
        print(f"   Our Position: {position_side}")
        
        # Check if winner
        is_winner = (position_side == 'YES' and winner == 'Yes') or (position_side == 'NO' and winner == 'No')
        
        if not is_winner:
            print(f"   ❌ Losing position - no redemption needed")
            continue
        
        # Check token balance
        if not token_id:
            print(f"   ⚠️  No token ID found")
            continue
        
        balance = ctf.functions.balanceOf(address, int(token_id)).call()
        print(f"   Token Balance: {balance / 1e6:.4f} shares")
        
        if balance == 0:
            print(f"   ✅ Already redeemed")
            continue
        
        # Redeem!
        print(f"   🎯 Winning position! Redeeming...")
        
        condition_bytes = bytes.fromhex(condition_id[2:])
        index_set = 1 if winner == 'Yes' else 2  # YES=1, NO=2
        
        usdc_before = usdc.functions.balanceOf(address).call()
        
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
            usdc_after = usdc.functions.balanceOf(address).call()
            profit = (usdc_after - usdc_before) / 1e6
            
            print(f"   ✅ REDEEMED!")
            print(f"   Profit: ${profit:+.2f}")
            print(f"   TX: https://polygonscan.com/tx/{tx_hash.hex()}")
            
            redeemed.append({
                'market_id': market_id,
                'name': market['name'],
                'profit': profit,
                'tx_hash': tx_hash.hex()
            })
        else:
            print(f"   ❌ Redemption failed")
            errors.append(market_id)
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        errors.append(market_id)

print(f"\n{'='*70}")
print(f"REDEMPTION SUMMARY")
print(f"{'='*70}")

if redeemed:
    total_profit = sum(r['profit'] for r in redeemed)
    print(f"✅ Successfully redeemed {len(redeemed)} position(s)")
    print(f"💰 Total profit: ${total_profit:+.2f}")
    for r in redeemed:
        print(f"   • {r['name']}: ${r['profit']:+.2f}")
else:
    print(f"ℹ️  No positions redeemed")

if errors:
    print(f"\n⚠️  Errors with {len(errors)} market(s): {', '.join(errors)}")
