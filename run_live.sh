#!/bin/bash
# run_live.sh - Run bot with LIVE trading enabled

export POLY_PAPER_TRADING=false
export POLY_LIVE_ENABLED=true
export POLY_DRY_RUN=false
export POLY_PRIVATE_KEY="0xbbb07245af22a13b1d3ee5dd2ccfb7c2196d3ee038e43ee15dccb9869187b806"
export POLY_ADDRESS="0x557A656C110a9eFdbFa28773DE4aCc2c3924a274"
export CHAINSTACK_NODE="https://polygon-mainnet.core.chainstack.com/b9d9af57530a7c7f59d9f2bf0c3e7052"
export MAX_SINGLE_TRADE_USD=5.0
export WARMUP_TRADE_COUNT=20
export WARMUP_MAX_BET=1.0

rm -f /tmp/master_bot_v6.lock /root/.openclaw/workspace/bot.lock
cd /root/.openclaw/workspace
exec python3 master_bot_v6_polyclaw_integration.py
