#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root/.openclaw/skills/polyclaw')

from web3 import Web3
from dotenv import load_dotenv
from pathlib import Path
import os
import json

# Load env
load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))
account = w3.eth.account.from_key(private_key)
address = account.address

print(f'Checking balances for: {address}')
print('='*60)

# CTF Contract
CTF_ADDRESS = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
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
]

ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)

# Iran market tokens
clob_token_ids = '["22119000719681531437948032382989063388011227465477033236689483589000306519260", "55823505712250773829843086215809661787295660306087828099782847325808746995742"]'
token_ids = json.loads(clob_token_ids)

print('\nIran Market (1320793) Token Balances:')
print('-'*60)
for i, token_id in enumerate(token_ids):
    side = 'YES' if i == 0 else 'NO'
    try:
        balance = ctf.functions.balanceOf(address, int(token_id)).call()
        print(f'{side} Token: {balance / 1e6:.6f} shares')
    except Exception as e:
        print(f'{side} Token: Error - {e}')

# USDC balance
USDC_ADDRESS = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
usdc_balance = usdc.functions.balanceOf(address).call()
print(f'\nUSDC.e Balance: ${usdc_balance / 1e6:.2f}')
