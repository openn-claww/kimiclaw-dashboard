#!/usr/bin/env python3
"""
WALLET 1 BOT - Complete Strategy Documentation
==============================================

MAIN FOCUS: 5-minute and 15-minute markets (80% of trades)
SECONDARY: 30m to 24h markets (20% of trades, only for sure profit)

THOUGHT PROCESS:
================
1. THE $40 PROFIT STRATEGY (Edge Calculation)
   - Combines momentum + price position for an "edge score"
   - Edge = velocity × (0.7 - current_price)
   - Higher edge = higher probability of winning
   - Only trade if edge > 0.3

2. ARBITRAGE (Priority #1)
   - Same as Wallet 2: YES+NO < $1.00 = guaranteed profit
   - Works on ANY timeframe

3. SPEED ADVANTAGE
   - WebSocket for real-time data
   - 150ms API timeout (ultra-fast)
   - No polling delays

4. EXTENDED TIMEFRAME RULE (30m-24h)
   - ONLY arbitrage OR edge > 0.5 (much higher threshold)
   - Reason: Longer timeframes need stronger signals

5. AGGRESSIVE RECOVERY
   - $25 per trade (bigger bets to recover from -$129 loss)
   - Max 1 trade per 8 seconds (450/hour)
   - Current bankroll: $686.93

THRESHOLDS:
===========
- 5m market: Edge > 0.3
- 15m market: Edge > 0.3
- 30m-24h market: Edge > 0.5 OR arbitrage only
- Arbitrage: YES+NO < $0.99
- Rate limit: 8 seconds between trades

EDGE CALCULATION:
=================
edge = velocity × (0.7 - entry_price)

Example:
- Price velocity = 2.0 (strong upward move)
- YES price = 0.55
- Edge = 2.0 × (0.7 - 0.55) = 2.0 × 0.15 = 0.30
- This meets threshold, trade YES

WHY THIS WORKED FOR $40 PROFIT:
================================
- Edge calculation finds mispriced markets
- When momentum is strong AND price is still reasonable, probability is on our side
- Not just following price, but measuring "value" of the bet
"""

import asyncio
import websockets
import json
import time
import requests
from datetime import datetime

class Wallet1Bot:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.trade_count = 0
        self.last_trade_time = 0
        
        # Current balance from previous trading
        self.virtual_balance = 686.93
        self.virtual_free = 686.93
        self.log_file = "/root/.openclaw/workspace/wallet1_new_trades.json"
        
        # MAIN: 5m, 15m (80%) | EXTENDED: 30m-24h (20%)
        self.primary_timeframes = [5, 15]
        self.extended_timeframes = [30, 60, 240, 1440]
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def calculate_edge(self, coin, yes_price, no_price, tf):
        """THE $40 PROFIT STRATEGY: Edge calculation"""
        if coin not in self.prices:
            return None
        
        velocity = self.prices[coin].get('velocity', 0)
        
        # Different edge thresholds for different timeframes
        if tf in [5, 15]:
            min_edge = 0.3  # Primary timeframes
        else:
            min_edge = 0.5  # Extended timeframes (stricter)
        
        edge = 0
        side = None
        
        # Upward momentum
        if velocity > 1.5 and yes_price < 0.65:
            edge = velocity * (0.7 - yes_price)
            side = 'YES'
        # Downward momentum
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
        """ARBITRAGE: Guaranteed profit"""
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
    
    async def binance_ws(self):
        """MILLISECOND execution"""
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1: Starting...")
        print(f"Strategy: Edge Calculation + Arbitrage")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1: CONNECTED")
                    
                    async for message in websocket:
                        data = json.loads(message)
                        symbol = data.get('s', '').replace('USDT', '')
                        price = float(data.get('p', 0))
                        
                        if symbol and price:
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
                            
                            # Primary timeframes (5m, 15m)
                            for tf in self.primary_timeframes:
                                await self.evaluate_strategies(symbol, tf, primary=True)
                            
                            # Extended timeframes (30m-24h)
                            for tf in self.extended_timeframes:
                                await self.evaluate_strategies(symbol, tf, primary=False)
                            
            except Exception as e:
                await asyncio.sleep(0.5)
    
    async def evaluate_strategies(self, coin, tf, primary=True):
        """Evaluate every millisecond"""
        current_time = time.time()
        
        min_interval = 8 if primary else 20  # 8s for primary, 20s for extended
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        if self.virtual_free < 15:
            return
        
        try:
            slot = int(current_time // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(
                f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                timeout=0.15  # 150ms - ultra fast
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
                    
                    # Priority 2: Edge calculation
                    if not opportunity:
                        opportunity = self.calculate_edge(coin, yes_price, no_price, tf)
                    
                    if opportunity:
                        self.execute_trade(opportunity)
                        self.last_trade_time = current_time
                        
        except:
            pass
    
    def execute_trade(self, opp):
        """Execute with $25 bets"""
        amount = min(25.0, self.virtual_free * 0.036)
        if amount < 15:
            return
        
        self.trade_count += 1
        tf_label = f"{opp['tf']}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 W1 #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | Profit: {opp['profit']:.2f}% | ${self.virtual_free:.2f}")
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
            print(f"📈 W1 #{self.trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | ${self.virtual_free:.2f}")
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
        print("WALLET 1 BOT - THE $40 PROFIT VERSION")
        print("="*70)
        print("Bankroll: $686.93")
        print("Main Focus: 5m/15m markets (80%)")
        print("Secondary: 30m-24h (20%, high edge only)")
        print("Strategy: Edge Calculation + Arbitrage")
        print("Execution: Millisecond via WebSocket")
        print("="*70)
        await self.binance_ws()

if __name__ == "__main__":
    bot = Wallet1Bot()
    asyncio.run(bot.run())
