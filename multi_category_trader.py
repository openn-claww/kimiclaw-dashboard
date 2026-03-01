#!/usr/bin/env python3
"""
Multi-Category Trading System
Weather + Sports + Crypto betting on Polymarket
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Add paths
sys.path.insert(0, '/root/.openclaw/skills/polyclaw')
sys.path.insert(0, '/root/.openclaw/skills/simmer-weather')

class MultiCategoryTrader:
    """Trade across Weather, Sports, and Crypto markets"""
    
    def __init__(self):
        self.categories = {
            'crypto': {'enabled': True, 'weight': 0.4},
            'sports': {'enabled': True, 'weight': 0.3},
            'weather': {'enabled': True, 'weight': 0.3}
        }
        self.max_bet = 1.0  # $1 per trade
        self.min_edge = 0.10  # 10% minimum edge
        
    def scan_crypto_markets(self):
        """Scan BTC/ETH short-term markets"""
        print("🔍 Scanning CRYPTO markets...")
        
        try:
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search 'Bitcoin' --limit 10"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            opportunities = []
            # Parse output and find high-edge opportunities
            # This would integrate with CoinGecko API for real prices
            
            return opportunities
        except Exception as e:
            print(f"Crypto scan error: {e}")
            return []
    
    def scan_sports_markets(self):
        """Scan NBA/NFL/Esports markets"""
        print("🔍 Scanning SPORTS markets...")
        
        try:
            # Search for various sports
            sports_terms = ['NBA', 'NFL', 'soccer', 'esports', 'tennis']
            all_markets = []
            
            for term in sports_terms:
                cmd = f"cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search '{term}' --limit 5"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
                if result.returncode == 0:
                    all_markets.append(result.stdout)
            
            # Parse for opportunities
            opportunities = []
            # Would integrate with sports APIs for real odds/data
            
            return opportunities
        except Exception as e:
            print(f"Sports scan error: {e}")
            return []
    
    def scan_weather_markets(self):
        """Scan weather markets using simmer-weather"""
        print("🔍 Scanning WEATHER markets...")
        
        try:
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python ../simmer-weather/weather_trader.py"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            # Parse JSON output
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout.split('===\n')[-1] if '===' in result.stdout else result.stdout)
                    return data.get('signals', [])
                except:
                    return []
            return []
        except Exception as e:
            print(f"Weather scan error: {e}")
            return []
    
    def calculate_edge(self, market_data, category):
        """Calculate trading edge based on category"""
        
        if category == 'crypto':
            # Compare real price vs market threshold
            # Would need CoinGecko integration
            pass
            
        elif category == 'sports':
            # Compare real odds vs market price
            # Would need sports API integration
            pass
            
        elif category == 'weather':
            # Compare forecast vs market price
            forecast_prob = market_data.get('forecast_precip', 0) / 100
            market_price = market_data.get('market_yes_price', 0)
            edge = forecast_prob - market_price
            return edge
            
        return 0
    
    def execute_trade(self, market_id, side, amount, category):
        """Execute trade with full logging"""
        print(f"🎯 EXECUTING {category.upper()} TRADE:")
        print(f"   Market: {market_id}")
        print(f"   Side: {side}")
        print(f"   Amount: ${amount}")
        
        try:
            # Execute via PolyClaw
            cmd = f"cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py buy {market_id} {side} {amount} --skip-sell"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"   ✅ Trade executed successfully!")
                
                # Log to database
                log_cmd = f"cd /root/.openclaw/skills/polytrader && python3 polytrader.py trade {market_id} {side} {amount} --reasoning '{category} trade with edge'"
                subprocess.run(log_cmd, shell=True, timeout=10)
                
                return True
            else:
                print(f"   ❌ Trade failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def run_full_scan(self):
        """Run complete multi-category scan"""
        print("="*60)
        print("MULTI-CATEGORY TRADING SCAN")
        print("="*60)
        print(f"Categories: Crypto ({self.categories['crypto']['weight']*100}%), Sports ({self.categories['sports']['weight']*100}%), Weather ({self.categories['weather']['weight']*100}%)")
        print(f"Max bet: ${self.max_bet} | Min edge: {self.min_edge*100}%")
        print("="*60)
        
        all_signals = []
        
        # Scan each category
        if self.categories['crypto']['enabled']:
            crypto_signals = self.scan_crypto_markets()
            all_signals.extend([{**s, 'category': 'crypto'} for s in crypto_signals])
            
        if self.categories['sports']['enabled']:
            sports_signals = self.scan_sports_markets()
            all_signals.extend([{**s, 'category': 'sports'} for s in sports_signals])
            
        if self.categories['weather']['enabled']:
            weather_signals = self.scan_weather_markets()
            all_signals.extend([{**s, 'category': 'weather'} for s in weather_signals])
        
        # Sort by edge
        all_signals.sort(key=lambda x: x.get('edge', 0), reverse=True)
        
        print(f"\n📊 TOTAL SIGNALS: {len(all_signals)}")
        
        # Execute top signals
        executed = 0
        for signal in all_signals:
            if signal.get('edge', 0) >= self.min_edge and executed < 3:  # Max 3 trades per scan
                success = self.execute_trade(
                    signal.get('market_id'),
                    signal.get('recommendation', 'YES'),
                    self.max_bet,
                    signal.get('category')
                )
                if success:
                    executed += 1
        
        print(f"\n✅ EXECUTED: {executed} trades")
        print("="*60)
        
        return all_signals

def main():
    trader = MultiCategoryTrader()
    signals = trader.run_full_scan()
    
    # Output for Discord
    if signals:
        print("\n🎯 TOP OPPORTUNITIES:")
        for s in signals[:5]:
            print(f"  {s.get('category', 'unknown').upper()}: {s.get('market_question', 'N/A')[:50]}... | Edge: {s.get('edge', 0)*100:.1f}%")
    else:
        print("\nℹ️ No high-edge opportunities found")

if __name__ == "__main__":
    main()
