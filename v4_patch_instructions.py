"""
v4_patch_instructions.py
════════════════════════
Step-by-step instructions for patching ultimate_bot_v4.py.

This file is a reference guide — not executable code.
Follow the numbered sections in order.

FILES TO COPY TO /root/.openclaw/workspace/ FIRST:
  live_trading_config.py
  v4_live_integration.py
  token_mapper.py
  live_trading/  (the full package from Part 1)

════════════════════════════════════════════════════════════════════
SECTION 1 — Add imports at the top of ultimate_bot_v4.py
════════════════════════════════════════════════════════════════════

Find the existing import block (near line 1-30).
ADD these lines AFTER the existing imports:

```python
# ── Live trading integration (Part 2 patch) ─────────────────────────────────
import os
from live_trading_config import load_live_config
from v4_live_integration import V4BotLiveIntegration
```

════════════════════════════════════════════════════════════════════
SECTION 2 — Add config loading near the top of the file
════════════════════════════════════════════════════════════════════

ADD this block AFTER the imports (before the class definition):

```python
# ── Load live trading config ─────────────────────────────────────────────────
# Reads from environment variables (see live_trading_config.py)
# To enable: export POLY_LIVE_ENABLED=true POLY_PRIVATE_KEY=0x... POLY_ADDRESS=0x...
try:
    _LIVE_CONFIG, _POLY_PRIVATE_KEY, _POLY_ADDRESS = load_live_config()
except EnvironmentError as e:
    logger.error(f"Live trading config error: {e}")
    _LIVE_CONFIG = {"enabled": False, "dry_run": True}
    _POLY_PRIVATE_KEY = None
    _POLY_ADDRESS = None
```

════════════════════════════════════════════════════════════════════
SECTION 3 — Initialize V4BotLiveIntegration in __init__
════════════════════════════════════════════════════════════════════

Find the class __init__ method. It likely looks something like:

```python
# EXISTING CODE (DO NOT REMOVE):
class UltimateBotV4:
    def __init__(self, ...):
        self.balance = 1000.0
        self.positions = {}
        # ... other init code
```

ADD these lines at the END of __init__, before any final return:

```python
        # ── Live trading integration (Part 2 patch) ──────────────────────────
        self.live = V4BotLiveIntegration(
            config=_LIVE_CONFIG,
            private_key=_POLY_PRIVATE_KEY,
            address=_POLY_ADDRESS,
        )
        logger.info(f"V4 bot live integration loaded: {self.live.get_status()}")
        # ── End live trading init ─────────────────────────────────────────────
```

════════════════════════════════════════════════════════════════════
SECTION 4 — Replace execute_buy
════════════════════════════════════════════════════════════════════

FIND this block (your virtual execute_buy):

```python
# ─── REMOVE THIS BLOCK ───────────────────────────────────────────────────────
def execute_buy(market_id, side, amount, price):
    # Virtual buy - just updates internal state
    self.positions[market_id] = {"side": side, "amount": amount, "entry": price}
    self.balance -= amount
    return {"status": "filled", "virtual": True}
# ─── END REMOVE ──────────────────────────────────────────────────────────────
```

REPLACE WITH:

```python
def execute_buy(self, market_id, side, amount, price):
    # ── Part 2 patch: route through live integration ──────────────────────────
    result = self.live.execute_buy(
        market_id=market_id,
        side=side,
        amount=amount,
        price=price,
        signal_data={
            # Pass whatever signal context V4 has available
            # These are logged for audit purposes
            "market_id": market_id,
            "side": side,
            "v4_estimated_price": price,
        },
    )

    # ── Update V4's internal balance and position tracking ────────────────────
    # This keeps V4's existing logic working regardless of live/virtual
    if result["success"]:
        self.balance -= amount
        self.positions[market_id] = {
            "side": side,
            "amount": result["filled_size"],   # Use actual fill size
            "entry": result["fill_price"],      # Use actual fill price
            "order_id": result.get("order_id"), # Store for sell lookup
            "virtual": result["virtual"],
        }

    return result
    # ── End Part 2 patch ──────────────────────────────────────────────────────
```

════════════════════════════════════════════════════════════════════
SECTION 5 — Replace execute_sell
════════════════════════════════════════════════════════════════════

FIND this block (your virtual execute_sell):

```python
# ─── REMOVE THIS BLOCK ───────────────────────────────────────────────────────
def execute_sell(market_id, exit_price):
    # Virtual sell - calculates P&L
    pos = self.positions[market_id]
    pnl = (exit_price - pos["entry"]) * pos["amount"] if pos["side"] == "YES" else (pos["entry"] - exit_price) * pos["amount"]
    self.balance += pos["amount"] + pnl
    return {"pnl": pnl, "virtual": True}
# ─── END REMOVE ──────────────────────────────────────────────────────────────
```

REPLACE WITH:

```python
def execute_sell(self, market_id, exit_price):
    # ── Part 2 patch: route through live integration ──────────────────────────
    result = self.live.execute_sell(
        market_id=market_id,
        exit_price=exit_price,
        signal_data={
            "market_id": market_id,
            "v4_exit_price": exit_price,
        },
    )

    # ── Update V4's internal balance and position tracking ────────────────────
    if result["success"] and market_id in self.positions:
        pos = self.positions[market_id]
        self.balance += pos["amount"] + result["pnl"]
        del self.positions[market_id]

    return result
    # ── End Part 2 patch ──────────────────────────────────────────────────────
```

════════════════════════════════════════════════════════════════════
SECTION 6 — Optional: Add status logging in the main loop
════════════════════════════════════════════════════════════════════

If V4 has a periodic status log or heartbeat, add this line:

```python
    # In your status/heartbeat section:
    live_status = self.live.get_status()
    logger.info(
        f"[LIVE STATUS] "
        f"live_pnl=${live_status['live_pnl']:+.4f} | "
        f"virtual_pnl=${live_status['virtual_pnl']:+.4f} | "
        f"open_positions={live_status['open_live_positions']} | "
        f"daily_loss=${live_status['daily_loss_used']:.2f}/{live_status['daily_loss_limit']:.2f}"
    )
```

════════════════════════════════════════════════════════════════════
SECTION 7 — Manual kill switch (emergency use)
════════════════════════════════════════════════════════════════════

If you need to halt live trading mid-run without restarting the bot,
you can call this from an admin interface or REPL:

```python
    # Halt all live trading immediately
    bot.live.trigger_kill_switch("manual_override")

    # Resume live trading
    bot.live.reset_kill_switch()
```

════════════════════════════════════════════════════════════════════
SECTION 8 — Deployment checklist
════════════════════════════════════════════════════════════════════

Before running with real money:

Step 1 — DRY RUN validation (paper trades only)
  □ export POLY_LIVE_ENABLED=true
  □ export POLY_DRY_RUN=true       ← still paper
  □ export POLY_PRIVATE_KEY=0x...
  □ export POLY_ADDRESS=0x...
  □ Run bot for 10+ trade cycles
  □ Verify live_trades_v4.json is being written
  □ Verify live_pnl and virtual_pnl are tracking

Step 2 — Pre-live wallet check
  □ python -c "
        from live_trading import LiveTrader
        import os
        t = LiveTrader(os.environ['POLY_PRIVATE_KEY'], os.environ['POLY_ADDRESS'])
        print(t.health_check())
    "
  □ Confirm usdc_balance >= your trading capital
  □ Confirm pol_balance >= 0.05 POL
  □ Confirm approvals_set = True
       If not: t.ensure_approvals()

Step 3 — Go live (small first)
  □ export POLY_MAX_POSITION=5      ← start at $5 max
  □ export POLY_DAILY_LOSS_LIMIT=10 ← $10 daily loss max
  □ export POLY_DRY_RUN=false       ← now it's real
  □ Run bot for first 5 live trades
  □ Confirm fills in live_trades_v4.json match wallet balance changes

Step 4 — Scale up (only after Step 3 validates)
  □ Increase POLY_MAX_POSITION gradually
  □ Review live vs virtual P&L divergence — large gaps signal
    slippage or fill issues to investigate

════════════════════════════════════════════════════════════════════
SECURITY NOTES
════════════════════════════════════════════════════════════════════

NEVER:
  - Hardcode POLY_PRIVATE_KEY in any source file
  - Commit .env files to git
  - Log private key (the integration never does this)
  - Share live_trades_v4.json publicly (contains order IDs and amounts)

DO:
  - Store private key in environment variable or secrets manager
  - Add live_trading_config.py, live_trades_v4.json to .gitignore
  - Rotate API credentials if they are ever exposed
"""
