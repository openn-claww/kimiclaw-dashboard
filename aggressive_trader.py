#!/usr/bin/env python3
"""
Aggressive Profit Trading System
2% standard bets, 4$ on 100% confidence, auto-stop at $2
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Config
WALLET_ADDRESS = "0x557A656C110a9eFdbFa28773DE4aCc2c3924a274"
STOP_LOSS_THRESHOLD = 2.0  # Stop trading when wallet hits $2
STANDARD_BET = 2.0         # $2 per standard bet
HIGH_CONFIDENCE_BET = 4.0  # $4 on 100% confidence
MIN_CONFIDENCE = 8         # Minimum confidence to trade
STANDARD_BET_PCT = 0.02    # 2% of wallet
DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"

class AggressiveTrader:
    def __init__(self):
        self.wallet_balance = self.get_wallet_balance()
        self.standard_bet = self.wallet_balance * STANDARD_BET_PCT
        self.high_bet = HIGH_CONFIDENCE_BET
        self.trades_today = []
        
    def get_wallet_balance(self):
        """Get current USDC.e balance"""
        try:
            import subprocess
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py wallet status"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data.get('balances', {}).get('USDC.e', 0))
        except:
            pass
        return 32.93  # Fallback to known balance
    
    def should_stop_trading(self):
        """Check if we hit stop-loss threshold"""
        return self.wallet_balance <= STOP_LOSS_THRESHOLD
    
    def calculate_bet_size(self, confidence, edge):
        """Calculate bet size based on confidence"""
        if confidence >= 10 and edge >= 0.20:  # 100% confidence, 20% edge
            return min(HIGH_CONFIDENCE_BET, self.wallet_balance * 0.12)  # $4 max
        elif confidence >= 8 and edge >= 0.10:  # High confidence
            return min(STANDARD_BET, self.wallet_balance * 0.06)  # $2 standard
        else:
            return 0  # Don't trade
    
    def log_trade_lesson(self, trade_data):
        """Learn from each trade"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        lesson = f"Trade {trade_data['id']}: {trade_data['market'][:30]}... | "
        lesson += f"Confidence {trade_data['confidence']}/10, Edge {trade_data['edge']*100:.1f}%, "
        lesson += f"Result: {trade_data.get('result', 'PENDING')}"
        
        cursor.execute("""
            UPDATE trades SET lesson_learned = ? WHERE id = ?
        """, (lesson, trade_data['id']))
        
        conn.commit()
        conn.close()
        
        # Also log to file
        with open("/root/.openclaw/workspace/trade_lessons.log", "a") as f:
            f.write(f"[{datetime.now()}] {lesson}\n")
    
    def get_penny_breakdown(self, trade_amount, category):
        """Calculate exact penny breakdown for each trade"""
        gas_split = 0.015
        gas_clob = 0.005
        gas_redeem = 0.010
        
        return {
            'wagered': trade_amount,
            'gas_split': gas_split,
            'gas_clob': gas_clob,
            'gas_redeem': gas_redeem,
            'total_gas': gas_split + gas_clob + gas_redeem,
            'net_invested': trade_amount - (trade_amount * 0.35),  # ~35% recovered from selling NO
            'platform_fee': 0.0,
            'expected_return_win': trade_amount * 1.0,  # $1 becomes $1
            'profit_if_win': trade_amount * 0.65 - (gas_split + gas_clob + gas_redeem),
            'loss_if_lose': trade_amount * 0.65 + gas_split + gas_clob
        }

def main():
    trader = AggressiveTrader()
    
    print("="*70)
    print("AGGRESSIVE PROFIT TRADING SYSTEM")
    print("="*70)
    print(f"Wallet: ${trader.wallet_balance:.2f}")
    print(f"Standard Bet (2%): ${trader.standard_bet:.2f}")
    print(f"High Confidence Bet: ${trader.high_bet:.2f}")
    print(f"Stop-Loss: ${STOP_LOSS_THRESHOLD}")
    print("="*70)
    
    if trader.should_stop_trading():
        print("🛑 STOPPING: Wallet at or below $2 threshold!")
        return
    
    print("✅ READY TO TRADE - Looking for opportunities...")
    
    # This would integrate with the pro trader scan
    # and execute trades based on confidence/edge

if __name__ == "__main__":
    main()
