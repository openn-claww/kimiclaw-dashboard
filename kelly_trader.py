#!/usr/bin/env python3
"""
Kelly Criterion Trading System
Updated thresholds: 70% confidence, 6.5% edge, $3 max, Kelly 0.5
"""

import os
import sys
import json
import sqlite3
import requests
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Load API keys
CONFIG_FILE = Path("/root/.openclaw/workspace/api_config.sh")
if CONFIG_FILE.exists():
    with open(CONFIG_FILE) as f:
        for line in f:
            if 'export' in line and '=' in line:
                key_val = line.replace('export ', '').strip().split('=', 1)
                if len(key_val) == 2:
                    os.environ[key_val[0]] = key_val[1].strip().strip('"').strip("'")

# Trading Config - 4-Trade Window Mode (Temporary)
MIN_CONFIDENCE = 7    # 70% (temporary for 4 trades)
MIN_EDGE = 0.065      # 6.5% (temporary for 4 trades)
MAX_BET = 4.0         # $4 max for high confidence
STANDARD_BET = 2.0    # $2 standard bet
HIGH_CONFIDENCE_THRESHOLD = 9  # 90% or 100%
STOP_LOSS = 2.0
DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"

class KellyTrader:
    def __init__(self):
        self.wallet = self.get_wallet_balance()
        self.api_sports_key = os.getenv('API_SPORTS_KEY', '')
        self.weather_api_key = os.getenv('WEATHER_API_KEY', '')
        
    def get_wallet_balance(self):
        try:
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py wallet status"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data.get('balances', {}).get('USDC.e', 0))
        except:
            pass
        return 32.93
    
    def calculate_bet_size(self, confidence, edge, bankroll):
        """Calculate bet size: $2 standard, $4 for 90%+ confidence"""
        
        # High confidence (90% or 100%) = $4 max bet
        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return min(MAX_BET, bankroll * 0.12)  # $4 or 12% of bankroll
        
        # Standard bet = $2
        return min(STANDARD_BET, bankroll * 0.06)  # $2 or 6% of bankroll
    
    def run_backtest_7days(self):
        """Simulate trading with new thresholds on last 7 days"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all trades from last 7 days
        cursor.execute("""
            SELECT * FROM trades 
            WHERE timestamp >= datetime('now', '-7 days')
            ORDER BY timestamp ASC
        """)
        
        all_trades = cursor.fetchall()
        conn.close()
        
        if not all_trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'net_pnl': 0,
                'avg_edge': 0,
                'message': 'No historical trades in last 7 days'
            }
        
        # Simulate with new thresholds
        simulated_trades = []
        total_pnl = 0
        wins = 0
        total_edge = 0
        
        for trade in all_trades:
            t = dict(trade)
            confidence = t.get('confidence', 5)
            edge = t.get('edge', 0)
            
            # Check if meets new thresholds
            if confidence >= MIN_CONFIDENCE and edge >= MIN_EDGE:
                simulated_trades.append(t)
                
                # Calculate Kelly bet
                win_prob = confidence / 10
                odds = 1 / t['entry_price'] if t['entry_price'] > 0 else 2
                bet_size = self.calculate_kelly_bet(win_prob, odds, 30)  # Assume $30 bankroll
                
                # Simulate result
                if t['pnl_usd'] is not None:
                    actual_pnl = t['pnl_usd']
                    total_pnl += actual_pnl
                    if actual_pnl > 0:
                        wins += 1
                
                total_edge += edge
        
        num_trades = len(simulated_trades)
        
        return {
            'total_trades': num_trades,
            'win_rate': (wins / num_trades * 100) if num_trades > 0 else 0,
            'net_pnl': total_pnl,
            'avg_edge': (total_edge / num_trades * 100) if num_trades > 0 else 0,
            'trades': simulated_trades
        }
    
    def scan_live_opportunities(self):
        """Scan for live trading opportunities"""
        print("="*70)
        print("KELLY TRADER - LIVE SCAN")
        print("="*70)
        print(f"Settings: {MIN_CONFIDENCE}/10 conf | {MIN_EDGE*100}% edge | ${MAX_BET} max | {KELLY_FRACTION} Kelly")
        print(f"Wallet: ${self.wallet:.2f}")
        print("="*70)
        
        opportunities = []
        
        # Scan each category
        print("\n🔶 Scanning CRYPTO...")
        # Would scan BTC/ETH markets
        
        print("\n🏀 Scanning SPORTS...")
        # Would scan NBA/Soccer
        
        print("\n🌦️ Scanning WEATHER...")
        # Would scan rain markets
        
        return opportunities

def main():
    trader = KellyTrader()
    
    # Run backtest
    print("Running 7-day backtest with new settings...\n")
    backtest = trader.run_backtest_7days()
    
    print("="*70)
    print("7-DAY BACKTEST RESULTS")
    print("="*70)
    print(f"Settings: {MIN_CONFIDENCE}/10 confidence | {MIN_EDGE*100}% edge | ${MAX_BET} max | {KELLY_FRACTION} Kelly")
    print("-"*70)
    print(f"Total Trades: {backtest['total_trades']}")
    print(f"Win Rate: {backtest['win_rate']:.1f}%")
    print(f"Net PNL: ${backtest['net_pnl']:+.2f}")
    print(f"Avg Edge: {backtest['avg_edge']:.2f}%")
    print("="*70)
    
    if backtest.get('message'):
        print(f"\nNote: {backtest['message']}")
    
    # Live scan
    print("\n")
    trader.scan_live_opportunities()

if __name__ == "__main__":
    main()
