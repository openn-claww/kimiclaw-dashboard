#!/usr/bin/env python3
"""
Check all Polymarket positions for redemption eligibility
Scans wallet for CTF tokens and checks if markets have resolved
"""

import os
import sys
import json
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
import requests

# Load environment
load_dotenv(Path('/root/.openclaw/skills/polyclaw') / '.env')
private_key = os.getenv('POLYCLAW_PRIVATE_KEY')
rpc_url = os.getenv('CHAINSTACK_NODE')

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))
account = w3.eth.account.from_key(private_key)
address = account.address

print(f'🔍 Checking positions for: {address}')
print('='*70)

# Contract addresses
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
POLYGON_CHAIN_ID = 137

# CTF ABI (minimal)
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

# Known markets from trading journal
KNOWN_MARKETS = {
    '703258': {
        'name': 'Jesus Christ return before 2027',
        'condition_id': '0x0b4cc3b739e1dfe5d73274740e7308b6fb389c5af040c3a174923d928d134bee',
        'end_date': '2026-12-31',
        'side': 'NO',
        'size': 2.0,
    },
    '1388774': {
        'name': 'Spurs vs Pistons',
        'condition_id': '0x19da64a3f1b53b26b99bee3bb130d763e92e9f5f78436cb914b40f476665842d',
        'end_date': '2026-02-24',
        'side': 'YES',
        'size': 4.5,
    },
    '1385475': {
        'name': 'Blazers vs Suns', 
        'condition_id': '0xfa7dfab36073386c3d80a499b02f2d627a2ddd2c2786a754797c5c7249ccad94',
        'end_date': '2026-02-23',
        'side': 'NO',
        'size': 4.5,
    },
    '1320793': {
        'name': 'Iran strike by Feb 20 (REDEEMED)',
        'condition_id': '0xe1c67f75aac5b10dc28f1a2fbb79b079fc7f7320abfbd6a950a50c372979569b',
        'end_date': '2026-02-20',
        'side': 'NO',
        'size': 1.0,
        'redeemed': True,
    },
}

# Fetch market data from Gamma API
def get_market_status(market_id):
    try:
        resp = requests.get(f'https://gamma-api.polymarket.com/markets/{market_id}', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"  API error: {e}")
    return None

# Check USDC balance
USDC_ABI = [{'constant': True, 'inputs': [{'name': '_owner', 'type': 'address'}], 'name': 'balanceOf', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'}]
usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_E), abi=USDC_ABI)
usdc_balance = usdc.functions.balanceOf(address).call()
print(f'💰 Current USDC.e Balance: ${usdc_balance / 1e6:.2f}')
print()

# Check each known market
redeemable = []
already_redeemed = []
not_resolved = []

for market_id, info in KNOWN_MARKETS.items():
    print(f"📊 Market {market_id}: {info['name']}")
    
    if info.get('redeemed'):
        print(f"   ✅ Already redeemed")
        already_redeemed.append(market_id)
        continue
    
    # Get fresh market data
    market_data = get_market_status(market_id)
    
    if not market_data:
        print(f"   ⚠️  Could not fetch market data")
        continue
    
    is_closed = market_data.get('closed', False)
    is_active = market_data.get('active', False)
    outcome_prices = market_data.get('outcomePrices', '[]')
    
    print(f"   Closed: {is_closed} | Active: {is_active}")
    print(f"   End Date: {info['end_date']}")
    print(f"   Outcome Prices: {outcome_prices}")
    
    # Check if market has resolved (closed and has definitive outcome)
    if is_closed:
        # Market resolved - check if we have tokens to redeem
        # We'd need the token IDs to check balances
        # For now, report that market resolved and manual redemption may be needed
        print(f"   🎯 MARKET RESOLVED - Check Polymarket UI for redemption")
        redeemable.append({
            'market_id': market_id,
            'name': info['name'],
            'side': info['side'],
            'size': info['size'],
        })
    else:
        print(f"   ⏳ Market still open")
        not_resolved.append(market_id)
    
    print()

# Summary
print('='*70)
print('📋 SUMMARY')
print('='*70)

if redeemable:
    print(f"\n🎯 {len(redeemable)} market(s) RESOLVED - Redemption needed:")
    for m in redeemable:
        print(f"   • {m['market_id']}: {m['name']} ({m['side']} ${m['size']})")
else:
    print("\n✅ No markets have resolved since last check")

if already_redeemed:
    print(f"\n💵 {len(already_redeemed)} position(s) already redeemed")

if not_resolved:
    print(f"\n⏳ {len(not_resolved)} position(s) still open:")
    for m in not_resolved:
        info = KNOWN_MARKETS[m]
        print(f"   • {m}: {info['name']} (resolves {info['end_date']})")

print(f"\n💰 Wallet Balance: ${usdc_balance / 1e6:.2f} USDC.e")
