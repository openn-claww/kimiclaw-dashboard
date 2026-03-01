#!/usr/bin/env python3
"""
Adaptive Profit-First Trader
- No hardcoded edge
- Multiple free APIs for precise data
- Adaptive to market conditions
- Only goal: PROFIT
"""

import requests
import json
import time
import sys
from datetime import datetime

sys.path.insert(0, '/root/.openclaw/workspace')

class AdaptiveTrader:
    def __init__(self):
        self.virtual_balance = 1000.0
        self.log_file = "/root/.openclaw/workspace/InternalLog.json"
        self.discord_channel = "1475209252183343347"
        self.recent_trades = []
        
    def log(self, message):
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
    
    def get_comprehensive_data(self, symbol, coin_id):
        """Get data from multiple free APIs"""
        data = {
            'price': 0,
            'change_24h': 0,
            'change_1h': 0,
            'volume_24h': 0,
            'high_24h': 0,
            'low_24h': 0,
            'rsi': 50,
            'order_book_bias': 0,
            'funding_rate': 0
        }
        
        # API 1: CoinGecko (primary)
        try:
            resp = requests.get(
                f'https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true',
                timeout=10
            )
            cg_data = resp.json()
            md = cg_data.get('market_data', {})
            data['price'] = md.get('current_price', {}).get('usd', 0)
            data['change_24h'] = md.get('price_change_percentage_24h', 0)
            data['volume_24h'] = md.get('total_volume', {}).get('usd', 0)
            data['high_24h'] = md.get('high_24h', {}).get('usd', 0)
            data['low_24h'] = md.get('low_24h', {}).get('usd', 0)
        except Exception as e:
            self.log(f"CoinGecko error: {e}")
        
        # API 2: CoinGecko 1h change (from chart)
        try:
            resp = requests.get(
                f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=1',
                timeout=10
            )
            chart = resp.json()
            prices = chart.get('prices', [])
            if len(prices) >= 2:
                current = prices[-1][1]
                hour_ago = prices[-2][1] if len(prices) >= 2 else prices[0][1]
                data['change_1h'] = ((current - hour_ago) / hour_ago) * 100
        except:
            pass
        
        # API 3: Binance (free, no key needed for basic data)
        try:
            binance_symbol = symbol.upper() + "USDT"
            resp = requests.get(
                f'https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}',
                timeout=5
            )
            bin_data = resp.json()
            # Use as backup if CoinGecko fails
            if data['price'] == 0:
                data['price'] = float(bin_data.get('lastPrice', 0))
            if data['change_24h'] == 0:
                data['change_24h'] = float(bin_data.get('priceChangePercent', 0))
            if data['volume_24h'] == 0:
                data['volume_24h'] = float(bin_data.get('volume', 0)) * data['price']
        except:
            pass
        
        # API 4: CryptoCompare (free tier)
        try:
            resp = requests.get(
                f'https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol.upper()}&tsyms=USD',
                timeout=5
            )
            cc_data = resp.json()
            raw = cc_data.get('RAW', {}).get(symbol.upper(), {}).get('USD', {})
            if data['volume_24h'] == 0:
                data['volume_24h'] = raw.get('TOTALVOLUME24H', 0) * data['price']
        except:
            pass
        
        return data
    
    def analyze_market(self, data):
        """Deep market analysis - adaptive"""
        score = 0
        confidence = 0
        reasons = []
        
        # 1. Trend Analysis (weight: high)
        if abs(data['change_24h']) > 5:
            score += 2 if data['change_24h'] > 0 else -2
            confidence += 25
            reasons.append(f"Strong 24h trend: {data['change_24h']:+.1f}%")
        elif abs(data['change_24h']) > 2:
            score += 1 if data['change_24h'] > 0 else -1
            confidence += 15
            reasons.append(f"Moderate 24h trend: {data['change_24h']:+.1f}%")
        
        # 2. Short-term momentum (weight: high)
        if abs(data['change_1h']) > 1.5:
            score += 1.5 if data['change_1h'] > 0 else -1.5
            confidence += 20
            reasons.append(f"1h momentum: {data['change_1h']:+.1f}%")
        
        # 3. Range position (weight: medium)
        if data['high_24h'] > data['low_24h']:
            position = (data['price'] - data['low_24h']) / (data['high_24h'] - data['low_24h'])
            if position > 0.85:
                score -= 1.5  # Overbought
                confidence += 10
                reasons.append(f"Near 24h high ({position*100:.0f}%) - pullback likely")
            elif position < 0.15:
                score += 1.5  # Oversold
                confidence += 10
                reasons.append(f"Near 24h low ({position*100:.0f}%) - bounce likely")
        
        # 4. Volume confirmation (weight: medium)
        if data['volume_24h'] > 1000000000:  # $1B+
            confidence += 15
            reasons.append("High volume confirms trend")
        
        return {
            'score': score,
            'confidence': min(confidence, 100),
            'direction': 'UP' if score > 0 else 'DOWN' if score < 0 else 'NEUTRAL',
            'strength': abs(score),
            'reasons': reasons
        }
    
    def should_trade(self, analysis, market_price):
        """Adaptive trade decision - no hardcoded edge"""
        # Must have strong confidence
        if analysis['confidence'] < 40:
            return False, "Low confidence"
        
        # Must have clear direction
        if analysis['direction'] == 'NEUTRAL':
            return False, "No clear direction"
        
        # Must have strong signal
        if analysis['strength'] < 2:
            return False, "Signal too weak"
        
        # Check if market price aligns with our direction
        # If we predict UP, YES should be reasonably priced (<0.7)
        # If we predict DOWN, NO should be reasonably priced (<0.7)
        if analysis['direction'] == 'UP' and market_price > 0.75:
            return False, "YES too expensive for UP bet"
        if analysis['direction'] == 'DOWN' and market_price > 0.75:
            return False, "NO too expensive for DOWN bet"
        
        return True, "Strong signal + good price"
    
    def scan_all_markets(self):
        """Scan 5m and 15m markets with adaptive logic"""
        coins = [
            ('btc', 'bitcoin', 'BTC'),
            ('eth', 'ethereum', 'ETH'),
            ('sol', 'solana', 'SOL'),
            ('xrp', 'ripple', 'XRP')
        ]
        
        opportunities = []
        current = int(time.time())
        
        for coin, coin_id, symbol in coins:
            # Get comprehensive data
            data = self.get_comprehensive_data(symbol, coin_id)
            
            if data['price'] == 0:
                continue
            
            # Analyze
            analysis = self.analyze_market(data)
            
            # Scan 5m
            slot_5m = (current // 300) * 300
            opp_5m = self.check_market(coin, '5m', slot_5m, analysis, data)
            if opp_5m:
                opportunities.append(opp_5m)
            
            # Scan 15m
            slot_15m = (current // 900) * 900
            opp_15m = self.check_market(coin, '15m', slot_15m, analysis, data)
            if opp_15m:
                opportunities.append(opp_15m)
        
        return opportunities
    
    def check_market(self, coin, timeframe, slot, analysis, data):
        """Check specific market"""
        slug = f'{coin}-updown-{timeframe}-{slot}'
        
        try:
            resp = requests.get(f'https://gamma-api.polymarket.com/markets/slug/{slug}', timeout=3)
            if resp.status_code != 200:
                return None
            
            market_data = resp.json()
            prices = json.loads(market_data.get('outcomePrices', '[]'))
            
            if len(prices) != 2:
                return None
            
            yes_price = float(prices[0])
            no_price = float(prices[1])
            
            # Determine which side to bet based on analysis
            if analysis['direction'] == 'UP':
                side = 'YES'
                market_price = yes_price
                potential_profit = (1 - yes_price) * 100
            elif analysis['direction'] == 'DOWN':
                side = 'NO'
                market_price = no_price
                potential_profit = (1 - no_price) * 100
            else:
                return None
            
            # Adaptive decision
            should_trade, reason = self.should_trade(analysis, market_price)
            
            if should_trade:
                return {
                    'coin': coin.upper(),
                    'timeframe': timeframe,
                    'side': side,
                    'price': market_price,
                    'potential_profit': potential_profit,
                    'analysis': analysis,
                    'data': data,
                    'reason': reason
                }
            
        except Exception as e:
            pass
        
        return None
    
    def execute_trade(self, opp):
        """Execute trade with full documentation"""
        amount = min(20.0, self.virtual_balance * 0.02)
        
        reasons = [
            f"{opp['coin']} at ${opp['data']['price']:,.2f}",
            f"24h: {opp['data']['change_24h']:+.2f}% | 1h: {opp['data']['change_1h']:+.2f}%",
            f"Signal: {opp['analysis']['direction']} (strength: {opp['analysis']['strength']:.1f})",
            f"Confidence: {opp['analysis']['confidence']:.0f}%"
        ]
        reasons.extend(opp['analysis']['reasons'])
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'trade_sim',
            'market': f"{opp['coin']} Up or Down - {opp['timeframe']}",
            'side': opp['side'],
            'amount': amount,
            'entry_price': opp['price'],
            'reason_points': reasons,
            'confidence': opp['analysis']['confidence'],
            'signal_strength': opp['analysis']['strength'],
            'direction': opp['analysis']['direction'],
            'virtual_balance_after': self.virtual_balance - amount,
            'real_balance_snapshot': 4.53,
            'notes': f"ADAPTIVE: {opp['timeframe']} | {opp['analysis']['direction']} | Conf: {opp['analysis']['confidence']:.0f}%"
        }
        
        log = self.load_log()
        log.append(trade)
        self.save_log(log)
        
        self.virtual_balance -= amount
        
        self.log(f"TRADE: {opp['coin']} {opp['timeframe']} {opp['side']} @ {opp['price']:.3f} | Conf: {opp['analysis']['confidence']:.0f}%")
        
        return trade
    
    def run(self):
        """Main loop"""
        self.log("ADAPTIVE TRADER STARTED")
        self.log("Multi-API | No hardcoded edge | Profit-first")
        self.log("APIs: CoinGecko + Binance + CryptoCompare")
        
        while True:
            try:
                opportunities = self.scan_all_markets()
                
                if opportunities:
                    # Pick best opportunity
                    best = max(opportunities, key=lambda x: x['analysis']['confidence'] * x['analysis']['strength'])
                    self.execute_trade(best)
                else:
                    self.log("No high-confidence opportunities")
                
                time.sleep(60)
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    trader = AdaptiveTrader()
    trader.run()
