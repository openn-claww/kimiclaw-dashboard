#!/bin/bash
# setup.sh — One-command deployment with full validation.
#
# Creates:
#   status.sh   — Show bot running status, balance, open trades
#   trades.sh   — Show all trades with PnL
#   health.sh   — System health (CPU, memory, processes)
#   restart.sh  — Clean restart (kill all, start fresh)
#   settle.sh   — Manually check and settle open trades
#
# Usage: ./setup.sh [--validate-only]

set -euo pipefail

WORKSPACE="/root/.openclaw/workspace"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
BLUE='\033[0;34m'; NC='\033[0m'

log_ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $*"; }
log_err()  { echo -e "${RED}[✗]${NC} $*"; }
log_info() { echo -e "${BLUE}[→]${NC} $*"; }

VALIDATE_ONLY=false
[[ "${1:-}" == "--validate-only" ]] && VALIDATE_ONLY=true

echo ""
echo "════════════════════════════════════════════"
echo "  BOT SETUP — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════════"
echo ""

# ── Step 1: Validate environment ─────────────────────────────────────────────
log_info "Step 1: Validating environment..."

ERRORS=0

# Python 3
if python3 --version &>/dev/null; then
    log_ok "Python 3: $(python3 --version)"
else
    log_err "Python 3 not found"; ERRORS=$((ERRORS+1))
fi

# Required packages
for pkg in psutil; do
    if python3 -c "import $pkg" &>/dev/null; then
        log_ok "Python package: $pkg"
    else
        log_warn "Missing package: $pkg — installing..."
        pip3 install "$pkg" --break-system-packages --quiet
        log_ok "Installed: $pkg"
    fi
done

# Workspace directories
for dir in "$WORKSPACE" "$WORKSPACE/pids" "$WORKSPACE/memory"; do
    if [[ -d "$dir" ]]; then
        log_ok "Directory: $dir"
    else
        mkdir -p "$dir"
        log_ok "Created: $dir"
    fi
done

# Required bot files
for f in "ultimate_bot_v4_fixed.py" "process_controller.py" \
          "trade_manager.py" "logger.py" "monitor.py"; do
    if [[ -f "$SCRIPT_DIR/$f" ]]; then
        log_ok "File: $f"
    else
        log_warn "Not found: $SCRIPT_DIR/$f (may need to copy manually)"
    fi
done

