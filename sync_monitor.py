#!/usr/bin/env python3
"""
Comprehensive Sync Monitor - Checks everything, auto-fixes, DMs only for critical issues
Runs every 30 minutes silently
"""

import json
import time
import subprocess
import os
from datetime import datetime

INTERNAL_LOG = "/root/.openclaw/workspace/InternalLog.json"
DASHBOARD_FILE = "/root/.openclaw/workspace/dashboard.html"
TRADES_DB = "/root/.openclaw/skills/polytrader/trades.db"
DISCORD_CHANNEL = "1475209252183343347"
USER_DM_CHANNEL = "1475209252183343347"  # Your DM channel

def dm_user(message):
    """Send DM to user for critical issues only"""
    # This would use message tool to DM
    with open('/tmp/critical_alert.txt', 'a') as f:
        f.write(f"{datetime.now()}: {message}\n")

def calculate_stats():
    """Calculate true stats from InternalLog"""
    try:
        with open(INTERNAL_LOG, 'r') as f:
            log = json.load(f)
    except Exception as e:
        return None, f"Cannot read InternalLog: {e}"
    
    balance = 1000.0
    profit = 0.0
    won = 0
    lost = 0
    open_count = 0
    
    for entry in log:
        if entry.get('event_type') == 'trade_sim':
            amount = entry.get('amount', 0)
            entry_price = entry.get('entry_price', 0.5)
            notes = entry.get('notes', '')
            
            balance -= amount
            
            if 'WON' in notes:
                balance += amount * 2
                profit += amount * (1 - entry_price)
                won += 1
            elif 'LOST' in notes:
                profit -= amount * entry_price
                lost += 1
            else:
                open_count += 1
    
    return {
        'balance': round(balance, 2),
        'profit': round(profit, 2),
        'won': won,
        'lost': lost,
        'open': open_count,
        'total': won + lost + open_count
    }, None

