#!/usr/bin/env python3
"""
Secure Trading Executor for Cron Jobs
Uses environment variables without exposing secrets
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Ensure we're in the right directory
SKILL_DIR = Path("/root/.openclaw/skills/polyclaw")
sys.path.insert(0, str(SKILL_DIR))

def run_command(cmd_list):
    """Run a command with proper environment"""
    env = os.environ.copy()
    
    # Load .env file if exists
    env_file = SKILL_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key] = value
    
    result = subprocess.run(
        cmd_list,
        cwd=SKILL_DIR,
        env=env,
        capture_output=True,
        text=True
    )
    return result

def get_wallet_status():
    """Check wallet balance"""
    result = run_command([
        "uv", "run", "python", "scripts/polyclaw.py", "wallet", "status"
    ])
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

def get_positions():
    """Get current positions"""
    result = run_command([
        "uv", "run", "python", "scripts/polyclaw.py", "positions"
    ])
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

def execute_trade(market_id, side, amount):
    """Execute a trade"""
    result = run_command([
        "uv", "run", "python", "scripts/polyclaw.py", "buy", market_id, side, str(amount), "--skip-sell"
    ])
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

def main():
    """Main trading logic for cron"""
    print(f"=== Trading Heartbeat {datetime.now().isoformat()} ===")
    
    # Check wallet
    print("\n--- Wallet Status ---")
    wallet = get_wallet_status()
    print(wallet)
    
    # Check positions
    print("\n--- Current Positions ---")
    positions = get_positions()
    print(positions)
    
    # TODO: Add market scanning and trading logic here
    # For now, just reporting
    
    print("\n--- Action ---")
    print("DRY RUN: Would scan for 15-min markets here")
    print("LIVE MODE: Would execute $1 trades if edge > 10%")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "wallet": wallet,
        "positions": positions,
        "action": "monitoring"
    }
    
    with open("/root/.openclaw/workspace/last_heartbeat.json", "w") as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
