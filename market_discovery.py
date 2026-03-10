#!/usr/bin/env python3
"""
Market Discovery Utility for V4 Bot
Finds current 5m and 15m crypto markets on Polymarket.
"""

import requests
import json
import time
from datetime import datetime
from typing import Optional, Dict, List

GAMMA_API = "https://gamma-api.polymarket.com"

class MarketDiscovery:
    """Discovers active 5m and 15m crypto prediction markets."""
    
    COINS = ["btc", "eth"]
    TIMEFRAMES = [5, 15]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "V4Bot/1.0"
        })
    
    def get_current_slot(self, timeframe: int) -> int:
        """Get current slot timestamp for a timeframe."""
        current = int(time.time())
        seconds = timeframe * 60
        return (current // seconds) * seconds
    
    def get_slug(self, coin: str, timeframe: int, slot: int) -> str:
        """Generate market slug."""
        return f"{coin}-updown-{timeframe}m-{slot}"
    
    def find_market(self, coin: str, timeframe: int) -> Optional[Dict]:
        """Find current market for coin/timeframe."""
        slot = self.get_current_slot(timeframe)
        slug = self.get_slug(coin, timeframe, slot)
        
        try:
            response = self.session.get(
                f"{GAMMA_API}/events",
                params={"slug": slug, "closed": "false", "limit": 1},
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if not data:
                return None
            
            event = data[0]
            markets = event.get("markets", [])
            
            if not markets:
                return None
            
            market = markets[0]
            
            # Parse CLOB token IDs
            clob_tokens_str = market.get("clobTokenIds", "[]")
            if isinstance(clob_tokens_str, str):
                clob_tokens = json.loads(clob_tokens_str)
            else:
                clob_tokens = clob_tokens_str
            
            # Parse prices
            prices_str = market.get("outcomePrices", "[0, 0]")
            if isinstance(prices_str, str):
                prices = json.loads(prices_str)
            else:
                prices = prices_str
            
            return {
                "coin": coin.upper(),
                "timeframe": timeframe,
                "slot": slot,
                "slug": slug,
                "market_id": market.get("id"),
                "question": market.get("question"),
                "condition_id": market.get("conditionId"),
                "end_date": market.get("endDate"),
                "yes_token": clob_tokens[0] if len(clob_tokens) > 0 else None,
                "no_token": clob_tokens[1] if len(clob_tokens) > 1 else None,
                "yes_price": float(prices[0]) if len(prices) > 0 else 0,
                "no_price": float(prices[1]) if len(prices) > 1 else 0,
                "active": market.get("active", False),
                "closed": market.get("closed", True),
            }
            
        except Exception as e:
            print(f"Error finding {coin} {timeframe}m market: {e}")
            return None
    
    def find_all_markets(self) -> List[Dict]:
        """Find all current 5m and 15m markets."""
        markets = []
        
        for coin in self.COINS:
            for tf in self.TIMEFRAMES:
                market = self.find_market(coin, tf)
                if market:
                    markets.append(market)
        
        return markets
    
    def print_market_summary(self, markets: List[Dict]):
        """Print formatted market summary."""
        print("=" * 70)
        print("ACTIVE CRYPTO PREDICTION MARKETS")
        print("=" * 70)
        print(f"Discovery time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print()
        
        if not markets:
            print("❌ No active markets found!")
            return
        
        for m in markets:
            spread = m["yes_price"] + m["no_price"] - 1
            status = "✅ ACTIVE" if m["active"] and not m["closed"] else "❌ INACTIVE"
            
            print(f"{m['coin']} {m['timeframe']}m Market:")
            print(f"  Status: {status}")
            print(f"  Question: {m['question']}")
            print(f"  YES Price: {m['yes_price']:.3f} | NO Price: {m['no_price']:.3f}")
            print(f"  Spread: {spread*100:.2f}%")
            print(f"  YES Token: {m['yes_token'][:20]}...")
            print(f"  NO Token:  {m['no_token'][:20]}...")
            print()
        
        print("=" * 70)
        print(f"Found {len(markets)} active market(s)")
        print("=" * 70)

def main():
    """CLI usage."""
    discovery = MarketDiscovery()
    markets = discovery.find_all_markets()
    discovery.print_market_summary(markets)
    
    # Save to file for bot usage
    if markets:
        with open("/root/.openclaw/workspace/active_markets.json", "w") as f:
            json.dump(markets, f, indent=2)
        print("\nMarkets saved to: active_markets.json")

if __name__ == "__main__":
    main()