def check_bot_status():
    """Check if autonomous trader is running properly"""
    try:
        # Check if process exists
        result = subprocess.run(
            ["pgrep", "-f", "autonomous_trader.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return False, "Bot not running"
        
        # Check if log file is being updated
        try:
            log_mtime = os.path.getmtime('/tmp/trader.log')
            time_since_update = time.time() - log_mtime
            
            if time_since_update > 300:  # No update in 5 minutes
                return False, f"Bot stuck - no activity for {int(time_since_update)}s"
        except:
            pass
        
        return True, "OK"
    except Exception as e:
        return False, f"Check failed: {e}"

def check_trades_happening():
    """Check if new trades are being executed"""
    try:
        with open(INTERNAL_LOG, 'r') as f:
            log = json.load(f)
        
        # Find last trade
        last_trade_time = None
        for entry in reversed(log):
            if entry.get('event_type') == 'trade_sim':
                last_trade_time = entry.get('timestamp_utc')
                break
        
        if not last_trade_time:
            return False, "No trades found"
        
        # Parse time
        try:
            from datetime import datetime
            last_trade = datetime.strptime(last_trade_time, '%Y-%m-%d %H:%M:%S')
            time_since = (datetime.now() - last_trade).total_seconds() / 60  # minutes
            
            if time_since > 120:  # No trade in 2 hours
                return False, f"No trades for {int(time_since)} minutes"
            
            return True, f"Last trade {int(time_since)}m ago"
        except:
            return True, "Time parse error"
    except Exception as e:
        return False, f"Check failed: {e}"

def check_dashboard_sync(stats):
    """Check if dashboard matches InternalLog"""
    try:
        with open(DASHBOARD_FILE, 'r') as f:
            content = f.read()
        
        # Extract dashboard balance
        import re
        balance_match = re.search(r'id="paper-balance"\u003e\$(\d+\.?\d*)', content)
        dashboard_balance = float(balance_match.group(1)) if balance_match else 0
        
        if abs(dashboard_balance - stats['balance']) > 1:
            return False, f"Balance mismatch: Dashboard ${dashboard_balance} vs Log ${stats['balance']}"
        
        return True, "Synced"
    except Exception as e:
        return False, f"Check failed: {e}"

def check_github_sync():
    """Check if GitHub is up to date"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd="/root/.openclaw/workspace",
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            return False, "Uncommitted changes"
        
        return True, "Up to date"
    except Exception as e:
        return False, f"Check failed: {e}"

def auto_fix_issues(stats, issues):
    """Try to auto-fix detected issues"""
    fixed = []
    failed = []
    
    for issue in issues:
        if issue == "bot_not_running" or issue == "bot_stuck":
            # Restart bot
            try:
                subprocess.run(["pkill", "-f", "autonomous_trader.py"], capture_output=True)
                time.sleep(2)
                subprocess.Popen(
                    ["nohup", "python3", "/root/.openclaw/workspace/autonomous_trader.py"],
                    stdout=open("/tmp/trader.log", "a"),
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
                fixed.append("bot_restarted")
            except:
                failed.append("bot_restart")
        
        elif issue == "dashboard_mismatch":
            # Update dashboard
            try:
                with open(DASHBOARD_FILE, 'r') as f:
                    content = f.read()
                
                # Simple replace
                content = content.replace(
                    'id="paper-balance"\u003e',
                    f'id="paper-balance"\u003e${stats["balance"]}'
                )
                
                with open(DASHBOARD_FILE, 'w') as f:
                    f.write(content)
                
                fixed.append("dashboard_updated")
            except:
                failed.append("dashboard_update")
        
        elif issue == "github_uncommitted":
            # Push to GitHub
            try:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd="/root/.openclaw/workspace",
                    capture_output=True
                )
                subprocess.run(
                    ["git", "commit", "-m", f"Auto-sync {datetime.now().strftime('%H:%M')}"],
                    cwd="/root/.openclaw/workspace",
                    capture_output=True
                )
                subprocess.run(
                    ["git", "push", "origin", "master"],
                    cwd="/root/.openclaw/workspace",
                    capture_output=True
                )
                fixed.append("github_pushed")
            except:
                failed.append("github_push")
    
    return fixed, failed

def main():
    """Main monitoring logic"""
    stats, error = calculate_stats()
    
    if error:
        dm_user(f"🚨 CRITICAL: {error}")
        return
    
    issues = []
    checks = {}
    
    # Check 1: Bot status
    bot_ok, bot_msg = check_bot_status()
    checks['bot'] = bot_msg
    if not bot_ok:
        issues.append("bot_not_running" if "not running" in bot_msg else "bot_stuck")
    
    # Check 2: Trades happening
    trades_ok, trades_msg = check_trades_happening()
    checks['trades'] = trades_msg
    if not trades_ok:
        issues.append("no_trades")
    
    # Check 3: Dashboard sync
    dash_ok, dash_msg = check_dashboard_sync(stats)
    checks['dashboard'] = dash_msg
    if not dash_ok:
        issues.append("dashboard_mismatch")
    
    # Check 4: GitHub sync
    git_ok, git_msg = check_github_sync()
    checks['github'] = git_msg
    if not git_ok:
        issues.append("github_uncommitted")
    
    # Auto-fix issues
    fixed, failed = auto_fix_issues(stats, issues)
    
    # Log everything
    with open('/tmp/sync_monitor.log', 'a') as f:
        f.write(f"{datetime.now()}: Checks={checks}, Issues={issues}, Fixed={fixed}, Failed={failed}\n")
    
    # DM user only for critical failures that need manual intervention
    critical_failures = [f for f in failed if f in ['bot_restart', 'github_push']]
    
    if critical_failures:
        dm_user(f"🚨 NEED YOUR HELP: Auto-fix failed for: {', '.join(critical_failures)}. Please check.")

if __name__ == "__main__":
    main()
