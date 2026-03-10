#!/usr/bin/env python3
"""
Dry Run Validation - Simulate 10+ trades through V4 + Live Integration
Tests the full stack without real money or network calls.
"""

import os
import sys
import json
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

# Set test environment
os.environ['POLY_LIVE_ENABLED'] = 'true'
os.environ['POLY_DRY_RUN'] = 'true'
os.environ['POLY_PRIVATE_KEY'] = '0x' + 'a' * 64
os.environ['POLY_ADDRESS'] = '0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF'
os.environ['POLY_MAX_POSITION'] = '10'

print("=" * 70)
print("V4 + CLOB INTEGRATION - DRY RUN VALIDATION")
print("=" * 70)
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Mock the live trading modules to avoid network calls
mock_live_trader = MagicMock()
mock_live_trader.is_ready.return_value = True
mock_live_trader.dry_run = True
mock_live_trader.place_buy_order.return_value = {
    "filled": True,
    "order_id": "dry_run_order_001",
    "fill_price": 0.48,
    "filled_size": 2.08,
    "status": "filled",
    "error": None,
}
mock_live_trader.place_sell_order.return_value = {
    "filled": True,
    "order_id": "dry_run_order_002", 
    "fill_price": 0.65,
    "filled_size": 2.08,
    "status": "filled",
    "error": None,
}

# Simulate 10 trades
results = {
    "trades_executed": 0,
    "buys": 0,
    "sells": 0,
    "virtual_pnl": 0,
    "live_pnl": 0,
    "errors": 0,
}

print("Simulating 10 trade cycles through live integration...")
print()

# Patch before importing
with patch.dict('sys.modules', {
    'live_trading.clob_integration': MagicMock(LiveTrader=mock_live_trader),
}):
    from v4_live_integration import V4BotLiveIntegration
    from live_trading_config import load_live_config
    
    cfg, pk, addr = load_live_config()
    live = V4BotLiveIntegration(cfg, pk, addr)
    
    print(f"✅ Integration loaded")
    print(f"   Enabled: {live.enabled}")
    print(f"   Dry Run: {live.dry_run}")
    print(f"   Max Position: ${cfg['max_position_size']}")
    print()
    
    # Simulate 10 trades
    test_markets = [
        ("BTC-5m", "YES", 0.45, 0.62),
        ("ETH-5m", "NO", 0.52, 0.38),
        ("BTC-15m", "YES", 0.41, 0.58),
        ("ETH-15m", "YES", 0.48, 0.71),
        ("BTC-5m", "NO", 0.55, 0.42),
        ("ETH-5m", "YES", 0.44, 0.68),
        ("BTC-15m", "NO", 0.58, 0.35),
        ("ETH-15m", "NO", 0.51, 0.40),
        ("BTC-5m", "YES", 0.47, 0.64),
        ("ETH-5m", "YES", 0.43, 0.59),
    ]
    
    positions = {}  # Track open positions
    
    for i, (market, side, entry, exit_price) in enumerate(test_markets, 1):
        print(f"Trade {i:2d}: {market} | {side} @ {entry:.2f}")
        
        # Execute buy
        amount = 10.0  # $10 per trade
        buy_result = live.execute_buy(
            market_id=market,
            side=side,
            amount=amount,
            price=entry,
            signal_data={"test_id": i, "expected_exit": exit_price},
        )
        
        if buy_result["success"]:
            results["trades_executed"] += 1
            results["buys"] += 1
            positions[market] = {
                "side": side,
                "entry": buy_result["fill_price"],
                "size": buy_result["filled_size"],
                "order_id": buy_result["order_id"],
            }
            print(f"        ✅ BUY filled @ {buy_result['fill_price']:.3f}")
            
            # Simulate time passing, then sell
            time.sleep(0.1)  # Small delay
            
            sell_result = live.execute_sell(
                market_id=market,
                exit_price=exit_price,
                signal_data={"test_id": i, "exit_reason": "take_profit"},
            )
            
            if sell_result["success"]:
                results["sells"] += 1
                pnl = sell_result.get("pnl", 0)
                results["virtual_pnl"] += pnl
                print(f"        ✅ SELL @ {sell_result['fill_price']:.3f} | P&L: ${pnl:+.2f}")
            else:
                results["errors"] += 1
                print(f"        ❌ SELL failed: {sell_result.get('error', 'unknown')}")
        else:
            results["errors"] += 1
            print(f"        ❌ BUY failed: {buy_result.get('error', 'unknown')}")
    
    # Get final status
    status = live.get_status()

print()
print("=" * 70)
print("DRY RUN RESULTS")
print("=" * 70)
print(f"Trades Executed: {results['trades_executed']}/10")
print(f"Buys:            {results['buys']}")
print(f"Sells:           {results['sells']}")  
print(f"Errors:          {results['errors']}")
print(f"Virtual P&L:     ${results['virtual_pnl']:+.2f}")
print(f"Live P&L:        ${status.get('live_pnl', 0):+.2f}")
print()

# Validation checks
checks = []
checks.append(("All 10 trades executed", results["trades_executed"] == 10))
checks.append(("All buys succeeded", results["buys"] == 10))
checks.append(("All sells succeeded", results["sells"] == 10))
checks.append(("No errors", results["errors"] == 0))
checks.append(("Live integration tracked P&L", status.get("virtual_pnl") is not None))
checks.append(("Kill switch not triggered", not status.get("kill_switch_triggered", False)))

print("VALIDATION CHECKS:")
all_passed = True
for check_name, passed in checks:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status} {check_name}")
    if not passed:
        all_passed = False

print()
if all_passed:
    print("=" * 70)
    print("🎉 ALL CHECKS PASSED - Ready for live trading")
    print("=" * 70)
    print()
    print("Next step: Scale up position sizes gradually")
    print("  1. Set POLY_DRY_RUN=false")
    print("  2. Set POLY_MAX_POSITION=5 (start small)")
    print("  3. Monitor first 5 live trades closely")
    print("  4. Gradually increase to $20, $50, etc.")
    sys.exit(0)
else:
    print("=" * 70)
    print("⚠️  SOME CHECKS FAILED - Review before going live")
    print("=" * 70)
    sys.exit(1)
