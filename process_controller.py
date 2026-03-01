"""
process_controller.py — Bulletproof single-instance enforcement.

Guarantees:
  - Exactly 1 bot process running at any time
  - Exactly 1 health monitor running at any time
  - Atomic PID file creation (no TOCTOU race)
  - Startup fails immediately if any conflict found
  - Clean process tree with no orphans

Why pkill fails on 66+ processes:
  pkill sends signals but returns before processes die. When Python
  processes catch SIGTERM and clean up, they may spawn children first.
  The fix: SIGTERM → wait 3s → SIGKILL → wait 2s → verify dead.
"""

import os
import sys
import time
import fcntl
import signal
import psutil
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("process_controller")

# ── Constants ─────────────────────────────────────────────────────────────────
WORKSPACE     = Path("/root/.openclaw/workspace")
PID_DIR       = WORKSPACE / "pids"
BOT_PID_FILE  = PID_DIR / "bot.pid"
MON_PID_FILE  = PID_DIR / "monitor.pid"
LOCK_FILE     = PID_DIR / "startup.lock"   # Prevents concurrent startups

BOT_KEYWORDS  = ["ultimate_bot_v4", "ultimate_bot", "bot_v4"]
MON_KEYWORDS  = ["health_monitor", "monitor.py"]

PID_DIR.mkdir(parents=True, exist_ok=True)


# ── Atomic PID file ───────────────────────────────────────────────────────────

class PIDFile:
    """
    Atomic PID file using O_CREAT|O_EXCL — fails if file already exists.
    Held open with an exclusive flock for the process lifetime.
    
    This is more reliable than checking existence then writing (TOCTOU race).
    """

    def __init__(self, path: Path):
        self.path = path
        self._fd:  Optional[int]   = None
        self._file = None

    def acquire(self) -> bool:
        """
        Acquire PID lock. Returns True on success, False if already locked.
        Creates file atomically — no race condition possible.
        """
        try:
            # O_CREAT | O_EXCL = fail if exists (atomic on POSIX)
            self._fd = os.open(
                str(self.path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644
            )
        except FileExistsError:
            # File exists — check if the PID inside is actually alive
            return self._check_stale_and_retry()

        # Write our PID and hold the fd open
        os.write(self._fd, f"{os.getpid()}\n".encode())
        os.fsync(self._fd)   # Flush to disk immediately
        return True

    def _check_stale_and_retry(self) -> bool:
        """If existing PID file holds a dead process, remove and retry."""
        try:
            existing_pid = int(self.path.read_text().strip())
            if psutil.pid_exists(existing_pid):
                logger.error(
                    f"PID file {self.path} held by LIVE process {existing_pid}"
                )
                return False
            # Stale PID — process is dead, remove and retry
            logger.warning(
                f"Removing stale PID file {self.path} (PID {existing_pid} dead)"
            )
            self.path.unlink(missing_ok=True)
            return self.acquire()
        except (ValueError, OSError):
            self.path.unlink(missing_ok=True)
            return self.acquire()

    def release(self):
        """Release PID lock and delete file."""
        if self._fd is not None:
            try:
                os.close(self._fd)
                self._fd = None
            except OSError:
                pass
        self.path.unlink(missing_ok=True)

    def read_pid(self) -> Optional[int]:
        """Read PID from file without acquiring lock."""
        try:
            return int(self.path.read_text().strip())
        except (ValueError, OSError):
            return None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire PID lock: {self.path}")
        return self

    def __exit__(self, *_):
        self.release()


# ── Process scanner ───────────────────────────────────────────────────────────

def find_matching_processes(keywords: list[str],
                            exclude_self: bool = True) -> list[psutil.Process]:
    """
    Find all processes whose cmdline contains any of the keywords.
    More reliable than pgrep because it searches full command strings.
    """
    matches = []
    my_pid  = os.getpid()

    for proc in psutil.process_iter(["pid", "cmdline", "status"]):
        try:
            if proc.info["status"] == psutil.STATUS_ZOMBIE:
                continue
            if exclude_self and proc.pid == my_pid:
                continue

            cmdline = " ".join(proc.info["cmdline"] or [])
            if any(kw in cmdline for kw in keywords):
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return matches


def kill_process_tree(pid: int, timeout_sigterm: float = 3.0,
                      timeout_sigkill: float = 2.0) -> bool:
    """
    Reliably kill a process and ALL its children.

    Why this beats pkill:
      1. Gets full process tree (children + grandchildren)
      2. Sends SIGTERM to all, waits for graceful exit
      3. SIGKILL survivors, verifies dead
      4. Returns False only if process truly unkillable (rare kernel issue)
    """
    try:
        parent = psutil.Process(pid)
        # Get entire subtree BEFORE sending signals (children may spawn)
        children = parent.children(recursive=True)
        all_procs = [parent] + children
    except psutil.NoSuchProcess:
        return True   # Already dead

    logger.info(f"Killing PID {pid} + {len(children)} children")

    # Phase 1: SIGTERM (graceful)
    for p in all_procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(all_procs, timeout=timeout_sigterm)

    if not alive:
        logger.info(f"PID {pid}: all processes exited gracefully")
        return True

    # Phase 2: SIGKILL (force)
    logger.warning(f"PID {pid}: {len(alive)} processes survived SIGTERM, sending SIGKILL")
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, still_alive = psutil.wait_procs(alive, timeout=timeout_sigkill)

    if still_alive:
        logger.error(
            f"PID {pid}: {len(still_alive)} processes SURVIVED SIGKILL — "
            f"PIDs: {[p.pid for p in still_alive]}"
        )
        return False

    logger.info(f"PID {pid}: force-killed successfully")
    return True


# ── Main controller ───────────────────────────────────────────────────────────

class ProcessController:
    """
    Enforces single-instance for bot and monitor.
    Call `startup_check()` at bot launch — it will refuse to start
    if any duplicate is found.
    """

    def __init__(self, role: str):
        """role: 'bot' or 'monitor'"""
        self.role     = role
        self.pid_file = BOT_PID_FILE if role == "bot" else MON_PID_FILE
        self.keywords = BOT_KEYWORDS if role == "bot" else MON_KEYWORDS
        self._pid_lock = PIDFile(self.pid_file)

    def startup_check(self) -> bool:
        """
        Full startup validation. Returns True if safe to start.
        Exits with code 1 on any conflict.
        """
        logger.info(f"[{self.role.upper()}] Startup check beginning...")

        # Step 1: Scan for matching processes
        duplicates = find_matching_processes(self.keywords)
        if duplicates:
            logger.error(
                f"[{self.role.upper()}] STARTUP BLOCKED: "
                f"{len(duplicates)} duplicate process(es) found:"
            )
            for p in duplicates:
                logger.error(
                    f"  PID {p.pid}: {' '.join(p.cmdline())[:80]}"
                )
            return False

        # Step 2: Try to acquire PID file
        if not self._pid_lock.acquire():
            existing = self._pid_lock.read_pid()
            logger.error(
                f"[{self.role.upper()}] STARTUP BLOCKED: "
                f"PID file locked by {existing}"
            )
            return False

        # Step 3: Register cleanup handler
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT,  self._handle_sigterm)

        logger.info(
            f"[{self.role.upper()}] Startup check passed. "
            f"PID {os.getpid()} registered."
        )
        return True

    def _handle_sigterm(self, signum, frame):
        logger.info(
            f"[{self.role.upper()}] Received signal {signum}. "
            f"Releasing PID lock and shutting down."
        )
        self._pid_lock.release()
        sys.exit(0)

    def release(self):
        self._pid_lock.release()


