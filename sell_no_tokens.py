#!/usr/bin/env python3
"""Complete the trade - sell NO tokens"""
import sys
sys.path.insert(0, '/root/.openclaw/skills/polyclaw')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/skills/polyclaw/.env')

# Token IDs from our trade
YES_TOKEN = "18841986060142256287290700664282531878132082051689991014861932350762463310100"
NO_TOKEN = "61990560992505359549880912388595128445296612230106036684631699819561651920898"

print("="*60)
print("SELLING NO TOKENS")
print("="*60)
print(f"NO Token ID: {NO_TOKEN[:30]}...")
print(f"Amount: ~1.0 tokens (to be sold at market price)")
print()

try:
    # Try to import and use CLOB
    from lib.wallet_manager import WalletManager
    from lib.clob_client import ClobClientWrapper
    
    wallet = WalletManager()
    print(f"Wallet: {wallet.address}")
    
    if not wallet.is_unlocked:
        print("❌ Wallet not unlocked")
        sys.exit(1)
    
    # Initialize CLOB client
    print("\nConnecting to CLOB...")
    clob = ClobClientWrapper(wallet.get_unlocked_key(), wallet.address)
    
    # Sell NO tokens at market price (~$0.50)
    print("Selling NO tokens...")
    order_id, filled, error = clob.sell_fok(
        token_id=NO_TOKEN,
        amount=1.0,  # ~1 token
        price=0.45,  # Slightly below market for quick fill
    )
    
    if filled:
        print(f"✅ SOLD! Order ID: {order_id}")
        print("You now hold only YES tokens")
    elif order_id:
        print(f"⏳ Order placed: {order_id}")
        print("Waiting for fill...")
    else:
        print(f"⚠️ Error: {error}")
        
except ImportError as e:
    print(f"❌ Missing module: {e}")
    print("\nCLOB module not available in this environment.")
    print("You can manually sell the NO tokens at:")
    print("https://polymarket.com/portfolio")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nYou can manually manage tokens at:")
    print("https://polymarket.com/portfolio")
