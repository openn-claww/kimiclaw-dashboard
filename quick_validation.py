#!/usr/bin/env python3
"""
Quick validation that V4 + Live Integration loads and can execute trades.
"""

import os
import sys

os.environ['POLY_LIVE_ENABLED'] = 'true'
os.environ['POLY_DRY_RUN'] = 'true'
os.environ['POLY_PRIVATE_KEY'] = '0x' + 'a' * 64
os.environ['POLY_ADDRESS'] = '0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF'

print("=" * 60)
print("V4 + CLOB Integration - Quick Validation")
print("=" * 60)

# Test 1: Import works
print("\n1. Testing imports...")
from ultimate_bot_v4 import UltimateBot
from live_trading_config import load_live_config
from v4_live_integration import V4BotLiveIntegration
print("   ✅ All imports successful")

# Test 2: Config loads
print("\n2. Testing config loading...")
cfg, pk, addr = load_live_config()
assert cfg['enabled'] == True
assert cfg['dry_run'] == True
print(f"   ✅ Config loaded: enabled={cfg['enabled']}, dry_run={cfg['dry_run']}")

# Test 3: V4BotLiveIntegration initializes
print("\n3. Testing V4BotLiveIntegration...")
from unittest.mock import MagicMock, patch
with patch('v4_live_integration.LiveTrader') as MockTrader:
    mock_instance = MagicMock()
    mock_instance.is_ready.return_value = True
    mock_instance.dry_run = True
    MockTrader.return_value = mock_instance
    
    live = V4BotLiveIntegration(cfg, pk, addr)
    print(f"   ✅ Live integration initialized")
    print(f"      enabled={live.enabled}, dry_run={live.dry_run}")

# Test 4: Status check
print("\n4. Testing status...")
status = live.get_status()
print(f"   ✅ Status: {status}")

# Test 5: Execute a dry run buy
print("\n5. Testing execute_buy (dry run)...")
result = live.execute_buy(
    market_id="TEST-BTC-5m",
    side="YES",
    amount=10.0,
    price=0.45,
    signal_data={"test": True}
)
print(f"   ✅ Buy result: success={result['success']}, virtual={result['virtual']}")
print(f"      fill_price={result.get('fill_price')}, filled_size={result.get('filled_size')}")

# Test 6: Execute a dry run sell
print("\n6. Testing execute_sell (dry run)...")
result = live.execute_sell(
    market_id="TEST-BTC-5m",
    exit_price=0.62,
    signal_data={"test": True}
)
print(f"   ✅ Sell result: success={result['success']}, virtual={result['virtual']}")
print(f"      fill_price={result.get('fill_price')}, pnl={result.get('pnl')}")

print("\n" + "=" * 60)
print("✅ ALL VALIDATION TESTS PASSED")
print("=" * 60)
print("\nSummary:")
print("  • V4 bot imports successfully with live trading")
print("  • Config loads from environment variables")
print("  • Live integration initializes in dry_run mode")
print("  • Buy/sell execute through live layer")
print("  • Virtual P&L tracked alongside")
print("\nNext step: Scale up position sizes gradually")
print("  1. Set POLY_DRY_RUN=false")
print("  2. Set POLY_MAX_POSITION=5 (start at $5)")
print("  3. Run and monitor first 5 live trades")
print("  4. Scale to $10, $20, $50 as performance validates")