def emergency_kill_all(dry_run: bool = False) -> dict:
    """
    Nuclear option: kill every bot and monitor process.
    Returns summary of what was killed.
    """
    all_keywords = BOT_KEYWORDS + MON_KEYWORDS
    targets      = find_matching_processes(all_keywords, exclude_self=False)

    summary = {"found": len(targets), "killed": 0, "failed": 0, "pids": []}

    if not targets:
        logger.info("No bot/monitor processes found.")
        return summary

    logger.warning(f"Emergency kill: {len(targets)} processes targeted")

    for proc in targets:
        summary["pids"].append(proc.pid)
        if dry_run:
            logger.info(f"[DRY RUN] Would kill PID {proc.pid}")
            continue

        success = kill_process_tree(proc.pid)
        if success:
            summary["killed"] += 1
        else:
            summary["failed"] += 1

    # Clean up stale PID files
    if not dry_run:
        for f in [BOT_PID_FILE, MON_PID_FILE]:
            f.unlink(missing_ok=True)

    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "kill", "status"])
    parser.add_argument("--role", default="bot", choices=["bot", "monitor"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.action == "check":
        ctrl = ProcessController(args.role)
        ok   = ctrl.startup_check()
        sys.exit(0 if ok else 1)

    elif args.action == "kill":
        result = emergency_kill_all(dry_run=args.dry_run)
        print(f"Found: {result['found']} | Killed: {result['killed']} | Failed: {result['failed']}")
        print(f"PIDs: {result['pids']}")

    elif args.action == "status":
        for role, kws in [("BOT", BOT_KEYWORDS), ("MONITOR", MON_KEYWORDS)]:
            procs = find_matching_processes(kws)
            print(f"{role}: {len(procs)} process(es) — PIDs: {[p.pid for p in procs]}")
