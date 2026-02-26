#!/usr/bin/env python3
"""
CROSS-PLATFORM ARBITRAGE SCANNER
Compare Polymarket vs other prediction markets
"""

import time
import requests
import json
from datetime import datetime

class CrossPlatformArbitrage:
    def __init__(self):
        self.running = True
        self.opportunities = []
        
    def get_polymarket_odds(self, market_slug):
        """Get Polymarket odds"""
        try:
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{market_slug}", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                if len(prices) == 2:
                    return {'yes': float(prices[0]), 'no': float(prices[1])}
        except:
            pass
        return None
    
    def get_kalshi_odds(self, market_ticker):
        """Get Kalshi odds (would need API key in production)"""
        # Placeholder - Kalshi requires API key
        return None
    
    def check_crypto_arbitrage(self):
        """Check for crypto market arbitrage opportunities"""
        opportunities = []
        
        coins = ['btc', 'eth', 'sol']
        timeframes = [5, 15, 30, 60]
        
        for coin in coins:
            for tf in timeframes:
                try:
                    current_time = time.time()
                    slot = int(current_time // (tf * 60)) * (tf * 60)
                    slug = f"{coin}-updown-{tf}m-{slot}"
                    
                    odds = self.get_polymarket_odds(slug)
                    if odds:
                        total = odds['yes'] + odds['no']
                        
                        # Arbitrage opportunity
                        if total < 0.99:
                            profit = (1 - total) * 100
                            opportunities.append({
                                'platform': 'Polymarket',
                                'market': f"{coin.upper()} {tf}m",
                                'yes': odds['yes'],
                                'no': odds['no'],
                                'total': total,
                                'profit': profit,
                                'action': 'BUY_BOTH'
                            })
                        
                        # Check for extreme prices (potential value)
                        if odds['yes'] < 0.15 or odds['no'] < 0.15:
                            opportunities.append({
                                'platform': 'Polymarket',
                                'market': f"{coin.upper()} {tf}m",
                                'yes': odds['yes'],
                                'no': odds['no'],
                                'note': 'Extreme price - potential value',
                                'action': 'ANALYZE'
                            })
                            
                except:
                    pass
        
        return opportunities
    
    def scan(self):
        """Scan for arbitrage opportunities"""
        print("="*70)
        print("CROSS-PLATFORM ARBITRAGE SCANNER")
        print("="*70)
        print("Scanning Polymarket for opportunities...")
        print()
        
        while self.running:
            opportunities = self.check_crypto_arbitrage()
            
            if opportunities:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(opportunities)} opportunities:")
                for opp in opportunities:
                    if 'profit' in opp:
                        print(f"  🎯 ARBITRAGE: {opp['market']} | Profit: {opp['profit']:.2f}%")
                        print(f"     YES: {opp['yes']:.3f} | NO: {opp['no']:.3f} | Total: {opp['total']:.3f}")
                    else:
                        print(f"  📊 {opp['market']} | YES: {opp['yes']:.3f} | NO: {opp['no']:.3f} | {opp['note']}")
                print()
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No arbitrage opportunities (scanning every 10s)")
            
            time.sleep(10)

if __name__ == "__main__":
    scanner = CrossPlatformArbitrage()
    scanner.scan()
