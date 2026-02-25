#!/usr/bin/env python3
"""
Wallet 2 - Focused on 5min/15min markets ONLY
$500 virtual bankroll, millisecond execution
"""

import asyncio
import websockets
import json
import time
import requests
from datetime import datetime

class Wallet2Trader:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.trade_count = 0
        self.last_trade_time = 0
        self.virtual_balance = 500.0
        self.virtual_free = 500.0
        self.separate_log = "/root/.openclaw/workspace/wallet2_trades.json"
        
        # ONLY 5min and 15min markets
        self.timeframes = [5, 15]
        
    def log_trade(self, trade):
        try:
            with open(self.separate_log, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.separate_log, 'w') as f:
            json.dump(log, f, indent=2)
    
    def check_arbitrage(self, coin, yes_price, no_price, tf):
        """Strategy 1: Arbitrage on 5m/15m markets"""
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
    
    def check_momentum(self, coin, tf):
        """Strategy 2: Momentum on 5m/15m"""
        if coin in self.prices and coin in self.last_prices:
            change = (self.prices[coin]['price'] - self.last_prices[coin]['price']) / self.last_prices[coin]['price']
            
            # Strong momentum in 5m/15m timeframe
            threshold = 0.005 if tf == 5 else 0.008  # 0.5% for 5m, 0.8% for 15m
            
            if abs(change) > threshold:
                return {
                    'type': 'MOMENTUM',
                    'coin': coin,
                    'tf': tf,
                    'side': 'YES' if change > 0 else 'NO',
                    'strength': abs(change) * 100
                }
        return None
    
    async def binance_ws(self):
        """WebSocket for millisecond data"""
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2: WebSocket connecting...")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2: Connected!")
                    
                    async for message in websocket:
                        data = json.loads(message)
                        symbol = data.get('s', '').replace('USDT', '')
                        price = float(data.get('p', 0))
                        
                        if symbol and price:
                            # Calculate velocity
                            velocity = 0
                            if symbol in self.prices:
                                time_diff = time.time() - self.prices[symbol]['time']
                                price_diff = price - self.prices[symbol]['price']
                                if time_diff > 0:
                                    velocity = price_diff / time_diff
                            
                            if symbol in self.prices:
                                self.last_prices[symbol] = self.prices[symbol].copy()
                            
                            self.prices[symbol] = {
                                'price': price,
                                'time': time.time(),
                                'velocity': velocity
                            }
                            
                            # Check ALL timeframes on every tick (millisecond)
                            for tf in self.timeframes:
                                await self.evaluate_strategies(symbol, tf)
                            
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
                await asyncio.sleep(1)
    
    async def evaluate_strategies(self, coin, tf):
        """Evaluate every millisecond"""
        current_time = time.time()
        
        # Different rate limits for different timeframes
        min_interval = 10 if tf == 5 else 20  # 6/min for 5m, 3/min for 15m
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        if self.virtual_free < 10:
            return
        
        try:
            slot = int(current_time // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(
                f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                timeout=0.2  # 200ms timeout for speed
            )
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                
                if len(prices) == 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    opportunity = None
                    
                    # Priority 1: Arbitrage
                    opportunity = self.check_arbitrage(coin, yes_price, no_price, tf)
                    
                    # Priority 2: Momentum
                    if not opportunity:
                        momentum = self.check_momentum(coin, tf)
                        if momentum:
                            opportunity = {
                                'type': 'MOMENTUM',
                                'coin': coin,
                                'tf': tf,
                                'side': momentum['side'],
                                'price': yes_price if momentum['side'] == 'YES' else no_price,
                                'reason': f"{momentum['strength']:.2f}% move"
                            }
                    
                    if opportunity:
                        self.execute_trade(opportunity)
                        self.last_trade_time = current_time
                        
        except:
            pass
    
    def execute_trade(self, opp):
        """Execute with $20 bets"""
        amount = min(20.0, self.virtual_free * 0.04)
        if amount < 10:
            return
        
        self.trade_count += 1
        tf_label = f"{opp['tf']}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | Profit: {opp['profit']:.2f}% | ${self.virtual_free:.2f}")
            
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet2_trade',
                'strategy': 'ARBITRAGE',
                'market': f"{opp['coin'].upper()} Up or Down - {tf_label}",
                'side': 'BOTH',
                'amount': amount,
                'yes_price': opp['yes'],
                'no_price': opp['no'],
                'expected_profit': opp['profit'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
            
        else:
            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{self.trade_count} {opp['type']} {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | ${self.virtual_free:.2f}")
            
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet2_trade',
                'strategy': opp['type'],
                'market': f"{opp['coin'].upper()} Up or Down - {tf_label}",
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        
        self.log_trade(trade)
    
    async def run(self):
        print("="*70)
        print("WALLET 2 - 5MIN/15MIN FOCUS ONLY")
        print("="*70)
        print(f"Virtual Bankroll: $500.00")
        print(f"Timeframes: 5min, 15min ONLY")
        print(f"Execution: Millisecond via WebSocket")
        print(f"Position Size: $20.00")
        print("="*70)
        print()
        await self.binance_ws()

if __name__ == "__main__":
    trader = Wallet2Trader()
    asyncio.run(trader.run())
