#!/usr/bin/env python3
"""
Check all active positions for redemption eligibility
"""

import os
import sys
import json
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

print(f'Checking all positions for: {address}')
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

# Active positions from trading journal
ACTIVE_POSITIONS = [
    # NBA Markets
    {
        'market_id': '1388774',
        'name': 'Spurs vs Pistons',
        'yes_token': '19142327053998389470086705003890707625472105728508265412585954595363891062660',
        'no_token': '48248423741315746221490871940483624927210637856299229637517646297035568109388',
        'side_held': 'YES',  # Based on trading journal
        'end_date': '2026-02-24',
    },
    {
        'market_id': '1385475',
        'name': 'Blazers vs Suns',
        'yes_token': '61208409487579219570477960039139418649842262205786179762630480653396721246836',
        'no_token': '94005336293241469024004520025094687913386243374672117887301233895307085665296',
        'side_held': 'NO',  # Based on trading journal
        'end_date': '2026-02-23',
    },
    # Jesus return 2027
    {
        'market_id': '703258',
        'name': 'Jesus returns before 2027',
        'yes_token': '121909824159536297676840485489876768302243983953226880000000000000000000000000',  # Need actual
        'no_token': '121909824159536297676840485489876768302243983953226880000000000000000000000001',  # Need actual
        'side_held': 'NO',
        'end_date': '2026-12-31',
    },
]

print('\nChecking token balances for active positions:')
print('-'*60)

redeemable = []

for pos in ACTIVE_POSITIONS:
    print(f"\n{pos['name']} (Market {pos['market_id']}):")
    print(f"  Side held: {pos['side_held']}")
    print(f"  End date: {pos['end_date']}")
    
    # Check YES token balance
    try:
        yes_balance = ctf.functions.balanceOf(address, int(pos['yes_token'])).call()
        print(f"  YES Token Balance: {yes_balance / 1e6:.6f} shares")
    except Exception as e:
        print(f"  YES Token Balance: Error - {e}")
        yes_balance = 0
    
    # Check NO token balance
    try:
        no_balance = ctf.functions.balanceOf(address, int(pos['no_token'])).call()
        print(f"  NO Token Balance: {no_balance / 1e6:.6f} shares")
    except Exception as e:
        print(f"  NO Token Balance: Error - {e}")
        no_balance = 0
    
    # Check if position is redeemable (has winning tokens)
    if pos['side_held'] == 'YES' and yes_balance > 0:
        print(f"  → Potential YES redemption: {yes_balance / 1e6:.6f} shares")
        redeemable.append({
            'market': pos['name'],
            'side': 'YES',
            'amount': yes_balance / 1e6
        })
    elif pos['side_held'] == 'NO' and no_balance > 0:
        print(f"  → Potential NO redemption: {no_balance / 1e6:.6f} shares")
        redeemable.append({
            'market': pos['name'],
            'side': 'NO',
            'amount': no_balance / 1e6
        })

# USDC balance
USDC_ADDRESS = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
usdc_balance = usdc.functions.balanceOf(address).call()

print(f'\n{"="*60}')
print(f'USDC.e Balance: ${usdc_balance / 1e6:.2f}')
print(f'\nRedeemable positions found: {len(redeemable)}')
for r in redeemable:
    print(f"  - {r['market']}: {r['side']} side, {r['amount']:.6f} shares")
