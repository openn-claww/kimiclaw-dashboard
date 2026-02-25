#!/usr/bin/env python3
"""
High-Frequency Continuous Trader
- No polling, continuous execution
- Sub-second latency
- Arbitrage detection
- Real-time WebSocket data
"""

import asyncio
import websockets
import json
import time
import threading
from datetime import datetime
import requests

class HFTrader:
    def __init__(self):
        self.running = True
        self.positions = {}
        self.prices = {}
        self.last_trade_time = 0
        self.trade_count = 0
        
    async def binance_ws(self):
        """Real-time Binance WebSocket for price data"""
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    async for message in websocket:
                        data = json.loads(message)
                        symbol = data.get('s', '').replace('USDT', '')
                        price = float(data.get('p', 0))
                        
                        if symbol and price:
                            self.prices[symbol] = {
                                'price': price,
                                'time': time.time()
                            }
                            
                        # Check for trade opportunity every message (sub-second)
                        self.check_opportunity(symbol, price)
                        
            except Exception as e:
                print(f"WebSocket error: {e}")
                await asyncio.sleep(1)
    
    def check_opportunity(self, symbol, price):
        """Check for arbitrage or edge opportunity"""
        current_time = time.time()
        
        # Rate limit: max 1 trade per 5 seconds
        if current_time - self.last_trade_time < 5:
            return
        
        # Get Polymarket price (fast REST call)
        try:
            coin = symbol.lower()
            slot = int(current_time // 300) * 300
            slug = f"{coin}-updown-5m-{slot}"
            
            resp = requests.get(
                f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                timeout=0.5  # 500ms timeout for speed
            )
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                
                if len(prices) == 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    # Check for arbitrage: YES + NO < 1.0
                    if yes_price + no_price < 0.99:
                        # Buy both sides for guaranteed profit
                        self.execute_arbitrage(coin, yes_price, no_price)
                        self.last_trade_time = current_time
                        
                    # Check for momentum edge
                    elif self.detect_momentum(symbol, price):
                        side = 'YES' if price > self.prices.get(symbol, {}).get('price', price) else 'NO'
                        self.execute_trade(coin, side, yes_price if side == 'YES' else no_price)
                        self.last_trade_time = current_time
                        
        except:
            pass
    
    def detect_momentum(self, symbol, current_price):
        """Detect price momentum in last 10 seconds"""
        if symbol not in self.prices:
            return False
        
        prev = self.prices[symbol]
        time_diff = time.time() - prev.get('time', 0)
        
        if time_diff > 10:  # Data too old
            return False
        
        price_change = (current_price - prev['price']) / prev['price'] * 100
        
        # Strong momentum: >0.5% in 10 seconds
        return abs(price_change) > 0.5
    
    def execute_arbitrage(self, coin, yes_price, no_price):
        """Execute arbitrage trade - buy both sides"""
        print(f"ARBITRAGE: {coin} | YES={yes_price:.3f} | NO={no_price:.3f} | Sum={yes_price+no_price:.3f}")
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'trade_sim',
            'market': f'{coin.upper()} Up or Down - 5 Minutes',
            'side': 'ARBITRAGE',
            'amount': 20.0,
            'yes_price': yes_price,
            'no_price': no_price,
            'notes': f'ARBITRAGE: Buy YES+NO for {yes_price+no_price:.3f} (<1.0)'
        }
        
        self.save_trade(trade)
        self.trade_count += 1
    
    def execute_trade(self, coin, side, price):
        """Execute single side trade"""
        print(f"TRADE: {coin} | {side} @ {price:.3f}")
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'trade_sim',
            'market': f'{coin.upper()} Up or Down - 5 Minutes',
            'side': side,
            'amount': 20.0,
            'entry_price': price,
            'notes': f'MOMENTUM: {side} @ {price:.3f}'
        }
        
        self.save_trade(trade)
        self.trade_count += 1
    
    def save_trade(self, trade):
        """Save trade to log"""
        try:
            with open('/root/.openclaw/workspace/InternalLog.json', 'r') as f:
                log = json.load(f)
        except:
            log = []
        
        log.append(trade)
        
        with open('/root/.openclaw/workspace/InternalLog.json', 'w') as f:
            json.dump(log, f, indent=2)
    
    async def run(self):
        """Main loop"""
        print("HIGH-FREQUENCY TRADER STARTED")
        print("Features: WebSocket data | Sub-second latency | Arbitrage detection")
        print("No polling - continuous execution")
        
        # Run WebSocket connection
        await self.binance_ws()

if __name__ == "__main__":
    trader = HFTrader()
    asyncio.run(trader.run())
