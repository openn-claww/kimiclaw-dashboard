"""
atomic_json.py
Atomic JSON read/write for Polymarket bot wallet and state files.

WHY THIS EXISTS:
  A plain `json.dump(data, open(file, 'w'))` is not atomic.
  If the process crashes mid-write, the file contains partial JSON.
  On the next restart, json.load() throws and the bot cannot start.
  With $690 in the wallet, that is unacceptable.

HOW IT WORKS:
  Write   → temp file → validate → backup current → rename temp over original
  Rename is atomic on Linux (POSIX guarantee). The original file is either
  the old version or the new version — never half-written.

USAGE:
  from atomic_json import atomic_write_json, safe_load_json

  # Write (replaces your json.dump calls):
  ok = atomic_write_json(wallet_dict, "/root/.openclaw/workspace/wallet_v4_production.json")
  if not ok:
      logger.critical("Wallet write failed — investigate immediately")

  # Read (replaces your json.load calls):
  wallet = safe_load_json(
      "/root/.openclaw/workspace/wallet_v4_production.json",
      default={"starting_bankroll": 500.0, "trades": []}
  )
"""

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── WRITE ───────────────────────────────────────────────────────────────────

def atomic_write_json(
    data:        dict,
    filepath:    str | Path,
    keep_backup: bool = True,
    indent:      int  = 2,
) -> bool:
    """
    Atomically write JSON data to a file.

    Steps:
      1. Serialize data to a .tmp file in the same directory
      2. Read it back and parse it — catches serialization errors before
         touching the real file
      3. If keep_backup and the current file is valid JSON: copy it to .backup
      4. os.replace() the .tmp over the real file (atomic on Linux/POSIX)

    Args:
        data:        Dictionary to write. Must be JSON-serializable.
        filepath:    Destination path (e.g. "wallet_v4_production.json")
        keep_backup: Maintain a .backup copy of the previous good state.
        indent:      JSON indentation level (2 = readable, 0 = compact)

    Returns:
        True on success, False on any failure. Never raises.
    """
    filepath = Path(filepath)
    tmp_path = filepath.with_suffix(".tmp")

    try:
        # ── Step 1: Write to temp file ────────────────────────────
        # Use the same directory so rename crosses no filesystem boundary
        serialized = json.dumps(data, indent=indent, default=_json_default)
        tmp_path.write_text(serialized, encoding="utf-8")

        # ── Step 2: Validate by reading back ─────────────────────
        # This catches: circular refs, unencodable types that slipped through,
        # filesystem write errors that didn't raise immediately
        verified = json.loads(tmp_path.read_text(encoding="utf-8"))
        if not isinstance(verified, dict):
            raise ValueError(f"Serialized data is {type(verified).__name__}, expected dict")

        # ── Step 3: Backup the current good file ──────────────────
        if keep_backup and filepath.exists():
            backup = filepath.with_suffix(".backup")
            try:
                # Only back up if the existing file is valid JSON
                existing = json.loads(filepath.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    shutil.copy2(filepath, backup)
                    logger.debug(f"Backup updated: {backup}")
            except (json.JSONDecodeError, OSError) as e:
                # Existing file is already corrupted — skip backup,
                # the .backup from the previous write is still good
                logger.warning(
                    f"Skipped backup: existing {filepath.name} is invalid ({e}). "
                    f"Previous backup retained."
                )

        # ── Step 4: Atomic rename ─────────────────────────────────
        # On Linux, os.replace() is a single syscall (rename(2)) — atomic.
        # Either the old file exists or the new one does. Never half-written.
        os.replace(tmp_path, filepath)

        logger.debug(f"Atomic write OK: {filepath} ({len(serialized)} bytes)")
        return True

    except Exception as e:
        logger.error(f"Atomic write FAILED for {filepath}: {e}")
        # Clean up the temp file if it exists
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return False


# ─── READ ────────────────────────────────────────────────────────────────────

def safe_load_json(
    filepath:    str | Path,
    default:     dict | None = None,
) -> dict:
    """
    Load JSON with automatic fallback to .backup if the main file is corrupted.

    Fallback chain:
      1. Try main file  → return if valid
      2. Try .backup    → return if valid (and log a warning)
      3. Return default (or {} if default is None)

    Never raises. Always returns a dict.

    Args:
        filepath: Main file path
        default:  Returned if both main and backup fail

    Returns:
        Parsed dict, or default
    """
    filepath = Path(filepath)
    backup   = filepath.with_suffix(".backup")
    fallback = default if default is not None else {}

    # ── Try main file ─────────────────────────────────────────────
    result, error = _try_load(filepath)
    if result is not None:
        return result

    main_error = error
    logger.warning(f"Main file unreadable ({filepath.name}): {main_error}")

    # ── Try backup ────────────────────────────────────────────────
    result, error = _try_load(backup)
    if result is not None:
        logger.warning(
            f"Loaded from BACKUP ({backup.name}) — main file was corrupted. "
            f"Run restore_from_backup('{filepath}') to make backup the new main, "
            f"or the next successful write will fix it automatically."
        )
        return result

    # ── Both failed ───────────────────────────────────────────────
    if not filepath.exists() and not backup.exists():
        logger.info(f"No file found at {filepath} — returning default")
    else:
        logger.critical(
            f"BOTH {filepath.name} AND {backup.name} are corrupted or unreadable. "
            f"Manual recovery required. Returning default: {fallback}"
        )

    return dict(fallback)  # Return a copy so caller can't mutate the default


# ─── RESTORE ─────────────────────────────────────────────────────────────────

def restore_from_backup(filepath: str | Path) -> bool:
    """
    Restore the main file from its .backup copy.

    Use when:
    - You know the main file is corrupted
    - You want to roll back to the state before the last write

    Args:
        filepath: Path to the main file (not the backup)

    Returns:
        True if restored successfully, False otherwise
    """
    filepath = Path(filepath)
    backup   = filepath.with_suffix(".backup")

    if not backup.exists():
        logger.error(f"No backup found at {backup}")
        return False

    # Validate the backup before restoring
    result, error = _try_load(backup)
    if result is None:
        logger.error(f"Backup is also invalid ({error}) — cannot restore")
        return False

    # Atomic restore: copy backup → .restore_tmp → replace main
    restore_tmp = filepath.with_suffix(".restore_tmp")
    try:
        shutil.copy2(backup, restore_tmp)
        os.replace(restore_tmp, filepath)
        logger.info(f"Restored {filepath.name} from backup successfully")
        return True
    except OSError as e:
        logger.error(f"Restore failed: {e}")
        try:
            restore_tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


# ─── INTROSPECTION ───────────────────────────────────────────────────────────

def get_file_status(filepath: str | Path) -> dict:
    """
    Diagnostic: check the health of a JSON file and its backup.

    Returns a dict with:
        main_exists, main_valid, main_size_bytes, main_modified,
        backup_exists, backup_valid, backup_size_bytes, backup_modified
    """
    filepath = Path(filepath)
    backup   = filepath.with_suffix(".backup")

    def file_info(path: Path) -> dict:
        if not path.exists():
            return {"exists": False, "valid": False, "size_bytes": 0, "modified": None}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = isinstance(data, dict)
        except (json.JSONDecodeError, OSError):
            valid = False
        stat = path.stat()
        return {
            "exists":       True,
            "valid":        valid,
            "size_bytes":   stat.st_size,
            "modified":     time.strftime("%Y-%m-%d %H:%M:%S UTC",
                                          time.gmtime(stat.st_mtime)),
        }

    main_info   = file_info(filepath)
    backup_info = file_info(backup)

    return {
        "main_path":            str(filepath),
        "main_exists":          main_info["exists"],
        "main_valid":           main_info["valid"],
        "main_size_bytes":      main_info["size_bytes"],
        "main_modified":        main_info["modified"],
        "backup_path":          str(backup),
        "backup_exists":        backup_info["exists"],
        "backup_valid":         backup_info["valid"],
        "backup_size_bytes":    backup_info["size_bytes"],
        "backup_modified":      backup_info["modified"],
    }


def print_file_status(filepath: str | Path):
    """Pretty-print the status of a JSON file and its backup."""
    s = get_file_status(filepath)
    ok = lambda v: "✓" if v else "✗"
    print(f"\n{'─'*50}")
    print(f"  File status: {Path(filepath).name}")
    print(f"{'─'*50}")
    print(f"  Main:   {ok(s['main_valid'])} valid  |  "
          f"{s['main_size_bytes']:,} bytes  |  {s['main_modified'] or 'not found'}")
    print(f"  Backup: {ok(s['backup_valid'])} valid  |  "
          f"{s['backup_size_bytes']:,} bytes  |  {s['backup_modified'] or 'not found'}")
    print(f"{'─'*50}\n")


# ─── INTERNAL HELPERS ────────────────────────────────────────────────────────

def _try_load(path: Path) -> tuple[dict | None, str | None]:
    """
    Attempt to load and parse a JSON file.
    Returns (data, None) on success, (None, error_message) on failure.
    """
    if not path.exists():
        return None, "file not found"
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None, "file is empty"
        data = json.loads(text)
        if not isinstance(data, dict):
            return None, f"top-level type is {type(data).__name__}, expected dict"
        return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error at line {e.lineno}: {e.msg}"
    except OSError as e:
        return None, f"OS error: {e}"


def _json_default(obj: Any) -> Any:
    """
    JSON serializer for types that aren't handled by default.
    Extend this if your wallet contains custom types.
    """
    if hasattr(obj, "isoformat"):      # datetime, date
        return obj.isoformat()
    if hasattr(obj, "__float__"):      # Decimal, numpy float, etc.
        return float(obj)
    if hasattr(obj, "tolist"):         # numpy arrays
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ─── TESTS ───────────────────────────────────────────────────────────────────

def run_tests(test_dir: str = "/tmp/atomic_json_tests"):
    """
    Self-contained test suite. Run with:
        python3 atomic_json.py

    Tests:
      1. Basic write and read
      2. Backup is created on second write
      3. Corrupted main → fallback to backup
      4. Both corrupted → returns default
      5. restore_from_backup()
      6. Unserializable data returns False without corrupting file
      7. get_file_status() diagnostic
      8. Simulated mid-write crash (truncated .tmp does not corrupt main)
    """
    import traceback

    Path(test_dir).mkdir(parents=True, exist_ok=True)
    wallet = Path(test_dir) / "wallet_test.json"
    backup = wallet.with_suffix(".backup")

    passed = failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  ✓  {name}")
            passed += 1
        else:
            print(f"  ✗  {name}{(' — ' + detail) if detail else ''}")
            failed += 1

    def reset():
        for f in [wallet, backup, wallet.with_suffix(".tmp")]:
            f.unlink(missing_ok=True)

    print(f"\n{'═'*55}")
    print("  atomic_json.py — Test Suite")
    print(f"{'═'*55}")

    # ── Test 1: Basic write and read ──────────────────────────────
    print("\n[1] Basic write and read")
    reset()
    data = {"bankroll": 690.0, "trades": [{"id": "t1", "pnl": 195.0}]}
    ok   = atomic_write_json(data, wallet)
    check("atomic_write_json returns True", ok)
    check("file exists", wallet.exists())
    check("no .tmp left behind", not wallet.with_suffix(".tmp").exists())
    loaded = safe_load_json(wallet)
    check("data round-trips correctly", loaded == data,
          f"got {loaded}")
    check("bankroll preserved", loaded.get("bankroll") == 690.0)

    # ── Test 2: Backup created on second write ────────────────────
    print("\n[2] Backup created on second write")
    data2 = {"bankroll": 700.0, "trades": [{"id": "t2", "pnl": 10.0}]}
    ok    = atomic_write_json(data2, wallet)
    check("second write succeeds", ok)
    check(".backup exists", backup.exists())
    backup_data = json.loads(backup.read_text())
    check("backup contains PREVIOUS data (bankroll=690)", backup_data.get("bankroll") == 690.0)
    loaded2 = safe_load_json(wallet)
    check("main file has NEW data (bankroll=700)", loaded2.get("bankroll") == 700.0)

    # ── Test 3: Corrupted main → fallback to backup ───────────────
    print("\n[3] Corrupted main file → fallback to backup")
    wallet.write_text("{ this is not valid json at all <<<", encoding="utf-8")
    recovered = safe_load_json(wallet, default={"bankroll": 0.0})
    check("safe_load_json returns backup data", recovered.get("bankroll") == 690.0,
          f"got bankroll={recovered.get('bankroll')}")

    # ── Test 4: Both corrupted → returns default ──────────────────
    print("\n[4] Both files corrupted → returns default")
    wallet.write_text("GARBAGE", encoding="utf-8")
    backup.write_text("MORE GARBAGE", encoding="utf-8")
    result = safe_load_json(wallet, default={"bankroll": 500.0, "trades": []})
    check("returns default when both corrupted", result == {"bankroll": 500.0, "trades": []})

    # ── Test 5: restore_from_backup ──────────────────────────────
    print("\n[5] restore_from_backup()")
    reset()
    atomic_write_json({"bankroll": 690.0}, wallet)
    atomic_write_json({"bankroll": 700.0}, wallet)
    # Now corrupt main
    wallet.write_text("BAD JSON", encoding="utf-8")
    ok = restore_from_backup(wallet)
    check("restore_from_backup returns True", ok)
    restored = json.loads(wallet.read_text())
    check("main now contains backup data", restored.get("bankroll") == 690.0,
          f"got {restored.get('bankroll')}")

    # ── Test 6: Unserializable data ───────────────────────────────
    print("\n[6] Unserializable data doesn't corrupt existing file")
    reset()
    atomic_write_json({"bankroll": 690.0}, wallet)
    original_content = wallet.read_text()

    class Unserializable:
        pass

    ok = atomic_write_json({"bankroll": 700.0, "bad": Unserializable()}, wallet)
    check("returns False for unserializable data", not ok)
    check("original file unchanged after failed write",
          wallet.read_text() == original_content)
    check("no .tmp file left behind", not wallet.with_suffix(".tmp").exists())

    # ── Test 7: get_file_status ───────────────────────────────────
    print("\n[7] get_file_status() diagnostic")
    reset()
    atomic_write_json({"bankroll": 690.0}, wallet)
    atomic_write_json({"bankroll": 700.0}, wallet)
    status = get_file_status(wallet)
    check("main_valid is True",   status["main_valid"])
    check("backup_valid is True", status["backup_valid"])
    check("main_exists is True",  status["main_exists"])

    # ── Test 8: Mid-write crash simulation ────────────────────────
    print("\n[8] Simulated mid-write crash (truncated .tmp)")
    reset()
    atomic_write_json({"bankroll": 690.0}, wallet)
    # Simulate crash: leave a corrupt .tmp but don't rename
    wallet.with_suffix(".tmp").write_text('{"bankroll": 700', encoding="utf-8")  # truncated
    # safe_load_json should still read the good main file
    result = safe_load_json(wallet)
    check("main file readable despite corrupt .tmp", result.get("bankroll") == 690.0)
    # Now write again — should overwrite the corrupt .tmp cleanly
    ok = atomic_write_json({"bankroll": 710.0}, wallet)
    check("write succeeds after stale .tmp", ok)
    check("new data correct", safe_load_json(wallet).get("bankroll") == 710.0)

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'═'*55}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'═'*55}\n")

    # Cleanup
    import shutil as _shutil
    _shutil.rmtree(test_dir, ignore_errors=True)

    return failed == 0


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,   # Keep test output clean — only show warnings+
        format="%(levelname)-8s %(message)s"
    )
    success = run_tests()
    import sys
    sys.exit(0 if success else 1)
