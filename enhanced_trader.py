#!/usr/bin/env python3
"""
ENHANCED TRADER - All 3 Features Implemented:
1. Multi-market correlation (BTC leads, ETH/SOL follow)
2. Kelly Criterion position sizing
3. Position tracking & limits
"""

import os
import json
import time
import requests
from datetime import datetime

# Load environment
env_file = '/root/.openclaw/skills/polyclaw/.env'
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

class EnhancedTrader:
    def __init__(self, wallet_name, initial_balance):
        self.wallet_name = wallet_name
        self.initial_balance = initial_balance
        self.virtual_free = initial_balance
        self.trade_count = 0
        self.last_trade_time = 0
        self.log_file = f"/root/.openclaw/workspace/{wallet_name}_enhanced.json"
        
        # Position tracking for #3
        self.open_positions = {'YES': 0, 'NO': 0, 'total_risk': 0}
        self.max_position_pct = 0.30  # 30% max per side
        self.max_total_risk = 0.50    # 50% max total risk
        
        # Thresholds
        self.thresholds = {5: 0.08, 15: 0.15, 30: 0.25, 60: 0.40}
        
        # Multi-market correlation data (#2)
        self.prices = {}
        self.velocities = {}
        self.correlations = {
            'BTC': {'ETH': 0.85, 'SOL': 0.75, 'XRP': 0.70},
            'ETH': {'BTC': 0.85, 'SOL': 0.80, 'XRP': 0.65},
            'SOL': {'BTC': 0.75, 'ETH': 0.80, 'XRP': 0.60},
            'XRP': {'BTC': 0.70, 'ETH': 0.65, 'SOL': 0.60}
        }
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def get_binance_price(self, coin):
        try:
            resp = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT', timeout=2)
            return float(resp.json()['price'])
        except:
            return None
    
    def kelly_position_size(self, edge, odds=2.0):  # #1 Kelly Criterion
        """Calculate bet size using Kelly Criterion"""
        if edge <= 0:
            return 0
        
        # Kelly formula: f* = (bp - q) / b
        # b = odds - 1, p = probability of win, q = 1-p
        # Simplified: bet = edge * bankroll / (odds - 1)
        
        b = odds - 1  # Decimal odds minus 1
        p = 0.5 + edge  # Estimated win probability
        q = 1 - p
        
        kelly_fraction = (b * p - q) / b if b > 0 else 0
        
        # Half Kelly for safety (less volatile)
        half_kelly = kelly_fraction * 0.5
        
        # Calculate actual bet
        bet = half_kelly * self.initial_balance
        
        # Cap at 5% of bankroll max
        max_bet = self.initial_balance * 0.05
        bet = min(bet, max_bet)
        
        # Min $10 bet
        return max(bet, 10) if bet >= 10 else 0
    
    def check_position_limits(self, side, amount):  # #3 Position Limits
        """Check if trade respects position limits"""
        current_side = self.open_positions.get(side, 0)
        total_risk = self.open_positions.get('total_risk', 0)
        
        # Check side limit (30% max)
        if (current_side + amount) / self.initial_balance > self.max_position_pct:
            return False
        
        # Check total risk limit (50% max)
        if (total_risk + amount) / self.initial_balance > self.max_total_risk:
            return False
        
        return True
    
    def update_positions(self, side, amount):
        """Track open positions"""
        self.open_positions[side] = self.open_positions.get(side, 0) + amount
        self.open_positions['total_risk'] = self.open_positions.get('total_risk', 0) + amount
    
    def check_polymarket(self, coin, tf):
        try:
            slot = int(time.time() // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=1)
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                if len(prices) == 2:
                    return {'yes': float(prices[0]), 'no': float(prices[1])}
        except:
            pass
        return None
    
    def find_opportunities(self, coin, tf, price, velocity):  # #2 Multi-market
        """Find opportunities including correlated markets"""
        opportunities = []
        
        # Primary opportunity
        opp = self.analyze_market(coin, tf, price, velocity)
        if opp:
            opportunities.append(opp)
        
        # Correlated markets (#2 feature)
        if coin in self.correlations:
            for other_coin, correlation in self.correlations[coin].items():
                if other_coin in self.velocities:
                    # Adjust velocity by correlation
                    correlated_velocity = self.velocities[other_coin] * correlation
                    opp = self.analyze_market(other_coin, tf, None, correlated_velocity, 
                                               source_coin=coin, correlation=correlation)
                    if opp:
                        opportunities.append(opp)
        
        return opportunities
    
    def analyze_market(self, coin, tf, price, velocity, source_coin=None, correlation=None):
        """Analyze single market for opportunity"""
        if self.virtual_free < 10:
            return None
        
        current_time = time.time()
        min_interval = 8 if tf <= 15 else 15
        if current_time - self.last_trade_time < min_interval:
            return None
        
        pm = self.check_polymarket(coin, tf)
        if not pm:
            return None
        
        yes_price = pm['yes']
        no_price = pm['no']
        total = yes_price + no_price
        
        # Arbitrage check
        if total < 0.995:
            edge = 1 - total
            bet_size = self.kelly_position_size(edge, 1/total)  # #1 Kelly
            if bet_size > 0 and self.check_position_limits('BOTH', bet_size):  # #3 Limits
                return {
                    'type': 'ARBITRAGE',
                    'coin': coin,
                    'tf': tf,
                    'side': 'BOTH',
                    'amount': bet_size,
                    'edge': edge,
                    'reason': f'YES+NO={total:.3f}'
                }
        
        # Momentum analysis
        if price:
            change_pct = (velocity / price) * 100
        else:
            change_pct = velocity * 100  # Already in percent
        
        threshold = self.thresholds.get(tf, 0.5)
        
        if abs(change_pct) > threshold:
            # Calculate edge
            if change_pct > 0:
                edge = min(change_pct / 100, 0.15)
                side = 'YES'
                market_price = yes_price
            else:
                edge = min(abs(change_pct) / 100, 0.15)
                side = 'NO'
                market_price = no_price
            
            # Kelly sizing (#1)
            odds = 1 / market_price if market_price > 0 else 2.0
            bet_size = self.kelly_position_size(edge, odds)
            
            if bet_size > 0 and self.check_position_limits(side, bet_size):  # #3 Limits
                reason = f"Move: {change_pct:+.2f}%"
                if source_coin and correlation:
                    reason += f" (from {source_coin}, corr: {correlation:.0%})"
                
                return {
                    'type': 'MOMENTUM',
                    'coin': coin,
                    'tf': tf,
                    'side': side,
                    'amount': bet_size,
                    'edge': edge,
                    'reason': reason
                }
        
        return None
    
    def execute_trade(self, opp):
        """Execute trade with all features"""
        amount = opp['amount']
        side = opp.get('side', 'BOTH')
        
        self.trade_count += 1
        self.virtual_free -= amount
        self.last_trade_time = time.time()
        
        # Update position tracking (#3)
        if side == 'BOTH':
            self.update_positions('YES', amount / 2)
            self.update_positions('NO', amount / 2)
        else:
            self.update_positions(side, amount)
        
        emoji = '🎯' if opp['type'] == 'ARBITRAGE' else '📈'
        tf_label = f"{opp['tf']}m"
        
        print(f"{emoji} [{datetime.now().strftime('%H:%M:%S')}] {self.wallet_name} #{self.trade_count}")
        print(f"   {opp['coin'].upper()} {tf_label} | {side} | ${amount:.2f}")
        print(f"   Edge: {opp['edge']:.2%} | {opp['reason']}")
        print(f"   Balance: ${self.virtual_free:.2f} | Positions: YES=${self.open_positions['YES']:.0f} NO=${self.open_positions['NO']:.0f}")
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'wallet': self.wallet_name,
            'type': opp['type'],
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': side,
            'amount': amount,
            'edge': opp['edge'],
            'reason': opp['reason'],
            'virtual_balance': self.virtual_free,
            'positions': dict(self.open_positions)
        }
        self.log_trade(trade)
    
    def scan(self):
        """Main scanning loop"""
        coins = ['BTC', 'ETH', 'SOL', 'XRP']
        timeframes = [5, 15, 30]
        
        print("="*70)
        print(f"🚀 ENHANCED TRADER - {self.wallet_name}")
        print("="*70)
        print(f"Balance: ${self.initial_balance:.2f}")
        print("Features: #1 Kelly Sizing | #2 Multi-Market | #3 Position Limits")
        print("="*70)
        print()
        
        cycle = 0
        while True:
            # Get all prices first
            for coin in coins:
                price = self.get_binance_price(coin)
                if price:
                    if coin in self.prices:
                        self.velocities[coin] = price - self.prices[coin]
                    self.prices[coin] = price
            
            # Find opportunities with multi-market correlation
            for coin in coins:
                if coin in self.prices and coin in self.velocities:
                    for tf in timeframes:
                        opportunities = self.find_opportunities(
                            coin, tf, self.prices[coin], self.velocities[coin]
                        )
                        
                        for opp in opportunities:
                            self.execute_trade(opp)
                            time.sleep(1)  # Brief pause between trades
            
            cycle += 1
            if cycle % 20 == 0:  # Status every minute
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.wallet_name}: ${self.virtual_free:.2f} | Trades: {self.trade_count}")
            
            time.sleep(3)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'wallet1':
        trader = EnhancedTrader('WALLET_1', 686.93)
    else:
        trader = EnhancedTrader('WALLET_2', 500.00)
    trader.scan()
