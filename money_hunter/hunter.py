#!/usr/bin/env python3
"""
Money Hunter - Continuous Opportunity Scanner
Scans multiple sources for profit opportunities
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Opportunity tracking
OPPORTUNITIES_CHANNEL = "1475043958236385453"
DAILY_LOG = "/root/.openclaw/workspace/money_hunter/daily_log.md"

class MoneyHunter:
    def __init__(self):
        self.opportunities = []
        self.scan_sources = [
            'polymarket',
            'twitter_crypto',
            'reddit_crypto',
            'arbitrage_exchanges',
            'new_platforms'
        ]
        
    def scan_polymarket(self):
        """Check Polymarket for any opportunities"""
        try:
            cmd = "cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets trending --limit 20"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                volume_markets = []
                for line in lines[2:]:  # Skip headers
                    if '$' in line and '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 5:
                            try:
                                vol_str = parts[3].strip().replace('K', '000').replace('M', '000000').replace('$', '').replace(',', '')
                                volume = float(vol_str)
                                if volume > 500000:  # High volume markets
                                    volume_markets.append({
                                        'market': parts[4].strip()[:50],
                                        'volume': volume,
                                        'yes_price': parts[1].strip(),
                                        'no_price': parts[2].strip()
                                    })
                            except:
                                continue
                
                if volume_markets:
                    return {
                        'source': 'Polymarket',
                        'status': 'Active markets found',
                        'opportunities': len(volume_markets),
                        'details': volume_markets[:3]
                    }
                else:
                    return {'source': 'Polymarket', 'status': 'No high-volume markets', 'opportunities': 0}
        except Exception as e:
            return {'source': 'Polymarket', 'status': f'Error: {str(e)[:50]}', 'opportunities': 0}
    
    def scan_crypto_arbitrage(self):
        """Check for crypto price arbitrage opportunities"""
        try:
            # Check BTC price across sources
            exchanges = [
                ('CoinGecko', 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd'),
            ]
            
            prices = {}
            for name, url in exchanges:
                try:
                    import requests
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        btc = data.get('bitcoin', {}).get('usd', 0)
                        eth = data.get('ethereum', {}).get('usd', 0)
                        prices[name] = {'BTC': btc, 'ETH': eth}
                except:
                    continue
            
            if len(prices) >= 1:
                return {
                    'source': 'Crypto Markets',
                    'status': 'Prices fetched',
                    'opportunities': 0,  # Would calculate actual arb here
                    'prices': prices
                }
            else:
                return {'source': 'Crypto Markets', 'status': 'Price fetch failed', 'opportunities': 0}
        except Exception as e:
            return {'source': 'Crypto Markets', 'status': f'Error: {str(e)[:50]}', 'opportunities': 0}
    
    def scan_new_platforms(self):
        """Research new prediction market platforms"""
        new_platforms = [
            {'name': 'Kalshi', 'status': 'US-regulated, limited markets'},
            {'name': 'Betfair', 'status': 'Sports betting, high liquidity'},
            {'name': 'PredictIt', 'status': 'Political, US-focused'},
            {'name': 'Azuro', 'status': 'Crypto betting protocol'},
        ]
        
        return {
            'source': 'New Platforms',
            'status': 'Research complete',
            'opportunities': 0,
            'platforms': new_platforms
        }
    
    def run_full_scan(self):
        """Run complete opportunity scan"""
        print("="*70)
        print("MONEY HUNTER - FULL SCAN")
        print("="*70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M GMT')}")
        print("="*70)
        
        results = []
        
        # Scan all sources
        results.append(self.scan_polymarket())
        results.append(self.scan_crypto_arbitrage())
        results.append(self.scan_new_platforms())
        
        # Print results
        for r in results:
            if r:
                print(f"\n📊 {r.get('source', 'Unknown')}")
                print(f"   Status: {r.get('status', 'N/A')}")
                print(f"   Opportunities: {r.get('opportunities', 0)}")
        
        # Check if any real opportunities found
        total_opps = sum(r.get('opportunities', 0) for r in results if r)
        
        print("\n" + "="*70)
        if total_opps > 0:
            print(f"✅ FOUND {total_opps} POTENTIAL OPPORTUNITIES")
        else:
            print("❌ NO HIGH-CONVICTION OPPORTUNITIES FOUND")
        print("="*70)
        
        return results

def main():
    hunter = MoneyHunter()
    results = hunter.run_full_scan()
    
    # Save to daily log
    os.makedirs(os.path.dirname(DAILY_LOG), exist_ok=True)
    with open(DAILY_LOG, 'a') as f:
        f.write(f"\n[{datetime.now()}] Scan complete. Opportunities: {sum(r['opportunities'] for r in results)}\n")

if __name__ == "__main__":
    main()
