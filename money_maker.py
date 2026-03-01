#!/usr/bin/env python3
"""
Multi-Strategy Money Maker
Short-term trading: 5min, 15min, 30min markets + other opportunities
"""

import os
import sys
import json
import time
import sqlite3
import requests
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/skills/polyclaw')
sys.path.insert(0, '/root/.openclaw/workspace')

DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"
LOG_FILE = "/root/.openclaw/workspace/money_maker.log"

class MoneyMaker:
    def __init__(self):
        self.wallet_usdc = 0
        self.wallet_pol = 0
        self.active_bets = 0
        self.daily_profit = 0
        self.positions = []
        self.opportunities = []
        
    def log(self, msg):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{timestamp}] {msg}\n")
        print(f"[{timestamp}] {msg}")
    
    def get_wallet_balance(self):
        try:
            # Use bash -c to properly source .env and run command
            cmd = "bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py wallet status'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                # Parse JSON from output - find the JSON object
                output = result.stdout.strip()
                # Find JSON boundaries
                start = output.find('{')
                end = output.rfind('}')
                if start != -1 and end != -1:
                    data = json.loads(output[start:end+1])
                    self.wallet_usdc = float(data.get('balances', {}).get('USDC.e', 0))
                    self.wallet_pol = float(data.get('balances', {}).get('POL', 0))
                    return self.wallet_usdc
        except Exception as e:
            self.log(f"Wallet parse error: {e}")
            # Fallback: try to use cached value from memory db
            try:
                conn = sqlite3.connect("/root/.openclaw/workspace/memory/memory.db")
                cursor = conn.cursor()
                cursor.execute("SELECT content FROM memories WHERE type='wallet_balance' ORDER BY timestamp DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    self.wallet_usdc = float(row[0])
                    return self.wallet_usdc
            except:
                pass
        return 0
    
    def get_positions(self):
        try:
            cmd = "bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py positions'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[2:]  # Skip header
                positions = []
                for line in lines:
                    if '|' in line and '$' in line:
                        parts = line.split('|')
                        if len(parts) >= 5:
                            positions.append({
                                'id': parts[0].strip(),
                                'side': parts[1].strip(),
                                'entry': parts[2].strip(),
                                'now': parts[3].strip(),
                                'pnl': parts[4].strip(),
                                'market': parts[5].strip() if len(parts) > 5 else ''
                            })
                self.positions = positions
                return positions
        except Exception as e:
            self.log(f"Positions error: {e}")
        return []
    
    def scan_short_term_markets(self):
        """Scan for short-term markets"""
        self.log("Scanning short-term markets...")
        
        opportunities = []
        
        # Search terms for short-term markets
        search_terms = [
            'Bitcoin',
            'NBA',
            'Nuggets',
            'Warriors',
            'Cavaliers',
            'Thunder',
            'Spurs',
            'Pistons',
            'Celtics',
            'Lakers',
            'Iran',
            'Fed',
            'Trump',
            'Crypto',
            'Ethereum'
        ]
        
        for term in search_terms[:8]:
            try:
                cmd = f"bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search \"{term}\" --limit 10'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[2:]  # Skip header
                    for line in lines:
                        if '|' in line and '$' in line:
                            parts = line.split('|')
                            if len(parts) >= 5:
                                try:
                                    market_id = parts[0].strip()
                                    yes_price = float(parts[1].replace('$', '').strip())
                                    no_price = float(parts[2].replace('$', '').strip())
                                    volume_str = parts[3].strip().replace('K', '000').replace('M', '000000').replace('$', '').replace(',', '')
                                    volume = float(volume_str)
                                    question = parts[4].strip()
                                    
                                    # Look for short-term opportunities with edge
                                    # Relaxed volume threshold to $50K for more opportunities
                                    if volume > 50000:
                                        # Look for mispriced markets (edge > 10%)
                                        # Relaxed threshold: prices < $0.40 for 10%+ edge
                                        if yes_price < 0.40:  # Undervalued YES
                                            opportunities.append({
                                                'id': market_id,
                                                'market': question,
                                                'side': 'YES',
                                                'price': yes_price,
                                                'volume': volume,
                                                'edge': round((0.5 - yes_price) * 100, 1),
                                                'timeframe': self.detect_timeframe(question)
                                            })
                                        elif no_price < 0.40:  # Undervalued NO
                                            opportunities.append({
                                                'id': market_id,
                                                'market': question,
                                                'side': 'NO',
                                                'price': no_price,
                                                'volume': volume,
                                                'edge': round((0.5 - no_price) * 100, 1),
                                                'timeframe': self.detect_timeframe(question)
                                            })
                                except:
                                    continue
            except Exception as e:
                self.log(f"Search error for '{term}': {e}")
                continue
        
        # Also check trending markets
        try:
            cmd = "bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets trending --limit 15'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[2:]
                for line in lines:
                    if '|' in line and '$' in line:
                        parts = line.split('|')
                        if len(parts) >= 5:
                            try:
                                market_id = parts[0].strip()
                                yes_price = float(parts[1].replace('$', '').strip())
                                no_price = float(parts[2].replace('$', '').strip())
                                volume_str = parts[3].strip().replace('K', '000').replace('M', '000000').replace('$', '').replace(',', '')
                                volume = float(volume_str)
                                question = parts[4].strip()
                                
                                if volume > 50000:
                                    # Relaxed threshold for trending: < $0.35 for 15%+ edge
                                    if yes_price < 0.35:  # Strong undervalued YES
                                        opportunities.append({
                                            'id': market_id,
                                            'market': question,
                                            'side': 'YES',
                                            'price': yes_price,
                                            'volume': volume,
                                            'edge': round((0.5 - yes_price) * 100, 1),
                                            'timeframe': self.detect_timeframe(question)
                                        })
                                    elif no_price < 0.35:  # Strong undervalued NO
                                        opportunities.append({
                                            'id': market_id,
                                            'market': question,
                                            'side': 'NO',
                                            'price': no_price,
                                            'volume': volume,
                                            'edge': round((0.5 - no_price) * 100, 1),
                                            'timeframe': self.detect_timeframe(question)
                                        })
                            except:
                                continue
        except Exception as e:
            self.log(f"Trending search error: {e}")
        
        # Remove duplicates
        seen = set()
        unique_opps = []
        for opp in opportunities:
            if opp['id'] not in seen:
                seen.add(opp['id'])
                unique_opps.append(opp)
        
        self.log(f"Found {len(unique_opps)} short-term opportunities")
        # Debug: log first few opportunities found
        for opp in unique_opps[:3]:
            self.log(f"  Opp: {opp['market'][:40]}... {opp['side']} @ ${opp['price']:.2f} (edge: {opp['edge']}%)")
        
        self.opportunities = unique_opps
        return unique_opps
    
    def detect_timeframe(self, question):
        """Detect market timeframe from question"""
        q_lower = question.lower()
        if '5 min' in q_lower or '5min' in q_lower:
            return '5min'
        elif '15 min' in q_lower or '15min' in q_lower:
            return '15min'
        elif '30 min' in q_lower or '30min' in q_lower:
            return '30min'
        elif '1 hour' in q_lower or '1hour' in q_lower:
            return '1hour'
        elif 'nba' in q_lower or 'vs' in q_lower:
            return 'sports-today'
        elif 'bitcoin up or down' in q_lower:
            return 'daily-btc'
        else:
            return 'daily'
    
    def execute_trade(self, opportunity, bet_size):
        """Execute a trade"""
        self.log(f"Executing trade: {opportunity['market'][:40]}...")
        
        try:
            cmd = f"bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py buy {opportunity['id']} {opportunity['side']} {bet_size} --skip-sell'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                self.log(f"✅ Trade executed: ${bet_size} on {opportunity['side']}")
                
                # Log to database
                self.log_trade_to_db(opportunity, bet_size)
                
                return True
            else:
                self.log(f"❌ Trade failed: {result.stderr[:100]}")
                return False
        except Exception as e:
            self.log(f"❌ Error: {e}")
            return False
    
    def log_trade_to_db(self, opp, amount):
        """Log trade to database"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (market_id, market_question, side, size_usd, entry_price, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, 'OPEN')
            """, (opp['id'], opp['market'], opp['side'], amount, opp['price'], 65))
            conn.commit()
            conn.close()
        except:
            pass
    
    def run_money_making_session(self):
        """Main money making session"""
        self.log("="*70)
        self.log("MONEY MAKER - ACTIVE SESSION")
        self.log("="*70)
        
        # Update wallet
        self.get_wallet_balance()
        self.log(f"Wallet: ${self.wallet_usdc:.2f} USDC.e | {self.wallet_pol:.2f} POL")
        
        # Get current positions
        positions = self.get_positions()
        self.log(f"Active positions: {len(positions)}")
        
        # 1. Scan short-term markets
        short_term = self.scan_short_term_markets()
        self.log(f"Found {len(short_term)} short-term opportunities")
        
        # Sort by edge
        short_term.sort(key=lambda x: x['edge'], reverse=True)
        
        # Execute best opportunities (max $5 each, min $2)
        executed = 0
        errors = []
        min_bet = 2
        max_bet = 5
        
        if self.wallet_usdc < min_bet:
            errors.append(f"Insufficient funds: ${self.wallet_usdc:.2f} USDC.e (need ${min_bet}+ for trading)")
            # Try to find opportunities anyway for reporting
            for opp in short_term[:5]:
                if opp['edge'] >= 10:
                    errors.append(f"Would trade: {opp['market'][:50]}... {opp['side']} @ ${opp['price']:.2f} (edge: {opp['edge']}%)")
        else:
            for opp in short_term[:3]:  # Top 3
                # Relaxed edge threshold to 5% for more trades
                if opp['edge'] >= 5 and self.wallet_usdc >= min_bet + 1:  # Need bet + gas
                    bet_size = min(max_bet, self.wallet_usdc - 1)  # Keep $1 for gas
                    if bet_size >= min_bet:
                        if self.execute_trade(opp, bet_size):
                            executed += 1
                            self.wallet_usdc -= bet_size
                            if executed >= 2:  # Max 2 trades per session
                                break
        
        self.log("="*70)
        self.log(f"Session complete. Executed: {executed} trades")
        self.log(f"Wallet: ${self.wallet_usdc:.2f} USDC.e")
        self.log("="*70)
        
        return {
            'trades_executed': executed,
            'short_term_opps': len(short_term),
            'wallet_usdc': self.wallet_usdc,
            'wallet_pol': self.wallet_pol,
            'positions_count': len(positions),
            'errors': errors,
            'top_opportunities': short_term[:5]
        }

def main():
    maker = MoneyMaker()
    result = maker.run_money_making_session()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
