#!/bin/bash
# emergency_stop.sh — Guaranteed kill of ALL bot processes.
#
# Why pkill fails on 66+ processes:
#   pkill returns BEFORE processes die. When Python catches SIGTERM
#   and spawns cleanup threads, those threads become new targets.
#   This script uses a 3-phase approach: SIGTERM → wait → SIGKILL → verify.
#
# Usage:
#   ./emergency_stop.sh           # Kill everything
#   ./emergency_stop.sh --dry-run # Show what would be killed, don't kill

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[DRY RUN] No processes will be killed"
fi

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Keywords to match ─────────────────────────────────────────────────────────
BOT_PATTERNS=(
    "ultimate_bot_v4"
    "ultimate_bot"
    "bot_v4_fixed"
    "bot_v4_production"
    "health_monitor"
    "monitor.py"
    "process_controller"
)

MY_PID=$$
MY_PPID=$PPID

echo ""
echo "════════════════════════════════════════"
echo "  EMERGENCY STOP — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════"
echo ""

# ── Step 1: Find all matching PIDs ───────────────────────────────────────────
declare -a TARGET_PIDS=()

for pattern in "${BOT_PATTERNS[@]}"; do
    while IFS= read -r pid; do
        # Skip self, parent shell, and empty
        [[ -z "$pid" ]]            && continue
        [[ "$pid" == "$MY_PID" ]]  && continue
        [[ "$pid" == "$MY_PPID" ]] && continue

        # Check it's still alive
        if kill -0 "$pid" 2>/dev/null; then
            TARGET_PIDS+=("$pid")
        fi
    done < <(pgrep -f "$pattern" 2>/dev/null || true)
done

# Deduplicate
TARGET_PIDS=($(printf '%s\n' "${TARGET_PIDS[@]}" | sort -u))

if [[ ${#TARGET_PIDS[@]} -eq 0 ]]; then
    log_info "No bot/monitor processes found. Nothing to kill."
else
    log_warn "Found ${#TARGET_PIDS[@]} process(es) to terminate:"
    for pid in "${TARGET_PIDS[@]}"; do
        cmd=$(ps -p "$pid" -o args= 2>/dev/null | head -c 80 || echo "unknown")
        echo "  PID $pid: $cmd"
    done
fi

echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY RUN complete. Exiting without killing."
    exit 0
fi

if [[ ${#TARGET_PIDS[@]} -eq 0 ]]; then
    log_info "Nothing to do."
else
    # ── Phase 1: SIGTERM (graceful shutdown) ──────────────────────────────────
    log_info "Phase 1: Sending SIGTERM to ${#TARGET_PIDS[@]} process(es)..."
    for pid in "${TARGET_PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done

    # Wait up to 5 seconds for graceful exit
    sleep 3
    STILL_ALIVE=()
    for pid in "${TARGET_PIDS[@]}"; do
        kill -0 "$pid" 2>/dev/null && STILL_ALIVE+=("$pid") || true
    done

    if [[ ${#STILL_ALIVE[@]} -eq 0 ]]; then
        log_info "All processes exited gracefully after SIGTERM."
    else
        log_warn "${#STILL_ALIVE[@]} process(es) survived SIGTERM. Escalating..."

        # ── Phase 2: Kill child processes first ───────────────────────────────
        log_info "Phase 2: Killing child process trees..."
        for pid in "${STILL_ALIVE[@]}"; do
            # Get all children recursively
            children=$(pgrep -P "$pid" 2>/dev/null || true)
            for child in $children; do
                log_warn "  Killing child PID $child of $pid"
                kill -KILL "$child" 2>/dev/null || true
            done
        done
        sleep 1

        # ── Phase 3: SIGKILL survivors ────────────────────────────────────────
        log_info "Phase 3: Sending SIGKILL..."
        for pid in "${STILL_ALIVE[@]}"; do
            kill -KILL "$pid" 2>/dev/null || true
            log_warn "  SIGKILL sent to PID $pid"
        done
        sleep 2
    fi

    # ── Verification ─────────────────────────────────────────────────────────
    ZOMBIES=()
    for pid in "${TARGET_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            ZOMBIES+=("$pid")
        fi
    done

    if [[ ${#ZOMBIES[@]} -eq 0 ]]; then
        log_info "✓ All ${#TARGET_PIDS[@]} process(es) confirmed dead."
    else
        log_error "⚠ ${#ZOMBIES[@]} process(es) survived SIGKILL: ${ZOMBIES[*]}"
        log_error "These may be zombie processes — check with: ps aux | grep defunct"
    fi
fi

# ── Step 2: Clean up PID files ────────────────────────────────────────────────
PID_DIR="/root/.openclaw/workspace/pids"
if [[ -d "$PID_DIR" ]]; then
    log_info "Removing stale PID files in $PID_DIR..."
    rm -f "$PID_DIR"/*.pid "$PID_DIR"/*.lock 2>/dev/null || true
fi

# ── Step 3: Clean up lock files ───────────────────────────────────────────────
for lockfile in /tmp/*.lock /tmp/bot*.lock; do
    [[ -f "$lockfile" ]] && rm -f "$lockfile" && log_info "Removed: $lockfile"
done

# ── Step 4: Final process scan ───────────────────────────────────────────────
echo ""
log_info "Final scan for remaining bot processes:"
REMAINING=0
for pattern in "${BOT_PATTERNS[@]}"; do
    while IFS= read -r pid; do
        [[ -z "$pid" || "$pid" == "$MY_PID" ]] && continue
        if kill -0 "$pid" 2>/dev/null; then
            cmd=$(ps -p "$pid" -o args= 2>/dev/null | head -c 60 || echo "unknown")
            log_warn "  Still running: PID $pid — $cmd"
            REMAINING=$((REMAINING + 1))
        fi
    done < <(pgrep -f "$pattern" 2>/dev/null || true)
done

if [[ $REMAINING -eq 0 ]]; then
    echo ""
    log_info "✓ EMERGENCY STOP COMPLETE. Bot system fully stopped."
    log_info "  Safe to restart with: ./setup.sh"
else
    echo ""
    log_error "✗ $REMAINING process(es) could not be killed."
    log_error "  Manual intervention required: sudo kill -9 <pid>"
fi

echo ""
exit $REMAINING
