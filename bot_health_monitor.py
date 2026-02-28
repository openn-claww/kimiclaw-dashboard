#!/usr/bin/env python3
"""
V4 Bot Health Monitor
Checks if bot is running, restarts if needed, logs status
"""

import subprocess
import json
import time
from datetime import datetime
import os

BOT_SCRIPT = "/root/.openclaw/workspace/ultimate_bot_v4_production.py"
LOG_FILE = "/root/.openclaw/workspace/bot_health_log.json"
PID_FILE = "/tmp/ultimate_v4_pid.txt"
CHECK_INTERVAL = 60  # Check every minute

def log_health(status, details=""):
    entry = {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "status": status,
        "details": details
    }
    try:
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)
    except:
        logs = []
    logs.append(entry)
    # Keep last 1000 entries
    logs = logs[-1000:]
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def is_bot_running():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ultimate_bot_v4_production.py"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip()
    except:
        return False

def start_bot():
    try:
        subprocess.Popen(
            ["python3", BOT_SCRIPT],
            stdout=open("/tmp/ultimate_v4_production.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        return True
    except Exception as e:
        return False

def check_wallet_activity():
    """Check if wallet has recent activity"""
    try:
        wallet_file = "/root/.openclaw/workspace/wallet_v4_production.json"
        with open(wallet_file, 'r') as f:
            wallet = json.load(f)
        
        trades = wallet.get('trades', [])
        if trades:
            last_trade = trades[-1]
            last_time = datetime.strptime(last_trade['timestamp_utc'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            minutes_since = (now - last_time).total_seconds() / 60
            return minutes_since < 30  # Active if trade in last 30 min
        return False
    except:
        return False

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] V4 Health Monitor Started")
    
    while True:
        running = is_bot_running()
        
        if not running:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Bot NOT running - restarting...")
            if start_bot():
                log_health("RESTARTED", "Bot was down, restarted successfully")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Bot restarted")
            else:
                log_health("RESTART_FAILED", "Failed to restart bot")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Restart failed")
        else:
            # Bot is running, check activity
            active = check_wallet_activity()
            status = "RUNNING_ACTIVE" if active else "RUNNING_IDLE"
            log_health(status, "Bot healthy" if active else "No recent trades")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
