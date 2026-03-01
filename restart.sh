#!/bin/bash
# restart.sh — Safe restart with duplicate process prevention

set -e

WORKSPACE="/root/.openclaw/workspace"
LOCKFILE="$WORKSPACE/bot.lock"
BOT="ultimate_bot_v4_production.py"  # Canonical name — never change this
LOGFILE="$WORKSPACE/bot.log"

echo "[restart.sh] $(date -u '+%Y-%m-%d %H:%M:%S UTC') — Starting restart"

# Step 1: Check if already running via lock
if [ -f "$LOCKFILE" ]; then
    EXISTING_PID=$(cat "$LOCKFILE" 2>/dev/null)
    if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "[restart.sh] Bot running as PID $EXISTING_PID — stopping..."
        kill -TERM "$EXISTING_PID"
        sleep 3
        # Force kill if still alive
        kill -0 "$EXISTING_PID" 2>/dev/null && kill -9 "$EXISTING_PID" 2>/dev/null || true
    fi
fi

# Step 2: Kill any stray variants (catches bots started without restart.sh)
pkill -f "ultimate_bot" 2>/dev/null || true
pkill -f "monitor.py" 2>/dev/null || true
sleep 2

# Step 3: Verify clean slate
REMAINING=$(ps aux | grep -E "ultimate_bot" | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "[restart.sh] ERROR: $REMAINING processes still running after kill. Aborting."
    ps aux | grep -E "ultimate_bot" | grep -v grep
    exit 1
fi

# Step 4: Clean stale lockfile
rm -f "$LOCKFILE"

# Step 5: Start the bot
echo "[restart.sh] Starting $BOT..."
cd "$WORKSPACE"
nohup python3 "$BOT" >> "$LOGFILE" 2>&1 &

# Step 6: Verify started and lock acquired
sleep 3
if [ -f "$LOCKFILE" ]; then
    BOT_PID=$(cat "$LOCKFILE")
    echo "[restart.sh] ✓ Bot started — PID $BOT_PID"
    echo "[restart.sh] Monitor: tail -f $LOGFILE"
else
    echo "[restart.sh] ERROR: Bot started but lock file not created. Check logs:"
    tail -20 "$LOGFILE"
    exit 1
fi
