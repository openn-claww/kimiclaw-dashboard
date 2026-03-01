#!/bin/bash
# status.sh — Show bot status, balance, open trades, last activity
cd "$(dirname "${BASH_SOURCE[0]}")"

echo ""
echo "━━━ BOT STATUS $(date -u '+%H:%M:%S UTC') ━━━━━━━━━━━━━━━━━━━━━"

# Process check
BOT_PIDS=$(pgrep -f "ultimate_bot_v4" 2>/dev/null | tr '\n' ' ' || echo "none")
MON_PIDS=$(pgrep -f "monitor.py" 2>/dev/null | tr '\n' ' ' || echo "none")
echo "Bot PID(s):     $BOT_PIDS"
echo "Monitor PID(s): $MON_PIDS"

# Heartbeat age
HEARTBEAT=/tmp/bot_heartbeat.txt
if [[ -f "$HEARTBEAT" ]]; then
    HB_TS=$(python3 -c "import json; print(json.load(open('$HEARTBEAT'))['ts'])" 2>/dev/null)
    HB_AGE=$(python3 -c "import time; print(f'{(time.time()-float($HB_TS)):.0f}s ago')" 2>/dev/null || echo "unknown")
    echo "Last heartbeat: $HB_AGE"
else
    echo "Last heartbeat: MISSING ⚠"
fi

# Balance + trades
python3 -c "
import json, time
from pathlib import Path

w = Path('/root/.openclaw/workspace/wallet_v4_production.json')
if w.exists():
    d = json.loads(w.read_text())
    print(f\"Balance:        \${d.get('balance_usdc', 0):.4f} USDC\")
    pnl = d.get('total_pnl', 0)
    pnl_str = f'+{pnl:.4f}' if pnl >= 0 else f'{pnl:.4f}'
    print(f\"Total PnL:      \${pnl_str}\")
    print(f\"W/L:            {d.get('trades_won',0)}W / {d.get('trades_lost',0)}L\")

t = Path('/root/.openclaw/workspace/trades_v4.json')
if t.exists():
    trades = json.loads(t.read_text())
    open_t = [x for x in trades.values() if x.get('status') == 'open']
    print(f\"Open trades:    {len(open_t)}\")
    for tr in open_t:
        age = (time.time() - tr.get('entry_time', 0)) / 60
        overdue = ' ⚠ OVERDUE' if time.time() > tr.get('window_end',0)+60 else ''
        print(f\"  → {tr.get('coin')} {tr.get('side')} {tr.get('timeframe')} @ {tr.get('entry_price'):.3f} | {age:.0f}m old{overdue}\")
"

# Log tail
LOG=/tmp/ultimate_v4_fixed.log
if [[ -f "$LOG" ]]; then
    echo ""
    echo "━━━ LAST 5 LOG LINES ━━━━━━━━━━━━━━━━━━━━━━━━"
    tail -5 "$LOG"
fi
echo ""
