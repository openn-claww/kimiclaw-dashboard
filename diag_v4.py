#!/usr/bin/env python3
"""
diag_v4.py — Read V4BotLiveIntegration source to understand execute_buy
Run BEFORE restarting bot:
  python3 /root/.openclaw/workspace/diag_v4.py
"""
import sys, subprocess, inspect
from pathlib import Path

WS = "/root/.openclaw/workspace"
sys.path.insert(0, WS)

print("=" * 65)
print("  V4 LIVE INTEGRATION DIAGNOSTIC")
print("=" * 65)

# 1. Find the file
for search_path in [WS, "/root/.openclaw", "/root"]:
    for f in Path(search_path).rglob("v4_live_integration.py"):
        print(f"\nFound: {f}")
        src = f.read_text()
        # Show execute_buy implementation
        lines = src.splitlines()
        in_func = False
        for i, line in enumerate(lines, 1):
            if "def execute_buy" in line:
                in_func = True
            if in_func:
                print(f"  {i:4d}: {line}")
                if in_func and i > 10 and line.strip().startswith("def "):
                    break  # next function = stop
                if i > 80 and in_func:
                    print("  ... (truncated)")
                    break
        break

# 2. Try importing and calling get_status
try:
    from live_trading.v4_live_integration import V4BotLiveIntegration
    from live_trading.live_trading_config import load_live_config
    import os
    cfg, pk, addr = load_live_config()
    v4 = V4BotLiveIntegration(config=cfg, private_key=pk, address=addr)

    # Try prepare_trader
    for m in ("prepare_trader", "connect", "initialize"):
        fn = getattr(v4, m, None)
        if callable(fn):
            print(f"\nCalling {m}()...")
            fn()
            break

    print(f"\nget_status(): {v4.get_status()}")

    # Show all public methods
    print("\nPublic methods:")
    for name, val in inspect.getmembers(v4, predicate=inspect.ismethod):
        if not name.startswith("_"):
            try:
                sig = inspect.signature(val)
                print(f"  {name}{sig}")
            except Exception:
                print(f"  {name}()")

    # Check dry_run
    for attr in ("dry_run", "_dry_run", "config", "_config", "_live_enabled"):
        v = getattr(v4, attr, "NOT FOUND")
        print(f"  v4.{attr} = {v}")

except Exception as e:
    print(f"\n❌ Import/init failed: {e}")
    import traceback; traceback.print_exc()

print("\n" + "=" * 65)
print("  WHAT TO LOOK FOR:")
print("""
  1. Does execute_buy return a 'virtual' key? → Probably NO
     Fix already applied: we now derive virtual from order_id presence

  2. What does dry_run look like?
     If dry_run=True → V4 will NOT submit real orders
     Check: POLY_DRY_RUN=false must be set AND passed correctly to config

  3. Does execute_buy return order_id on live fill?
     Should see: order_id='0x...' or a UUID string
     If order_id=None/empty with success=True → V4 is in virtual mode internally

  4. After restart, look for in logs:
     [DIAG] execute_buy signature: ...
     [DIAG] self.live.dry_run = False  ← Must be False
     [LIVE] ✅ Order placed on-chain — order_id=...
""")
