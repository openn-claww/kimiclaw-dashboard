#!/usr/bin/env python3
"""
v6_stats.py - Show V6 bot detailed statistics
"""

import json
import os
from datetime import datetime

def load_json_safe(filepath):
    try:
        with open(filepath) as f:
            return json.load(f)
    except:
        return None

def main():
    print("=" * 70)
    print("              V6 BOT DETAILED STATISTICS")
    print("=" * 70)
    print()
    
    # Check if running
    bot_pid = None
    monitor_pid = None
    
    if os.path.exists("v6_bot.pid"):
        with open("v6_bot.pid") as f:
            bot_pid = f.read().strip()
    
    if os.path.exists("v6_health_monitor.pid"):
        with open("v6_health_monitor.pid") as f:
            monitor_pid = f.read().strip()
    
    print(f"🟢 Bot PID:        {bot_pid or 'Not running'}")
    print(f"🟢 Monitor PID:    {monitor_pid or 'Not running'}")
    print()
    
    # Load health data
    health_data = load_json_safe("v6_health_monitor.json")
    bot_health = load_json_safe("master_v6_health.json")
    
    if health_data:
        print("Health Monitor History:")
        print("-" * 70)
        
        # Get latest
        latest = health_data[-1] if health_data else {}
        stats = latest.get("stats", {})
        
        print(f"Last Update:     {latest.get('timestamp', 'N/A')}")
        print(f"Status:          {latest.get('status', 'N/A')}")
        print()
        print(f"Virtual Balance: $250.00")
        print(f"Total Trades:    {stats.get('trades', 0)}")
        print(f"Winning Trades:  {stats.get('wins', 0)}")
        print(f"Losing Trades:   {stats.get('trades', 0) - stats.get('wins', 0)}")
        
        win_rate = (stats.get('wins', 0) / stats.get('trades', 0) * 100) if stats.get('trades', 0) > 0 else 0
        print(f"Win Rate:        {win_rate:.1f}%")
        print(f"PnL:             ${stats.get('pnl', 0):+.2f}")
        print(f"ROI:             {(stats.get('pnl', 0) / 250 * 100):+.2f}%")
        print()
        
        # Show last 5 entries
        print("Recent Activity (Last 5 checks):")
        print("-" * 70)
        for entry in health_data[-5:]:
            ts = entry['timestamp'].split('T')[1].split('.')[0]
            status = entry['status']
            detail = entry.get('detail', '')[:50]
            print(f"  {ts} | {status:12} | {detail}")
    else:
        print("⚠️  No health data available yet")
    
    print()
    
    # Bot health file
    if bot_health:
        print("Bot Health File:")
        print("-" * 70)
        
        arb = bot_health.get("arb_engine", {})
        news = bot_health.get("news_feed", {})
        
        print(f"Arb Enabled:     {arb.get('enabled', False)}")
        print(f"Arb Trades:      {arb.get('trades', 0)}")
        print(f"Arb Wins:        {arb.get('wins', 0)}")
        print(f"Arb PnL:         ${arb.get('pnl_usd', 0):+.2f}")
        print(f"Min Spread:      {arb.get('min_spread', 'N/A')}")
        print()
        print(f"News Sentiment:  {news.get('sentiment', 'N/A')}")
        print(f"News Confidence: {news.get('confidence', 0)}")
        print(f"News Source:     {news.get('source', 'N/A')}")
    else:
        print("⚠️  No bot health file yet")
    
    print()
    print("=" * 70)
    print(f"Generated: {datetime.now().isoformat()}")
    print("=" * 70)

if __name__ == "__main__":
    main()
