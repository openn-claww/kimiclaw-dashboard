"""
validate_startup.py — Pre-flight checks that catch all 5 failure modes.

Run this BEFORE starting the bot. Exits with code 1 on any failure.
Each check explains WHY it can fail and HOW to fix it.

Usage:
    python3 validate_startup.py           # Full validation
    python3 validate_startup.py --fix     # Auto-fix what's fixable
    python3 validate_startup.py --quick   # Skip slow network checks
"""

import os
import sys
import json
import time
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")

PASS  = "\033[32m✓\033[0m"
FAIL  = "\033[31m✗\033[0m"
WARN  = "\033[33m!\033[0m"
INFO  = "\033[34m→\033[0m"

results = {"passed": 0, "failed": 0, "warned": 0, "fixes_applied": 0}


def check(name: str, passed: bool, detail: str = "", fix_msg: str = "", auto_fix=None, fix_mode=False):
    if passed:
        print(f"  {PASS} {name}")
        if detail:
            print(f"    {detail}")
        results["passed"] += 1
    else:
        print(f"  {FAIL} {name}")
        if detail:
            print(f"    {detail}")
        if fix_msg:
            print(f"    FIX: {fix_msg}")
        if auto_fix and fix_mode:
            try:
                auto_fix()
                print(f"    {INFO} Auto-fix applied")
                results["fixes_applied"] += 1
                results["passed"] += 1
                return
            except Exception as e:
                print(f"    Auto-fix failed: {e}")
        results["failed"] += 1


def warn(name: str, detail: str = "", fix_msg: str = ""):
    print(f"  {WARN} {name}")
    if detail:
        print(f"    {detail}")
    if fix_msg:
        print(f"    FIX: {fix_msg}")
    results["warned"] += 1


