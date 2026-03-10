#!/bin/bash
# send_final_report.sh - Run this at 17:30 PM to send final report

echo "=== 12-HOUR MISSION COMPLETE ==="
echo "Time: $(date)"
echo ""

echo "1. CHECKING DELIVERABLES..."
echo ""

# Check Strategy Builder
echo "📊 STRATEGY BUILDER:"
if [ -f "/root/.openclaw/workspace/NEW_STRATEGY_READY.txt" ]; then
    echo "  ✅ Strategy complete"
    cat /root/.openclaw/workspace/NEW_STRATEGY_READY.txt
else
    echo "  ⚠️  Strategy status unknown - check subagent logs"
fi
echo ""

# Check Dashboard Builder
echo "🖥️  DASHBOARD BUILDER:"
if [ -f "/root/.openclaw/workspace/DASHBOARD_URL.txt" ]; then
    echo "  ✅ Dashboard ready"
    echo "  🌐 URL: $(cat /root/.openclaw/workspace/DASHBOARD_URL.txt)"
else
    echo "  ⚠️  Dashboard URL not found - check subagent logs"
fi
echo ""

# Check Use Case Researcher
echo "💰 USE CASE RESEARCHER:"
if [ -f "/root/.openclaw/workspace/USE_CASES_REPORT.md" ]; then
    echo "  ✅ Report complete"
    ls -la /root/.openclaw/workspace/USE_CASES_REPORT.md
else
    echo "  ⚠️  Report not found - check subagent logs"
fi
echo ""

echo "=== END OF REPORT ==="
