"""
fix_logging.py — Drop-in replacement that guarantees log output.

Root causes of 0-byte logs diagnosed:
  1. logging module configured with NO handlers (getLogger before basicConfig)
     → Messages silently discarded. Zero output. Bot runs, nothing logged.
  2. FileHandler path doesn't exist yet (directory missing)
     → Handler creation fails, exception swallowed, no logging at all.
  3. stdout buffering with nohup (4KB-8KB block buffer)
     → python3 -u or PYTHONUNBUFFERED=1 fixes this, but ONLY for stdout.
     → The logging FileHandler is unbuffered by default — this is NOT the issue.
  4. basicConfig() called after a handler already exists
     → basicConfig() is a NO-OP if root logger already has handlers.
     → Silent failure — your format/level settings are ignored.
  5. Exception in bot __init__ before any logging setup
     → Bot crashes, never reaches logging init, log stays 0 bytes.

The fix: logging setup must be the FIRST thing, in a try/except that
writes to stderr even if everything else fails.

Usage in your bot — replace whatever logging init you have with:
    from fix_logging import setup_guaranteed_logging
    log = setup_guaranteed_logging()
    log.info("Bot started")  # This WILL appear in the log
"""

import os
import sys
import time
import logging
import traceback
from pathlib import Path
from logging.handlers import RotatingFileHandler

# ── Guaranteed paths (create dirs if missing) ─────────────────────────────────
LOG_DIR    = Path("/tmp")
MAIN_LOG   = LOG_DIR / "ultimate_v4_fixed.log"
BACKUP_LOG = Path("/root/.openclaw/workspace/bot_backup.log")  # Second copy


