#!/usr/bin/env python3
"""
MASTER TRADER - Combined Best Features
- From v1: Basic scanning
- From v2: Multi-timeframe (5m + 15m)
- From v3: Multi-API (CoinGecko + Binance + CryptoCompare)
- From v4: Adaptive edge (no hardcoded)
- NEW: Continuous improvement, single file
"""

import requests
import json
import time
import os
from datetime import datetime

class MasterTrader:
    def __init__(self):
        self.version = "5.0"
        self.log_file = "/root/.openclaw/workspace/InternalLog.json"
        self.virtual_balance = 1000.0
        self.total_profit = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        
    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        
    def load_log(self):
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_log(self, log):
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def update_stats(self):
        """Update internal stats from log"""
        log = self.load_log()
        self.virtual_balance = 1000.0
        self.total_profit = 0.0
        self.win_count = 0
        self.loss_count = 0
        
        for entry in log:
            if entry.get('event_type') == 'trade_sim':
                amount = entry.get('amount', 0)
                entry_price = entry.get('entry_price', 0.5)
                notes = entry.get('notes', '')
                
                self.virtual_balance -= amount
                
                if 'WON' in notes:
                    self.virtual_balance += amount * 2
                    self.total_profit += amount * (1 - entry_price)
                    self.win_count += 1
                elif 'LOST' in notes:
                    self.total_profit -= amount * entry_price
                    self.loss_count += 1
        
        self.trade_count = self.win_count + self.loss_count
    
    def get_crypto_data(self, coin_id, symbol):
        """Multi-API data fetch (CoinGecko + Binance backup)"""
        data = {'price': 0, 'change_24h': 0, 'change_1h': 0, 'volume': 0, 'high': 0, 'low': 0}
        
        # Primary: CoinGecko
        try:
            r = requests.get(f'https://api.coingecko.com/api/v3/coins/{coin_id}?market_data=true', timeout=10)
            d = r.json().get('market_data', {})
            data['price'] = d.get('current_price', {}).get('usd', 0)
            data['change_24h'] = d.get('price_change_percentage_24h', 0)
            data['volume'] = d.get('total_volume', {}).get('usd', 0)
            data['high'] = d.get('high_24h', {}).get('usd', 0)
            data['low'] = d.get('low_24h', {}).get('usd', 0)
            
            # 1h change from chart
            r2 = requests.get(f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=1', timeout=10)
            prices = r2.json().get('prices', [])
            if len(prices) >= 2:
                data['change_1h'] = ((prices[-1][1] - prices[-2][1]) / prices[-2][1]) * 100
        except:
            pass
        
        # Backup: Binance
        if data['price'] == 0:
            try:
                r = requests.get(f'https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT', timeout=5)
                d = r.json()
                data['price'] = float(d.get('lastPrice', 0))
                data['change_24h'] = float(d.get('priceChangePercent', 0))
            except:
                pass
        
        return data
    
    def analyze(self, data):
        """Adaptive analysis - returns confidence score"""
        score = 0
        confidence = 0
        reasons = []
        
        # Strong trend
        if abs(data['change_24h']) > 5:
            score += 3 if data['change_24h'] > 0 else -3
            confidence += 30
            reasons.append(f"24h: {data['change_24h']:+.1f}%")
        elif abs(data['change_24h']) > 2:
            score += 1.5 if data['change_24h'] > 0 else -1.5
            confidence += 15
            reasons.append(f"24h: {data['change_24h']:+.1f}%")
        
        # 1h momentum
        if abs(data['change_1h']) > 1.5:
            score += 1 if data['change_1h'] > 0 else -1
            confidence += 15
            reasons.append(f"1h: {data['change_1h']:+.1f}%")
        
        # Range position
        if data['high'] > data['low']:
            pos = (data['price'] - data['low']) / (data['high'] - data['low'])
            if pos > 0.85:
                score -= 2
                confidence += 10
                reasons.append(f"Near high ({pos*100:.0f}%)")
            elif pos < 0.15:
                score += 2
                confidence += 10
                reasons.append(f"Near low ({pos*100:.0f}%)")
        
        direction = 'UP' if score > 0 else 'DOWN' if score < 0 else 'NEUTRAL'
        
        return {
            'score': score,
            'confidence': min(confidence, 100),
            'direction': direction,
            'strength': abs(score),
            'reasons': reasons
        }
    
    def scan_markets(self):
        """Scan both 5m and 15m markets"""
        coins = [('btc', 'bitcoin', 'BTC'), ('eth', 'ethereum', 'ETH'), ('sol', 'solana', 'SOL'), ('xrp', 'ripple', 'XRP')]
        current = int(time.time())
        opportunities = []
        
        for coin, coin_id, symbol in coins:
            data = self.get_crypto_data(coin_id, symbol)
            if data['price'] == 0:
                continue
            
            analysis = self.analyze(data)
            
            # Scan 5m
            slot = (current // 300) * 300
            opp = self.check_market(coin, '5m', slot, analysis, data)
            if opp:
                opportunities.append(opp)
            
            # Scan 15m
            slot = (current // 900) * 900
            opp = self.check_market(coin, '15m', slot, analysis, data)
            if opp:
                opportunities.append(opp)
        
        return opportunities
    
    def check_market(self, coin, tf, slot, analysis, data):
        """Check specific market"""
        if analysis['direction'] == 'NEUTRAL' or analysis['confidence'] < 40 or analysis['strength'] < 2:
            return None
        
        try:
            r = requests.get(f'https://gamma-api.polymarket.com/markets/slug/{coin}-updown-{tf}-{slot}', timeout=3)
            if r.status_code != 200:
                return None
            
            prices = json.loads(r.json().get('outcomePrices', '[]'))
            if len(prices) != 2:
                return None
            
            yes, no = float(prices[0]), float(prices[1])
            
            if analysis['direction'] == 'UP':
                if yes < 0.75:
                    return {'coin': coin.upper(), 'tf': tf, 'side': 'YES', 'price': yes, 'analysis': analysis, 'data': data}
            else:
                if no < 0.75:
                    return {'coin': coin.upper(), 'tf': tf, 'side': 'NO', 'price': no, 'analysis': analysis, 'data': data}
        except:
            pass
        
        return None
    
    def trade(self, opp):
        """Execute trade"""
        amount = min(20.0, self.virtual_balance * 0.02)
        
        reasons = [
            f"{opp['coin']} at ${opp['data']['price']:,.2f}",
            f"24h: {opp['data']['change_24h']:+.1f}% | 1h: {opp['data']['change_1h']:+.1f}%",
            f"Direction: {opp['analysis']['direction']} | Conf: {opp['analysis']['confidence']:.0f}%"
        ] + opp['analysis']['reasons']
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'trade_sim',
            'market': f"{opp['coin']} Up or Down - {opp['tf']}",
            'side': opp['side'],
            'amount': amount,
            'entry_price': opp['price'],
            'reason_points': reasons,
            'confidence': opp['analysis']['confidence'],
            'virtual_balance_after': self.virtual_balance - amount,
            'notes': f"v{self.version}: {opp['tf']} {opp['side']} | Conf: {opp['analysis']['confidence']:.0f}%"
        }
        
        log = self.load_log()
        log.append(trade)
        self.save_log(log)
        
        self.virtual_balance -= amount
        self.log(f"TRADE: {opp['coin']} {opp['tf']} {opp['side']} @ {opp['price']:.3f} (conf: {opp['analysis']['confidence']:.0f}%)")
    
    def run(self):
        """Main loop"""
        self.log(f"MASTER TRADER v{self.version} STARTED")
        self.log("Features: Multi-API | 5m+15m | Adaptive | No hardcoded edge")
        
        while True:
            try:
                self.update_stats()
                opps = self.scan_markets()
                
                if opps:
                    best = max(opps, key=lambda x: x['analysis']['confidence'])
                    self.trade(best)
                
                time.sleep(60)
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    trader = MasterTrader()
    trader.run()
