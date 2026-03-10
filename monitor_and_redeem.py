#!/usr/bin/env python3
"""Monitor and auto-redeem the $1 YES position"""
import sys
import time
import json
import os

sys.path.insert(0, '/root/.openclaw/skills/polyclaw')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/skills/polyclaw/.env')

from lib.wallet_manager import WalletManager
from web3 import Web3

# Market details from our trade
CONDITION_ID = "0x77db1082063e3720440a52f7e17531452887ede3dc1661fe6a18dd14a06e7e07"
TX_HASH = "3ba0b78260e909bbb0f01de48f7353f5866f07d656e74f83e728ef7637a550c6"

def check_resolution():
    """Check if market is resolved via Gamma API"""
    import requests
    try:
        # Query the condition ID
        url = f"https://gamma-api.polymarket.com/events?condition_ids={CONDITION_ID}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data and len(data) > 0:
            event = data[0]
            return {
                'resolved': event.get('resolved', False),
                'closed': event.get('closed', False),
                'winner': event.get('winner'),
                'resolution': event.get('resolution')
            }
    except Exception as e:
        print(f"API check failed: {e}")
    
    return None

def main():
    print("="*60)
    print("AUTO-REDEMPTION MONITOR")
    print("="*60)
    print(f"Condition ID: {CONDITION_ID}")
    print(f"Original TX: {TX_HASH}")
    print()
    
    # Check initial status
    status = check_resolution()
    if status:
        print(f"Market Closed: {status['closed']}")
        print(f"Market Resolved: {status['resolved']}")
        if status['winner']:
            print(f"Winner: {status['winner']}")
        print()
    
    if status and status['resolved']:
        print("✅ Market already resolved!")
        print(f"Winner: {status['winner']}")
        # TODO: Execute redemption
    else:
        print("⏳ Market not yet resolved.")
        print("Monitoring will check every 30 seconds...")
        print("(You can leave this running)")
        
        # Monitor loop
        checks = 0
        while True:
            time.sleep(30)
            checks += 1
            
            status = check_resolution()
            if status and status['resolved']:
                print(f"\n🎉 RESOLVED! Winner: {status['winner']}")
                print("Attempting redemption...")
                # TODO: Redeem
                break
            
            if checks % 10 == 0:
                print(f"  ...checked {checks} times, still waiting")

if __name__ == "__main__":
    main()
