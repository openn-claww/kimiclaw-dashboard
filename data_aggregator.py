#!/usr/bin/env python3
"""
Multi-Source Data Intelligence
Aggregates data from CoinGecko, Polymarket, and other sources
"""

import requests
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")
CACHE_DIR = Path("/root/.openclaw/workspace/cache")
CACHE_DIR.mkdir(exist_ok=True)

class DataAggregator:
    """Aggregate data from multiple sources"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'KimiClaw-Trader/1.0'
        })
    
    def get_coingecko_data(self, coin_id='bitcoin'):
        """Get crypto price from CoinGecko"""
        cache_file = CACHE_DIR / f'coingecko_{coin_id}.json'
        
        # Check cache (5 min expiry)
        if cache_file.exists():
            with open(cache_file) as f:
                cached = json.load(f)
                if (datetime.now() - datetime.fromisoformat(cached['timestamp'])).seconds < 300:
                    return cached['data']
        
        try:
            url = f'https://api.coingecko.com/api/v3/coins/{coin_id}'
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    'price_usd': data['market_data']['current_price']['usd'],
                    'change_24h': data['market_data']['price_change_percentage_24h'],
                    'high_24h': data['market_data']['high_24h']['usd'],
                    'low_24h': data['market_data']['low_24h']['usd'],
                    'market_cap': data['market_data']['market_cap']['usd'],
                    'volume_24h': data['market_data']['total_volume']['usd'],
                    'last_updated': data['last_updated']
                }
                
                # Cache result
                with open(cache_file, 'w') as f:
                    json.dump({'timestamp': datetime.now().isoformat(), 'data': result}, f)
                
                return result
            else:
                return {'error': f'Status {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}
    
    def get_polymarket_market(self, market_id):
        """Get specific market data from Polymarket"""
        cache_file = CACHE_DIR / f'polymarket_{market_id}.json'
        
        if cache_file.exists():
            with open(cache_file) as f:
                cached = json.load(f)
                if (datetime.now() - datetime.fromisoformat(cached['timestamp'])).seconds < 60:
                    return cached['data']
        
        try:
            url = f'https://gamma-api.polymarket.com/markets/{market_id}'
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    'question': data.get('question'),
                    'yes_price': float(data.get('outcomesPrices', [0, 0])[0]) / 100,
                    'no_price': float(data.get('outcomesPrices', [0, 0])[1]) / 100,
                    'volume_24h': data.get('volume24hr', 0),
                    'liquidity': data.get('liquidity', 0),
                    'end_date': data.get('endDate'),
                    'active': data.get('active', False),
                    'closed': data.get('closed', False)
                }
                
                with open(cache_file, 'w') as f:
                    json.dump({'timestamp': datetime.now().isoformat(), 'data': result}, f)
                
                return result
            else:
                return {'error': f'Status {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}
    
    def calculate_edge(self, market_id, real_price, threshold):
        """Calculate trading edge for binary markets"""
        market = self.get_polymarket_market(market_id)
        
        if 'error' in market:
            return {'error': market['error']}
        
        # Determine if real price is above/below threshold
        real_above = real_price > threshold
        
        # Market probability
        market_yes_prob = market['yes_price']
        market_no_prob = market['no_price']
        
        # Calculate edge
        if real_above:
            # Real is above, so YES should be high
            edge = 1.0 - market_yes_prob  # Potential profit if YES is undervalued
            recommendation = 'YES' if edge > 0.1 else 'HOLD'
        else:
            # Real is below, so NO should be high
            edge = 1.0 - market_no_prob
            recommendation = 'NO' if edge > 0.1 else 'HOLD'
        
        return {
            'real_price': real_price,
            'threshold': threshold,
            'real_above_threshold': real_above,
            'market_yes_prob': market_yes_prob,
            'market_no_prob': market_no_prob,
            'edge': edge,
            'recommendation': recommendation,
            'confidence': min(10, int(edge * 10))
        }
    
    def scan_opportunities(self):
        """Scan for trading opportunities"""
        opportunities = []
        
        # Get BTC data
        btc_data = self.get_coingecko_data('bitcoin')
        if 'error' not in btc_data:
            # Check BTC $66K market
            edge_66k = self.calculate_edge('1369917', btc_data['price_usd'], 66000)
            if 'error' not in edge_66k and edge_66k['edge'] > 0.1:
                opportunities.append({
                    'market': 'BTC >$66K',
                    'market_id': '1369917',
                    'recommendation': edge_66k['recommendation'],
                    'edge': edge_66k['edge'],
                    'confidence': edge_66k['confidence'],
                    'real_price': btc_data['price_usd']
                })
        
        return opportunities
    
    def generate_intelligence_report(self):
        """Generate comprehensive market intelligence"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'btc': self.get_coingecko_data('bitcoin'),
            'eth': self.get_coingecko_data('ethereum'),
            'opportunities': self.scan_opportunities()
        }
        
        # Save report
        report_file = Path(f"/root/.openclaw/workspace/reports/intelligence_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report

def main():
    agg = DataAggregator()
    report = agg.generate_intelligence_report()
    
    print("="*60)
    print("MARKET INTELLIGENCE REPORT")
    print("="*60)
    
    if 'error' not in report['btc']:
        btc = report['btc']
        print(f"\n📊 Bitcoin:")
        print(f"   Price: ${btc['price_usd']:,.2f}")
        print(f"   24h Change: {btc['change_24h']:+.2f}%")
        print(f"   24h High: ${btc['high_24h']:,.2f}")
        print(f"   24h Low: ${btc['low_24h']:,.2f}")
    
    if report['opportunities']:
        print(f"\n🎯 Opportunities Found: {len(report['opportunities'])}")
        for opp in report['opportunities']:
            print(f"   {opp['market']}: {opp['recommendation']} (edge: {opp['edge']:.1%}, conf: {opp['confidence']}/10)")
    else:
        print("\n🎯 No high-confidence opportunities found")
    
    print("="*60)
    
    return report

if __name__ == "__main__":
    main()
