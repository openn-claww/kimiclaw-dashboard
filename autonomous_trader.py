#!/usr/bin/env python3
"""
Autonomous Paper Trading Bot
Runs 24/7 without user intervention
"""

import requests
import json
import time
import sys
from datetime import datetime

sys.path.insert(0, '/root/.openclaw/workspace')

class AutonomousTrader:
    def __init__(self):
        self.virtual_balance = 1000.0
        self.open_trades = []
        self.total_profit = 0.0
        self.discord_channel = "1475209252183343347"
        self.log_file = "/root/.openclaw/workspace/InternalLog.json"
        self.last_report_time = 0
        
    def log(self, message):
        """Print with timestamp"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def load_log(self):
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_log(self, log):
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def update_balance(self):
        """Recalculate balance from log"""
        log = self.load_log()
        balance = 1000.0
        profit = 0.0
        open_count = 0
        
        for entry in log:
            if entry.get('event_type') == 'trade_sim':
                amount = entry.get('amount', 0)
                balance -= amount
                open_count += 1
                
                if 'WON' in entry.get('notes', ''):
                    balance += amount * 2
                    profit += amount * (1 - entry.get('entry_price', 0.5))
                    open_count -= 1
                elif 'LOST' in entry.get('notes', ''):
                    profit -= amount * entry.get('entry_price', 0.5)
                    open_count -= 1
        
        self.virtual_balance = balance
        self.total_profit = profit
        return open_count
    
    def scan_and_trade(self):
        """Main trading logic"""
        current = int(time.time())
        slot_5m = (current // 300) * 300
        
        # Get crypto prices
        try:
            resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,ripple&vs_currencies=usd', timeout=5)
            prices = resp.json()
        except:
            self.log("Failed to get prices")
            return
        
        # Scan markets
        coins = [
            ('btc', 'BTC', prices['bitcoin']['usd']),
            ('eth', 'ETH', prices['ethereum']['usd']),
            ('sol', 'SOL', prices['solana']['usd']),
            ('xrp', 'XRP', prices['ripple']['usd'])
        ]
        
        markets = []
        for coin, name, price in coins:
            slug = f'{coin}-updown-5m-{slot_5m}'
            try:
                resp = requests.get(f'https://gamma-api.polymarket.com/markets/slug/{slug}', timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    p = json.loads(data.get('outcomePrices', '[]'))
                    if len(p) == 2:
                        yes, no = float(p[0]), float(p[1])
                        markets.append({'coin': name, 'yes': yes, 'no': no, 'price': price})
            except:
                pass
        
        if not markets:
            return
        
        # Find best trade
        best = None
        best_edge = 0
        
        for m in markets:
            yes, no = m['yes'], m['no']
            if yes < no:
                side, price, edge = 'YES', yes, (0.50 - yes) * 100
            else:
                side, price, edge = 'NO', no, (0.50 - no) * 100
            
            if edge > best_edge and edge > 0.3:  # Min 0.3% edge
                best_edge = edge
                best = {
                    'coin': m['coin'],
                    'side': side,
                    'price': price,
                    'edge': edge,
                    'spot': m['price']
                }
        
        if best:
            self.execute_trade(best)
    
    def execute_trade(self, best):
        """Execute paper trade"""
        amount = min(20.0, self.virtual_balance * 0.02)
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'trade_sim',
            'market': best['coin'] + ' Up or Down - 5 Minutes',
            'side': best['side'],
            'amount': amount,
            'entry_price': best['price'],
            'reason_points': [
                best['coin'] + ' at $' + str(best['spot']) + ' (CoinGecko)',
                best['side'] + ' at ' + str(round(best['price'],3)) + ' = ' + str(round(best['edge'],2)) + '% edge',
                '5-min slot active with liquidity'
            ],
            'your_prob': 50 + best['edge'],
            'ev': best['edge'] * amount / 100,
            'virtual_balance_after': self.virtual_balance - amount,
            'real_balance_snapshot': 4.53,
            'notes': 'AUTO-TRADE: ' + str(round(best['edge'],2)) + '% edge'
        }
        
        log = self.load_log()
        log.append(trade)
        self.save_log(log)
        
        self.virtual_balance -= amount
        
        self.log(f"TRADE: {best['coin']} {best['side']} @ {best['price']:.3f} (edge: {best['edge']:.2f}%)")
        
        # Post to Discord
        self.post_discord(trade, best)
    
    def post_discord(self, trade, best):
        """Post trade to Discord"""
        # This will be called via message tool
        pass
    
    def hourly_report(self):
        """Generate hourly status report"""
        current_time = time.time()
        if current_time - self.last_report_time < 3600:  # 1 hour
            return
        
        self.last_report_time = current_time
        open_count = self.update_balance()
        
        report = f"""
📊 HOURLY REPORT - {datetime.now().strftime('%H:%M UTC')}
Virtual Balance: ${self.virtual_balance:.2f}
Total Profit: ${self.total_profit:+.2f}
Open Trades: {open_count}
Status: Scanning 5-min markets continuously
        """.strip()
        
        self.log("Hourly report generated")
        return report
    
    def run(self):
        """Main loop"""
        self.log("AUTONOMOUS TRADER STARTED")
        self.log("Scanning every 60 seconds...")
        
        iteration = 0
        while True:
            try:
                iteration += 1
                
                # Update balance
                open_count = self.update_balance()
                
                # Scan and trade
                self.scan_and_trade()
                
                # Hourly report
                if iteration % 60 == 0:  # Every 60 iterations (roughly hourly)
                    self.hourly_report()
                
                # Sleep 60 seconds
                time.sleep(60)
                
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    trader = AutonomousTrader()
    trader.run()