# Wallet file
if [[ -f "$WORKSPACE/wallet_v4_production.json" ]]; then
    balance=$(python3 -c "
import json
d = json.load(open('$WORKSPACE/wallet_v4_production.json'))
print(f\"\${d.get('balance_usdc', 0):.4f}\")
" 2>/dev/null || echo "?")
    log_ok "Wallet found: \$$balance USDC"
else
    log_warn "Wallet file missing — will be created on first run"
    python3 -c "
import json
from pathlib import Path
p = Path('$WORKSPACE/wallet_v4_production.json')
p.write_text(json.dumps({'balance_usdc': 500.0, 'total_pnl': 0.0,
                          'trades_won': 0, 'trades_lost': 0}, indent=2))
print('Created default wallet: \$500.00')
"
fi

if [[ $ERRORS -gt 0 ]]; then
    log_err "$ERRORS validation error(s). Fix before continuing."
    exit 1
fi

log_ok "All validations passed."
echo ""

[[ "$VALIDATE_ONLY" == "true" ]] && { log_info "Validate-only mode. Exiting."; exit 0; }

# ── Step 2: Emergency stop any running bots ──────────────────────────────────
log_info "Step 2: Stopping any running bot instances..."
if [[ -x "$SCRIPT_DIR/emergency_stop.sh" ]]; then
    "$SCRIPT_DIR/emergency_stop.sh" || true
else
    log_warn "emergency_stop.sh not found or not executable"
fi
sleep 2

# ── Step 3: Create utility scripts ───────────────────────────────────────────
log_info "Step 3: Creating utility scripts..."

# status.sh
cat > "$SCRIPT_DIR/status.sh" << 'HEREDOC'
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
HEREDOC
chmod +x "$SCRIPT_DIR/status.sh"
log_ok "Created: status.sh"

# trades.sh
cat > "$SCRIPT_DIR/trades.sh" << 'HEREDOC'
#!/bin/bash
# trades.sh — Show all trades with PnL
python3 /root/.openclaw/workspace/../trade_manager.py list 2>/dev/null || \
python3 -c "
import json
from pathlib import Path

f = Path('/root/.openclaw/workspace/trades_v4.json')
if not f.exists():
    print('No trades file found.')
    exit(0)

trades = json.loads(f.read_text())
if not trades:
    print('No trades recorded.')
    exit(0)

print(f\"\n{'─'*80}\")
print(f\"{'ID':<22} {'Coin':<6} {'Side':<5} {'TF':<5} {'Entry':<8} {'Status':<8} {'PnL':>8}\")
print(f\"{'─'*80}\")
for t in sorted(trades.values(), key=lambda x: x.get('entry_time', 0)):
    pnl = t.get('net_pnl', 0)
    pnl_str = f'+{pnl:.4f}' if pnl >= 0 else f'{pnl:.4f}'
    status = t.get('status', '?')
    icon = '✅' if status == 'won' else ('❌' if status == 'lost' else '⏳')
    print(f\"{t.get('trade_id','?')[:22]:<22} {t.get('coin',''):<6} {t.get('side',''):<5} {t.get('timeframe',''):<5} {t.get('entry_price',0):<8.3f} {icon+status:<8} {pnl_str:>8}\")
print(f\"{'─'*80}\n\")
"
HEREDOC
chmod +x "$SCRIPT_DIR/trades.sh"
log_ok "Created: trades.sh"

# health.sh
cat > "$SCRIPT_DIR/health.sh" << 'HEREDOC'
#!/bin/bash
# health.sh — System health check
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 monitor.py dashboard
HEREDOC
chmod +x "$SCRIPT_DIR/health.sh"
log_ok "Created: health.sh"

# restart.sh
cat > "$SCRIPT_DIR/restart.sh" << 'HEREDOC'
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
PYTHONUNBUFFERED=1 nohup python3 -u ultimate_bot_v4_fixed.py \
    >> /tmp/ultimate_v4_fixed.log 2>&1 &
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
HEREDOC
chmod +x "$SCRIPT_DIR/restart.sh"
log_ok "Created: restart.sh"

# settle.sh
cat > "$SCRIPT_DIR/settle.sh" << 'HEREDOC'
#!/bin/bash
# settle.sh — Manually check and settle all open trades
cd "$(dirname "${BASH_SOURCE[0]}")"
echo "Checking open trades for settlement..."
python3 trade_manager.py settle
echo ""
python3 trade_manager.py status
HEREDOC
chmod +x "$SCRIPT_DIR/settle.sh"
log_ok "Created: settle.sh"

# ── Step 4: Make all .sh files executable ────────────────────────────────────
chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true
log_ok "All scripts marked executable"

# ── Step 5: Verify setup ─────────────────────────────────────────────────────
log_info "Step 4: Final verification..."
./setup.sh --validate-only

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "════════════════════════════════════════════"
echo ""
echo "  Available commands:"
echo "  ./status.sh    — Bot status, balance, open trades"
echo "  ./trades.sh    — All trades with PnL"
echo "  ./health.sh    — System health dashboard"
echo "  ./restart.sh   — Clean restart"
echo "  ./settle.sh    — Settle open trades manually"
echo "  ./emergency_stop.sh  — Kill everything immediately"
echo ""
echo "  To start the bot:"
echo "  PYTHONUNBUFFERED=1 nohup python3 -u ultimate_bot_v4_fixed.py \\"
echo "      >> /tmp/ultimate_v4_fixed.log 2>&1 &"
echo ""
echo "  CRITICAL: Always use 'python3 -u' (unbuffered) to prevent"
echo "  0-byte log files when using nohup."
echo ""
