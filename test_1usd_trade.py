#!/usr/bin/env python3
"""
$1 Live Test Trade on BTC 5m Market
Tests the full CLOB integration with real market data.
"""

import os
import sys
import json
from datetime import datetime

# Set environment for test
os.environ.setdefault("POLY_LIVE_ENABLED", "true")
os.environ.setdefault("POLY_DRY_RUN", "true")  # Start with paper trading

print("=" * 70)
print("🧪 $1 TEST TRADE - BTC 5m MARKET")
print("=" * 70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
print()

# Check credentials
private_key = os.environ.get("POLY_PRIVATE_KEY")
address = os.environ.get("POLY_ADDRESS")

if not private_key or not address:
    print("⚠️  WARNING: POLY_PRIVATE_KEY or POLY_ADDRESS not set")
    print("   Using dummy credentials for dry run test...")
    os.environ["POLY_PRIVATE_KEY"] = "0x" + "a" * 64
    os.environ["POLY_ADDRESS"] = "0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF"
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
    print(f"   YES Token: {btc_5m['yes_token'][:30]}...")
    print(f"   NO Token: {btc_5m['no_token'][:30]}...")
    print()
except Exception as e:
    print(f"❌ Error loading market data: {e}")
    sys.exit(1)

# Import live trading
print("🔌 Initializing live trading module...")
try:
    sys.path.insert(0, '/root/.openclaw/workspace')
    from live_trading.live_trading_config import load_live_config
    from live_trading.v4_live_integration import V4BotLiveIntegration
    
    cfg, pk, addr = load_live_config()
    print(f"✅ Config loaded:")
    print(f"   Enabled: {cfg['enabled']}")
    print(f"   Dry Run: {cfg['dry_run']}")
    print(f"   Max Position: ${cfg['max_position_size']}")
    print(f"   Max Slippage: {cfg['max_slippage']*100:.1f}%")
    print()
    
    # Initialize live integration
    live = V4BotLiveIntegration(cfg, pk, addr)
    print(f"✅ Live integration initialized")
    print(f"   Status: {live.get_status()}")
    print()
    
except Exception as e:
    print(f"❌ Error initializing live trading: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Execute $1 test trade
print("=" * 70)
print("💰 EXECUTING $1 TEST TRADE")
print("=" * 70)
print()

side = "YES"
amount = 1.0  # $1
price = btc_5m['yes_price']
market_id = f"BTC-5m"

print(f"Trade Details:")
print(f"  Market: BTC 5-minute")
print(f"  Side: {side}")
print(f"  Amount: ${amount}")
print(f"  Target Price: {price}")
print(f"  Token ID: {btc_5m['yes_token'][:40]}...")
print()

print("🚀 Submitting order...")
print()

try:
    result = live.execute_buy(
        market_id=market_id,
        side=side,
        amount=amount,
        price=price,
        signal_data={
            "test_trade": True,
            "market_question": btc_5m['question'],
            "token_id": btc_5m['yes_token'],
            "discovery_time": datetime.now().isoformat(),
        },
    )
    
    print("=" * 70)
    print("📋 TRADE RESULT")
    print("=" * 70)
    print()
    print(f"Success: {result['success']}")
    print(f"Virtual: {result['virtual']}")
    print(f"Order ID: {result.get('order_id', 'N/A')}")
    print(f"Fill Price: {result.get('fill_price', 'N/A')}")
    print(f"Filled Size: {result.get('filled_size', 'N/A')}")
    print()
    
    if result['success']:
        print("✅ TEST TRADE SUCCESSFUL!")
        print()
        print("Next steps:")
        print("  1. Check order status on Polymarket CLOB")
        print("  2. Verify position in portfolio")
        print("  3. If dry_run=True, retry with POLY_DRY_RUN=false for real trade")
        print()
        print(f"To go live:")
        print(f"  export POLY_DRY_RUN=false")
        print(f"  export POLY_PRIVATE_KEY='your_real_key'")
        print(f"  export POLY_ADDRESS='your_real_address'")
    else:
        print("❌ TEST TRADE FAILED")
        print(f"Error: {result.get('error', 'Unknown error')}")
        
except Exception as e:
    print(f"❌ Error executing trade: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
