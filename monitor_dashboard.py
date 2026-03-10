#!/usr/bin/env python3
"""
Bot Monitor Dashboard
Real-time monitoring of V4 bot with resolution fallback
"""

import json
import time
import os
from datetime import datetime
from pathlib import Path

def clear():
    os.system('clear' if os.name != 'nt' else 'cls')

def load_json_safe(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def tail_jsonl(path, n=10):
    try:
        with open(path) as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-n:] if line.strip()]
    except:
        return []

def format_money(val):
    return f"${val:,.2f}" if val else "$0.00"

def main():
    while True:
        clear()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("="*70)
        print(f"  V4 BOT MONITOR - {now}")
        print("="*70)
        
        # Load wallet state
        wallet = load_json_safe("/root/.openclaw/workspace/wallet_v4_production.json", {})
        print("\n📊 WALLET STATUS")
        print("-"*70)
        print(f"  Balance:       {format_money(wallet.get('bankroll_current'))}")
        print(f"  Started:       {wallet.get('started_at', 'N/A')}")
        print(f"  Total Trades:  {wallet.get('total_trades', 0)}")
        print(f"  Win Rate:      {wallet.get('winning_trades', 0)}/{wallet.get('total_trades', 0)} wins")
        print(f"  Total P&L:     {format_money(wallet.get('total_pnl'))}")
        
        # Load resolution state
        resolution = load_json_safe("/root/.openclaw/workspace/resolution_state.json", {})
        unresolved = [v for v in resolution.values() if not v.get('resolved')]
        resolved = [v for v in resolution.values() if v.get('resolved')]
        
        print("\n🔍 RESOLUTION FALLBACK STATUS")
        print("-"*70)
        print(f"  Tracked positions: {len(resolution)}")
        print(f"  Unresolved:        {len(unresolved)}")
        print(f"  Resolved:          {len(resolved)}")
        
        if unresolved:
            print("\n  🔴 UNRESOLVED:")
            for pos in unresolved[:3]:  # Show first 3
                print(f"    - {pos.get('market_id')} ({pos.get('coin')} {pos.get('timeframe_minutes')}m)")
        
        if resolved:
            print("\n  ✅ RECENTLY RESOLVED:")
            for pos in resolved[-3:]:  # Show last 3
                tier = pos.get('resolution_tier', 1)
                tier_label = {1: "OFFICIAL", 2: "FALLBACK", 3: "FORCED"}.get(tier, "?")
                print(f"    - {pos.get('market_id')} → {pos.get('resolution_outcome')} [{tier_label}]")
        
        # Recent audit entries
        audit = tail_jsonl("/root/.openclaw/workspace/resolution_audit.jsonl", 5)
        if audit:
            print("\n📝 RECENT AUDIT ENTRIES")
            print("-"*70)
            for entry in audit:
                tier = entry.get('tier', 1)
                tier_label = {1: "T1", 2: "T2", 3: "T3"}.get(tier, "?")
                print(f"  [{tier_label}] {entry.get('market_id')} | {entry.get('outcome')} | {entry.get('source')}")
        
        # Check bot process
        import subprocess
        try:
            result = subprocess.run(['pgrep', '-f', 'ultimate_bot_v4_production'], 
                                  capture_output=True, text=True)
            if result.stdout.strip():
                pid = result.stdout.strip().split('\n')[0]
                print(f"\n🤖 BOT STATUS: Running (PID {pid})")
            else:
                print(f"\n🤖 BOT STATUS: NOT RUNNING")
        except:
            print(f"\n🤖 BOT STATUS: Unknown")
        
        # Recent trades
        trades = wallet.get('trades', [])
        if trades:
            print("\n💰 RECENT TRADES")
            print("-"*70)
            for trade in trades[-3:]:
                status = trade.get('resolution_status', 'OPEN')
                pnl = trade.get('pnl', 0)
                print(f"  {trade.get('market')} {trade.get('side')} @ {trade.get('entry_price')} | {status} | {format_money(pnl)}")
        
        print("\n" + "="*70)
        print("Press Ctrl+C to exit. Refreshing every 10 seconds...")
        print("="*70)
        
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n\nMonitor stopped.")
            break

if __name__ == "__main__":
    main()
