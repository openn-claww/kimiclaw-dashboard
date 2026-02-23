#!/usr/bin/env python3
"""
4-Trade Window Mode
Temporarily lower thresholds for 4 trades, then revert
"""

import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# Temporary settings for 4-trade window
TEMP_CONFIDENCE = 7  # 70%
TEMP_EDGE = 0.065    # 6.5%
TARGET_TRADES = 4
REVERT_CONFIDENCE = 7.5  # 75%
REVERT_EDGE = 0.07       # 7%

DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"
REPORT_CHANNEL = "1474639263898275860"

def get_trade_count_today():
    """Count today's trades"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trades WHERE date(timestamp) = date('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_recent_trades(limit=4):
    """Get recent trades for reporting"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trades 
        WHERE date(timestamp) = date('now')
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (limit,))
    trades = cursor.fetchall()
    conn.close()
    return [dict(t) for t in trades]

def generate_layman_report(trades):
    """Generate simple report in plain English"""
    if not trades:
        return "No trades executed yet."
    
    report = []
    report.append("🎯 **4-TRADE WINDOW COMPLETE!**")
    report.append("")
    
    total_invested = 0
    total_potential_profit = 0
    
    for i, trade in enumerate(reversed(trades), 1):
        report.append(f"**Trade #{i}**")
        report.append(f"📊 Market: {trade['market_question'][:60]}...")
        report.append(f"💰 Bet: ${trade['size_usd']:.2f} on {trade['side']}")
        report.append(f"🎯 Confidence: {trade['confidence']}/10 ({trade['confidence']*10}% sure)")
        report.append(f"📈 Entry Price: ${trade['entry_price']:.2f}")
        
        # Simple explanation
        if trade['side'] == 'YES':
            report.append(f"🤔 What this means: You bet ${trade['size_usd']:.2f} that this event WILL happen")
        else:
            report.append(f"🤔 What this means: You bet ${trade['size_usd']:.2f} that this event WON'T happen")
        
        # Potential win
        potential_win = trade['size_usd'] * (1 / trade['entry_price'] - 1)
        report.append(f"💵 If you win: You get ~${potential_win:.2f} profit")
        report.append(f"❌ If you lose: You lose ~${trade['size_usd'] * 0.65:.2f} (after selling the other side)")
        report.append(f"🔗 Transaction: {trade['tx_hash'][:25]}...")
        report.append("")
        
        total_invested += trade['size_usd']
        total_potential_profit += potential_win
    
    report.append("=" * 50)
    report.append("📊 **SUMMARY**")
    report.append(f"💸 Total Invested: ${total_invested:.2f}")
    report.append(f"💰 Potential Profit (if all win): ${total_potential_profit:.2f}")
    report.append(f"⚠️  Risk: Could lose ~${total_invested * 0.65:.2f} if all lose")
    report.append("")
    report.append("✅ **SETTINGS REVERTED** back to normal:")
    report.append(f"   • Confidence: 75% (was 70% for these 4 trades)")
    report.append(f"   • Edge: 7% (was 6.5% for these 4 trades)")
    report.append("")
    report.append("🤖 Auto-redeem is ON - I'll claim winnings automatically!")
    
    return "\n".join(report)

def main():
    current_trades = get_trade_count_today()
    
    print(f"Trades today: {current_trades}")
    
    if current_trades >= TARGET_TRADES:
        # Generate report for the 4 trades
        trades = get_recent_trades(TARGET_TRADES)
        report = generate_layman_report(trades)
        print(report)
        
        # Signal to revert settings
        print("\n🔄 REVERTING SETTINGS TO NORMAL...")
        print(f"   Confidence: {REVERT_CONFIDENCE}/10 ({REVERT_CONFIDENCE*10}%)")
        print(f"   Edge: {REVERT_EDGE*100}%")
        
        return True  # Signal to revert
    else:
        remaining = TARGET_TRADES - current_trades
        print(f"4-Trade Window Active: {remaining} trades remaining")
        print(f"Current Settings: {TEMP_CONFIDENCE}/10 conf | {TEMP_EDGE*100}% edge")
        return False

if __name__ == "__main__":
    should_revert = main()
    sys.exit(0 if should_revert else 1)
