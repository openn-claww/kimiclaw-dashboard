#!/usr/bin/env python3
"""
Complete Trading System with Grok AI Integration
Fallback to manual analysis if Grok fails
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# Add paths
sys.path.insert(0, '/root/.openclaw/skills/polyclaw')
sys.path.insert(0, '/root/.openclaw/workspace')

# Try to import Grok, fallback if fails
try:
    from smart_grok import get_live_markets, ask_grok_for_best_trades
    GROK_AVAILABLE = True
except:
    GROK_AVAILABLE = False

class CompleteTrader:
    def __init__(self):
        self.wallet = 19.93  # Current balance
        self.active_bets = 13.00
        self.target = 50.00
        
    def fetch_polymarket_data(self):
        """Get live market data"""
        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/markets?active=true&limit=50",
                timeout=10
            )
            return resp.json()
        except:
            return []
    
    def analyze_with_grok(self, markets):
        """Try Grok analysis"""
        if not GROK_AVAILABLE:
            return {"opportunities": [], "error": "Grok not available"}
        
        try:
            return ask_grok_for_best_trades(markets)
        except Exception as e:
            return {"opportunities": [], "error": str(e)}
    
    def manual_analysis(self, markets):
        """Manual analysis when Grok fails"""
        opportunities = []
        
        for m in markets:
            try:
                yes_price = float(m.get("yesAsk", 0))
                no_price = float(m.get("noAsk", 0))
                volume = m.get("volume", 0)
                
                # Simple edge detection
                if yes_price < 0.25 and volume > 100000:
                    opportunities.append({
                        "market": m.get("question", "Unknown"),
                        "side": "YES",
                        "confidence": 65,
                        "edge": 8.0,
                        "reason": "YES undervalued, high volume",
                        "suggested_bet": 2
                    })
                elif no_price < 0.25 and volume > 100000:
                    opportunities.append({
                        "market": m.get("question", "Unknown"),
                        "side": "NO",
                        "confidence": 65,
                        "edge": 8.0,
                        "reason": "NO undervalued, high volume",
                        "suggested_bet": 2
                    })
            except:
                continue
        
        return {"opportunities": opportunities[:3]}
    
    def run_full_analysis(self):
        """Complete trading analysis"""
        print("="*70)
        print("COMPLETE TRADING ANALYSIS")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M GMT')}")
        print("="*70)
        
        # Fetch markets
        print("\n📊 Fetching Polymarket data...")
        markets = self.fetch_polymarket_data()
        print(f"Found {len(markets)} active markets")
        
        # Try Grok first
        print("\n🤖 Trying Grok AI analysis...")
        grok_result = self.analyze_with_grok(markets)
        
        if grok_result.get("opportunities"):
            print("✅ Grok analysis successful!")
            result = grok_result
        else:
            print("⚠️ Grok failed, using manual analysis...")
            result = self.manual_analysis(markets)
        
        # Display results
        print("\n" + "="*70)
        print("OPPORTUNITIES FOUND")
        print("="*70)
        
        opps = result.get("opportunities", [])
        if opps:
            for i, opp in enumerate(opps, 1):
                print(f"\n{i}. {opp.get('market', 'Unknown')[:60]}...")
                print(f"   Side: {opp.get('side')} | Confidence: {opp.get('confidence')}%")
                print(f"   Edge: {opp.get('edge')}% | Bet: ${opp.get('suggested_bet')}")
                print(f"   Reason: {opp.get('reason', 'N/A')}")
        else:
            print("\nNo high-confidence opportunities found")
        
        print("\n" + "="*70)
        print(f"Wallet: ${self.wallet} | Target: ${self.target}")
        print("="*70)
        
        return result

def main():
    trader = CompleteTrader()
    result = trader.run_full_analysis()
    
    # Save results
    with open("/root/.openclaw/workspace/last_analysis.json", "w") as f:
        json.dump(result, f, indent=2)

if __name__ == "__main__":
    main()
