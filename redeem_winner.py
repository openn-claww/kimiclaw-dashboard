#!/usr/bin/env python3
"""Redeem winning YES position"""
import sys
import os

sys.path.insert(0, '/root/.openclaw/skills/polyclaw')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/skills/polyclaw/.env')

from lib.wallet_manager import WalletManager
from lib.contracts import CONTRACTS, CTF_ABI, POLYGON_CHAIN_ID
from web3 import Web3

# Market details
CONDITION_ID = "0x77db1082063e3720440a52f7e17531452887ede3dc1661fe6a18dd14a06e7e07"

print("="*60)
print("REDEEM WINNING POSITION")
print("="*60)
print(f"Condition ID: {CONDITION_ID}")
print(f"Expected Winner: YES (based on price data)")
print()

wallet = WalletManager()
print(f"Wallet: {wallet.address}")

if not wallet.is_unlocked:
    print("❌ Wallet not unlocked")
    sys.exit(1)

# Get Web3
w3 = Web3(Web3.HTTPProvider(wallet.rpc_url, request_kwargs={"timeout": 60}))
address = Web3.to_checksum_address(wallet.address)
account = w3.eth.account.from_key(wallet.get_unlocked_key())

# Check initial balance
usdc = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACTS["USDC_E"]),
    abi=[{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
)
balance_before = usdc.functions.balanceOf(address).call() / 1e6
print(f"USDC balance before: ${balance_before:.4f}")

# Redeem
print("\n1️⃣ Redeeming winning position...")
ctf = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACTS["CTF"]),
    abi=CTF_ABI,
)

condition_bytes = bytes.fromhex(CONDITION_ID[2:])

# Redeem to USDC
tx = ctf.functions.redeemPositions(
    Web3.to_checksum_address(CONTRACTS["USDC_E"]),
    bytes(32),  # parentCollectionId
    condition_bytes,
    [1]  # indexSet for YES
).build_transaction({
    "from": address,
    "nonce": w3.eth.get_transaction_count(address),
    "gas": 200000,
    "gasPrice": w3.eth.gas_price,
    "chainId": POLYGON_CHAIN_ID,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"✅ Redeem TX: {tx_hash.hex()}")
print(f"   https://polygonscan.com/tx/{tx_hash.hex()}")

print("\n   Waiting 15s for confirmation...")
import time
time.sleep(15)

# Check final balance
balance_after = usdc.functions.balanceOf(address).call() / 1e6
print(f"\n💰 USDC balance after: ${balance_after:.4f}")
profit = balance_after - balance_before
if profit > 0:
    print(f"🎉 PROFIT: +${profit:.4f} USDC")
else:
    print(f"Balance change: ${profit:+.4f}")

print("\n" + "="*60)
print("REDEEM COMPLETE!")
print("="*60)
