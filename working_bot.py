#!/usr/bin/env python3
"""
WORKING BOT v1.0 - No crashes, simple, trades every opportunity
"""

import time
import requests
import json
from datetime import datetime

class WorkingBot:
    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
        self.free = balance
        self.trades = 0
        self.last_trade = 0
        self.log_file = f"{name}_working.json"
        
    def log(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def get_price(self, coin):
        try:
            r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT', timeout=3)
            return float(r.json()['price'])
        except:
            return None
    
    def get_polymarket(self, coin, tf):
        try:
            slot = int(time.time() // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            r = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=3)
            if r.status_code == 200:
                data = r.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                if len(prices) == 2:
                    return {'yes': float(prices[0]), 'no': float(prices[1])}
        except:
            pass
        return None
    
    def should_trade(self, coin, tf, price, last_price):
        if self.free < 20:
            return None
        
        if time.time() - self.last_trade < 10:
            return None
        
        pm = self.get_polymarket(coin, tf)
        if not pm:
            return None
        
        yes, no = pm['yes'], pm['no']
        total = yes + no
        
        # Arbitrage
        if total < 0.995:
            return {'type': 'ARBITRAGE', 'side': 'BOTH', 'amount': 25, 'reason': f'Total={total:.3f}'}
        
        # Momentum
        if last_price and price:
            change = ((price - last_price) / last_price) * 100
            
            if tf == 5 and abs(change) > 0.1:
                side = 'YES' if change > 0 else 'NO'
                return {'type': 'MOMENTUM', 'side': side, 'amount': 20, 'reason': f'{change:+.2f}%'}
            
            if tf == 15 and abs(change) > 0.2:
                side = 'YES' if change > 0 else 'NO'
                return {'type': 'MOMENTUM', 'side': side, 'amount': 20, 'reason': f'{change:+.2f}%'}
        
        # Value
        if yes < 0.20:
            return {'type': 'VALUE', 'side': 'YES', 'amount': 15, 'reason': f'YES={yes:.3f}'}
        if no < 0.20:
            return {'type': 'VALUE', 'side': 'NO', 'amount': 15, 'reason': f'NO={no:.3f}'}
        
        return None
    
    def execute(self, coin, tf, opp):
        amt = min(opp['amount'], self.free * 0.05)
        if amt < 10:
            return
        
        self.free -= amt
        self.trades += 1
        self.last_trade = time.time()
        
        print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] {self.name} #{self.trades}")
        print(f"   {coin} {tf}m | {opp['side']} | ${amt:.2f} | {opp['type']}")
        print(f"   {opp['reason']} | Balance: ${self.free:.2f}")
        
        self.log({
            'time': datetime.now().strftime('%H:%M:%S'),
            'name': self.name,
            'coin': coin,
            'tf': tf,
            'side': opp['side'],
            'amount': amt,
            'type': opp['type'],
            'reason': opp['reason'],
            'balance': self.free
        })
    
    def run(self):
        print(f"=== {self.name} STARTED ===")
        print(f"Balance: ${self.balance:.2f}")
        print("Scanning: BTC, ETH, SOL, XRP | 5m, 15m")
        print("="*50)
        
        prices = {}
        cycle = 0
        
        while True:
            for coin in ['BTC', 'ETH', 'SOL', 'XRP']:
                price = self.get_price(coin)
                if price:
                    last = prices.get(coin)
                    
                    for tf in [5, 15]:
                        opp = self.should_trade(coin, tf, price, last)
                        if opp:
                            self.execute(coin, tf, opp)
                    
                    prices[coin] = price
            
            cycle += 1
            if cycle % 20 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.name}: ${self.free:.2f} | Trades: {self.trades}")
            
            time.sleep(3)

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else 'BOT'
    balance = 500.0 if '2' in name else 686.93
    WorkingBot(name, balance).run()
