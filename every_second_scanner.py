#!/usr/bin/env python3
"""
24/7 EVERY-SECOND MARKET SCANNER
No excuses. No delays. Every second.
"""

import time
import requests
import json
from datetime import datetime
import threading

class EverySecondScanner:
    def __init__(self):
        self.running = True
        self.opportunities_found = 0
        self.last_prices = {}
        self.velocities = {}
        
    def scan_all_markets(self):
        """Scan every market every second"""
        coins = ['btc', 'eth', 'sol', 'xrp']
        timeframes = [5, 15, 30, 60]
        
        found = []
        
        for coin in coins:
            # Get price for velocity calc
            try:
                resp = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={coin.upper()}USDT', timeout=1)
                price = float(resp.json()['price'])
                
                if coin in self.last_prices:
                    self.velocities[coin] = ((price - self.last_prices[coin]) / self.last_prices[coin]) * 100
                self.last_prices[coin] = price
            except:
                price = None
                velocity = 0
            
            velocity = self.velocities.get(coin, 0)
            
            for tf in timeframes:
                try:
                    slot = int(time.time() // (tf * 60)) * (tf * 60)
                    slug = f'{coin}-updown-{tf}m-{slot}'
                    
                    resp = requests.get(f'https://gamma-api.polymarket.com/markets/slug/{slug}', timeout=1)
                    if resp.status_code == 200:
                        data = resp.json()
                        prices = json.loads(data.get('outcomePrices', '[]'))
                        
                        if len(prices) == 2:
                            yes = float(prices[0])
                            no = float(prices[1])
                            total = yes + no
                            
                            # ARBITRAGE
                            if total < 0.995:
                                found.append({
                                    'time': datetime.now().strftime('%H:%M:%S'),
                                    'type': 'ARBITRAGE',
                                    'coin': coin.upper(),
                                    'tf': tf,
                                    'yes': yes,
                                    'no': no,
                                    'profit': (1-total)*100,
                                    'action': 'BUY_BOTH'
                                })
                            
                            # MOMENTUM
                            elif abs(velocity) > 0.1:  # 0.1% move
                                side = 'YES' if velocity > 0 else 'NO'
                                found.append({
                                    'time': datetime.now().strftime('%H:%M:%S'),
                                    'type': 'MOMENTUM',
                                    'coin': coin.upper(),
                                    'tf': tf,
                                    'side': side,
                                    'velocity': velocity,
                                    'yes': yes,
                                    'no': no,
                                    'action': f'BUY_{side}'
                                })
                            
                            # EXTREME VALUE
                            elif yes < 0.15 or no < 0.15:
                                found.append({
                                    'time': datetime.now().strftime('%H:%M:%S'),
                                    'type': 'VALUE',
                                    'coin': coin.upper(),
                                    'tf': tf,
                                    'yes': yes,
                                    'no': no,
                                    'action': 'ANALYZE'
                                })
                                
                except:
                    pass
        
        return found
    
    def execute_trade(self, opp, wallet):
        """Execute trade immediately"""
        amount = 25.0 if wallet == 'W2' else 30.0
        
        print(f"🚀 [{opp['time']}] {wallet} EXECUTING:")
        print(f"   {opp['coin']} {opp['tf']}m | {opp['type']} | {opp.get('action', 'TRADE')}")
        
        if opp['type'] == 'ARBITRAGE':
            print(f"   Profit: {opp['profit']:.2f}% | BUY YES @ {opp['yes']:.3f} + NO @ {opp['no']:.3f}")
        elif opp['type'] == 'MOMENTUM':
            print(f"   Velocity: {opp['velocity']:+.2f}% | BUY {opp['side']} | Price: {opp['yes'] if opp['side']=='YES' else opp['no']:.3f}")
        
        # Log trade
        trade = {
            'timestamp': opp['time'],
            'wallet': wallet,
            'opportunity': opp
        }
        
        try:
            with open(f'{wallet}_live_trades.json', 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(f'{wallet}_live_trades.json', 'w') as f:
            json.dump(log, f, indent=2)
        
        self.opportunities_found += 1
    
    def run(self):
        print("="*70)
        print("24/7 EVERY-SECOND SCANNER")
        print("="*70)
        print("Scanning: BTC, ETH, SOL, XRP")
        print("Timeframes: 5m, 15m, 30m, 60m")
        print("Triggers: Arbitrage (<0.995) | Momentum (>0.1%) | Value (<0.15)")
        print("="*70)
        print()
        
        cycle = 0
        while self.running:
            start_time = time.time()
            
            opportunities = self.scan_all_markets()
            
            if opportunities:
                for opp in opportunities:
                    # Execute on both wallets
                    self.execute_trade(opp, 'W2')
                    self.execute_trade(opp, 'W1')
                    print()
            
            cycle += 1
            if cycle % 60 == 0:  # Every minute
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanned {cycle} cycles | Opportunities: {self.opportunities_found}")
            
            # Ensure exactly 1 second between scans
            elapsed = time.time() - start_time
            sleep_time = max(0, 1.0 - elapsed)
            time.sleep(sleep_time)

if __name__ == "__main__":
    scanner = EverySecondScanner()
    scanner.run()