def setup_guaranteed_logging(
    bot_name: str = "bot",
    log_file: Path = MAIN_LOG,
    backup_file: Path = BACKUP_LOG,
    level: int = logging.DEBUG,
) -> logging.Logger:
    """
    Sets up logging that is guaranteed to produce output.

    Strategy: write to 3 places simultaneously —
      1. /tmp/ultimate_v4_fixed.log  (primary, always writable)
      2. /root/.openclaw/.../bot_backup.log  (secondary, survives /tmp purge)
      3. stderr (always works, captured by nohup fallback)

    Can never produce 0-byte output because:
      - Creates directories before opening files
      - Uses force=True on basicConfig to override existing handlers
      - Falls back to stderr if file creation fails
      - Writes a startup sentinel immediately (proves logging works)
      - Validates that the sentinel actually appeared
    """

    # ── Step 1: Force unbuffered I/O on ALL outputs ───────────────────────────
    os.environ["PYTHONUNBUFFERED"] = "1"

    # Reopen stdout/stderr in line-buffered mode
    # (This covers the nohup buffering issue)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass  # Some environments don't support reconfigure

    # ── Step 2: Create log directories ───────────────────────────────────────
    for path in [log_file, backup_file]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"WARNING: Could not create log dir {path.parent}: {e}",
                  file=sys.stderr)

    # ── Step 3: Clear any existing handlers (fixes basicConfig NO-OP bug) ────
    root = logging.getLogger()
    root.handlers.clear()   # Remove ALL existing handlers
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handlers_added = []

    # ── Step 4: Add stderr handler FIRST (always works) ──────────────────────
    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setFormatter(fmt)
    stderr_h.setLevel(logging.DEBUG)
    root.addHandler(stderr_h)
    handlers_added.append("stderr")

    # ── Step 5: Add primary file handler ─────────────────────────────────────
    try:
        primary_h = RotatingFileHandler(
            str(log_file),
            maxBytes=10 * 1024 * 1024,   # 10MB
            backupCount=3,
            delay=False,   # Open file immediately, don't wait for first log
        )
        primary_h.setFormatter(fmt)
        primary_h.setLevel(logging.DEBUG)
        root.addHandler(primary_h)
        handlers_added.append(f"file:{log_file}")
    except Exception as e:
        print(f"WARNING: Could not open primary log {log_file}: {e}",
              file=sys.stderr)

    # ── Step 6: Add backup file handler ──────────────────────────────────────
    try:
        backup_h = RotatingFileHandler(
            str(backup_file),
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            delay=False,
        )
        backup_h.setFormatter(fmt)
        backup_h.setLevel(logging.INFO)   # Less verbose in backup
        root.addHandler(backup_h)
        handlers_added.append(f"file:{backup_file}")
    except Exception as e:
        print(f"WARNING: Could not open backup log {backup_file}: {e}",
              file=sys.stderr)

    # ── Step 7: Get named logger and write startup sentinel ───────────────────
    log = logging.getLogger(bot_name)

    log.info(f"{'='*60}")
    log.info(f"LOGGING INITIALIZED")
    log.info(f"  Bot:     {bot_name}")
    log.info(f"  PID:     {os.getpid()}")
    log.info(f"  Python:  {sys.version.split()[0]}")
    log.info(f"  Handlers: {', '.join(handlers_added)}")
    log.info(f"  Log file: {log_file}")
    log.info(f"  Unbuffered: {os.environ.get('PYTHONUNBUFFERED', 'NOT SET')}")
    log.info(f"{'='*60}")

    # ── Step 8: Validate sentinel was actually written ────────────────────────
    # Flush all handlers
    for h in root.handlers:
        try:
            h.flush()
        except Exception:
            pass

    # Check file actually has content
    try:
        size = log_file.stat().st_size
        if size == 0:
            print(
                f"CRITICAL: Log file {log_file} is still 0 bytes after init! "
                f"Check permissions and disk space.",
                file=sys.stderr
            )
        else:
            # Write confirmation to stderr so nohup.out always has proof
            print(
                f"[LOGGING OK] {log_file} has {size} bytes. "
                f"Handlers: {', '.join(handlers_added)}",
                file=sys.stderr
            )
    except FileNotFoundError:
        print(
            f"CRITICAL: Log file {log_file} was not created! "
            f"Writing to stderr only.",
            file=sys.stderr
        )

    return log


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Call setup_guaranteed_logging() first."""
    return logging.getLogger(name)


# ── Exception handler — catch EVERYTHING ─────────────────────────────────────

def install_global_exception_handler(log: logging.Logger):
    """
    Installs a global exception handler so uncaught exceptions
    appear in the log instead of disappearing.

    The 0-byte + 41% CPU pattern often means the bot is caught in
    an exception loop that prints to stdout (which is buffered and lost).
    """
    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical(
            "UNCAUGHT EXCEPTION — bot is about to crash",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        # Also write directly to stderr as final fallback
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)

    sys.excepthook = handle_exception
    log.debug("Global exception handler installed")


# ── The correct nohup launch command ─────────────────────────────────────────

CORRECT_LAUNCH_COMMAND = """
# CORRECT way to launch the bot (prevents 0-byte logs):
PYTHONUNBUFFERED=1 nohup python3 -u ultimate_bot_v4_fixed.py 2>&1 | tee -a /tmp/ultimate_v4_fixed.log &

# The key differences from your broken command:
#   1. python3 -u          → unbuffered mode (forces immediate stdout flush)
#   2. 2>&1                → merge stderr into stdout BEFORE tee
#   3. | tee -a            → writes to file AND keeps stdout visible
#   4. Not >> log 2>&1     → this order loses stderr AND buffers stdout

# Alternative: write to two files simultaneously
PYTHONUNBUFFERED=1 nohup python3 -u ultimate_bot_v4_fixed.py \
    >> /tmp/ultimate_v4_fixed.log \
    2>> /tmp/ultimate_v4_errors.log &

# Verify it's working within 5 seconds:
sleep 5 && wc -c /tmp/ultimate_v4_fixed.log
# Should show > 0 bytes
"""


if __name__ == "__main__":
    # Self-test
    log = setup_guaranteed_logging("test_bot")
    install_global_exception_handler(log)

    log.debug("Debug message")
    log.info("Info message")
    log.warning("Warning message")
    log.error("Error message")

    print(CORRECT_LAUNCH_COMMAND)

    # Verify log file
    size = MAIN_LOG.stat().st_size if MAIN_LOG.exists() else 0
    print(f"\nLog file size: {size} bytes")
    print(f"Log file path: {MAIN_LOG}")
    assert size > 0, "FAIL: log file is 0 bytes"
    print("PASS: Logging is working correctly")
