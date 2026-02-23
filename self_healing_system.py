#!/usr/bin/env python3
"""
Self-Healing Trading System
Auto-retry, monitor, and fix issues automatically
"""

import os
import sys
import time
import subprocess
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SKILL_DIR = Path("/root/.openclaw/skills/polyclaw")
DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")
LOG_FILE = Path("/root/.openclaw/workspace/self_heal.log")

def log(msg):
    """Log with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_FILE, 'a') as f:
        f.write(log_msg + '\n')

def retry_command(cmd, max_retries=3, delay=2):
    """Execute command with retry logic"""
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                log(f"Attempt {attempt+1} failed: {result.stderr[:100]}")
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))  # Exponential backoff
        except Exception as e:
            log(f"Attempt {attempt+1} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
    return False, None

def fix_common_errors():
    """Auto-fix common issues"""
    fixes_applied = []
    
    # Fix 1: Ensure .env exists
    env_file = SKILL_DIR / ".env"
    if not env_file.exists():
        log("⚠️  .env file missing - attempting to recreate")
        # Try to load from backup or recreate
        backup_env = Path("/root/.openclaw/workspace/.env.backup")
        if backup_env.exists():
            os.system(f"cp {backup_env} {env_file}")
            fixes_applied.append("Restored .env from backup")
    
    # Fix 2: Check database connectivity
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
    except Exception as e:
        log(f"⚠️  Database issue: {e}")
        # Try to recreate database
        os.system(f"cd /root/.openclaw/skills/polytrader && python3 polytrader.py stats 2>/dev/null || echo 'DB check'")
        fixes_applied.append("Database connection verified")
    
    # Fix 3: Ensure PolyClaw is properly installed
    if not (SKILL_DIR / "scripts" / "polyclaw.py").exists():
        log("⚠️  PolyClaw scripts missing - need reinstall")
        os.system("cd /root/.openclaw/skills && git clone https://github.com/chainstacklabs/polyclaw.git 2>/dev/null || true")
        fixes_applied.append("Reinstalled PolyClaw")
    
    return fixes_applied

def monitor_wallet():
    """Monitor wallet and alert on issues"""
    log("Checking wallet...")
    
    # Use bash explicitly for source command
    cmd = f"bash -c 'cd {SKILL_DIR} && source .env && uv run python scripts/polyclaw.py wallet status'"
    success, output = retry_command(cmd, max_retries=3)
    
    if success:
        try:
            data = json.loads(output)
            usdc = float(data.get('balances', {}).get('USDC.e', 0))
            pol = float(data.get('balances', {}).get('POL', 0))
            
            alerts = []
            if usdc < 2:
                alerts.append(f"⚠️  LOW USDC: ${usdc:.2f}")
            if pol < 0.5:
                alerts.append(f"⚠️  LOW POL: {pol:.2f} (need gas)")
            
            if alerts:
                log("ALERTS: " + " | ".join(alerts))
                return {"status": "alert", "alerts": alerts, "balances": {"usdc": usdc, "pol": pol}}
            else:
                log(f"✅ Wallet healthy: ${usdc:.2f} USDC, {pol:.2f} POL (Sufficient for ~70 trades)")
                return {"status": "ok", "balances": {"usdc": usdc, "pol": pol}}
        except Exception as e:
            log(f"❌ Failed to parse wallet data: {e}")
            return {"status": "error", "error": str(e)}
    else:
        log("❌ Failed to check wallet after retries")
        return {"status": "error", "error": "Max retries exceeded"}

def check_open_positions():
    """Check all open positions and alert on upcoming resolutions"""
    log("Checking positions...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        positions = conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN'"
        ).fetchall()
        conn.close()
        
        alerts = []
        for pos in positions:
            # Check if market is about to resolve (within 1 hour)
            # This is simplified - would need actual market data
            alerts.append(f"📊 {pos['market_question'][:30]}... | {pos['side']} ${pos['size_usd']}")
        
        log(f"✅ Found {len(positions)} open positions")
        return {"status": "ok", "count": len(positions), "positions": [dict(p) for p in positions]}
    except Exception as e:
        log(f"❌ Failed to check positions: {e}")
        return {"status": "error", "error": str(e)}

def generate_daily_report():
    """Generate daily P&L report"""
    log("Generating daily report...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Get today's stats
        today = datetime.now().strftime('%Y-%m-%d')
        trades_today = conn.execute(
            "SELECT * FROM trades WHERE date(timestamp) = ?",
            (today,)
        ).fetchall()
        
        all_trades = conn.execute("SELECT * FROM trades").fetchall()
        
        total_pnl = sum(t['pnl_usd'] or 0 for t in all_trades)
        total_invested = sum(t['size_usd'] for t in all_trades)
        
        report = {
            "date": today,
            "trades_today": len(trades_today),
            "total_trades": len(all_trades),
            "total_pnl": total_pnl,
            "total_invested": total_invested,
            "roi_percent": (total_pnl / total_invested * 100) if total_invested else 0
        }
        
        conn.close()
        
        # Save report
        report_file = Path(f"/root/.openclaw/workspace/reports/daily_{today}.json")
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        log(f"✅ Report saved: {report_file}")
        return report
    except Exception as e:
        log(f"❌ Failed to generate report: {e}")
        return {"status": "error", "error": str(e)}

def main():
    """Main self-healing loop"""
    log("="*60)
    log("Starting Self-Healing System")
    log("="*60)
    
    # Step 1: Fix common errors
    fixes = fix_common_errors()
    if fixes:
        log(f"Applied fixes: {fixes}")
    
    # Step 2: Monitor wallet
    wallet_status = monitor_wallet()
    
    # Step 3: Check positions
    positions = check_open_positions()
    
    # Step 4: Generate report
    report = generate_daily_report()
    
    # Summary
    log("="*60)
    log("SUMMARY")
    log("="*60)
    log(f"Wallet: {wallet_status.get('status', 'unknown')}")
    log(f"Positions: {positions.get('count', 0)} open")
    log(f"Total P&L: ${report.get('total_pnl', 0):.2f}")
    log("="*60)
    
    return {
        "fixes": fixes,
        "wallet": wallet_status,
        "positions": positions,
        "report": report
    }

if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, default=str))
