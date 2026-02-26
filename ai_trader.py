#!/usr/bin/env python3
"""
AI NEWS TRADER - Real OpenAI Integration
Uses GPT-4 for probability analysis
"""

import os
import time
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class AINewsTrader:
    def __init__(self):
        self.running = True
        self.virtual_balance = 500.0
        self.virtual_free = 500.0
        self.log_file = "/root/.openclaw/workspace/ai_news_trades.json"
        self.last_trade_time = 0
        self.trade_count = 0
        
        # Initialize OpenAI
        try:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            print("✅ OpenAI API connected")
        except Exception as e:
            print(f"❌ OpenAI Error: {e}")
            self.client = None
        
    def log_trade(self, trade):
        try:
            with open(self.log_file, 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open(self.log_file, 'w') as f:
            json.dump(log, f, indent=2)
    
    def get_crypto_price(self):
        try:
            resp = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=2)
            return float(resp.json()['price'])
        except:
            return None
    
    def analyze_with_openai(self, price_change, current_price, market_price):
        """Real OpenAI analysis"""
        if not self.client:
            # Fallback if no OpenAI
            return self.fallback_analysis(price_change, market_price)
        
        try:
            prompt = f"""You are a crypto trading expert analyzing Bitcoin price movements for Polymarket prediction markets.

Current data:
- BTC price change: {price_change:+.2f}%
- Current BTC price: ${current_price:,.2f}
- Polymarket YES price: ${market_price:.3f}

This is a 5-minute prediction market: "Will Bitcoin be UP or DOWN in 5 minutes?"

Based on the momentum and current market price, what is the true probability of Bitcoin being UP in 5 minutes?

Return ONLY a JSON object:
{{
    "probability": 0.XX,
    "confidence": "high/medium/low",
    "reason": "one sentence explanation"
}}"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            
            result = json.loads(response.choices[0].message.content)
            ai_prob = result.get('probability', market_price)
            
            edge = abs(ai_prob - market_price)
            
            return {
                'ai_probability': ai_prob,
                'market_price': market_price,
                'edge': edge,
                'confidence': result.get('confidence', 'medium'),
                'reason': result.get('reason', ''),
                'recommendation': 'BUY_YES' if ai_prob > market_price + 0.08 else 'BUY_NO' if ai_prob < market_price - 0.08 else 'NO_TRADE'
            }
        except Exception as e:
            print(f"OpenAI error: {e}")
            return self.fallback_analysis(price_change, market_price)
    
    def fallback_analysis(self, price_change, market_price):
        """Simple analysis if OpenAI fails"""
        if price_change > 0.3:
            ai_prob = min(market_price + 0.15, 0.75)
        elif price_change < -0.3:
            ai_prob = max(market_price - 0.15, 0.25)
        else:
            ai_prob = market_price
        
        edge = abs(ai_prob - market_price)
        
        return {
            'ai_probability': ai_prob,
            'market_price': market_price,
            'edge': edge,
            'confidence': 'medium',
            'reason': f"Price moved {price_change:+.2f}%",
            'recommendation': 'BUY_YES' if ai_prob > market_price + 0.08 else 'BUY_NO' if ai_prob < market_price - 0.08 else 'NO_TRADE'
        }
    
    def check_polymarket(self, coin, tf):
        try:
            current_time = time.time()
            slot = int(current_time // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=1)
            
            if resp.status_code == 200:
                data = resp.json()
                prices = json.loads(data.get('outcomePrices', '[]'))
                if len(prices) == 2:
                    return float(prices[0])
        except:
            pass
        return None
    
    def execute_trade(self, coin, tf, side, amount, analysis):
        global trade_count
        
        current_time = time.time()
        if current_time - self.last_trade_time < 20:
            return
        
        if self.virtual_free < amount:
            return
        
        self.trade_count += 1
        self.virtual_free -= amount
        self.last_trade_time = current_time
        
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] AI TRADE #{self.trade_count}")
        print(f"   {coin.upper()} {tf}m | {side} | ${amount}")
        print(f"   AI: {analysis['ai_probability']:.2f} | Market: {analysis['market_price']:.2f} | Edge: {analysis['edge']:.2f}")
        print(f"   Confidence: {analysis['confidence']} | {analysis['reason']}")
        
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'ai_trade',
            'strategy': 'AI_ANALYSIS',
            'market': f"{coin.upper()} {tf}m",
            'side': side,
            'amount': amount,
            'ai_probability': analysis['ai_probability'],
            'market_price': analysis['market_price'],
            'edge': analysis['edge'],
            'confidence': analysis['confidence'],
            'reason': analysis['reason'],
            'virtual_balance': self.virtual_free
        }
        
        self.log_trade(trade)
    
    def run(self):
        print("="*70)
        print("🤖 AI TRADER - Real OpenAI Integration")
        print("="*70)
        print("Bankroll: $500.00")
        print("Strategy: GPT-4 analysis → Trade when edge > 8%")
        print("="*70)
        print()
        
        last_price = None
        
        while self.running:
            price = self.get_crypto_price()
            
            if price and last_price:
                change_pct = ((price - last_price) / last_price) * 100
                
                # If price moved more than 0.2%, analyze with AI
                if abs(change_pct) > 0.2:
                    print(f"\n📊 BTC moved {change_pct:+.2f}% to ${price:,.2f}")
                    
                    for tf in [5, 15]:
                        market_price = self.check_polymarket('btc', tf)
                        
                        if market_price:
                            analysis = self.analyze_with_openai(change_pct, price, market_price)
                            
                            print(f"   {tf}m Market: AI={analysis['ai_probability']:.2f}, Market={analysis['market_price']:.2f}, Edge={analysis['edge']:.2f}")
                            
                            if analysis['edge'] > 0.08 and analysis['recommendation'] != 'NO_TRADE':
                                side = 'YES' if analysis['recommendation'] == 'BUY_YES' else 'NO'
                                self.execute_trade('btc', tf, side, 20.0, analysis)
                            elif analysis['edge'] <= 0.08:
                                print(f"   ⚠️ Edge too small ({analysis['edge']:.2f}), no trade")
                
                last_price = price
            elif price:
                last_price = price
            
            time.sleep(3)

if __name__ == "__main__":
    bot = AINewsTrader()
    bot.run()
