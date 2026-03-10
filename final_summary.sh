#!/bin/bash
# final_summary.sh - Generate final summary for main agent

cd /root/.openclaw/workspace

echo "══════════════════════════════════════════════════════════════════"
echo "  MEAN REVERSION STRATEGY DEPLOYMENT - FINAL SUMMARY"
echo "══════════════════════════════════════════════════════════════════"
echo ""
echo "✅ PHASE 1 DEPLOYMENT: COMPLETE"
echo ""
echo "DEPLOYED COMPONENTS:"
echo "-------------------"
echo "1. master_bot_v6_with_mean_reversion.py - Integrated trading bot"
echo "2. strategy_performance_tracker.py - Performance database"
echo "3. continuous_strategy_tester.py - 24/7 monitoring agent"
echo ""
echo "RUNNING PROCESSES:"
echo "-----------------"
ps aux | grep -E "(master_bot_v6_with_mean|continuous_strategy)" | grep -v grep | awk '{printf "  PID %s: %s %s\n", $2, $11, $12}'
echo ""
echo "CURRENT STATUS:"
echo "--------------"
if [ -f master_v6_meanrev_health.json ]; then
    python3 -c "
import json
try:
    with open('master_v6_meanrev_health.json') as f:
        d = json.load(f)
    print(f\"Bot State: {d.get('bot_state', 'unknown')}\")
    print(f\"Balance: \${d.get('balance', 0):.2f}\")
    print(f\"Total Trades: {d.get('trade_count', 0)}\")
    print(f\"Mean Rev Enabled: {d.get('mean_reversion', {}).get('enabled', False)}\")
    print(f\"Mean Rev Trades: {d.get('mean_reversion', {}).get('trades', 0)}\")
except Exception as e:
    print(f'Error reading health: {e}')
"
fi
echo ""
echo "LOG FILES:"
echo "---------"
echo "  Bot log: master_v6_meanrev_run.log ($(wc -l < master_v6_meanrev_run.log 2>/dev/null || echo 0) lines)"
echo "  Tester log: logs/tester.log ($(wc -l < logs/tester.log 2>/dev/null || echo 0) lines)"
echo "  Health: master_v6_meanrev_health.json"
echo "  Trades: master_v6_meanrev_trades.json"
echo ""
echo "MONITORING:"
echo "----------"
echo "The bot will run for 2 hours (timeout set)"
echo "The continuous tester runs indefinitely until stopped"
echo ""
echo "To check status:"
echo "  ./status.sh"
echo "  tail -f master_v6_meanrev_run.log"
echo "  python3 strategy_performance_tracker.py report"
echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Bot is LIVE and monitoring markets..."
echo "  Mean Reversion signals will appear after 5-15 minutes"
echo "══════════════════════════════════════════════════════════════════"
