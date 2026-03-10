#!/bin/bash
# start_v6_paper.sh - Start V6 Paper Trading with $250 virtual balance

cd /root/.openclaw/workspace

echo "Starting V6 Paper Trading..."
echo "Virtual Balance: $250"
echo ""

# Kill any existing V6 bot
pkill -f "master_bot_v6_polyclaw" 2>/dev/null
sleep 2

# Set environment
export POLY_PAPER_TRADING=true
export POLY_VIRTUAL_BALANCE=250
export NEWSAPI_KEY_1=06dc3ef927d3416aba1b6ece3fb57716
export NEWSAPI_KEY_2=9bd8097226574cd3932fa65081029738
export NEWSAPI_KEY_3=a7dce4fae15c486c811af014a1094728
export GNEWS_KEY=01f1ea1cc4375f5a24c0afb3d953e4d4
export CURRENTS_KEY=06dc3ef927d3416aba1b6ece3fb57716

# Start bot
nohup python3 master_bot_v6_polyclaw_integration.py > v6_bot_output.log 2>&1 &
PID=$!
echo $PID > v6_bot.pid

echo "V6 Bot started with PID: $PID"
echo ""
echo "To monitor: tail -f v6_bot_output.log"
echo "To stop: kill $(cat v6_bot.pid)"
