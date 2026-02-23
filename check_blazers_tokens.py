#!/usr/bin/env python3
"""Check token balances for Blazers vs Suns"""

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

print(f'Checking token balances for: {address}')
print('='*60)

CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'

# Token IDs from market
YES_TOKEN = '61208409487579219570477960039139418649842262205786179762630480653396721246836'
NO_TOKEN = '94005336293241469024004520025094687913386243374672117887301233895307085665296'

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

ctf = w3.eth.contract(address=w3.to_checksum_address(CTF), abi=CTF_ABI)

yes_balance = ctf.functions.balanceOf(address, int(YES_TOKEN)).call()
no_balance = ctf.functions.balanceOf(address, int(NO_TOKEN)).call()

print(f"YES Token Balance (Blazers): {yes_balance / 1e6:.6f}")
print(f"NO Token Balance (Suns):     {no_balance / 1e6:.6f}")

if yes_balance == 0 and no_balance == 0:
    print("\n✅ All tokens redeemed!")
else:
    print(f"\n⚠️  Tokens still held: YES={yes_balance/1e6:.2f}, NO={no_balance/1e6:.2f}")
