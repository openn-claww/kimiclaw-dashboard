"""
monitor.py — Health monitoring, alerting, and dashboard.

Checks every 60 seconds:
  - Bot heartbeat (file age)
  - Duplicate processes
  - Memory + CPU thresholds
  - Open trades overdue
  - Consecutive loss circuit breaker
  - Balance kill switch (>10% drawdown)

Dashboard: python monitor.py dashboard
"""

import os
import sys
import json
import time
import logging
import psutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("monitor")

# ── Configuration ─────────────────────────────────────────────────────────────
WORKSPACE           = Path("/root/.openclaw/workspace")
HEARTBEAT_FILE      = Path("/tmp/bot_heartbeat.txt")
ALERT_LOG           = Path("/tmp/alerts_v4.log")
TRADES_FILE         = WORKSPACE / "trades_v4.json"
WALLET_FILE         = WORKSPACE / "wallet_v4_production.json"

MAX_HEARTBEAT_AGE_S = 300     # Alert if no heartbeat for 5 min
MAX_NO_TRADE_MIN    = 30      # Alert if no trades for 30 min
MAX_MEMORY_MB       = 200     # Alert if memory > 200MB
MAX_CPU_PCT         = 30      # Alert if CPU > 30%
CIRCUIT_BREAKER_N   = 3       # Stop after N consecutive losses
KILL_SWITCH_PCT     = 10.0    # Stop if balance drops >10%
CHECK_INTERVAL_S    = 60      # Monitor loop interval

BOT_KEYWORDS        = ["ultimate_bot_v4", "ultimate_bot", "bot_v4"]
MON_KEYWORDS        = ["monitor.py", "health_monitor"]

# ── Alert system ──────────────────────────────────────────────────────────────

ALERT_HISTORY: list[dict] = []

def send_alert(level: str, code: str, message: str):
    """
    Record alert to log file and stdout.
    Extend this to send Telegram/email by adding handlers below.
    """
    alert = {
        "ts":      time.time(),
        "time":    datetime.now(timezone.utc).isoformat(),
        "level":   level,
        "code":    code,
        "message": message,
    }
    ALERT_HISTORY.append(alert)

    line = f"[ALERT {level}] {code}: {message}"
    logger.warning(line) if level == "WARN" else logger.error(line)

    # Append to alert log file
    with open(ALERT_LOG, "a") as f:
        f.write(json.dumps(alert) + "\n")

    # ── Add Telegram/Slack/email here ─────────────────────────────────────
    # Example Telegram (uncomment and add your token/chat_id):
    # import urllib.request
    # TOKEN   = os.environ.get("TELEGRAM_TOKEN")
    # CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    # if TOKEN and CHAT_ID:
    #     msg = urllib.parse.quote(f"🤖 {line}")
    #     urllib.request.urlopen(
    #         f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    #         f"?chat_id={CHAT_ID}&text={msg}", timeout=5
    #     )


# ── Individual health checks ──────────────────────────────────────────────────

def check_heartbeat() -> dict:
    """Alert if bot heartbeat file is stale."""
    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        age  = time.time() - data.get("ts", 0)
        pid  = data.get("pid")
        ok   = age < MAX_HEARTBEAT_AGE_S

        if not ok:
            send_alert("ERROR", "NO_HEARTBEAT",
                       f"No bot heartbeat for {age:.0f}s (max {MAX_HEARTBEAT_AGE_S}s)")

        return {"ok": ok, "age_s": round(age, 1), "pid": pid}

    except FileNotFoundError:
        send_alert("ERROR", "NO_HEARTBEAT", "Heartbeat file missing — bot may not be running")
        return {"ok": False, "age_s": None, "pid": None}
    except Exception as e:
        return {"ok": False, "error": str(e), "age_s": None, "pid": None}


def check_duplicate_processes() -> dict:
    """Alert if more than 1 bot or monitor process is running."""
    def find(keywords):
        matches = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info["cmdline"] or [])
                if any(kw in cmd for kw in keywords):
                    matches.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return matches

    bot_pids = find(BOT_KEYWORDS)
    mon_pids = find(MON_KEYWORDS)

    ok = len(bot_pids) <= 1 and len(mon_pids) <= 1

    if len(bot_pids) > 1:
        send_alert("ERROR", "DUPLICATE_BOT",
                   f"{len(bot_pids)} bot processes: {bot_pids}")
    if len(mon_pids) > 1:
        send_alert("WARN", "DUPLICATE_MONITOR",
                   f"{len(mon_pids)} monitor processes: {mon_pids}")

    return {"ok": ok, "bot_pids": bot_pids, "monitor_pids": mon_pids}


