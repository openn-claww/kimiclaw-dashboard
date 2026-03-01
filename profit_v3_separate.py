#!/usr/bin/env python3
"""
Profitable Trader v3.0 - Separate $500 Virtual Wallet
Independent from main trading log
"""

import asyncio
import websockets
import json
import time
import requests
from datetime import datetime

class ProfitableTraderV3:
    def __init__(self):
        self.running = True
        self.prices = {}
        self.last_prices = {}
        self.trade_count = 0
        self.last_trade_time = 0
        # SEPARATE $500 VIRTUAL BANKROLL
        self.virtual_balance = 500.0
        self.virtual_free = 500.0
        self.open_positions = []
        self.total_profit = 0.0
        self.separate_log = "/root/.openclaw/workspace/profit_v3_trades.json"
        
    def log_trade(self, trade):
        """Log to separate file"""
        try:
            with open(self.separate_log, 'r') as f:
                log = json.load(f)
        except:
            log = []
        
        log.append(trade)
        
        with open(self.separate_log, 'w') as f:
            json.dump(log, f, indent=2)
    
    def check_arbitrage(self, coin, yes_price, no_price):
        """Strategy 1: Arbitrage - guaranteed profit"""
        total = yes_price + no_price
        if total < 0.99:
            profit_pct = (1.0 - total) * 100
            return {
                'type': 'ARBITRAGE',
                'coin': coin,
                'yes': yes_price,
                'no': no_price,
                'profit': profit_pct,
                'action': 'BUY_BOTH'
            }
        return None
    
    def check_whale(self, coin):
        """Strategy 2: Whale tracking"""
        if coin in self.prices and coin in self.last_prices:
            change = (self.prices[coin]['price'] - self.last_prices[coin]['price']) / self.last_prices[coin]['price']
            if abs(change) > 0.01:  # 1% move = whale
                return {
                    'type': 'WHALE',
                    'coin': coin,
                    'side': 'YES' if change > 0 else 'NO',
                    'strength': abs(change) * 100
                }
        return None
    
    def check_news(self, coin):
        """Strategy 3: News sentiment via velocity"""
        if coin in self.prices and 'velocity' in self.prices[coin]:
            v = self.prices[coin]['velocity']
            if v > 2.0:
                return {'type': 'NEWS', 'coin': coin, 'sentiment': 'BULLISH'}
            elif v < -2.0:
                return {'type': 'NEWS', 'coin': coin, 'sentiment': 'BEARISH'}
        return None
    
    async def binance_ws(self):
        """Strategy 4: Sub-second execution via WebSocket"""
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket connecting...")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket connected!")
                    
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
                            
                            # Store last price
                            if symbol in self.prices:
                                self.last_prices[symbol] = self.prices[symbol].copy()
                            
                            # Update current
                            self.prices[symbol] = {
                                'price': price,
                                'time': time.time(),
                                'velocity': velocity
                            }
                            
                            # Evaluate on every message (sub-second)
                            await self.evaluate_strategies(symbol)
                            
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket error: {e}")
                await asyncio.sleep(1)
    
    async def evaluate_strategies(self, coin):
        """Strategy 5: High frequency - evaluate all strategies"""
        current_time = time.time()
        
        # Rate limit: 5 trades per minute = 300/hour = 7200/day
        if current_time - self.last_trade_time < 12:
            return
        
        # Check balance
        if self.virtual_free < 10:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Low balance: ${self.virtual_free:.2f}")
            return
        
        try:
            slot = int(current_time // 300) * 300
            slug = f"{coin.lower()}-updown-5m-{slot}"
            
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=0.3)
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                
                if len(prices) == 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    opportunity = None
                    
                    # Priority 1: Arbitrage (guaranteed profit)
                    opportunity = self.check_arbitrage(coin, yes_price, no_price)
                    
                    # Priority 2: Whale activity
                    if not opportunity:
                        whale = self.check_whale(coin)
                        if whale:
                            opportunity = {
                                'type': 'WHALE',
                                'coin': coin,
                                'side': whale['side'],
                                'price': yes_price if whale['side'] == 'YES' else no_price,
                                'reason': f"Whale: {whale['strength']:.1f}%"
                            }
                    
                    # Priority 3: News sentiment
                    if not opportunity:
                        news = self.check_news(coin)
                        if news:
                            side = 'YES' if news['sentiment'] == 'BULLISH' else 'NO'
                            opportunity = {
                                'type': 'NEWS',
                                'coin': coin,
                                'side': side,
                                'price': yes_price if side == 'YES' else no_price,
                                'reason': news['sentiment']
                            }
                    
                    # Execute if found
                    if opportunity:
                        self.execute_trade(opportunity)
                        self.last_trade_time = current_time
                        
        except Exception as e:
            pass
    
    def execute_trade(self, opp):
        """Execute trade with $500 virtual bankroll"""
        # Position size: 4% of virtual bankroll = $20
        amount = min(20.0, self.virtual_free * 0.04)
        
        if amount < 10:
            return
        
        self.trade_count += 1
        
        if opp['type'] == 'ARBITRAGE':
            print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] ARBITRAGE #{self.trade_count}: {opp['coin']} | Profit: {opp['profit']:.2f}% | Balance: ${self.virtual_free:.2f}")
            
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'trade_sim_v3',
                'strategy': 'ARBITRAGE',
                'market': f"{opp['coin'].upper()} Up or Down - 5 Minutes",
                'side': 'BOTH',
                'amount': amount,
                'yes_price': opp['yes'],
                'no_price': opp['no'],
                'expected_profit': opp['profit'],
                'virtual_balance_before': self.virtual_free,
                'virtual_balance_after': self.virtual_free - amount,
                'notes': f"ARBITRAGE: {opp['profit']:.2f}% guaranteed"
            }
            
            # Deduct from virtual balance
            self.virtual_free -= amount
            self.open_positions.append({
                'type': 'ARBITRAGE',
                'amount': amount,
                'yes_price': opp['yes'],
                'no_price': opp['no']
            })
            
        else:
            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] TRADE #{self.trade_count}: {opp['coin']} | {opp['side']} @ {opp['price']:.3f} | Type: {opp['type']} | Balance: ${self.virtual_free:.2f}")
            
            trade = {
                'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': 'trade_sim_v3',
                'strategy': opp['type'],
                'market': f"{opp['coin'].upper()} Up or Down - 5 Minutes",
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price'],
                'virtual_balance_before': self.virtual_free,
                'virtual_balance_after': self.virtual_free - amount,
                'notes': f"{opp['type']}: {opp.get('reason', opp['side'])}"
            }
            
            self.virtual_free -= amount
            self.open_positions.append({
                'type': opp['type'],
                'side': opp['side'],
                'amount': amount,
                'entry_price': opp['price']
            })
        
        self.log_trade(trade)
    
    def print_status(self):
        """Print current status"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] STATUS UPDATE")
        print(f"Virtual Balance: ${self.virtual_free:.2f} / $500.00")
        print(f"Open Positions: {len(self.open_positions)}")
        print(f"Total Trades: {self.trade_count}")
        print(f"P&L: ${self.virtual_free - 500:.2f}")
        print()
    
    async def status_reporter(self):
        """Report status every 5 minutes"""
        while self.running:
            await asyncio.sleep(300)  # 5 minutes
            self.print_status()
    
    async def run(self):
        print("="*70)
        print("PROFITABLE TRADER v3.0 - SEPARATE $500 VIRTUAL WALLET")
        print("="*70)
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Virtual Bankroll: $500.00")
        print(f"Position Size: $20.00 (4% per trade)")
        print(f"Max Trades: 7,200/day (5 per minute)")
        print()
        print("Strategies Active:")
        print("  1. ARBITRAGE - Guaranteed profit when YES+NO < $1.00")
        print("  2. WHALE TRACKING - Follow 1%+ price moves")
        print("  3. NEWS SENTIMENT - Velocity-based detection")
        print("  4. SUB-SECOND - WebSocket real-time execution")
        print("  5. HIGH FREQUENCY - Up to 7,200 trades/day")
        print("="*70)
        print()
        
        # Run both WebSocket and status reporter
        await asyncio.gather(
            self.binance_ws(),
            self.status_reporter()
        )

if __name__ == "__main__":
    trader = ProfitableTraderV3()
    asyncio.run(trader.run())
