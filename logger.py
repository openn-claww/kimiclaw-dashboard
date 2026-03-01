"""
logger.py — Comprehensive logging with rotation and real-time tail.

Why your bot produced a 0-byte log with nohup + >>:
  1. Python buffers stdout by default (4KB or 8KB block buffer)
  2. nohup redirects stdout to nohup.out OR your >> file
  3. If the process dies before the buffer flushes, nothing reaches disk
  4. Fix: PYTHONUNBUFFERED=1 OR python -u OR sys.stdout.reconfigure(line_buffering=True)
  5. Better fix: use the logging module with a FileHandler (always unbuffered)

This module gives you:
  - Structured JSON log entries (machine-parseable)
  - Human-readable console output simultaneously
  - Rolling file: keeps last MAX_LINES lines, rotates at size limit
  - Separate channels: trades.log, errors.log, blocked.log
  - Real-time tail: `python logger.py tail`
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from collections import deque
from logging.handlers import RotatingFileHandler

# ── Log file locations ────────────────────────────────────────────────────────
LOG_DIR     = Path("/tmp")
MAIN_LOG    = LOG_DIR / "ultimate_v4_fixed.log"
TRADES_LOG  = LOG_DIR / "trades_v4.log"
ERRORS_LOG  = LOG_DIR / "errors_v4.log"
BLOCKED_LOG = LOG_DIR / "blocked_v4.log"
HEARTBEAT_F = LOG_DIR / "bot_heartbeat.txt"

MAX_BYTES   = 5 * 1024 * 1024   # 5MB per file before rotation
BACKUP_COUNT = 3                 # Keep 3 rotated backups
MAX_LINES   = 1000               # Rolling window for tail


# ── Formatters ────────────────────────────────────────────────────────────────

class HumanFormatter(logging.Formatter):
    """Readable format for console + main log."""
    COLORS = {
        "DEBUG":    "\033[36m",    # Cyan
        "INFO":     "\033[0m",     # Default
        "WARNING":  "\033[33m",    # Yellow
        "ERROR":    "\033[31m",    # Red
        "CRITICAL": "\033[35m",    # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        color = self.COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        name  = f"{record.name:<20}"
        msg   = record.getMessage()

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{ts} {level} {name} {msg}"


class JSONFormatter(logging.Formatter):
    """Machine-parseable JSON for trades and errors."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts":      time.time(),
            "time":    datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            entry["traceback"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            entry.update(record.extra)
        return json.dumps(entry)


# ── Rolling file handler (keeps last N lines) ─────────────────────────────────

class RollingLineHandler(logging.Handler):
    """
    Keeps a rolling window of the last MAX_LINES log entries.
    Also writes to a file. Combines rotation + line limit.
    """

    def __init__(self, path: Path, max_lines: int = MAX_LINES):
        super().__init__()
        self.path      = path
        self.max_lines = max_lines
        self._buffer: deque = deque(maxlen=max_lines)
        self._reload_buffer()

    def _reload_buffer(self):
        """Load existing log into rolling buffer on startup."""
        try:
            lines = self.path.read_text().splitlines()
            for line in lines[-self.max_lines:]:
                self._buffer.append(line)
        except FileNotFoundError:
            pass

    def emit(self, record: logging.LogRecord):
        try:
            line = self.format(record)
            self._buffer.append(line)
            # Rewrite file with rolling window (atomic via temp file)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("\n".join(self._buffer) + "\n")
            tmp.replace(self.path)   # Atomic rename
        except Exception:
            self.handleError(record)


# ── Bot logger setup ──────────────────────────────────────────────────────────

def setup_logging(bot_name: str = "bot", level: int = logging.DEBUG) -> logging.Logger:
    """
    Configure the full logging stack. Call once at bot startup.

    Critical: Forces unbuffered I/O so nohup never produces 0-byte logs.
    """
    # Fix 0-byte log issue: force line buffering on stdout
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    # Also set env var for subprocesses
    os.environ["PYTHONUNBUFFERED"] = "1"

    root = logging.getLogger()
    root.setLevel(level)

    # Remove default handlers
    root.handlers.clear()

    human_fmt = HumanFormatter()
    json_fmt  = JSONFormatter()

    # 1. Console handler (always on, human-readable)
    console_h = logging.StreamHandler(sys.stdout)
    console_h.setFormatter(human_fmt)
    console_h.setLevel(logging.DEBUG)
    root.addHandler(console_h)

    # 2. Main log file (rotating, human-readable)
    main_h = RotatingFileHandler(
        MAIN_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    main_h.setFormatter(human_fmt)
    main_h.setLevel(logging.DEBUG)
    root.addHandler(main_h)

    # 3. Rolling tail (last 1000 lines, human-readable)
    roll_h = RollingLineHandler(LOG_DIR / f"{bot_name}_tail.log")
    roll_h.setFormatter(human_fmt)
    roll_h.setLevel(logging.INFO)
    root.addHandler(roll_h)

    # 4. Error log (JSON, errors only — for alerting)
    error_h = RotatingFileHandler(
        ERRORS_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    error_h.setFormatter(json_fmt)
    error_h.setLevel(logging.ERROR)
    root.addHandler(error_h)

    # 5. Trade log (JSON — all trade events)
    trade_h = RotatingFileHandler(
        TRADES_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    trade_h.setFormatter(json_fmt)
    trade_h.setLevel(logging.INFO)
    trade_h.addFilter(_TradeFilter())
    root.addHandler(trade_h)

    # 6. Blocked entries log
    blocked_h = RotatingFileHandler(
        BLOCKED_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    blocked_h.setFormatter(json_fmt)
    blocked_h.setLevel(logging.INFO)
    blocked_h.addFilter(_BlockedFilter())
    root.addHandler(blocked_h)

    logger = logging.getLogger(bot_name)
    logger.info(
        f"Logging initialized. "
        f"Main: {MAIN_LOG} | Errors: {ERRORS_LOG} | Trades: {TRADES_LOG}"
    )
    return logger


class _TradeFilter(logging.Filter):
    def filter(self, record):
        return "[TRADE" in record.getMessage() or "[SETTLEMENT" in record.getMessage()


class _BlockedFilter(logging.Filter):
    def filter(self, record):
        return "[ENTRY BLOCKED" in record.getMessage() or "[ZONE BLOCK" in record.getMessage()


# ── Structured log helpers ─────────────────────────────────────────────────────

def log_websocket_message(logger: logging.Logger, coin: str, price: float,
                           velocity: float, volume: float, timestamp: float):
    """Log every WebSocket tick — structured for later analysis."""
    logger.debug(
        f"[WS] {coin} | price={price:.4f} vel={velocity:+.4f} "
        f"vol={volume:.2f} ts={timestamp:.0f}"
    )


def log_market_check(logger: logging.Logger, coin: str, tf: str,
                      slug: str, yes_price: float, no_price: float,
                      zone_status: str):
    """Log every market check with zone status."""
    logger.debug(
        f"[MARKET] {coin} {tf} | slug={slug[-20:]} | "
        f"YES={yes_price:.3f} NO={no_price:.3f} | zone={zone_status}"
    )


def log_trade_decision(logger: logging.Logger, coin: str, side: str,
                        price: float, allowed: bool, stage: str, reason: str):
    """Log every entry decision with full pass/fail details."""
    status = "ALLOWED" if allowed else f"BLOCKED@{stage}"
    logger.info(
        f"[ENTRY {status}] {coin} {side} @ {price:.3f} | {reason}"
    )


def log_exception(logger: logging.Logger, msg: str, exc: Exception):
    """Log exception with full traceback — never swallow silently."""
    logger.error(
        f"{msg}: {type(exc).__name__}: {exc}\n"
        f"{''.join(traceback.format_exc())}",
        exc_info=True
    )


# ── Heartbeat writer ──────────────────────────────────────────────────────────

class HeartbeatWriter:
    """
    Writes a heartbeat file every 60 seconds.
    Monitor reads this to detect silent crashes.
    """

    def __init__(self, bot_name: str = "bot"):
        self.path     = HEARTBEAT_F
        self.bot_name = bot_name
        self._last    = 0.0

    def beat(self, extra: Optional[dict] = None):
        now = time.time()
        if now - self._last < 60:
            return   # Don't flood disk

        data = {
            "ts":       now,
            "time":     datetime.now(timezone.utc).isoformat(),
            "bot":      self.bot_name,
            "pid":      os.getpid(),
            "extra":    extra or {},
        }
        self.path.write_text(json.dumps(data, indent=2))
        self._last = now

    def age_seconds(self) -> float:
        try:
            data = json.loads(self.path.read_text())
            return time.time() - data.get("ts", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            return float("inf")


# ── Real-time tail ────────────────────────────────────────────────────────────

def tail_log(log_file: Path = MAIN_LOG, lines: int = 50):
    """Print last N lines and follow new entries (like tail -f)."""
    import subprocess
    try:
        subprocess.run(["tail", f"-{lines}", "-f", str(log_file)])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["tail", "errors", "trades",
                                           "blocked", "test"])
    parser.add_argument("--lines", type=int, default=50)
    args = parser.parse_args()

    if args.action == "tail":
        tail_log(MAIN_LOG, args.lines)
    elif args.action == "errors":
        tail_log(ERRORS_LOG, args.lines)
    elif args.action == "trades":
        tail_log(TRADES_LOG, args.lines)
    elif args.action == "blocked":
        tail_log(BLOCKED_LOG, args.lines)
    elif args.action == "test":
        log = setup_logging("test_bot")
        log.debug("Debug message — WebSocket tick")
        log.info("[TRADE OPEN] BTC YES @ 0.12")
        log.info("[ENTRY BLOCKED] ETH NO @ 0.45 — zone_block")
        log.warning("Warning: volume low")
        log.error("Error: API timeout")
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            log_exception(log, "Test exception caught", e)
        print(f"\nLog written to: {MAIN_LOG}")