def check_system_resources() -> dict:
    """Alert if memory or CPU exceed thresholds."""
    mem_mb  = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    cpu_pct = psutil.cpu_percent(interval=1)

    # Also check the bot process specifically
    bot_mem = 0.0
    for proc in psutil.process_iter(["pid", "cmdline", "memory_info"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or [])
            if any(kw in cmd for kw in BOT_KEYWORDS):
                bot_mem = proc.info["memory_info"].rss / 1024 / 1024
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    mem_ok = bot_mem < MAX_MEMORY_MB
    cpu_ok = cpu_pct < MAX_CPU_PCT

    if not mem_ok:
        send_alert("WARN", "HIGH_MEMORY",
                   f"Bot memory {bot_mem:.0f}MB > max {MAX_MEMORY_MB}MB")
    if not cpu_ok:
        send_alert("WARN", "HIGH_CPU",
                   f"System CPU {cpu_pct:.0f}% > max {MAX_CPU_PCT}%")

    return {
        "ok":        mem_ok and cpu_ok,
        "bot_mem_mb": round(bot_mem, 1),
        "cpu_pct":    round(cpu_pct, 1),
    }


def check_trading_activity() -> dict:
    """Alert if no trades executed in last 30 minutes."""
    try:
        trades = json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else {}
        if not trades:
            return {"ok": True, "last_trade_min": None, "open_trades": 0}

        all_trades = list(trades.values())
        latest_ts  = max(t.get("entry_time", 0) for t in all_trades)
        age_min    = (time.time() - latest_ts) / 60
        open_count = sum(1 for t in all_trades if t.get("status") == "open")
        overdue    = sum(1 for t in all_trades
                        if t.get("status") == "open"
                        and time.time() > t.get("window_end", 0) + 60)

        ok = age_min < MAX_NO_TRADE_MIN or True  # Silence in off-hours is OK

        if overdue > 0:
            send_alert("WARN", "OVERDUE_TRADES",
                       f"{overdue} trade(s) past resolution window")

        return {
            "ok":             True,
            "last_trade_min": round(age_min, 1),
            "open_trades":    open_count,
            "overdue":        overdue,
        }
    except Exception as e:
        return {"ok": True, "error": str(e)}


def check_circuit_breakers() -> dict:
    """
    Circuit breaker: stop trading after N consecutive losses.
    Kill switch: stop if balance drops >10%.
    """
    try:
        trades = json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else {}
        wallet = json.loads(WALLET_FILE.read_text()) if WALLET_FILE.exists() else {}

        settled   = sorted(
            [t for t in trades.values() if t.get("status") in ("won", "lost")],
            key=lambda t: t.get("settled_at", 0)
        )

        # Consecutive losses
        consec_losses = 0
        for t in reversed(settled):
            if t["status"] == "lost":
                consec_losses += 1
            else:
                break

        circuit_open = consec_losses >= CIRCUIT_BREAKER_N

        # Balance kill switch
        balance     = wallet.get("balance_usdc", 500.0)
        start_bal   = 500.0   # Hardcoded starting balance
        drawdown_pct = (start_bal - balance) / start_bal * 100
        kill_switch  = drawdown_pct >= KILL_SWITCH_PCT

        if circuit_open:
            send_alert("ERROR", "CIRCUIT_BREAKER",
                       f"{consec_losses} consecutive losses — trading should stop")
        if kill_switch:
            send_alert("ERROR", "KILL_SWITCH",
                       f"Balance dropped {drawdown_pct:.1f}% "
                       f"(${balance:.2f} from ${start_bal:.2f})")

        return {
            "ok":             not circuit_open and not kill_switch,
            "consec_losses":  consec_losses,
            "circuit_open":   circuit_open,
            "balance":        round(balance, 4),
            "drawdown_pct":   round(drawdown_pct, 2),
            "kill_switch":    kill_switch,
        }
    except Exception as e:
        return {"ok": True, "error": str(e)}


# ── Full health report ─────────────────────────────────────────────────────────

def run_health_check() -> dict:
    """Run all checks, return consolidated report."""
    return {
        "ts":          time.time(),
        "heartbeat":   check_heartbeat(),
        "processes":   check_duplicate_processes(),
        "resources":   check_system_resources(),
        "trading":     check_trading_activity(),
        "safety":      check_circuit_breakers(),
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

def print_dashboard():
    """One-command overview of everything."""
    report = run_health_check()

    def _ok(section: dict) -> str:
        return "✅" if section.get("ok", False) else "❌"

    # Header
    print(f"\n{'═'*60}")
    print(f"  BOT DASHBOARD — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'═'*60}")

    # Heartbeat
    hb = report["heartbeat"]
    age_str = f"{hb['age_s']:.0f}s ago" if hb.get("age_s") is not None else "MISSING"
    print(f"\n{_ok(hb)} HEARTBEAT   {age_str}  PID: {hb.get('pid', 'N/A')}")

    # Processes
    pr = report["processes"]
    print(f"{_ok(pr)} PROCESSES   Bot PIDs: {pr.get('bot_pids', [])} | "
          f"Monitor PIDs: {pr.get('monitor_pids', [])}")

    # Resources
    rs = report["resources"]
    print(f"{_ok(rs)} RESOURCES   Memory: {rs.get('bot_mem_mb', 0):.0f}MB | "
          f"CPU: {rs.get('cpu_pct', 0):.0f}%")

    # Trading activity
    tr = report["trading"]
    last = f"{tr.get('last_trade_min', '?'):.0f}m ago" if tr.get("last_trade_min") else "never"
    print(f"{_ok(tr)} ACTIVITY    Last trade: {last} | "
          f"Open: {tr.get('open_trades', 0)} | "
          f"Overdue: {tr.get('overdue', 0)}")

    # Safety
    sf = report["safety"]
    cb = "OPEN ⛔" if sf.get("circuit_open") else "closed"
    ks = "TRIGGERED ⛔" if sf.get("kill_switch") else "off"
    print(f"{_ok(sf)} SAFETY      Balance: ${sf.get('balance', 0):.4f} | "
          f"Drawdown: {sf.get('drawdown_pct', 0):.1f}% | "
          f"Circuit: {cb} ({sf.get('consec_losses', 0)} losses) | "
          f"Kill switch: {ks}")

    # Alerts
    if ALERT_HISTORY:
        print(f"\n{'─'*60}")
        print(f"  RECENT ALERTS ({len(ALERT_HISTORY)} in this session)")
        print(f"{'─'*60}")
        for alert in ALERT_HISTORY[-5:]:
            print(f"  [{alert['level']}] {alert['code']}: {alert['message']}")

    print(f"\n{'═'*60}\n")

    overall = all(
        report[k].get("ok", True)
        for k in ["heartbeat", "processes", "resources", "safety"]
    )
    return overall


# ── Monitor loop ──────────────────────────────────────────────────────────────

class HealthMonitor:
    """Runs health checks on interval. Designed to run as a separate process."""

    def __init__(self):
        from process_controller import ProcessController
        self.ctrl = ProcessController("monitor")

    def start(self):
        if not self.ctrl.startup_check():
            logger.error("Monitor startup blocked — duplicate detected")
            sys.exit(1)

        logger.info(f"[MONITOR] Started. PID {os.getpid()}. "
                    f"Checking every {CHECK_INTERVAL_S}s")

        try:
            while True:
                self._run_checks()
                time.sleep(CHECK_INTERVAL_S)
        except KeyboardInterrupt:
            logger.info("[MONITOR] Shutting down")
        finally:
            self.ctrl.release()

    def _run_checks(self):
        report = run_health_check()
        ok_str = "OK" if all(
            report[k].get("ok", True) for k in report if k != "ts"
        ) else "ISSUES DETECTED"
        logger.info(
            f"[MONITOR] Health check: {ok_str} | "
            f"HB: {report['heartbeat'].get('age_s', '?')}s | "
            f"Mem: {report['resources'].get('bot_mem_mb', 0):.0f}MB | "
            f"Losses: {report['safety'].get('consec_losses', 0)}"
        )


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("action",
                        choices=["dashboard", "check", "start", "alerts"])
    args = parser.parse_args()

    if args.action == "dashboard":
        ok = print_dashboard()
        sys.exit(0 if ok else 1)

    elif args.action == "check":
        report = run_health_check()
        print(json.dumps(report, indent=2))

    elif args.action == "start":
        monitor = HealthMonitor()
        monitor.start()

    elif args.action == "alerts":
        try:
            lines = ALERT_LOG.read_text().splitlines()[-20:]
            for line in lines:
                try:
                    a = json.loads(line)
                    print(f"[{a['level']}] {a['time']} {a['code']}: {a['message']}")
                except json.JSONDecodeError:
                    print(line)
        except FileNotFoundError:
            print("No alerts logged yet.")
