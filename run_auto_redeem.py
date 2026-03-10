#!/usr/bin/env python3
"""
Auto Redeem Daemon - Standalone Script
Continuously monitors and redeems winning Polymarket positions.
Run this alongside or independently of the trading bot.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('auto_redeem_daemon')

# Add paths
POLYCLAW_DIR = Path("/root/.openclaw/skills/polyclaw")
WORKSPACE_DIR = Path("/root/.openclaw/workspace")
sys.path.insert(0, str(POLYCLAW_DIR))
sys.path.insert(0, str(WORKSPACE_DIR))

# Load PolyClaw env
from dotenv import load_dotenv
load_dotenv(POLYCLAW_DIR / ".env")

# Import auto_redeem module
from auto_redeem import AutoRedeemer

def main():
    """Run auto-redeem daemon."""
    print("=" * 70)
    print("🔄 AUTO REDEEM DAEMON")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize redeemer
    try:
        redeemer = AutoRedeemer()
        log.info("✅ AutoRedeemer initialized")
    except Exception as e:
        log.error(f"❌ Failed to initialize: {e}")
        sys.exit(1)
    
    # Run continuous loop
    check_interval = int(os.getenv("REDEEM_CHECK_INTERVAL", "300"))  # 5 min default
    
    log.info(f"⏱️  Check interval: {check_interval} seconds")
    log.info("🔍 Monitoring positions for resolution...")
    log.info("Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            try:
                # Check all positions
                log.info("🔄 Checking positions...")
                results = redeemer.check_all_positions()
                
                if results:
                    for result in results:
                        status = "✅" if result.get("success") else "❌"
                        market = result.get("market_id", "unknown")
                        pnl = result.get("pnl", 0)
                        log.info(f"{status} {market}: P&L ${pnl:+.2f}")
                else:
                    log.info("ℹ️ No positions to redeem")
                
                # Show stats
                stats = redeemer.get_stats()
                log.info(f"📊 Stats: {stats['redeemed']} redeemed, "
                        f"{stats['failed']} failed, "
                        f"{stats['manual_required']} manual required")
                
            except Exception as e:
                log.error(f"Error in check loop: {e}")
            
            log.info(f"⏳ Sleeping {check_interval}s...")
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print()
        log.info("🛑 Stopping auto-redeem daemon")
        stats = redeemer.get_stats()
        log.info(f"📈 Final stats: {stats}")

if __name__ == "__main__":
    main()
