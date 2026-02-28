#!/usr/bin/env python3
"""
BOT HEALTH MONITOR
Automatically restarts bot if it stops
"""

import subprocess
import time
import os
import signal
import sys
from datetime import datetime

# Configuration
BOT_SCRIPT = "/root/.openclaw/workspace/ultimate_bot_v5_simple.py"
LOG_FILE = "/tmp/ultimate_v5.log"
PID_FILE = "/tmp/ultimate_v5.pid"
CHECK_INTERVAL = 60  # Check every 60 seconds
MAX_RESTARTS = 5     # Max restarts per hour
RESTART_WINDOW = 3600  # 1 hour

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}")
    with open("/tmp/bot_monitor.log", "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

def is_bot_running():
    """Check if bot process is running."""
    try:
        # Check by process name
        result = subprocess.run(
            ["pgrep", "-f", "ultimate_bot_v5_simple"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
        return False
    except:
        return False

def get_bot_pid():
    """Get bot PID if running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ultimate_bot_v5_simple"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return int(result.stdout.strip().split('\n')[0])
        return None
    except:
        return None

def start_bot():
    """Start the bot."""
    try:
        # Kill any existing bot processes
        subprocess.run(["pkill", "-f", "ultimate_bot_v5_simple"], 
                      capture_output=True)
        time.sleep(2)
        
        # Start bot with nohup
        process = subprocess.Popen(
            ["nohup", "python3", BOT_SCRIPT],
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        
        # Save PID
        with open(PID_FILE, "w") as f:
            f.write(str(process.pid))
        
        log(f"✅ Bot started with PID: {process.pid}")
        return True
    except Exception as e:
        log(f"❌ Failed to start bot: {e}")
        return False

def check_bot_health():
    """Check if bot is healthy (responding)."""
    # Check if log has recent activity (within last 5 minutes)
    try:
        if os.path.exists(LOG_FILE):
            stat = os.stat(LOG_FILE)
            last_modified = stat.st_mtime
            time_since_update = time.time() - last_modified
            
            if time_since_update > 300:  # 5 minutes
                log(f"⚠️ Bot log stale ({int(time_since_update)}s since update)")
                return False
        return True
    except:
        return True

def main():
    log("="*60)
    log("BOT HEALTH MONITOR STARTED")
    log("="*60)
    log(f"Monitoring: {BOT_SCRIPT}")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log(f"Max restarts per hour: {MAX_RESTARTS}")
    
    restart_times = []
    
    while True:
        try:
            # Clean old restart times
            current_time = time.time()
            restart_times = [t for t in restart_times if current_time - t < RESTART_WINDOW]
            
            # Check if bot is running
            if not is_bot_running():
                log("⚠️ Bot is NOT running!")
                
                # Check restart limit
                if len(restart_times) >= MAX_RESTARTS:
                    log(f"❌ Max restarts ({MAX_RESTARTS}) reached in last hour. Waiting...")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Restart bot
                log("🔄 Restarting bot...")
                if start_bot():
                    restart_times.append(current_time)
                    log(f"✅ Bot restarted (restart #{len(restart_times)} this hour)")
                else:
                    log("❌ Failed to restart bot")
            
            else:
                # Bot is running, check health
                pid = get_bot_pid()
                if pid:
                    log(f"✅ Bot healthy (PID: {pid})")
                
                if not check_bot_health():
                    log("⚠️ Bot may be stuck (no log activity)")
                    # Could add more aggressive restart here
            
            # Wait before next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log("👋 Monitor stopped by user")
            break
        except Exception as e:
            log(f"❌ Monitor error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
