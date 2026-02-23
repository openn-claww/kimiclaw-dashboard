#!/usr/bin/env python3
"""
Redeem Iran Feb 20 market position (Market 1320793)
Market resolved to NO - redeem NO tokens
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

print(f'Redeeming positions for: {address}')
print('='*60)

# Contract addresses
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
POLYGON_CHAIN_ID = 137

# Iran Market 1320793
IRAN_MARKET = {
    'market_id': '1320793',
    'condition_id': '0xe1c67f75aac5b10dc28f1a2fbb79b079fc7f7320abfbd6a950a50c372979569b',
    'yes_token_id': '22119000719681531437948032382989063388011227465477033236689483589000306519260',
    'no_token_id': '55823505712250773829843086215809661787295660306087828099782847325808746995742',
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

# Check balances
yes_token_id = int(IRAN_MARKET['yes_token_id'])
no_token_id = int(IRAN_MARKET['no_token_id'])

yes_balance = ctf.functions.balanceOf(address, yes_token_id).call()
no_balance = ctf.functions.balanceOf(address, no_token_id).call()

print(f'\nIran Market (1320793) Token Balances:')
print(f'YES Token: {yes_balance / 1e6:.6f} shares')
print(f'NO Token: {no_balance / 1e6:.6f} shares')

# Market resolved to NO, so we redeem NO position (index set [2])
if no_balance > 0:
    print(f'\n🎯 Found winning NO position!')
    print(f'Attempting to redeem {no_balance / 1e6:.6f} NO shares...')
    
    try:
        condition_bytes = bytes.fromhex(IRAN_MARKET['condition_id'][2:])
        
        tx = ctf.functions.redeemPositions(
            w3.to_checksum_address(USDC_E),
            bytes(32),  # parentCollectionId (empty)
            condition_bytes,
            [2]  # NO = index 2
        ).build_transaction({
            'from': address,
            'nonce': w3.eth.get_transaction_count(address),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'chainId': POLYGON_CHAIN_ID,
        })
        
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        
        print(f'Redeem TX submitted: {tx_hash.hex()}')
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            print(f'✅ Redeem successful! Block: {receipt["blockNumber"]}')
            print(f'TX: https://polygonscan.com/tx/{tx_hash.hex()}')
        else:
            print('❌ Redeem failed')
            
    except Exception as e:
        print(f'❌ Redeem error: {e}')
else:
    print('\n⚠️  No NO tokens found to redeem')

# Check USDC balance after
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_E), abi=USDC_ABI)
usdc_balance = usdc.functions.balanceOf(address).call()
print(f'\nUSDC.e Balance: ${usdc_balance / 1e6:.2f}')
