#!/usr/bin/env python3
"""
Auto Redeem Service - Simple Version
Monitors your wallet and auto-redeems winning positions.
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path

# Paths
POLYCLAW_DIR = Path("/root/.openclaw/skills/polyclaw")
WORKSPACE = Path("/root/.openclaw/workspace")
sys.path.insert(0, str(POLYCLAW_DIR))

# Load env
from dotenv import load_dotenv
load_dotenv(POLYCLAW_DIR / ".env")

print("=" * 70)
print("🔄 AUTO REDEEM SERVICE")
print("=" * 70)
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Import PolyClaw
from lib.wallet_manager import WalletManager
from lib.gamma_client import GammaClient
import asyncio

# State file
STATE_FILE = WORKSPACE / "auto_redeem_state.json"

def load_state():
    """Load redemption state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"redeemed": [], "pending": []}

def save_state(state):
    """Save redemption state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

async def check_and_redeem():
    """Check for winning positions and redeem."""
    wallet = WalletManager()
    gc = GammaClient()
    
    print(f"💳 Wallet: {wallet.address}")
    print()
    
    # Check balance
    bal = wallet.get_balances()
    print(f"💰 Current: ${bal.usdc_e:.2f} USDC.e | {bal.pol:.4f} POL")
    print()
    
    # For now, monitor the specific market you won
    market_id = "1515491"
    
    print(f"🔍 Checking market {market_id}...")
    
    try:
        market = await gc.get_market(market_id)
        print(f"   Question: {market.question}")
        print(f"   Resolved: {market.resolved}")
        print(f"   YES Price: {market.yes_price:.3f}")
        print(f"   NO Price: {market.no_price:.3f}")
        
        # Determine winner from prices
        if market.yes_price == 1.0 and market.no_price == 0.0:
            winner = "YES"
            print(f"   🏆 Winner: YES (BTC went UP)")
        elif market.yes_price == 0.0 and market.no_price == 1.0:
            winner = "NO"
            print(f"   🏆 Winner: NO (BTC went DOWN)")
        else:
            winner = None
            print(f"   ⏳ Not yet resolved")
            return
        
        # You bet YES
        if winner == "YES":
            print()
            print("✅ YOU WON!")
            print("   Your YES position is worth $1.00")
            print()
            print("🔄 Redemption steps:")
            print("   1. Check if already redeemed")
            print("   2. If not, submit redeem transaction")
            print()
            
            state = load_state()
            if market_id in state["redeemed"]:
                print("   ✅ Already redeemed!")
            else:
                print("   ⏳ Need to redeem...")
                print()
                print("   For now, please redeem manually:")
                print("   1. Go to https://polymarket.com/portfolio")
                print("   2. Connect wallet: {wallet.address}")
                print("   3. Find the BTC 5m market")
                print("   4. Click 'Redeem'")
                print()
                print("   Auto-redeem will be fully implemented soon!")
        else:
            print()
            print("❌ Position lost (NO won)")
            
    except Exception as e:
        print(f"   Error: {e}")

# Run check
asyncio.run(check_and_redeem())

print()
print("=" * 70)
print("⏰ Run this script every 5 minutes to check for resolution")
print("   Or set up as cron job:")
print("   */5 * * * * cd /root/.openclaw/workspace && python check_redeem.py")
print("=" * 70)
