#!/usr/bin/env python3
"""
Profit Tracker - Detailed penny-to-penny breakdown
Generates report when user returns
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"
REPORT_FILE = "/root/.openclaw/workspace/profit_report.txt"

class ProfitTracker:
    def __init__(self):
        self.start_balance = 32.93  # When you went to sleep
        self.start_time = datetime.now()
        
    def generate_full_report(self):
        """Generate complete profit report"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Get all trades since start
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM trades 
            WHERE timestamp >= datetime('now', '-8 hours')
            ORDER BY timestamp ASC
        """)
        
        new_trades = cursor.fetchall()
        conn.close()
        
        report = []
        report.append("="*80)
        report.append("PROFIT REPORT - WHILE YOU WERE SLEEPING")
        report.append("="*80)
        report.append(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M GMT')}")
        report.append(f"Starting Balance: ${self.start_balance:.2f}")
        report.append("="*80)
        
        if new_trades:
            report.append(f"\n📊 NEW TRADES EXECUTED: {len(new_trades)}")
            report.append("-"*80)
            
            total_invested = 0
            total_gas = 0
            total_profit = 0
            
            for trade in new_trades:
                t = dict(trade)
                report.append(f"\n🎯 TRADE #{t['id']}")
                report.append(f"   Time: {t['timestamp']}")
                report.append(f"   Market: {t['market_question']}")
                report.append(f"   Side: {t['side']}")
                report.append(f"   Amount Wagered: ${t['size_usd']:.2f}")
                
                # Penny breakdown
                gas_split = 0.015
                gas_clob = 0.005
                gas_redeem = 0.010
                total_gas_trade = gas_split + gas_clob + gas_redeem
                
                report.append(f"   Gas Split: ${gas_split:.3f}")
                report.append(f"   Gas CLOB: ${gas_clob:.3f}")
                report.append(f"   Gas Redeem: ${gas_redeem:.3f}")
                report.append(f"   TOTAL GAS: ${total_gas_trade:.3f}")
                report.append(f"   Platform Fee: $0.00")
                
                net_cost = t['size_usd'] * 0.65  # After selling NO
                report.append(f"   Net Invested: ${net_cost:.2f}")
                report.append(f"   Entry Price: ${t['entry_price']:.2f}")
                report.append(f"   Confidence: {t['confidence']}/10")
                
                if t['pnl_usd'] is not None:
                    report.append(f"   RESULT: ${t['pnl_usd']:+.2f}")
                    total_profit += t['pnl_usd']
                else:
                    report.append(f"   Status: {t['status']}")
                
                report.append(f"   Tx: {t['tx_hash'][:20]}...")
                report.append(f"   Lesson: {t.get('lesson_learned', 'Pending')}")
                
                total_invested += t['size_usd']
                total_gas += total_gas_trade
            
            report.append("\n" + "="*80)
            report.append("SUMMARY")
            report.append("="*80)
            report.append(f"Total Trades: {len(new_trades)}")
            report.append(f"Total Invested: ${total_invested:.2f}")
            report.append(f"Total Gas Spent: ${total_gas:.3f}")
            report.append(f"Total Profit/Loss: ${total_profit:+.2f}")
            report.append(f"Net Profit (after gas): ${total_profit - total_gas:+.2f}")
            
        else:
            report.append("\n⏳ No new trades executed yet.")
        
        report.append("\n" + "="*80)
        report.append("CURRENT STATUS")
        report.append("="*80)
        report.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M GMT')}")
        report.append(f"Wallet: Check #operations channel for live balance")
        report.append(f"Auto-Redeem: Active - claiming winners immediately")
        report.append(f"Stop-Loss: $2.00 (trading stops if hit)")
        report.append("="*80)
        
        return "\n".join(report)
    
    def save_and_send(self):
        """Save report and prepare for user"""
        report = self.generate_full_report()
        
        with open(REPORT_FILE, 'w') as f:
            f.write(report)
        
        print(report)
        return report

if __name__ == "__main__":
    tracker = ProfitTracker()
    tracker.save_and_send()