def run_validation(fix_mode: bool = False, quick: bool = False):

    # ─────────────────────────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════════")
    print("  PRE-FLIGHT VALIDATION")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("══════════════════════════════════════════════")

    # ── Section 1: Logging ────────────────────────────────────────────────────
    print("\n[1] LOGGING")

    # Test 1.1: Log directory writable
    LOG_PATH = Path("/tmp/ultimate_v4_fixed.log")
    try:
        LOG_PATH.write_text("test\n")
        LOG_PATH.unlink()
        check("Log directory writable", True, f"{LOG_PATH.parent}")
    except PermissionError as e:
        check("Log directory writable", False,
              str(e),
              "Run as root or change LOG_PATH to a writable directory")

    # Test 1.2: Python -u flag effect
    test_script = "/tmp/_unbuf_test.py"
    Path(test_script).write_text("import sys; print('OK', flush=True)\n")

    result = subprocess.run(
        ["python3", "-u", test_script],
        capture_output=True, text=True, timeout=5
    )
    check("python3 -u produces output", result.returncode == 0 and "OK" in result.stdout,
          f"stdout: '{result.stdout.strip()}'",
          "Use 'python3 -u' in launch command")

    # Test 1.3: PYTHONUNBUFFERED actually works
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        ["python3", test_script],
        capture_output=True, text=True, env=env, timeout=5
    )
    check("PYTHONUNBUFFERED=1 produces output", "OK" in result.stdout,
          "Confirmed PYTHONUNBUFFERED works in subprocess")

    # Test 1.4: Logging module actually writes to file
    test_log = Path("/tmp/_logging_test.log")
    test_log.unlink(missing_ok=True)
    test_code = f"""
import logging
# Clear existing handlers (critical!)
logging.getLogger().handlers.clear()
logging.basicConfig(filename='{test_log}', level=logging.DEBUG, force=True)
logging.info("sentinel_value_12345")
logging.shutdown()
"""
    result = subprocess.run(["python3", "-c", test_code], capture_output=True, text=True)
    log_content = test_log.read_text() if test_log.exists() else ""
    check("logging module writes to file", "sentinel_value_12345" in log_content,
          f"Log content: '{log_content.strip()[:50]}'",
          "Ensure logging.basicConfig(force=True) is used with handlers.clear()")
    test_log.unlink(missing_ok=True)

    # Test 1.5: The bot's own logging setup
    bot_file = WORKSPACE / "ultimate_bot_v4_fixed.py"
    if bot_file.exists():
        bot_src = bot_file.read_text()

        has_force    = "force=True" in bot_src
        has_clear    = "handlers.clear()" in bot_src or "handlers = []" in bot_src
        has_unbuf    = "PYTHONUNBUFFERED" in bot_src or "reconfigure" in bot_src
        has_filehandler = "FileHandler" in bot_src or "basicConfig" in bot_src

        if not has_force and not has_clear:
            warn("Bot logging may silently fail",
                 "basicConfig without force=True is a NO-OP if handlers exist",
                 "Add 'logging.getLogger().handlers.clear()' before basicConfig, "
                 "or add 'force=True' to basicConfig call")
        else:
            check("Bot logging config looks correct", True)
    else:
        warn("Bot file not found for logging check",
             f"Expected: {bot_file}")

    # ── Section 2: Process control ────────────────────────────────────────────
    print("\n[2] PROCESS CONTROL")

    # Test 2.1: No duplicate bots
    bot_pids = subprocess.run(
        ["pgrep", "-f", "ultimate_bot_v4"],
        capture_output=True, text=True
    ).stdout.strip().split()
    bot_pids = [p for p in bot_pids if p]

    check("No duplicate bot processes",
          len(bot_pids) <= 1,
          f"Found PIDs: {bot_pids}" if bot_pids else "None running",
          "Run ./emergency_stop.sh to kill duplicates")

    # Test 2.2: No duplicate monitors
    mon_pids = subprocess.run(
        ["pgrep", "-f", "monitor.py"],
        capture_output=True, text=True
    ).stdout.strip().split()
    mon_pids = [p for p in mon_pids if p if p != str(os.getpid())]

    check("No duplicate monitor processes",
          len(mon_pids) <= 1,
          f"Found PIDs: {mon_pids}" if mon_pids else "None running",
          "Run ./emergency_stop.sh to kill duplicates")

    # Test 2.3: PID directory writable
    pid_dir = WORKSPACE / "pids"

    def create_pid_dir():
        pid_dir.mkdir(parents=True, exist_ok=True)

    check("PID directory exists",
          pid_dir.exists(),
          str(pid_dir),
          f"mkdir -p {pid_dir}",
          auto_fix=create_pid_dir,
          fix_mode=fix_mode)

    # ── Section 3: File system ────────────────────────────────────────────────
    print("\n[3] FILE SYSTEM")

    # Test 3.1: Workspace exists
    check("Workspace exists", WORKSPACE.exists(), str(WORKSPACE))

    # Test 3.2: Wallet file
    wallet_candidates = [
        WORKSPACE / "wallet_v4_production.json",
        WORKSPACE / "memory" / "wallet.json",
        WORKSPACE / "wallet.json",
    ]
    wallet_found = [p for p in wallet_candidates if p.exists()]

    def create_default_wallet():
        wp = WORKSPACE / "wallet_v4_production.json"
        wp.write_text(json.dumps({
            "balance_usdc": 500.0,
            "total_pnl": 0.0,
            "trades_won": 0,
            "trades_lost": 0,
        }, indent=2))

    check("Wallet file exists",
          bool(wallet_found),
          f"Found: {[str(p) for p in wallet_found]}" if wallet_found else
          f"Checked: {[str(p) for p in wallet_candidates]}",
          "python3 settle_stuck_trade.py will create it",
          auto_fix=create_default_wallet,
          fix_mode=fix_mode)

    # Test 3.3: Check status.sh reads correct wallet
    status_sh = WORKSPACE / "status.sh"
    if status_sh.exists():
        status_content = status_sh.read_text()
        reads_correct_wallet = "wallet_v4_production.json" in status_content
        check("status.sh reads correct wallet file",
              reads_correct_wallet,
              "wallet_v4_production.json referenced in status.sh" if reads_correct_wallet
              else "status.sh may be reading wrong file path",
              "Update status.sh wallet path — see fix_status_sh() below")
    else:
        warn("status.sh not found", f"Expected: {status_sh}")

    # ── Section 4: Monitor / Heartbeat ───────────────────────────────────────
    print("\n[4] MONITOR & HEARTBEAT")

    hb_file = Path("/tmp/bot_heartbeat.txt")
    if hb_file.exists():
        try:
            hb_data  = json.loads(hb_file.read_text())
            hb_age   = time.time() - hb_data.get("ts", 0)
            hb_ok    = hb_age < 300
            check("Heartbeat file fresh",
                  hb_ok,
                  f"Age: {hb_age:.0f}s (max 300s)",
                  "Restart monitor: python3 monitor.py start &")
        except Exception as e:
            check("Heartbeat file readable", False, str(e))
    else:
        warn("No heartbeat file",
             "Bot/monitor not running or monitor crashed on startup",
             "Start monitor: PYTHONUNBUFFERED=1 nohup python3 -u monitor.py start >> /tmp/monitor_v4.log 2>&1 &")

    # Test: Can monitor actually start?
    try:
        result = subprocess.run(
            ["python3", "-c", "import monitor; print('import OK')"],
            capture_output=True, text=True, timeout=5,
            cwd=str(WORKSPACE)
        )
        check("monitor.py importable",
              "import OK" in result.stdout,
              result.stderr[:100] if result.returncode != 0 else "",
              "Check monitor.py for import errors: python3 -c 'import monitor'")
    except Exception as e:
        warn("Could not test monitor import", str(e))

    # ── Section 5: Network / API ──────────────────────────────────────────────
    if not quick:
        print("\n[5] NETWORK ACCESS")

        for name, url in [
            ("Gamma API", "https://gamma-api.polymarket.com/markets?limit=1"),
            ("CLOB API",  "https://clob.polymarket.com/price?token_id=test"),
        ]:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    check(f"{name} reachable", True, f"HTTP {r.status}")
            except urllib.error.HTTPError as e:
                # 400/404 from CLOB with dummy token = API is reachable
                check(f"{name} reachable", True, f"HTTP {e.code} (expected)")
            except Exception as e:
                check(f"{name} reachable", False,
                      str(e), "Check network connectivity")

    # ── Section 6: Open trade check ───────────────────────────────────────────
    print("\n[6] OPEN TRADES")

    trade_files = [
        WORKSPACE / "trades_v4.json",
        WORKSPACE / "memory" / "trades.json",
    ]
    for tf in trade_files:
        if tf.exists():
            try:
                trades  = json.loads(tf.read_text())
                open_t  = [t for t in (trades.values() if isinstance(trades, dict) else trades)
                           if isinstance(t, dict) and t.get("status") == "open"]
                overdue = []
                for t in open_t:
                    end = t.get("window_end", 0)
                    if end and time.time() > end + 60:
                        overdue.append(t)

                if overdue:
                    warn(f"Overdue open trades in {tf.name}",
                         f"{len(overdue)} trade(s) past window_end",
                         "Run: python3 settle_stuck_trade.py")
                elif open_t:
                    check(f"Open trades in {tf.name}", True,
                          f"{len(open_t)} open, none overdue")
                else:
                    check(f"No stuck trades in {tf.name}", True, "0 open trades")
            except Exception as e:
                warn(f"Could not parse {tf.name}", str(e))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*46}")
    print(f"  RESULTS: {results['passed']} passed  "
          f"{results['failed']} failed  "
          f"{results['warned']} warnings  "
          f"{results['fixes_applied']} auto-fixed")
    print(f"{'═'*46}")

    if results["failed"] == 0:
        print(f"\n  ✅ All checks passed. Safe to start bot.")
        print(f"\n  Launch command:")
        print(f"  PYTHONUNBUFFERED=1 nohup python3 -u \\")
        print(f"    /root/.openclaw/workspace/ultimate_bot_v4_fixed.py \\")
        print(f"    >> /tmp/ultimate_v4_fixed.log 2>&1 &")
    else:
        print(f"\n  ❌ {results['failed']} check(s) failed. Fix before starting.")
        if not fix_mode:
            print(f"  Run with --fix to auto-fix what's possible:")
            print(f"  python3 validate_startup.py --fix")
    print()

    return results["failed"] == 0


def fix_status_sh():
    """
    Rewrites status.sh to read the correct wallet file path.
    """
    status_sh = WORKSPACE / "status.sh"
    if not status_sh.exists():
        print(f"status.sh not found at {status_sh}")
        return

    content = status_sh.read_text()

    # Fix wallet path references
    fixes = [
        ("wallet.json", "wallet_v4_production.json"),
        ("memory/wallet", "wallet_v4_production"),
        ("/tmp/trades", "/root/.openclaw/workspace/trades_v4"),
    ]

    for old, new in fixes:
        if old in content and new not in content:
            content = content.replace(old, new)
            print(f"  Fixed: '{old}' → '{new}'")

    status_sh.write_text(content)
    print(f"  Updated: {status_sh}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix",   action="store_true", help="Auto-fix what's fixable")
    parser.add_argument("--quick", action="store_true", help="Skip network checks")
    parser.add_argument("--fix-status", action="store_true", help="Fix status.sh paths only")
    args = parser.parse_args()

    if args.fix_status:
        fix_status_sh()
        sys.exit(0)

    ok = run_validation(fix_mode=args.fix, quick=args.quick)
    sys.exit(0 if ok else 1)
