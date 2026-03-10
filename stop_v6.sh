#!/bin/bash
# stop_v6.sh - Stop V6 bot and health monitor

cd /root/.openclaw/workspace

echo "Stopping V6 Bot and Health Monitor..."

# Stop health monitor
if [ -f "v6_health_monitor.pid" ]; then
    PID=$(cat v6_health_monitor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        echo "✅ Health Monitor stopped (PID: $PID)"
    fi
    rm -f v6_health_monitor.pid
fi

# Stop bot
if [ -f "v6_bot.pid" ]; then
    PID=$(cat v6_bot.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        echo "✅ V6 Bot stopped (PID: $PID)"
    fi
    rm -f v6_bot.pid
fi

# Force kill any remaining
pkill -f "master_bot_v6_polyclaw" 2>/dev/null
pkill -f "v6_health_monitor" 2>/dev/null

echo "✅ All V6 processes stopped"
