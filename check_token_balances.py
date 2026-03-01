#!/usr/bin/env python3
"""Check token balances for all positions"""
import os
import json
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

print(f'Checking token balances for {address}')
print('='*70)

redeemable = []
for pos in data:
    token_id = pos.get('token_id', '')
    if token_id:
        try:
            token_int = int(token_id)
            balance = ctf.functions.balanceOf(address, token_int).call()
            if balance > 0:
                print(f"\n📊 {pos.get('question', 'Unknown')}")
                print(f"   Position: {pos.get('position', 'Unknown')} | Status: {pos.get('status', 'Unknown')}")
                print(f"   Token Balance: {balance / 1e6:.4f} CTF tokens")
                print(f"   Entry Amount: ${pos.get('entry_amount', 0)}")
                redeemable.append({
                    'position': pos,
                    'balance': balance / 1e6
                })
        except Exception as e:
            pass

print(f"\n{'='*70}")
print(f"Total positions with token balances: {len(redeemable)}")
