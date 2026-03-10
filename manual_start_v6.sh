#!/bin/bash
# manual_start_v6.sh - Manual V6 Bot Starter

cd /root/.openclaw/workspace

echo "============================================================"
echo "           V6 BOT MANUAL STARTER"
echo "============================================================"
echo ""

# Kill any existing
pkill -f "master_bot_v6_polyclaw" 2>/dev/null
pkill -f "v6_health_monitor" 2>/dev/null
sleep 2

# Set environment
echo "Setting environment variables..."
export POLY_PAPER_TRADING=true
export POLY_VIRTUAL_BALANCE=250
export NEWSAPI_KEY_1=06dc3ef927d3416aba1b6ece3fb57716
export NEWSAPI_KEY_2=9bd8097226574cd3932fa65081029738
export NEWSAPI_KEY_3=a7dce4fae15c486c811af014a1094728
export GNEWS_KEY=01f1ea1cc4375f5a24c0afb3d953e4d4
export CURRENTS_KEY=06dc3ef927d3416aba1b6ece3fb57716

echo "Environment set:"
echo "  POLY_PAPER_TRADING: $POLY_PAPER_TRADING"
echo "  POLY_VIRTUAL_BALANCE: $POLY_VIRTUAL_BALANCE"
echo "  GNEWS_KEY: ${GNEWS_KEY:0:10}..."
echo ""

# Start bot in background
echo "Starting V6 Bot..."
nohup python3 master_bot_v6_polyclaw_integration.py > v6_bot_output.log 2>&1 &
echo $! > v6_bot.pid
sleep 3

# Check if running
if ps -p $(cat v6_bot.pid) > /dev/null 2>&1; then
    echo "✅ V6 Bot STARTED (PID: $(cat v6_bot.pid))"
    echo ""
    echo "To monitor:"
    echo "  tail -f v6_bot_output.log"
    echo ""
    echo "To stop:"
    echo "  kill $(cat v6_bot.pid)"
    echo ""
    echo "First 10 lines of log:"
    echo "----------------------"
    head -10 v6_bot_output.log 2>/dev/null || echo "(Log not ready yet...)"
else
    echo "❌ Bot failed to start"
    echo ""
    echo "Error log:"
    echo "----------"
    cat v6_bot_output.log | tail -20
fi

echo ""
echo "============================================================"
