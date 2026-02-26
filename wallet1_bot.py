#!/usr/bin/env python3
"""
WALLET 1 BOT - Fixed Rate Limit Version
Uses Binance API instead of CoinGecko
"""

import time
import requests
import json
from datetime import datetime

class Wallet1Bot:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.velocities = {}
        self.trade_count = 0
        self.last_trade_time = 0
        self.virtual_balance = 686.93
        self.virtual_free = 686.93
        self.log_file = "/root/.openclaw/workspace/wallet1_new_trades.json"
        
        self.primary_timeframes = [5, 15]
        self.extended_timeframes = [30, 60, 240, 1440]
        self.coins = ['BTC', 'ETH', 'SOL', 'XRP']
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def get_crypto_price(self, coin):
        """Get price from Binance"""
        try:
            symbol = coin + 'USDT'
            resp = requests.get(
                f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}',
                timeout=3
            )
            if resp.status_code == 200:
                return float(resp.json()['price'])
        except:
            pass
        return None
    
    def calculate_edge(self, coin, yes_price, no_price, tf):
        if coin not in self.velocities:
            return None
        
        velocity = self.velocities[coin]
        min_edge = 0.3 if tf in [5, 15] else 0.5
        
        edge = 0
        side = None
        
        if velocity > 1.5 and yes_price < 0.65:
            edge = velocity * (0.7 - yes_price)
            side = 'YES'
        elif velocity < -1.5 and no_price < 0.65:
            edge = abs(velocity) * (0.7 - no_price)
            side = 'NO'
        
        if edge >= min_edge:
            return {
                'type': 'EDGE',
                'coin': coin,
                'tf': tf,
                'side': side,
                'price': yes_price if side == 'YES' else no_price,
                'edge': edge,
                'velocity': velocity
            }
        return None
    
    def check_arbitrage(self, coin, yes_price, no_price, tf):
        total = yes_price + no_price
        if total < 0.99:
            return {
                'type': 'ARBITRAGE',
                'coin': coin,
                'tf': tf,
                'yes': yes_price,
                'no': no_price,
                'profit': (1.0 - total) * 100
            }
        return None
    
    def evaluate_market(self, coin, tf):
        if self.virtual_free < 15:
            return
        
        current_time = time.time()
        min_interval = 8 if tf in [5, 15] else 20
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        try:
            slot = int(current_time // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(
                f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                timeout=1
            )
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                
                if len(prices) == 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    opportunity = None
                    opportunity = self.check_arbitrage(coin, yes_price, no_price, tf)
                    
                    if not opportunity:
                        opportunity = self.calculate_edge(coin, yes_price, no_price, tf)
                    
                    if opportunity:
                        self.execute_trade(opportunity)
                        self.last_trade_time = current_time
                        
        except:
            pass
    
    def execute_trade(self, opp):
        amount = min(25.0, self.virtual_free * 0.036)
        if amount < 15:
            return
        
        self.trade_count += 1
        tf_label = f"{opp['tf']}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W1 #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | +{opp['profit']:.1f}% | ${self.virtual_free:.2f}")
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet1_trade',
                'strategy': 'ARBITRAGE',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': 'BOTH',
                'amount': amount,
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        else:
            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W1 #{self.trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | ${self.virtual_free:.2f}")
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet1_trade',
                'strategy': 'EDGE',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price'],
                'edge': opp['edge'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        
        self.log_trade(trade)
    
    def run(self):
        print("="*70)
        print("WALLET 1 BOT - BINANCE API (No Rate Limits)")
        print("="*70)
        print("Bankroll: $686.93")
        print("Main: 5m/15m (80%) | Extended: 30m-24h (20%)")
        print("Scanning every 3 seconds...")
        print("="*70)
        
        cycle = 0
        while self.running:
            cycle += 1
            for coin in self.coins:
                price = self.get_crypto_price(coin)
                if price:
                    if coin in self.last_prices:
                        change = price - self.last_prices[coin]
                        self.velocities[coin] = change
                    
                    for tf in self.primary_timeframes + self.extended_timeframes:
                        self.evaluate_market(coin, tf)
                    
                    self.last_prices[coin] = price
            
            if cycle % 10 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning... Balance: ${self.virtual_free:.2f} | Trades: {self.trade_count}")
            
            time.sleep(3)

if __name__ == "__main__":
    bot = Wallet1Bot()
    bot.run()
