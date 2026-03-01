#!/bin/bash
# diagnose.sh — Run this on your machine to capture exact system state.
# Outputs a full report to /tmp/bot_diagnosis.txt
# Usage: bash diagnose.sh | tee /tmp/bot_diagnosis.txt

echo "════════════════════════════════════════════════════════"
echo "  BOT SYSTEM DIAGNOSIS — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════════════════════"

# ── 1. Process state ──────────────────────────────────────────────────────────
echo ""
echo "━━━ PROCESSES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ps aux | grep -E "python|bot|monitor|openclaw" | grep -v grep || echo "(none found)"

echo ""
echo "━━━ PYTHON PROCESSES (detailed) ━━━━━━━━━━━━━━━━━━━━━━━"
for pid in $(pgrep python3 2>/dev/null); do
    echo "--- PID $pid ---"
    cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' '; echo
    echo "  CPU/MEM: $(ps -p $pid -o %cpu,%mem --no-headers 2>/dev/null)"
    echo "  Status:  $(cat /proc/$pid/status 2>/dev/null | grep -E '^State:' | head -1)"
done

# ── 2. Log files ──────────────────────────────────────────────────────────────
echo ""
echo "━━━ LOG FILES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for f in \
    /tmp/ultimate_v4_fixed.log \
    /tmp/monitor_v4.log \
    /tmp/bot_heartbeat.txt \
    /tmp/alerts_v4.log \
    /tmp/errors_v4.log \
    /tmp/trades_v4.log \
    /tmp/blocked_v4.log \
    /root/.openclaw/workspace/ultimate_v4_fixed.log \
    /root/.openclaw/workspace/bot.log; do
    if [[ -f "$f" ]]; then
        SIZE=$(wc -c < "$f")
        LINES=$(wc -l < "$f")
        MTIME=$(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1)
        echo "EXISTS  $SIZE bytes  $LINES lines  modified $MTIME  — $f"
        if [[ $SIZE -gt 0 ]]; then
            echo "  Last 3 lines:"
            tail -3 "$f" | sed 's/^/    /'
        fi
    else
        echo "MISSING — $f"
    fi
done

# ── 3. Data files ─────────────────────────────────────────────────────────────
echo ""
echo "━━━ DATA FILES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
WORKSPACE="/root/.openclaw/workspace"

for f in \
    "$WORKSPACE/wallet_v4_production.json" \
    "$WORKSPACE/wallet.json" \
    "$WORKSPACE/memory/trades.json" \
    "$WORKSPACE/trades_v4.json" \
    "$WORKSPACE/memory/wallet.json" \
    "$WORKSPACE/memory/memory.db"; do
    if [[ -f "$f" ]]; then
        SIZE=$(wc -c < "$f")
        echo "EXISTS  $SIZE bytes — $f"
        # Print content for JSON files
        if [[ "$f" == *.json && $SIZE -lt 5000 ]]; then
            cat "$f" | python3 -m json.tool 2>/dev/null | head -30 | sed 's/^/  /'
        fi
    else
        echo "MISSING — $f"
    fi
done

# ── 4. Find ALL json files in workspace ───────────────────────────────────────
echo ""
echo "━━━ ALL JSON FILES IN WORKSPACE ━━━━━━━━━━━━━━━━━━━━━━"
find "$WORKSPACE" -name "*.json" -type f 2>/dev/null | while read f; do
    SIZE=$(wc -c < "$f")
    echo "  $SIZE bytes — $f"
done

# ── 5. Heartbeat check ────────────────────────────────────────────────────────
echo ""
echo "━━━ HEARTBEAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
HB="/tmp/bot_heartbeat.txt"
if [[ -f "$HB" ]]; then
    echo "File exists:"
    cat "$HB"
    HB_TS=$(python3 -c "import json; print(json.load(open('$HB'))['ts'])" 2>/dev/null || echo "0")
    HB_AGE=$(python3 -c "import time; print(f'{(time.time()-$HB_TS):.0f} seconds old')" 2>/dev/null)
    echo "Age: $HB_AGE"
else
    echo "MISSING — monitor either never started or crashed on startup"
fi

# ── 6. PYTHONUNBUFFERED check ─────────────────────────────────────────────────
echo ""
echo "━━━ ENVIRONMENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for pid in $(pgrep python3 2>/dev/null); do
    echo "PID $pid environment:"
    cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep -E "PYTHON|PATH|HOME" | sed 's/^/  /'
done

# ── 7. The stuck ETH trade ────────────────────────────────────────────────────
echo ""
echo "━━━ STUCK TRADE LOOKUP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
# Search ALL json files for any trade data
for f in $(find "$WORKSPACE" -name "*.json" 2>/dev/null); do
    if python3 -c "
import json, sys
d = json.load(open('$f'))
found = False
def search(obj):
    global found
    if isinstance(obj, dict):
        if any(k in obj for k in ['entry_price', 'side', 'coin', 'YES', 'NO']):
            found = True
            print(f'  FOUND in $f: {list(obj.keys())[:8]}')
        for v in obj.values():
            search(v)
    elif isinstance(obj, list):
        for item in obj:
            search(item)
search(d)
" 2>/dev/null; then
        echo "  (above contains trade-like data)"
    fi
done

# ── 8. Test logging right now ─────────────────────────────────────────────────
echo ""
echo "━━━ LOGGING TEST (live) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TEST_LOG="/tmp/logging_test_$(date +%s).log"
python3 -u - << 'PYEOF' >> "$TEST_LOG" 2>&1
import logging, sys, time
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    force=True
)
logging.info("LOGGING TEST: stdout works")

import logging as L
fh = L.FileHandler("/tmp/file_logging_test.log")
fh.setFormatter(L.Formatter("%(asctime)s %(message)s"))
root = L.getLogger()
root.addHandler(fh)
L.info("LOGGING TEST: file handler works")
PYEOF
echo "stdout capture: $(cat $TEST_LOG)"
echo "file capture:   $(cat /tmp/file_logging_test.log 2>/dev/null || echo EMPTY)"
rm -f "$TEST_LOG" /tmp/file_logging_test.log

echo ""
echo "════════════════════════════════════════════════════════"
echo "  DIAGNOSIS COMPLETE — paste output to Claude"
echo "════════════════════════════════════════════════════════"
