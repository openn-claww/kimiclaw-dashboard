#!/bin/bash
# status_v6.sh - Check V6 bot and health monitor status

cd /root/.openclaw/workspace

echo "============================================================"
echo "              V6 BOT STATUS CHECK"
echo "============================================================"
echo ""

# Check Health Monitor
if [ -f "v6_health_monitor.pid" ]; then
    PID=$(cat v6_health_monitor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "🟢 Health Monitor: RUNNING (PID: $PID)"
    else
        echo "🔴 Health Monitor: STOPPED (stale PID file)"
        rm -f v6_health_monitor.pid
    fi
else
    echo "🔴 Health Monitor: NOT RUNNING"
fi

# Check Bot
if [ -f "v6_bot.pid" ]; then
    PID=$(cat v6_bot.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "🟢 V6 Bot:        RUNNING (PID: $PID)"
    else
        echo "🔴 V6 Bot:        STOPPED (stale PID file)"
        rm -f v6_bot.pid
    fi
else
    echo "🔴 V6 Bot:        NOT RUNNING"
fi

echo ""

# Show recent logs
if [ -f "v6_health_monitor.json" ]; then
    echo "Recent Health Status:"
    echo "---------------------"
    python3 -c "
import json
try:
    with open('v6_health_monitor.json') as f:
        data = json.load(f)
    for entry in data[-5:]:
        ts = entry['timestamp'].split('T')[1].split('.')[0]
        status = entry['status']
        pid = entry.get('pid', 'N/A')
        detail = entry.get('detail', '')[:60]
        print(f'  {ts} | {status:15} | PID:{pid:6} | {detail}')
except:
    print('  No health data available')
"
fi

echo ""

# Show bot stats if available
if [ -f "master_v6_health.json" ]; then
    echo "Bot Statistics:"
    echo "---------------"
    python3 -c "
import json
try:
    with open('master_v6_health.json') as f:
        data = json.load(f)
    
    arb = data.get('arb_engine', {})
    news = data.get('news_feed', {})
    
    print(f'  Arb Trades: {arb.get(\"trades\", 0)}')
    print(f'  Arb Wins:   {arb.get(\"wins\", 0)}')
    print(f'  Arb PnL:    \${arb.get(\"pnl_usd\", 0):+.2f}')
    print(f'  News:       {news.get(\"sentiment\", \"N/A\")}')
except:
    print('  No bot statistics available')
"
fi

echo ""
echo "============================================================"
echo ""
echo "Commands:"
echo "  Start:  bash start_v6_with_monitor.sh"
echo "  Stop:   bash stop_v6.sh"
echo "  Logs:   tail -f v6_bot_output.log"
echo ""
