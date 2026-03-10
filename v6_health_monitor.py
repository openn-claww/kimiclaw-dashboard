#!/usr/bin/env python3
"""
Health Monitor for V6 Polyclaw Bot
Checks bot status every 60 seconds, auto-restarts on crash.
Monitors V6 paper trading with $250 virtual balance.
"""

import os
import sys
import json
import time
import signal
import subprocess
from datetime import datetime, timezone

# ── V6 Configuration ─────────────────────────────────────────────────────────
BOT_SCRIPT   = "/root/.openclaw/workspace/master_bot_v6_polyclaw_integration.py"
BOT_LOG      = "/root/.openclaw/workspace/v6_bot_output.log"
BOT_PID_FILE = "/root/.openclaw/workspace/v6_bot.pid"
BOT_ENV_FILE = "/root/.openclaw/workspace/v6_bot_env.sh"

HEALTH_LOG      = "/root/.openclaw/workspace/v6_health_monitor.json"
MONITOR_PID_FILE = "/root/.openclaw/workspace/v6_health_monitor.pid"
MAX_LOG_ENTRIES = 200
CHECK_INTERVAL  = 60  # seconds

# Environment variables for V6
V6_ENV = {
    "POLY_PAPER_TRADING": "true",
    "POLY_VIRTUAL_BALANCE": "250",
    "NEWSAPI_KEY_1": "06dc3ef927d3416aba1b6ece3fb57716",
    "NEWSAPI_KEY_2": "9bd8097226574cd3932fa65081029738",
    "NEWSAPI_KEY_3": "a7dce4fae15c486c811af014a1094728",
    "GNEWS_KEY": "01f1ea1cc4375f5a24c0afb3d953e4d4",
    "CURRENTS_KEY": "06dc3ef927d3416aba1b6ece3fb57716",
}
# ─────────────────────────────────────────────────────────────────────────────


def acquire_monitor_lock():
    """Prevent multiple health monitor instances from running."""
    if os.path.exists(MONITOR_PID_FILE):
        try:
            with open(MONITOR_PID_FILE) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"[ERROR] V6 Health monitor already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # Stale PID file

    with open(MONITOR_PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def release_monitor_lock():
    if os.path.exists(MONITOR_PID_FILE):
        os.remove(MONITOR_PID_FILE)


def is_bot_running() -> tuple[bool, int | None]:
    """Return (running: bool, pid: int | None)."""
    if not os.path.exists(BOT_PID_FILE):
        return False, None
    try:
        with open(BOT_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, ValueError, OSError):
        return False, None


def get_bot_stats() -> dict:
    """Get current bot statistics from health file."""
    stats = {
        "virtual_balance": 250.0,
        "trades": 0,
        "wins": 0,
        "pnl": 0.0,
        "running_time": 0,
    }
    
    # Try to read V6 health file
    health_files = [
        "/root/.openclaw/workspace/master_v6_health.json",
        "/root/.openclaw/workspace/v6_paper_state.json",
    ]
    
    for health_file in health_files:
        if os.path.exists(health_file):
            try:
                with open(health_file) as f:
                    data = json.load(f)
                
                arb = data.get("arb_engine", {})
                stats["trades"] = arb.get("trades", 0)
                stats["wins"] = arb.get("wins", 0)
                stats["pnl"] = arb.get("pnl_usd", 0)
                
                # Calculate running time from log
                if os.path.exists(BOT_LOG):
                    stat = os.stat(BOT_LOG)
                    stats["running_time"] = time.time() - stat.st_mtime
                    
                break
            except:
                pass
    
    return stats


def start_bot() -> tuple[bool, str]:
    """Launch the V6 bot with nohup, redirect output, save PID."""
    try:
        # Build environment string
        env_exports = " ".join([f'export {k}="{v}";' for k, v in V6_ENV.items()])
        
        # Kill any existing bot first
        if os.path.exists(BOT_PID_FILE):
            try:
                with open(BOT_PID_FILE) as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)
            except:
                pass
        
        # Start new bot
        cmd = f"({env_exports} nohup python3 {BOT_SCRIPT} >> {BOT_LOG} 2>&1 & echo $!)"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        pid_str = result.stdout.strip()
        
        if not pid_str.isdigit():
            return False, f"Could not parse PID: '{pid_str}'"

        pid = int(pid_str)
        with open(BOT_PID_FILE, "w") as f:
            f.write(str(pid))

        # Verify it's running
        time.sleep(3)
        try:
            os.kill(pid, 0)
            return True, f"V6 Bot started with PID {pid}"
        except ProcessLookupError:
            return False, f"V6 Bot died immediately (check {BOT_LOG})"

    except Exception as e:
        return False, str(e)


def append_health_log(status: str, pid: int | None, detail: str, stats: dict = None):
    """Append one entry to the JSON health log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "pid": pid,
        "detail": detail,
        "stats": stats or {},
    }

    entries = []
    if os.path.exists(HEALTH_LOG):
        try:
            with open(HEALTH_LOG) as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append(entry)
    entries = entries[-MAX_LOG_ENTRIES:]

    with open(HEALTH_LOG, "w") as f:
        json.dump(entries, f, indent=2)

    print(f"[{entry['timestamp']}] {status} | PID={pid} | {detail}")


def run_monitor():
    acquire_monitor_lock()

    def _shutdown(signum, frame):
        print("\n[MONITOR] V6 Health monitor shutting down.")
        release_monitor_lock()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"[MONITOR] V6 Health Monitor started (PID {os.getpid()})")
    print(f"[MONITOR] Watching: {BOT_SCRIPT}")
    print(f"[MONITOR] Virtual Balance: $250 (Paper Trading)")
    print(f"[MONITOR] Check interval: {CHECK_INTERVAL}s")
    print("-" * 70)

    restart_count = 0
    
    try:
        while True:
            running, pid = is_bot_running()
            stats = get_bot_stats()

            if running:
                restart_count = 0  # Reset on success
                win_rate = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
                detail = f"Running | Trades: {stats['trades']} | Wins: {stats['wins']} | WinRate: {win_rate:.1f}% | PnL: ${stats['pnl']:+.2f}"
                append_health_log("OK", pid, detail, stats)
            else:
                restart_count += 1
                append_health_log("RESTARTING", None, f"Bot not running (restart #{restart_count})", stats)
                
                success, detail = start_bot()

                if success:
                    _, new_pid = is_bot_running()
                    append_health_log("RESTARTED", new_pid, detail, stats)
                else:
                    append_health_log("RESTART_FAILED", None, detail, stats)
                    # Back off if too many restarts
                    if restart_count > 5:
                        append_health_log("ERROR", None, "Too many restarts, waiting 5 min...", stats)
                        time.sleep(300)
                        restart_count = 0

            time.sleep(CHECK_INTERVAL)

    finally:
        release_monitor_lock()


if __name__ == "__main__":
    run_monitor()
