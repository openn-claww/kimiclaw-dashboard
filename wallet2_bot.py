#!/usr/bin/env python3
"""
WALLET 2 BOT - Fast Polling Version (WebSocket backup)
Main: 5m/15m | Extended: 30m-24h (arbitrage only)
"""

import time
import requests
import json
from datetime import datetime

class Wallet2Bot:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.trade_count = 0
        self.last_trade_time = 0
        self.virtual_balance = 500.0
        self.virtual_free = 500.0
        self.log_file = "/root/.openclaw/workspace/wallet2_trades.json"
        
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
        """Get price from CoinGecko"""
        try:
            coin_id = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'XRP': 'ripple'}[coin]
            resp = requests.get(
                f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd',
                timeout=2
            )
            if resp.status_code == 200:
                return resp.json()[coin_id]['usd']
        except:
            pass
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
    
    def check_momentum(self, coin, current_price, tf):
        if coin not in self.last_prices:
            return None
        
        change = (current_price - self.last_prices[coin]) / self.last_prices[coin]
        
        if tf == 5:
            threshold = 0.005
        elif tf == 15:
            threshold = 0.008
        else:
            threshold = 0.02
        
        if abs(change) > threshold:
            return {
                'type': 'MOMENTUM',
                'coin': coin,
                'tf': tf,
                'side': 'YES' if change > 0 else 'NO',
                'strength': abs(change) * 100
            }
        return None
    
    def evaluate_market(self, coin, tf, current_price):
        """Evaluate a specific market"""
        if self.virtual_free < 10:
            return
        
        current_time = time.time()
        
        # Rate limits
        min_interval = 10 if tf in [5, 15] else 30
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
                    
                    # Priority 1: Arbitrage (any timeframe)
                    opportunity = self.check_arbitrage(coin, yes_price, no_price, tf)
                    
                    # Priority 2: Momentum (primary only, or strong for extended)
                    if not opportunity:
                        momentum = self.check_momentum(coin, current_price, tf)
                        if momentum:
                            if tf in [5, 15] or momentum['strength'] > 3.0:
                                opportunity = {
                                    'type': 'MOMENTUM',
                                    'coin': coin,
                                    'tf': tf,
                                    'side': momentum['side'],
                                    'price': yes_price if momentum['side'] == 'YES' else no_price,
                                    'reason': f"{momentum['strength']:.2f}%"
                                }
                    
                    if opportunity:
                        self.execute_trade(opportunity)
                        self.last_trade_time = current_time
                        
        except:
            pass
    
    def execute_trade(self, opp):
        amount = min(20.0, self.virtual_free * 0.04)
        if amount < 10:
            return
        
        self.trade_count += 1
        tf_label = f"{opp['tf']}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W2 #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | +{opp['profit']:.1f}% | ${self.virtual_free:.2f}")
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet2_trade',
                'strategy': 'ARBITRAGE',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': 'BOTH',
                'amount': amount,
                'expected_profit': opp['profit'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        else:
            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W2 #{self.trade_count} MOMENTUM {opp['coin']} {tf_label} | {opp['side']} | {opp['reason']} | ${self.virtual_free:.2f}")
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet2_trade',
                'strategy': 'MOMENTUM',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': opp['side'],
                'amount': amount,
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        
        self.log_trade(trade)
    
    def run(self):
        print("="*70)
        print("WALLET 2 BOT - FAST POLLING")
        print("="*70)
        print("Bankroll: $500.00")
        print("Main: 5m/15m (80%) | Extended: 30m-24h (20%)")
        print("Scanning every 2 seconds...")
        print("="*70)
        
        while self.running:
            for coin in self.coins:
                price = self.get_crypto_price(coin)
                if price:
                    # Check primary timeframes
                    for tf in self.primary_timeframes:
                        self.evaluate_market(coin, tf, price)
                    
                    # Check extended timeframes
                    for tf in self.extended_timeframes:
                        self.evaluate_market(coin, tf, price)
                    
                    self.last_prices[coin] = price
            
            time.sleep(2)  # 2-second polling

if __name__ == "__main__":
    bot = Wallet2Bot()
    bot.run()
