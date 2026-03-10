#!/usr/bin/env python3
"""Quick $1 trade test - direct execution"""
import sys
import os
import time
import json

# Add polyclaw to path
sys.path.insert(0, '/root/.openclaw/skills/polyclaw')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/skills/polyclaw/.env')

from lib.wallet_manager import WalletManager
from lib.clob_client import ClobClientWrapper
from lib.contracts import CONTRACTS, CTF_ABI, POLYGON_CHAIN_ID
from web3 import Web3

# Market info
CONDITION_ID = "0x77db1082063e3720440a52f7e17531452887ede3dc1661fe6a18dd14a06e7e07"
YES_TOKEN = "18841986060142256287290700664282531878132082051689991014861932350762463310100"
NO_TOKEN = "61990560992505359549880912388595128445296612230106036684631699819561651920898"
AMOUNT_USD = 1.0

def main():
    print("="*50)
    print("$1 LIVE TRADE TEST")
    print("="*50)
    
    # Load wallet
    wallet = WalletManager()
    print(f"Wallet: {wallet.address}")
    print(f"Unlocked: {wallet.is_unlocked}")
    
    if not wallet.is_unlocked:
        print("❌ Wallet not unlocked")
        return 1
    
    # Check balance
    balances = wallet.get_balances()
    print(f"USDC.e: ${balances.usdc_e:.2f}")
    print(f"POL: {balances.pol:.4f}")
    
    if balances.usdc_e < AMOUNT_USD + 0.5:  # Need $1 + gas buffer
        print(f"❌ Insufficient funds (need ${AMOUNT_USD + 0.5:.2f})")
        return 1
    
    print(f"\n🎯 Trading ${AMOUNT_USD} on YES")
    print(f"Market ends: ~5 minutes")
    print(f"YES Token: {YES_TOKEN[:20]}...")
    
    # Get Web3
    w3 = Web3(Web3.HTTPProvider(
        wallet.rpc_url,
        request_kwargs={"timeout": 60}
    ))
    
    address = Web3.to_checksum_address(wallet.address)
    account = w3.eth.account.from_key(wallet.get_unlocked_key())
    
    # Split position (buy both YES and NO)
    print("\n1️⃣ Splitting USDC into YES+NO tokens...")
    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACTS["CTF"]),
        abi=CTF_ABI,
    )
    
    amount_wei = int(AMOUNT_USD * 1e6)
    condition_bytes = bytes.fromhex(CONDITION_ID[2:])
    
    try:
        tx = ctf.functions.splitPosition(
            Web3.to_checksum_address(CONTRACTS["USDC_E"]),
            bytes(32),
            condition_bytes,
            [1, 2],
            amount_wei,
        ).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 300000,
            "gasPrice": w3.eth.gas_price,
            "chainId": POLYGON_CHAIN_ID,
        })
        
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"✅ Split TX: {tx_hash.hex()}")
        print(f"   https://polygonscan.com/tx/{tx_hash.hex()}")
        
        # Wait for confirmation
        print("   Waiting 15s for confirmation...")
        time.sleep(15)
        
    except Exception as e:
        print(f"❌ Split failed: {e}")
        return 1
    
    # Sell NO tokens via CLOB (keep YES)
    print("\n2️⃣ Selling NO tokens via CLOB...")
    try:
        clob = ClobClientWrapper(wallet.get_unlocked_key(), wallet.address)
        order_id, filled, error = clob.sell_fok(
            token_id=NO_TOKEN,
            amount=AMOUNT_USD,
            price=0.50,  # Market sell
        )
        
        if filled:
            print(f"✅ CLOB sell filled: {order_id}")
        elif order_id:
            print(f"⏳ CLOB order placed: {order_id}")
            print(f"   (may fill partially)")
        else:
            print(f"⚠️ CLOB sell failed: {error}")
            print(f"   You now have both YES and NO tokens")
        
    except Exception as e:
        print(f"⚠️ CLOB error: {e}")
        print(f"   You have YES tokens - sell NO manually if needed")
    
    print("\n" + "="*50)
    print("TRADE COMPLETE")
    print("="*50)
    print(f"Position: ${AMOUNT_USD} YES")
    print(f"Entry: ~$0.505 per share")
    print(f"Check positions: polyclaw positions")
    print("="*50)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
