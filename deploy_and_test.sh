#!/bin/bash
# deploy_and_test.sh - Deploy mean reversion strategy and start testing

cd /root/.openclaw/workspace

echo "=========================================="
echo "MEAN REVERSION STRATEGY DEPLOYMENT"
echo "=========================================="
echo ""

# Set environment variables
export POLY_PAPER_TRADING=true
export MEANREV_ENABLED=true
export MEANREV_PAPER_MODE=true
export MEANREV_BANKROLL_PCT=0.20
export VIRTUAL_BANKROLL=686.93
export MAX_POSITIONS=8

echo "Configuration:"
echo "  Paper Trading: $POLY_PAPER_TRADING"
echo "  Mean Rev Enabled: $MEANREV_ENABLED"
echo "  Mean Rev Paper: $MEANREV_PAPER_MODE"
echo "  Mean Rev Allocation: $MEANREV_BANKROLL_PCT (20%)"
echo "  Total Bankroll: $VIRTUAL_BANKROLL"
echo ""

# Create directories
mkdir -p logs
mkdir -p reports

# Check if already running
if pgrep -f "master_bot_v6_with_mean_reversion.py" > /dev/null; then
    echo "⚠️  Bot already running! Stopping previous instance..."
    pkill -f "master_bot_v6_with_mean_reversion.py"
    sleep 3
fi

if pgrep -f "continuous_strategy_tester.py" > /dev/null; then
    echo "⚠️  Tester already running! Stopping previous instance..."
    pkill -f "continuous_strategy_tester.py"
    sleep 2
fi

echo "✅ Environment ready"
echo ""

# Start the continuous tester in background
echo "Starting continuous strategy tester..."
nohup python3 continuous_strategy_tester.py > logs/tester.log 2>&1 &
TESTER_PID=$!
echo "✅ Tester started (PID: $TESTER_PID)"
echo ""

# Start the bot with mean reversion
echo "Starting Master Bot V6 with Mean Reversion..."
echo "This will run for 1-2 hours of paper trading..."
echo ""

# Run for 2 hours (7200 seconds) then stop
timeout 7200 python3 master_bot_v6_with_mean_reversion.py 2>&1 | tee logs/bot_$(date +%Y%m%d_%H%M).log &
BOT_PID=$!
echo "✅ Bot started (PID: $BOT_PID)"
echo ""

echo "=========================================="
echo "DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Monitoring:"
echo "  Bot PID: $BOT_PID"
echo "  Tester PID: $TESTER_PID"
echo ""
echo "Log files:"
echo "  Bot log: logs/bot_*.log"
echo "  Tester log: logs/tester.log"
echo ""
echo "Status files:"
echo "  Health: master_v6_meanrev_health.json"
echo "  Trades: master_v6_meanrev_trades.json"
echo "  Mean Rev Trades: mean_reversion_trades.json"
echo ""
echo "To stop manually:"
echo "  kill $BOT_PID"
echo "  kill $TESTER_PID"
echo ""
echo "Bot will run for 2 hours then automatically stop."
echo "Check logs for real-time performance."
echo ""

# Save PIDs
echo "$BOT_PID" > /tmp/bot_v6_meanrev.pid
echo "$TESTER_PID" > /tmp/tester_v6_meanrev.pid

# Wait for bot to finish
wait $BOT_PID
BOT_EXIT=$?

echo ""
echo "=========================================="
echo "BOT FINISHED (Exit code: $BOT_EXIT)"
echo "=========================================="
echo ""

# Generate reports
echo "Generating performance reports..."
python3 strategy_performance_tracker.py report 2>/dev/null || echo "Report generation skipped"

echo ""
echo "Results:"
ls -la master_v6_meanrev_*.json 2>/dev/null || echo "No result files yet"
ls -la mean_reversion_*.json 2>/dev/null || echo "No mean reversion files yet"

echo ""
echo "=========================================="
echo "PHASE 1 COMPLETE"
echo "=========================================="

# Stop tester
kill $TESTER_PID 2>/dev/null

echo ""
echo "To continue with 24/7 testing, run:"
echo "  python3 continuous_strategy_tester.py"
