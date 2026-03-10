#!/bin/bash
# status.sh - Check deployment status

cd /root/.openclaw/workspace

echo "=========================================="
echo "MEAN REVERSION DEPLOYMENT STATUS"
echo "=========================================="
echo ""
echo "Running Processes:"
echo "------------------"
ps aux | grep -E "(master_bot_v6_with_mean|continuous_strategy)" | grep -v grep | awk '{print $2, $11, $12}' | while read pid cmd rest; do
    echo "  PID $pid: $cmd $rest"
done
echo ""

echo "Log Files:"
echo "----------"
ls -la master_v6_meanrev_run.log 2>/dev/null && echo "  ✅ Bot log: $(wc -l < master_v6_meanrev_run.log) lines"
ls -la logs/tester.log 2>/dev/null && echo "  ✅ Tester log: $(wc -l < logs/tester.log) lines"
echo ""

echo "Health Status:"
echo "--------------"
if [ -f master_v6_meanrev_health.json ]; then
    cat master_v6_meanrev_health.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  Bot State: {data.get('bot_state', 'unknown')}\")
print(f\"  Balance: ${data.get('balance', 0):.2f}\")
print(f\"  Trades: {data.get('trade_count', 0)}\")
print(f\"  Open Positions: {data.get('open_positions', 0)}\")
print(f\"  CLOB Connected: {data.get('clob_connected', False)}\")
print(f\"  RTDS Connected: {data.get('rtds_connected', False)}\")
mr = data.get('mean_reversion', {})
print(f\"  Mean Rev Enabled: {mr.get('enabled', False)}\")
print(f\"  Mean Rev Trades: {mr.get('trades', 0)}\")
print(f\"  Mean Rev Win Rate: {mr.get('win_rate', 0)*100:.1f}%\")
print(f\"  Mean Rev P&L: ${mr.get('total_pnl', 0):+.4f}\")
" 2>/dev/null
else
    echo "  ⚠️  Health file not found"
fi
echo ""

echo "Recent Bot Activity:"
echo "--------------------"
tail -10 master_v6_meanrev_run.log 2>/dev/null | grep -E "(ENTRY|EXIT|MeanRev)" | tail -5 || echo "  No recent trade activity"
echo ""

echo "Strategy Performance:"
echo "---------------------"
python3 strategy_performance_tracker.py report 2>/dev/null || echo "  ⚠️  Performance tracker not available"
echo ""

echo "=========================================="
echo "To monitor in real-time:"
echo "  tail -f master_v6_meanrev_run.log"
echo "  tail -f logs/tester.log"
echo "  watch -n 5 ./status.sh"
echo "=========================================="
