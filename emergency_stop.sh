#!/bin/bash
# emergency_stop.sh — Kill ALL bot and monitor processes
set -euo pipefail

echo "[STOP] $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "[STOP] Killing all bot processes..."

# Kill ALL ultimate_bot variants (fixed, production, v2, v3, etc.)
pkill -9 -f "ultimate_bot" 2>/dev/null || true
pkill -9 -f "strictriskbot" 2>/dev/null || true
pkill -9 -f "adaptive_trader" 2>/dev/null || true
pkill -9 -f "ai_trader" 2>/dev/null || true

echo "[STOP] Killing all monitor processes..."

# Kill ALL monitor variants
pkill -9 -f "monitor.py" 2>/dev/null || true
pkill -9 -f "bot_health_monitor" 2>/dev/null || true
pkill -9 -f "bot_monitor" 2>/dev/null || true
pkill -9 -f "health_monitor" 2>/dev/null || true
pkill -9 -f "discord_monitor" 2>/dev/null || true
pkill -9 -f "telegram_monitor" 2>/dev/null || true

echo "[STOP] Cleaning up PID files..."
rm -f /root/.openclaw/workspace/pids/*.pid 2>/dev/null || true

echo "[STOP] Verifying..."
sleep 1

# Check if anything is still running
RUNNING=$(ps aux | grep -E "(ultimate_bot|monitor)" | grep -v grep | grep -v "argusagent" | wc -l)

if [ "$RUNNING" -eq 0 ]; then
    echo "[STOP] ✅ All processes killed successfully"
else
    echo "[STOP] ⚠️  $RUNNING process(es) still running:"
    ps aux | grep -E "(ultimate_bot|monitor)" | grep -v grep | grep -v "argusagent" || true
fi
