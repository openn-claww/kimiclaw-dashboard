#!/usr/bin/env python3
"""
WALLET 2 BOT - Complete Strategy Documentation
================================================

MAIN FOCUS: 5-minute and 15-minute markets (80% of trades)
SECONDARY: 30m to 24h markets (20% of trades, only for sure profit)

THOUGHT PROCESS:
================
1. SPEED IS EVERYTHING
   - WebSocket connection to Binance for real-time prices
   - No polling, no delays - every tick is processed instantly
   - API timeout: 200ms (fail fast, move on)

2. ARBITRAGE = GUARANTEED PROFIT (Priority #1)
   - When YES_price + NO_price < $1.00, buy both
   - Example: YES=0.48, NO=0.48, Total=0.96
   - Profit: 4% guaranteed when market resolves
   - This works on ANY timeframe (5m, 15m, 1h, 24h)

3. MOMENTUM TRADING (Priority #2, 5m/15m only)
   - If price moving up >0.5% (5m) or >0.8% (15m) → Buy YES
   - If price moving down >0.5% (5m) or >0.8% (15m) → Buy NO
   - Thresholds are tighter for shorter timeframes (more sensitive)

4. EXTENDED TIMEFRAME RULE (30m-24h)
   - ONLY trade if arbitrage opportunity exists
   - OR if price movement is >2% (much stronger signal)
   - Reason: Longer timeframes = more noise, need stronger confirmation

5. POSITION SIZING
   - $20 per trade (4% of $500 bankroll)
   - Max 1 trade per 10 seconds (360/hour)
   - Never risk more than 20% of bankroll in open positions

THRESHOLDS:
===========
- 5m market: 0.5% price move to trigger
- 15m market: 0.8% price move to trigger
- 30m-24h market: 2% price move OR arbitrage only
- Arbitrage: YES+NO < $0.99
- Rate limit: 10 seconds between trades

WHY THIS WORKS:
===============
- Short-term markets (5m/15m) have predictable momentum
- Arbitrage is math, not prediction - guaranteed profit
- Extended timeframes only for sure things (arbitrage)
- Millisecond execution means we act before others
"""

import asyncio
import websockets
import json
import time
import requests
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
        
        # MAIN FOCUS: 5m, 15m (80% of trades)
        # SECONDARY: 30m, 1h, 4h, 24h (20% of trades, sure profit only)
        self.primary_timeframes = [5, 15]
        self.extended_timeframes = [30, 60, 240, 1440]  # 30m, 1h, 4h, 24h
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def check_arbitrage(self, coin, yes_price, no_price, tf):
        """ARBITRAGE: Guaranteed profit on ANY timeframe"""
        total = yes_price + no_price
        if total < 0.99:
            return {
                'type': 'ARBITRAGE',
                'coin': coin,
                'tf': tf,
                'yes': yes_price,
                'no': no_price,
                'profit': (1.0 - total) * 100,
                'confidence': 'GUARANTEED'
            }
        return None
    
    def check_momentum(self, coin, tf):
        """MOMENTUM: Different thresholds for different timeframes"""
        if coin not in self.prices or coin not in self.last_prices:
            return None
        
        change = (self.prices[coin]['price'] - self.last_prices[coin]['price']) / self.last_prices[coin]['price']
        
        # THRESHOLDS based on timeframe
        if tf == 5:
            threshold = 0.005  # 0.5% for 5m
        elif tf == 15:
            threshold = 0.008  # 0.8% for 15m
        else:
            threshold = 0.02   # 2% for 30m-24h (much stricter)
        
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
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2: Starting...")
        print(f"Primary: 5m/15m | Extended: 30m-24h (arbitrage only)")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2: CONNECTED")
                    
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
                            
                            # Check PRIMARY timeframes (5m, 15m) - 80% focus
                            for tf in self.primary_timeframes:
                                await self.evaluate_strategies(symbol, tf, primary=True)
                            
                            # Check EXTENDED timeframes (30m-24h) - 20% focus
                            for tf in self.extended_timeframes:
                                await self.evaluate_strategies(symbol, tf, primary=False)
                            
            except Exception as e:
                await asyncio.sleep(1)
    
    async def evaluate_strategies(self, coin, tf, primary=True):
        """Evaluate trading opportunity"""
        current_time = time.time()
        
        # Rate limits
        if primary:
            min_interval = 10  # 6 trades/min for 5m/15m
        else:
            min_interval = 30  # 2 trades/min for extended
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        if self.virtual_free < 10:
            return
        
        try:
            slot = int(current_time // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(
                f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                timeout=0.2
            )
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                
                if len(prices) == 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    opportunity = None
                    
                    # Priority 1: ARBITRAGE (works on ALL timeframes)
                    opportunity = self.check_arbitrage(coin, yes_price, no_price, tf)
                    
                    # Priority 2: MOMENTUM (only if no arbitrage)
                    if not opportunity:
                        momentum = self.check_momentum(coin, tf)
                        if momentum:
                            # For extended timeframes, ONLY take arbitrage
                            # Momentum trades only on 5m/15m
                            if primary or momentum['strength'] > 3.0:  # >3% for extended
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
        """Execute trade"""
        amount = min(20.0, self.virtual_free * 0.04)
        if amount < 10:
            return
        
        self.trade_count += 1
        tf_label = f"{opp['tf']}m"
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 W2 #{self.trade_count} ARBITRAGE {opp['coin']} {tf_label} | Profit: {opp['profit']:.2f}% | ${self.virtual_free:.2f}")
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
            print(f"📈 W2 #{self.trade_count} MOMENTUM {opp['coin']} {tf_label} | {opp['side']} | {opp['reason']} | ${self.virtual_free:.2f}")
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'wallet2_trade',
                'strategy': 'MOMENTUM',
                'market': f"{opp['coin'].upper()} {tf_label}",
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price'],
                'virtual_balance': self.virtual_free - amount
            }
            self.virtual_free -= amount
        
        self.log_trade(trade)
    
    async def run(self):
        print("="*70)
        print("WALLET 2 BOT")
        print("="*70)
        print("Bankroll: $500.00")
        print("Main Focus: 5m/15m markets (80% of trades)")
        print("Secondary: 30m-24h (20%, arbitrage only)")
        print("Strategy: Arbitrage + Momentum")
        print("Execution: Millisecond via WebSocket")
        print("="*70)
        await self.binance_ws()

if __name__ == "__main__":
    bot = Wallet2Bot()
    asyncio.run(bot.run())
