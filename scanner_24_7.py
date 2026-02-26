#!/usr/bin/env python3
"""
24/7 SCANNER - Runs forever, trades on any edge
No excuses. No crashes. Just trades.
"""

import time
import requests
import json
from datetime import datetime
import sys

# Force flush for logs
sys.stdout.flush()

class Scanner24_7:
    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
        self.free = balance
        self.trades = 0
        self.last_trade = 0
        self.log_file = f"{name}_24_7.json"
        
    def log(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def scan(self):
        coins = ['BTC', 'ETH', 'SOL', 'XRP']
        prices = {}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.name} STARTED | Balance: ${self.free:.2f}")
        print("="*60)
        sys.stdout.flush()
        
        while True:
            try:
                for coin in coins:
                    # Get price
                    try:
                        r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT', timeout=5)
                        price = float(r.json()['price'])
                        prices[coin] = price
                    except:
                        continue
                    
                    # Check 5m and 15m
                    for tf in [5, 15]:
                        try:
                            slot = int(time.time() // (tf * 60)) * (tf * 60)
                            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
                            r = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=5)
                            
                            if r.status_code == 200:
                                data = r.json()
                                pm_prices = json.loads(data.get('outcomePrices', '[]'))
                                
                                if len(pm_prices) == 2:
                                    yes = float(pm_prices[0])
                                    no = float(pm_prices[1])
                                    total = yes + no
                                    
                                    # TRADE CONDITIONS
                                    should_trade = False
                                    side = None
                                    reason = ""
                                    
                                    # 1. Arbitrage
                                    if total < 0.995:
                                        should_trade = True
                                        side = 'BOTH'
                                        reason = f"ARBITRAGE total={total:.3f}"
                                    
                                    # 2. Extreme value
                                    elif yes < 0.18:
                                        should_trade = True
                                        side = 'YES'
                                        reason = f"VALUE yes={yes:.3f}"
                                    elif no < 0.18:
                                        should_trade = True
                                        side = 'NO'
                                        reason = f"VALUE no={no:.3f}"
                                    
                                    # 3. Time-based trade (every 5 min if no other signal)
                                    elif time.time() - self.last_trade > 300 and self.free > 100:
                                        should_trade = True
                                        side = 'YES' if yes < no else 'NO'
                                        reason = "TIME-based entry"
                                    
                                    # EXECUTE
                                    if should_trade and time.time() - self.last_trade > 8:
                                        amt = min(20, self.free * 0.04)
                                        if amt >= 10:
                                            self.free -= amt
                                            self.trades += 1
                                            self.last_trade = time.time()
                                            
                                            print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] {self.name} #{self.trades}")
                                            print(f"   {coin} {tf}m | {side} | ${amt:.2f}")
                                            print(f"   {reason} | Balance: ${self.free:.2f}")
                                            print("-"*60)
                                            sys.stdout.flush()
                                            
                                            self.log({
                                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                'name': self.name,
                                                'coin': coin,
                                                'tf': tf,
                                                'side': side,
                                                'amount': amt,
                                                'reason': reason,
                                                'balance': self.free
                                            })
                        except Exception as e:
                            continue
                
                # Status every 2 minutes
                if int(time.time()) % 120 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.name}: ${self.free:.2f} | Trades: {self.trades}")
                    sys.stdout.flush()
                
                time.sleep(2)
                
            except Exception as e:
                print(f"Error: {e}")
                sys.stdout.flush()
                time.sleep(5)

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else 'BOT'
    bal = 500.0 if '2' in name else 686.93
    Scanner24_7(name, bal).scan()
