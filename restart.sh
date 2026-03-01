#!/bin/bash
# restart.sh — Clean restart: kill everything, start fresh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "[RESTART] $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "[RESTART] Stopping all processes..."
./emergency_stop.sh

sleep 3

echo "[RESTART] Validating environment..."
./setup.sh --validate-only

echo "[RESTART] Starting bot..."
# Use the PRODUCTION bot (not fixed)
PYTHONUNBUFFERED=1 nohup python3 -u ultimate_bot_v4_production.py \
    >> /tmp/ultimate_v4_production.log 2>&1 &
BOT_PID=$!
echo "[RESTART] Bot started with PID $BOT_PID"

sleep 2

echo "[RESTART] Starting monitor..."
PYTHONUNBUFFERED=1 nohup python3 -u monitor.py start \
    >> /tmp/monitor_v4.log 2>&1 &
MON_PID=$!
echo "[RESTART] Monitor started with PID $MON_PID"

sleep 2
./status.sh
