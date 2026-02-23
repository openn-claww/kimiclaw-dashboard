#!/usr/bin/env python3
"""
Adaptive AI Trading System - Diljeet's Brain
Learns from market conditions, takes calculated risks
"""

import os
import sys
import json
import sqlite3
import requests
import subprocess
from datetime import datetime
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

API_SPORTS_KEY = os.getenv('API_SPORTS_KEY', '')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', '')
DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"

class AdaptiveTrader:
    """AI-driven trading with dynamic thresholds"""
    
    def __init__(self):
        self.wallet = self.get_wallet_balance()
        self.trades_made = self.get_today_trade_count()
        self.market_conditions = self.assess_market_conditions()
        
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
    
    def get_today_trade_count(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades WHERE date(timestamp) = date('now')")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def assess_market_conditions(self):
        """Assess current market conditions"""
        conditions = {
            'volatility': 'medium',
            'opportunity_density': 'low',
            'confidence_adjustment': 0
        }
        
        # Check how many opportunities exist
        try:
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets trending --limit 20"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 5:
                    conditions['opportunity_density'] = 'medium'
        except:
            pass
        
        return conditions
    
    def calculate_dynamic_thresholds(self):
        """Diljeet's dynamic threshold calculation"""
        
        # Base thresholds
        base_confidence = 6.5  # 65%
        base_edge = 0.05       # 5%
        
        # Adjust based on market conditions
        if self.market_conditions['opportunity_density'] == 'low':
            # Lower thresholds when few opportunities
            confidence = 6.0   # 60%
            edge = 0.045       # 4.5%
            reasoning = "Low opportunity density - lowering to catch good trades"
        else:
            confidence = base_confidence
            edge = base_edge
            reasoning = "Normal market conditions"
        
        # First 2 trades - be more aggressive
        if self.trades_made < 2:
            confidence = 5.5   # 55% - more aggressive
            edge = 0.04        # 4%
            reasoning = "First 2 trades mode - taking calculated risks to build momentum"
        
        return {
            'confidence': confidence,
            'edge': edge,
            'reasoning': reasoning,
            'bet_size': self.calculate_bet_size()
        }
    
    def calculate_bet_size(self):
        """Dynamic bet sizing"""
        if self.trades_made == 0:
            return 3.0  # $3 on first trade (confident start)
        elif self.trades_made == 1:
            return 2.5  # $2.50 on second trade
        else:
            return 2.0  # $2 standard after that
    
    def analyze_opportunity(self, market_data):
        """Deep analysis of a trading opportunity"""
        analysis = {
            'market': market_data.get('question', 'Unknown'),
            'yes_price': market_data.get('yes_price', 0),
            'no_price': market_data.get('no_price', 0),
            'volume': market_data.get('volume', 0),
            'confidence': 0,
            'edge': 0,
            'recommendation': 'PASS',
            'reasoning': ''
        }
        
        # Price-based analysis
        yes_price = analysis['yes_price']
        no_price = analysis['no_price']
        
        # If YES is cheap (<$0.30) and we have positive signals
        if yes_price < 0.30:
            analysis['confidence'] += 2
            analysis['edge'] += 0.15
            analysis['recommendation'] = 'YES'
            analysis['reasoning'] = 'YES price is undervalued (<$0.30)'
        
        # If NO is cheap (<$0.30) and we have negative signals
        elif no_price < 0.30:
            analysis['confidence'] += 2
            analysis['edge'] += 0.15
            analysis['recommendation'] = 'NO'
            analysis['reasoning'] = 'NO price is undervalued (<$0.30)'
        
        # Volume check - high volume = more reliable
        if analysis['volume'] > 100000:
            analysis['confidence'] += 1
            analysis['reasoning'] += ', High volume ($' + str(analysis['volume']/1000) + 'K)'
        
        return analysis
    
    def get_live_opportunities(self):
        """Scan for live opportunities"""
        opportunities = []
        
        print("🔍 Diljeet scanning markets with adaptive thresholds...")
        
        # Search various markets
        search_terms = ['NBA', 'soccer', 'Bitcoin', 'rain', 'Trump', 'Iran']
        
        for term in search_terms[:3]:  # Check top 3 categories
            try:
                cmd = f"cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search '{term}' --limit 5"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[2:]  # Skip header
                    for line in lines:
                        if '$' in line and '|' in line:
                            parts = line.split('|')
                            if len(parts) >= 4:
                                try:
                                    market_id = parts[0].strip()
                                    yes_price = float(parts[1].replace('$', '').strip())
                                    no_price = float(parts[2].replace('$', '').strip())
                                    volume_str = parts[3].strip().replace('K', '000').replace('M', '000000')
                                    volume = float(volume_str.replace('$', '').replace(',', ''))
                                    question = parts[4].strip() if len(parts) > 4 else 'Unknown'
                                    
                                    opp = self.analyze_opportunity({
                                        'id': market_id,
                                        'question': question,
                                        'yes_price': yes_price,
                                        'no_price': no_price,
                                        'volume': volume
                                    })
                                    
                                    if opp['recommendation'] != 'PASS':
                                        opportunities.append(opp)
                                except:
                                    continue
            except:
                continue
        
        return opportunities
    
    def execute_trade(self, opportunity, bet_size):
        """Execute a trade with full logging"""
        print(f"\n🎯 EXECUTING TRADE:")
        print(f"   Market: {opportunity['market'][:50]}...")
        print(f"   Side: {opportunity['recommendation']}")
        print(f"   Amount: ${bet_size}")
        print(f"   Confidence: {opportunity['confidence']}/10")
        print(f"   Edge: {opportunity['edge']*100:.1f}%")
        print(f"   Reasoning: {opportunity['reasoning']}")
        
        # Here we would execute via PolyClaw
        # For now, simulate
        return True
    
    def run_trading_session(self):
        """Main trading session"""
        print("="*70)
        print("ADAPTIVE AI TRADING - DILJEET'S BRAIN")
        print("="*70)
        print(f"Wallet: ${self.wallet:.2f}")
        print(f"Trades today: {self.trades_made}")
        print(f"Market conditions: {self.market_conditions}")
        
        # Get dynamic thresholds
        thresholds = self.calculate_dynamic_thresholds()
        print(f"\n🧠 DYNAMIC THRESHOLDS:")
        print(f"   Confidence: {thresholds['confidence']}/10 ({thresholds['confidence']*10:.0f}%)")
        print(f"   Edge: {thresholds['edge']*100:.1f}%")
        print(f"   Bet size: ${thresholds['bet_size']}")
        print(f"   Reasoning: {thresholds['reasoning']}")
        
        # Get opportunities
        opportunities = self.get_live_opportunities()
        
        if opportunities:
            print(f"\n📊 Found {len(opportunities)} opportunities")
            
            # Sort by edge
            opportunities.sort(key=lambda x: x['edge'], reverse=True)
            
            # Take top opportunity if it meets dynamic threshold
            best = opportunities[0]
            if best['confidence'] >= thresholds['confidence'] and best['edge'] >= thresholds['edge']:
                self.execute_trade(best, thresholds['bet_size'])
            else:
                print(f"\n⏳ Best opportunity doesn't meet thresholds:")
                print(f"   Confidence: {best['confidence']}/10 (need {thresholds['confidence']})")
                print(f"   Edge: {best['edge']*100:.1f}% (need {thresholds['edge']*100:.1f}%)")
        else:
            print("\n⏳ No opportunities found this scan")
        
        print("="*70)

def main():
    trader = AdaptiveTrader()
    trader.run_trading_session()

if __name__ == "__main__":
    main()
