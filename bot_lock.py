"""
bot_lock.py
Prevents duplicate bot processes. Import and call acquire_lock()
as the very first thing in any bot entry point.

Usage:
    from bot_lock import acquire_lock
    acquire_lock()  # Exits immediately if another instance is running
"""

import os
import sys
import atexit
import signal
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LOCKFILE = Path("/root/.openclaw/workspace/bot.lock")


def acquire_lock():
    """
    Acquire exclusive lock for this process.
    Exits with code 1 if another instance is already running.
    Automatically releases lock on exit (normal or signal).
    """
    if LOCKFILE.exists():
        try:
            existing_pid = int(LOCKFILE.read_text().strip())
        except (ValueError, OSError):
            # Unreadable lockfile — treat as stale
            _remove_lockfile()
        else:
            # Check if that PID is actually alive
            try:
                os.kill(existing_pid, 0)  # Signal 0 = existence check only
                # Process IS running
                print(f"[bot_lock] FATAL: Bot already running as PID {existing_pid}.")
                print(f"[bot_lock] If this is wrong, run: rm {LOCKFILE}")
                sys.exit(1)
            except ProcessLookupError:
                # PID not found — stale lockfile from a crashed process
                logger.warning(f"Removing stale lockfile (PID {existing_pid} not found)")
                _remove_lockfile()
            except PermissionError:
                # PID exists but we can't signal it — it's running as different user
                # Treat as active to be safe
                print(f"[bot_lock] FATAL: Cannot verify PID {existing_pid} — assume running.")
                sys.exit(1)

    # Write our PID
    LOCKFILE.write_text(str(os.getpid()))
    logger.info(f"Lock acquired: PID {os.getpid()} → {LOCKFILE}")

    # Register cleanup for all exit paths
    atexit.register(_release_lock)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _handle_signal(signum, frame):
    """Clean up on SIGTERM/SIGINT before exiting."""
    logger.info(f"Received signal {signum} — releasing lock and exiting")
    sys.exit(0)  # atexit handler will call _release_lock


def _release_lock():
    """Release lock if we own it. Safe to call multiple times."""
    if LOCKFILE.exists():
        try:
            pid_in_file = int(LOCKFILE.read_text().strip())
            if pid_in_file == os.getpid():
                LOCKFILE.unlink()
                logger.info(f"Lock released: PID {os.getpid()}")
        except (ValueError, OSError):
            pass


def _remove_lockfile():
    try:
        LOCKFILE.unlink()
    except OSError:
        pass


def is_bot_running() -> bool:
    """
    Check from outside the bot whether an instance is running.
    Use in restart.sh via: python3 -c "from bot_lock import is_bot_running; print(is_bot_running())"
    """
    if not LOCKFILE.exists():
        return False
    try:
        pid = int(LOCKFILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, OSError):
        return False
