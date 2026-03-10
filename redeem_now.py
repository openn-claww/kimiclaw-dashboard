#!/usr/bin/env python3
"""
Quick Redeem - Immediate redemption of a specific market
Use this to manually redeem your $1 win right now.
"""

import os
import sys
from pathlib import Path

# Add paths
POLYCLAW_DIR = Path("/root/.openclaw/skills/polyclaw")
sys.path.insert(0, str(POLYCLAW_DIR))

# Load env
from dotenv import load_dotenv
load_dotenv(POLYCLAW_DIR / ".env")

print("=" * 70)
print("💰 QUICK REDEEM - Your $1 Win")
print("=" * 70)

# Import required modules
from lib.wallet_manager import WalletManager
from auto_redeem import CTFRedeemer, ResolutionChecker, RedemptionRecord

def redeem_now():
    """Redeem the winning position immediately."""
    
    wallet = WalletManager()
    redeemer = CTFRedeemer(wallet_manager=wallet)
    checker = ResolutionChecker()
    
    # The market you won
    market_id = "1515491"
    slug = "btc-updown-5m-1772899500"
    
    print(f"🎯 Checking market: {market_id}")
    print(f"   Slug: {slug}")
    print()
    
    # Check if resolved
    result = checker.check(slug)
    
    if not result:
        print("❌ Could not check market status")
        return
    
    print(f"✅ Market check complete:")
    print(f"   Resolved: {result.get('resolved')}")
    print(f"   Winner: {result.get('winner')}")
    print()
    
    if not result.get('resolved'):
        print("⏳ Market not yet resolved - check back later")
        return
    
    winner = result.get('winner')
    print(f"🏆 Winner is: {winner}")
    
    # Check if you won
    your_side = "YES"  # You bought YES
    if winner != your_side:
        print(f"❌ You bet {your_side} but {winner} won")
        print("   This position lost")
        return
    
    print(f"✅ You won! Your {your_side} position is winning!")
    print()
    
    # Create redemption record
    record = RedemptionRecord(
        market_id=market_id,
        slug=slug,
        side="YES",
        entry_price=0.480,
        size=1.0
    )
    
    print("🔄 Submitting redemption transaction...")
    print("   (This may take 10-30 seconds)")
    print()
    
    try:
        result = redeemer.redeem(record)
        
        if result.get("success"):
            print("=" * 70)
            print("✅ REDEMPTION SUCCESSFUL!")
            print("=" * 70)
            print()
            print(f"💰 Amount Redeemed: ${result.get('amount', 0):.2f}")
            print(f"📊 P&L: ${result.get('pnl', 0):+.2f}")
            print(f"🔗 Transaction: {result.get('tx_hash', 'N/A')[:20]}...")
            print()
            print("Your wallet should now have the USDC.e credited!")
            print("Check with: polyclaw wallet status")
        else:
            print("=" * 70)
            print("❌ Redemption failed")
            print("=" * 70)
            print()
            print(f"Error: {result.get('error', 'Unknown')}")
            print()
            print("Options:")
            print("  1. Try again in a few minutes")
            print("  2. Redeem manually on polymarket.com")
            print("  3. Wait for auto-redeem to handle it")
            
    except Exception as e:
        print(f"❌ Error during redemption: {e}")
        import traceback
        traceback.print_exc()

# Run
if __name__ == "__main__":
    redeem_now()

print()
print("=" * 70)
print("To run continuous auto-redeem:")
print("  python run_auto_redeem.py")
print("=" * 70)
