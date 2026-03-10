#!/usr/bin/env python3
"""
$1 REAL Trade on BTC 5m Market - PRODUCTION READY VERSION
Uses the fixed Master Bot V5 for actual live trading.
"""

import os
import sys
import json
from datetime import datetime

print("=" * 70)
print("💰 $1 REAL TRADE - BTC 5m MARKET")
print("=" * 70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
print()

# Check for REAL credentials
private_key = os.environ.get("POLY_PRIVATE_KEY")
address = os.environ.get("POLY_ADDRESS")

if not private_key or not address:
    print("❌ ERROR: Real credentials not found!")
    print()
    print("Set these environment variables first:")
    print("  export POLY_PRIVATE_KEY='0xYOUR_REAL_PRIVATE_KEY'")
    print("  export POLY_ADDRESS='0xYOUR_REAL_WALLET_ADDRESS'")
    print()
    print("Then run this script again.")
    sys.exit(1)

# Validate key format
if not private_key.startswith("0x") or len(private_key) != 66:
    print("❌ ERROR: Private key format looks wrong!")
    print(f"   Expected: 0x + 64 hex chars (66 total)")
    print(f"   Got: {len(private_key)} chars")
    print()
    print("Double-check your POLY_PRIVATE_KEY")
    sys.exit(1)

print("✅ Real credentials found")
print(f"   Address: {address[:10]}...{address[-8:]}")
print()

# Set environment for live trading
os.environ["POLY_LIVE_ENABLED"] = "true"
os.environ["POLY_DRY_RUN"] = "false"  # THIS IS REAL MONEY
os.environ["POLY_MAX_POSITION"] = "5"  # Start small

print("🔴 LIVE TRADING MODE ENABLED")
print("   This will use REAL USDC from your wallet!")
print()

# Load market data
print("📊 Loading BTC 5m market data...")
try:
    with open("/root/.openclaw/workspace/active_markets.json") as f:
        markets = json.load(f)
    
    btc_5m = [m for m in markets if m["coin"] == "BTC" and m["timeframe"] == 5][0]
    
    print(f"✅ Market found:")
    print(f"   Question: {btc_5m['question']}")
    print(f"   YES Price: {btc_5m['yes_price']}")
    print(f"   NO Price: {btc_5m['no_price']}")
    print()
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Import the PRODUCTION READY bot
print("🔌 Initializing Master Bot V5 (Production Ready)...")
try:
    sys.path.insert(0, '/root/.openclaw/workspace')
    from master_bot_v5_PRODUCTION_READY import MasterBot
    
    print("✅ Master Bot V5 loaded")
    print()
    
except Exception as e:
    print(f"❌ Error loading bot: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Final confirmation
print("=" * 70)
print("⚠️  FINAL CONFIRMATION")
print("=" * 70)
print()
print(f"You are about to trade REAL MONEY on Polymarket:")
print(f"  Market: BTC 5-minute (Up/Down)")
print(f"  Side: YES")
print(f"  Amount: $1.00 USDC")
print(f"  Wallet: {address[:10]}...{address[-8:]}")
print()

confirm = input("Type 'REAL' to confirm (anything else to abort): ")

if confirm.strip().upper() != "REAL":
    print()
    print("❌ Aborted. No trade executed.")
    sys.exit(0)

print()
print("🚀 EXECUTING REAL TRADE...")
print()

# Execute trade
try:
    # Initialize bot (this will check balances, etc.)
    bot = MasterBot()
    
    # Get current status
    status = bot.live.get_status() if hasattr(bot, 'live') else None
    print(f"Live trading status: {status}")
    print()
    
    # Execute the $1 trade
    market_id = "BTC-5m"
    side = "YES"
    amount = 1.0
    price = btc_5m['yes_price']
    
    result = bot.live.execute_buy(
        market_id=market_id,
        side=side,
        amount=amount,
        price=price,
        signal_data={
            "test_trade": True,
            "first_live_trade": True,
            "market_question": btc_5m['question'],
            "token_id": btc_5m['yes_token'],
        },
    )
    
    print("=" * 70)
    print("📋 TRADE RESULT")
    print("=" * 70)
    print()
    print(f"Success: {result.get('success', False)}")
    print(f"Virtual: {result.get('virtual', True)}")
    print(f"Order ID: {result.get('order_id', 'N/A')}")
    print(f"Fill Price: {result.get('fill_price', 'N/A')}")
    print(f"Filled Size: {result.get('filled_size', 'N/A')}")
    print()
    
    if result.get('success') and not result.get('virtual', True):
        print("🎉 REAL TRADE EXECUTED SUCCESSFULLY!")
        print()
        print("Next steps:")
        print("  1. Check your Polymarket portfolio")
        print("  2. Verify the $1 position is open")
        print("  3. Monitor with: cat master_v5_health.json")
        print()
        print("If this worked, you can run the full bot:")
        print("  python master_bot_v5_PRODUCTION_READY.py")
    elif result.get('virtual', True):
        print("⚠️  Trade executed in VIRTUAL mode")
        print("   Check logs for why live trading didn't activate")
    else:
        print("❌ Trade failed")
        print(f"   Error: {result.get('error', 'Unknown')}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
