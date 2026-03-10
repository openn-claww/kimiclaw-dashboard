#!/bin/bash
# set_env.sh — Safe env for $59 bankroll live trading
# Source before starting bot: source set_env.sh

cd "$(dirname "$0")"

# ── Load PolyClaw env first ──────────────────────────────
if [ -f /root/.openclaw/skills/polyclaw/.env ]; then
    source /root/.openclaw/skills/polyclaw/.env
fi

# ── Wallet ───────────────────────────────────────────────
export POLY_PRIVATE_KEY="${POLYCLAW_PRIVATE_KEY}"
export POLY_ADDRESS="0x557A656C110a9eFdbFa28773DE4aCc2c3924a274"
export CHAINSTACK_NODE="${CHAINSTACK_NODE}"

# ── Trading mode ─────────────────────────────────────────
export POLY_LIVE_ENABLED=true       # Enable live trading module
export POLY_DRY_RUN=false           # FALSE = Real money, TRUE = Paper

# ── Position sizing ($59 bankroll) ───────────────────────
export MAX_SINGLE_TRADE_USD=5.0       # $5 max per trade
export MIN_SINGLE_TRADE_USD=1.0       # $1 min per trade
export MAX_POSITION_PCT=0.08          # 8% of balance per trade
export POLY_MAX_POSITION=5.0          # For live_trading_config

# ── Risk limits ───────────────────────────────────────────
export MAX_DAILY_LOSS_PCT=0.10        # Stop at 10% daily loss ($5.90)
export POLY_DAILY_LOSS_LIMIT=5.90     # For live_trading_config
export MAX_CONSECUTIVE_LOSSES=5       # Stop after 5 losses in a row
export MAX_TOTAL_EXPOSURE_PCT=0.25    # Max 25% ($14.75) open at once
export MAX_API_ERRORS_PER_HOUR=30     # Kill switch threshold

# ── Warmup (first 20 trades capped at $1) ────────────────
export WARMUP_TRADE_COUNT=20
export WARMUP_MAX_BET=1.0

# ── Proxy (optional — get from iproyal.com / brightdata) ─
# export HTTPS_PROXY=http://user:pass@geo.iproyal.com:12321

# ── Telegram alerts ───────────────────────────────────────
# export TELEGRAM_BOT_TOKEN=your_token_here
# export TELEGRAM_CHAT_ID=your_chat_id_here

# ── OpenRouter (for hedge discovery) ─────────────────────
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY}"

echo "✅ Environment loaded"
echo "   POLY_LIVE_ENABLED: $POLY_LIVE_ENABLED"
echo "   POLY_DRY_RUN: $POLY_DRY_RUN" 
echo "   Wallet: $POLY_ADDRESS"
