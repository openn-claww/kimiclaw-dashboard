#!/bin/bash
# start_v6_with_monitor.sh - Start V6 bot with health monitoring

cd /root/.openclaw/workspace

echo "============================================================"
echo "           V6 BOT + HEALTH MONITOR LAUNCHER"
echo "============================================================"
echo ""

# Check if already running
if [ -f "v6_health_monitor.pid" ]; then
    OLD_PID=$(cat v6_health_monitor.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "⚠️  V6 Health Monitor already running (PID: $OLD_PID)"
        echo "    Stop it first with: kill $OLD_PID"
        exit 1
    fi
fi

if [ -f "v6_bot.pid" ]; then
    OLD_PID=$(cat v6_bot.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "⚠️  V6 Bot already running (PID: $OLD_PID)"
        echo "    Stop it first with: kill $OLD_PID"
        exit 1
    fi
fi

echo "🟢 Starting V6 Bot + Health Monitor..."
echo ""
echo "Configuration:"
echo "  Virtual Balance: $250"
echo "  Mode: Paper Trading"
echo "  Strategy: Arb + News + Kelly"
echo ""

# Kill any existing processes
pkill -f "master_bot_v6_polyclaw" 2>/dev/null
pkill -f "v6_health_monitor" 2>/dev/null
sleep 2

# Start health monitor (it will start the bot)
nohup python3 v6_health_monitor.py >> v6_health_monitor.log 2>&1 &
MONITOR_PID=$!
echo $MONITOR_PID > v6_health_monitor.pid

echo "✅ V6 Health Monitor started (PID: $MONITOR_PID)"
echo ""
echo "Monitor Logs:"
echo "  Bot Output: tail -f v6_bot_output.log"
echo "  Health Status: tail -f v6_health_monitor.log"
echo "  Health JSON: cat v6_health_monitor.json"
echo ""
echo "Commands:"
echo "  Stop All:    bash stop_v6.sh"
echo "  Check Status: bash status_v6.sh"
echo "  View Stats:  python3 v6_stats.py"
echo ""
echo "Waiting for bot to start..."
sleep 5

# Check if running
if ps -p $MONITOR_PID > /dev/null 2>&1; then
    echo "✅ V6 System is RUNNING"
    
    # Try to get bot PID
    if [ -f "v6_bot.pid" ]; then
        BOT_PID=$(cat v6_bot.pid)
        if ps -p $BOT_PID > /dev/null 2>&1; then
            echo "   Bot PID: $BOT_PID"
        fi
    fi
    echo "   Monitor PID: $MONITOR_PID"
else
    echo "❌ Failed to start - check v6_health_monitor.log"
    tail -20 v6_health_monitor.log
fi

echo ""
echo "============================================================"
