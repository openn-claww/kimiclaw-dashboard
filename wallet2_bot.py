#!/usr/bin/env python3
"""
WALLET 2 BOT - Simplified Working Version
Lower thresholds, every second scanning
"""

import websocket
import json
import time
import requests
from datetime import datetime

# Global variables
prices = {}
last_prices = {}
velocities = {}
trade_count = 0
last_trade_time = 0
virtual_free = 500.0
log_file = "/root/.openclaw/workspace/wallet2_trades.json"
timeframes = [5, 15, 30, 60, 240, 1440]

def log_trade(trade):
    try:
        with open(log_file, 'r') as f:
            log = json.load(f)
    except:
        log = []
    log.append(trade)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

def check_arbitrage(coin, yes_price, no_price, tf):
    total = yes_price + no_price
    if total < 0.99:
        return {'type': 'ARBITRAGE', 'coin': coin, 'tf': tf, 'profit': (1.0 - total) * 100}
    return None

def check_momentum(coin, tf):
    if coin not in velocities:
        return None
    
    velocity = velocities[coin]
    
    # LOWERED THRESHOLDS
    if tf == 5:
        threshold = 0.15  # 0.15% move
    elif tf == 15:
        threshold = 0.25  # 0.25% move
    else:
        threshold = 0.5   # 0.5% move
    
    if abs(velocity) > threshold:
        return {'type': 'MOMENTUM', 'coin': coin, 'tf': tf, 'side': 'YES' if velocity > 0 else 'NO', 'strength': abs(velocity)}
    return None

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 10:
        return
    
    current_time = time.time()
    min_interval = 10 if tf in [5, 15] else 30
    
    if current_time - last_trade_time < min_interval:
        return
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        
        resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=1)
        
        if resp.status_code == 200:
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                opportunity = None
                opportunity = check_arbitrage(coin, yes_price, no_price, tf)
                
                if not opportunity:
                    momentum = check_momentum(coin, tf)
                    if momentum:
                        if tf in [5, 15] or momentum['strength'] > 3.0:
                            opportunity = {
                                'type': 'MOMENTUM',
                                'coin': coin,
                                'tf': tf,
                                'side': momentum['side'],
                                'price': yes_price if momentum['side'] == 'YES' else no_price
                            }
                
                if opportunity:
                    execute_trade(opportunity)
                    last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp):
    global trade_count, virtual_free
    
    amount = min(20.0, virtual_free * 0.04)
    if amount < 10:
        return
    
    trade_count += 1
    tf_label = f"{opp['tf']}m"
    
    if opp['type'] == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W2 #{trade_count} ARBITRAGE {opp['coin']} {tf_label} | +{opp['profit']:.1f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet2_trade',
            'strategy': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'virtual_balance': virtual_free - amount
        }
        virtual_free -= amount
    else:
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W2 #{trade_count} MOMENTUM {opp['coin']} {tf_label} | {opp['side']} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet2_trade',
            'strategy': 'MOMENTUM',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': opp['side'],
            'amount': amount,
            'virtual_balance': virtual_free - amount
        }
        virtual_free -= amount
    
    log_trade(trade)

def on_message(ws, message):
    global prices, last_prices, velocities
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol and price:
            if symbol in prices:
                velocities[symbol] = price - prices[symbol]
            
            last_prices[symbol] = prices.get(symbol, price)
            prices[symbol] = price
            
            for tf in timeframes:
                evaluate_market(symbol, tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2: WebSocket CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Thresholds: 5m=0.15% | 15m=0.25% | Extended=0.5%")

print("="*70)
print("WALLET 2 BOT - LOWER THRESHOLDS")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
