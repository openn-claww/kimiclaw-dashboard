#!/usr/bin/env python3
"""
Health Monitor for ultimate_bot_v4_fixed.py
Checks bot status every 60 seconds, auto-restarts on crash.
Run as a single instance only — use a PID lock to prevent duplicates.
"""

import os
import sys
import json
import time
import signal
import subprocess
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────────
BOT_SCRIPT   = "/root/.openclaw/workspace/ultimate_bot_v4_fixed.py"
BOT_LOG      = "/tmp/ultimate_v4_fixed.log"
BOT_PID_FILE = "/tmp/ultimate_v4_fixed.pid"

HEALTH_LOG      = "/tmp/health_monitor_v4_fixed.json"
MONITOR_PID_FILE = "/tmp/health_monitor_v4_fixed.pid"
MAX_LOG_ENTRIES = 100
CHECK_INTERVAL  = 60  # seconds
# ─────────────────────────────────────────────────────────────────────────────


def acquire_monitor_lock():
    """Prevent multiple health monitor instances from running."""
    if os.path.exists(MONITOR_PID_FILE):
        try:
            with open(MONITOR_PID_FILE) as f:
                old_pid = int(f.read().strip())
            # Check if that process is actually alive
            os.kill(old_pid, 0)
            print(f"[ERROR] Health monitor already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Stale PID file — safe to overwrite
            pass

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
        os.kill(pid, 0)   # signal 0 = existence check only
        return True, pid
    except (ProcessLookupError, ValueError, OSError):
        return False, None


def start_bot() -> tuple[bool, str]:
    """
    Launch the bot with nohup, redirect output, save PID.
    Returns (success: bool, detail: str).
    """
    try:
        cmd = (
            f"nohup python3 {BOT_SCRIPT} >> {BOT_LOG} 2>&1 & echo $!"
        )
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True
        )
        pid_str = result.stdout.strip()
        if not pid_str.isdigit():
            return False, f"Could not parse PID from output: '{pid_str}'"

        pid = int(pid_str)
        with open(BOT_PID_FILE, "w") as f:
            f.write(str(pid))

        # Brief pause then confirm it's still alive
        time.sleep(2)
        try:
            os.kill(pid, 0)
            return True, f"Bot started with PID {pid}"
        except ProcessLookupError:
            return False, f"Bot process {pid} died immediately after launch"

    except Exception as e:
        return False, str(e)


def append_health_log(status: str, pid: int | None, detail: str):
    """Append one entry to the JSON health log; keep only last MAX_LOG_ENTRIES."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,          # "OK" | "RESTARTED" | "RESTART_FAILED"
        "pid": pid,
        "detail": detail,
    }

    entries = []
    if os.path.exists(HEALTH_LOG):
        try:
            with open(HEALTH_LOG) as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append(entry)
    entries = entries[-MAX_LOG_ENTRIES:]   # trim to last 100

    with open(HEALTH_LOG, "w") as f:
        json.dump(entries, f, indent=2)

    # Also echo to stdout for journald / nohup log
    print(f"[{entry['timestamp']}] {status} | PID={pid} | {detail}")


def run_monitor():
    acquire_monitor_lock()

    # Clean shutdown on SIGTERM / SIGINT
    def _shutdown(signum, frame):
        print("\n[MONITOR] Shutting down health monitor.")
        release_monitor_lock()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"[MONITOR] Started (PID {os.getpid()}). Watching: {BOT_SCRIPT}")

    try:
        while True:
            running, pid = is_bot_running()

            if running:
                append_health_log("OK", pid, "Bot is running normally.")
            else:
                append_health_log("OK", None, "Bot not running — attempting restart.")
                success, detail = start_bot()

                if success:
                    _, new_pid = is_bot_running()
                    append_health_log("RESTARTED", new_pid, detail)
                else:
                    append_health_log("RESTART_FAILED", None, detail)

            time.sleep(CHECK_INTERVAL)

    finally:
        release_monitor_lock()


if __name__ == "__main__":
    run_monitor()
