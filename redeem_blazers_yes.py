#!/usr/bin/env python3
"""
Redeem Blazers vs Suns winning position - YES on Trail Blazers
Market resolved: Trail Blazers won (outcome 0 = YES)
"""

import os
import sys
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

print(f'Redeeming for: {address}')
print('='*60)

# Contract addresses
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
POLYGON_CHAIN_ID = 137

# Market details - Blazers vs Suns
MARKET = {
    'market_id': '1385475',
    'name': 'Trail Blazers vs. Suns',
    'condition_id': '0xfa7dfab36073386c3d80a499b02f2d627a2ddd2c2786a754797c5c7249ccad94',
    'yes_token_id': '61208409487579219570477960039139418649842262205786179762630480653396721246836',
    'winning_index': 1,  # YES = index 1
}

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

# Check YES token balance (winning position)
yes_token_id = int(MARKET['yes_token_id'])
balance = ctf.functions.balanceOf(address, yes_token_id).call()
print(f"YES Token Balance: {balance / 1e6:.6f} USDC.e")

if balance == 0:
    print("⚠️  No winning tokens found - may already be redeemed")
    sys.exit(0)

print(f"🎯 Found winning YES position! Attempting redemption...")

# Build redemption transaction
condition_bytes = bytes.fromhex(MARKET['condition_id'][2:])

# Check USDC balance before
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_E), abi=USDC_ABI)
usdc_before = usdc.functions.balanceOf(address).call()
print(f"USDC.e Balance Before: ${usdc_before / 1e6:.2f}")

# Build and send redeem transaction
try:
    tx = ctf.functions.redeemPositions(
        w3.to_checksum_address(USDC_E),
        bytes(32),  # parentCollectionId (empty)
        condition_bytes,
        [1]  # YES = index 1
    ).build_transaction({
        'from': address,
        'nonce': w3.eth.get_transaction_count(address),
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
        'chainId': POLYGON_CHAIN_ID,
    })
    
    # Sign and send
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Redeem TX submitted: {tx_hash.hex()}")
    
    # Wait for receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    if receipt['status'] == 1:
        print(f"✅ Redeem successful! Block: {receipt['blockNumber']}")
        
        # Check USDC balance after
        usdc_after = usdc.functions.balanceOf(address).call()
        print(f"USDC.e Balance After: ${usdc_after / 1e6:.2f}")
        print(f"Profit: ${(usdc_after - usdc_before) / 1e6:+.2f}")
        print(f"\nTransaction: https://polygonscan.com/tx/{tx_hash.hex()}")
    else:
        print("❌ Redeem failed")
        
except Exception as e:
    print(f"❌ Error: {e}")
