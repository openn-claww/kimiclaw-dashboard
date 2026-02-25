#!/usr/bin/env python3
"""
Wallet 1 - The $40 Profit Version
WebSocket, millisecond execution, continuous scanning
Virtual bankroll: $686.93 (current balance)
"""

import asyncio
import websockets
import json
import time
import requests
from datetime import datetime

class Wallet1Trader:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.trade_count = 0
        self.last_trade_time = 0
        
        # Current balance from previous trading
        self.virtual_balance = 686.93
        self.virtual_free = 686.93
        self.open_positions = []
        
        self.log_file = "/root/.openclaw/workspace/wallet1_new_trades.json"
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def calculate_edge(self, coin, yes_price, no_price):
        """Calculate trading edge like the $40 profit version"""
        if coin not in self.prices:
            return None
        
        price = self.prices[coin]['price']
        velocity = self.prices[coin].get('velocity', 0)
        
        # The $40 profit strategy: momentum + price position
        edge = 0
        side = None
        
        # Strong upward momentum
        if velocity > 1.5 and yes_price < 0.65:
            edge = velocity * (0.7 - yes_price)
            side = 'YES'
        # Strong downward momentum
        elif velocity < -1.5 and no_price < 0.65:
            edge = abs(velocity) * (0.7 - no_price)
            side = 'NO'
        
        if edge > 0.3:  # Minimum edge threshold
            return {
                'type': 'EDGE',
                'coin': coin,
                'side': side,
                'price': yes_price if side == 'YES' else no_price,
                'edge': edge,
                'velocity': velocity
            }
        return None
    
    def check_arbitrage(self, coin, yes_price, no_price):
        """Arbitrage detection"""
        total = yes_price + no_price
        if total < 0.99:
            return {
                'type': 'ARBITRAGE',
                'coin': coin,
                'yes': yes_price,
                'no': no_price,
                'profit': (1.0 - total) * 100
            }
        return None
    
    async def binance_ws(self):
        """MILLISECOND execution via WebSocket"""
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1: WebSocket connecting...")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1: WebSocket CONNECTED - Millisecond execution active!")
                    
                    async for message in websocket:
                        data = json.loads(message)
                        symbol = data.get('s', '').replace('USDT', '')
                        price = float(data.get('p', 0))
                        
                        if symbol and price:
                            # MILLISECOND: Calculate on every tick
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
                            
                            # MILLISECOND: Evaluate on every single tick
                            await self.evaluate_strategies(symbol)
                            
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
                await asyncio.sleep(0.5)  # Fast reconnect
    
    async def evaluate_strategies(self, coin):
        """Evaluate EVERY MILLISECOND - no waiting"""
        current_time = time.time()
        
        # Can trade every 8 seconds max (450/hour)
        if current_time - self.last_trade_time < 8:
            return
        
        if self.virtual_free < 15:
            return
        
        # Check 5m and 15m markets
        for tf in [5, 15]:
            try:
                slot = int(current_time // (tf * 60)) * (tf * 60)
                slug = f"{coin.lower()}-updown-{tf}m-{slot}"
                
                # FAST API call - 150ms timeout
                resp = requests.get(
                    f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                    timeout=0.15
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    prices = json.loads(data.get('outcomePrices', '[]'))
                    
                    if len(prices) == 2:
                        yes_price = float(prices[0])
                        no_price = float(prices[1])
                        
                        opportunity = None
                        
                        # Priority 1: Arbitrage (guaranteed)
                        opportunity = self.check_arbitrage(coin, yes_price, no_price)
                        
                        # Priority 2: Edge calculation (the $40 profit strategy)
                        if not opportunity:
                            opportunity = self.calculate_edge(coin, yes_price, no_price)
                        
                        if opportunity:
                            self.execute_trade(opportunity, tf)
                            self.last_trade_time = current_time
                            return  # One trade at a time
                            
            except:
                pass
    
    def execute_trade(self, opp, tf):
        """Execute trade"""
        # $25 bets (aggressive to recover)
        amount = min(25.0, self.virtual_free * 0.036)
        if amount < 15:
            return
        
        self.trade_count += 1
        tf_label = f"{tf}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W1 #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | Profit: {opp['profit']:.2f}% | Balance: ${self.virtual_free:.2f}")
            
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
            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W1 #{self.trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | Balance: ${self.virtual_free:.2f}")
            
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet1_trade',
                'strategy': 'EDGE',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price'],
                'edge': opp['edge'],
                'velocity': opp['velocity'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        
        self.log_trade(trade)
    
    async def run(self):
        print("="*70)
        print("WALLET 1 - THE $40 PROFIT VERSION")
        print("="*70)
        print(f"Virtual Bankroll: $686.93")
        print(f"Execution: MILLISECOND via WebSocket")
        print(f"Scanning: CONTINUOUS (no 60s wait)")
        print(f"Position Size: $25.00")
        print(f"Strategy: Edge calculation + Arbitrage")
        print("="*70)
        print()
        await self.binance_ws()

if __name__ == "__main__":
    trader = Wallet1Trader()
    asyncio.run(trader.run())
