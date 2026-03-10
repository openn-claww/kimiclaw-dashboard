"""
live_trading_config.py — Configuration for V4 bot live trading patch.

USAGE:
  1. Copy this file to the same directory as ultimate_bot_v4.py
  2. Set environment variables before running:
       export POLY_PRIVATE_KEY="0xYOUR_KEY"
       export POLY_ADDRESS="0xYOUR_ADDRESS"
       export POLY_LIVE_ENABLED="true"      # only when ready for real money
  3. In ultimate_bot_v4.py, add at top:
       from live_trading_config import LIVE_TRADING_CONFIG, load_live_config

NEVER set "enabled": True without first confirming:
  - dry_run runs have been profitable for 10+ trades
  - Approvals are set on-chain (run wallet_manager.ensure_approvals())
  - Daily loss limit is set conservatively
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Master config block ──────────────────────────────────────────────────────
# All values here are the DEFAULTS. Environment variables override them.

LIVE_TRADING_CONFIG = {
    # ── Master switches ──
    "enabled": False,        # Top-level kill switch. Must be True for ANY live action.
    "dry_run": True,         # When enabled=True, dry_run=True = paper trades only.
                             # Set dry_run=False only when fully validated.

    # ── Order execution ──
    "max_slippage": 0.02,        # 2% max price deviation before order aborts
    "min_order_size": 1.00,      # USDC — Polymarket minimum
    "max_position_size": 20.00,  # USDC per position (start conservative)
    "default_order_type": "GTC", # GTC = Good Till Cancel

    # ── Risk limits ──
    "daily_loss_limit": 20.00,   # USDC — hard stop for the day
    "max_open_positions": 5,     # Max concurrent live positions
    "gas_reserve_pol": 0.05,     # POL kept for gas (never trade below this)

    # ── Network ──
    "polygon_rpc": "https://polygon-rpc.com",
    "clob_api_url": "https://clob.polymarket.com",

    # ── Logging ──
    "trade_log_path": "live_trades_v4.json",
    "log_level": "INFO",

    # ── Parallel tracking ──
    "track_virtual_pnl": True,  # Keep running virtual P&L alongside live
                                 # for performance comparison
}


def load_live_config() -> dict:
    """
    Load config, overriding defaults with environment variables.

    Env var mapping:
      POLY_LIVE_ENABLED     → enabled (true/false)
      POLY_DRY_RUN          → dry_run (true/false, default true)
      POLY_MAX_SLIPPAGE     → max_slippage (float, e.g. "0.02")
      POLY_MAX_POSITION     → max_position_size (float, e.g. "20.0")
      POLY_DAILY_LOSS_LIMIT → daily_loss_limit (float)
      POLY_PRIVATE_KEY      → returned separately (never stored in config dict)
      POLY_ADDRESS          → returned separately
    """
    cfg = dict(LIVE_TRADING_CONFIG)  # copy defaults

    # Boolean overrides
    if os.environ.get("POLY_LIVE_ENABLED", "").lower() == "true":
        cfg["enabled"] = True
    if os.environ.get("POLY_DRY_RUN", "true").lower() == "false":
        cfg["dry_run"] = False

    # Float overrides
    for env_key, cfg_key in [
        ("POLY_MAX_SLIPPAGE",     "max_slippage"),
        ("POLY_MAX_POSITION",     "max_position_size"),
        ("POLY_DAILY_LOSS_LIMIT", "daily_loss_limit"),
    ]:
        val = os.environ.get(env_key)
        if val:
            try:
                cfg[cfg_key] = float(val)
            except ValueError:
                logger.warning(f"Invalid env var {env_key}={val}, using default")

    # Credentials (loaded separately — never stored inside config dict)
    private_key = os.environ.get("POLY_PRIVATE_KEY")
    address = os.environ.get("POLY_ADDRESS")

    if cfg["enabled"] and (not private_key or not address):
        raise EnvironmentError(
            "Live trading enabled but POLY_PRIVATE_KEY or POLY_ADDRESS not set. "
            "Export both environment variables before starting the bot."
        )

    mode_str = "DISABLED"
    if cfg["enabled"]:
        mode_str = "DRY RUN (paper)" if cfg["dry_run"] else "🔴 LIVE (real money)"

    logger.info(f"Live trading config loaded — mode: {mode_str}")
    logger.info(
        f"  max_position=${cfg['max_position_size']} | "
        f"daily_loss_limit=${cfg['daily_loss_limit']} | "
        f"max_slippage={cfg['max_slippage']*100:.1f}%"
    )

    return cfg, private_key, address
