#!/usr/bin/env python3
"""
WALLET 3 BOT - BTC ONLY SPECIALIST
Focus only on Bitcoin, highest conviction trades
"""

import websocket
import json
import time
import requests
from datetime import datetime

prices = {}
last_prices = {}
velocity = 0
smoothed_velocity = 0
trade_count = 0
last_trade_time = 0
virtual_free = 500.00
log_file = "/root/.openclaw/workspace/wallet3_trades.json"

# BTC ONLY - Very tight thresholds
VELOCITY_THRESHOLD = 0.20  # $200 move
VELOCITY_SMOOTHING = 0.3   # EMA smoothing factor

timeframes = [5, 15]

def log_trade(trade):
    try:
        with open(log_file, 'r') as f:
            log = json.load(f)
    except:
        log = []
    log.append(trade)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

def calculate_edge(yes_price, no_price, vel):
    min_edge = 0.10
    
    edge = 0
    side = None
    
    # Use smoothed velocity for more reliable signals
    if vel > VELOCITY_THRESHOLD and yes_price < 0.60:
        edge = vel * (0.75 - yes_price)
        side = 'YES'
    elif vel < -VELOCITY_THRESHOLD and no_price < 0.60:
        edge = abs(vel) * (0.75 - no_price)
        side = 'NO'
    
    if edge >= min_edge:
        return {'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge, 'velocity': vel}
    return None

def check_arbitrage(yes_price, no_price):
    total = yes_price + no_price
    if total < 0.99:
        return {'profit': (1.0 - total) * 100}
    return None

def evaluate_market(tf):
    global trade_count, last_trade_time, virtual_free, smoothed_velocity
    
    if virtual_free < 25:
        return
    
    current_time = time.time()
    min_interval = 15 if tf == 5 else 30
    
    if current_time - last_trade_time < min_interval:
        return
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"btc-updown-{tf}m-{slot}"
        
        resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                opportunity = check_arbitrage(yes_price, no_price)
                
                if not opportunity:
                    opportunity = calculate_edge(yes_price, no_price, smoothed_velocity)
                
                if opportunity:
                    execute_trade(opportunity, tf)
                    last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp, tf):
    global trade_count, virtual_free
    
    amount = min(30.0, virtual_free * 0.06)  # Larger BTC bets
    if amount < 25:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W3 #{trade_count} ARB BTC {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet3_trade',
            'strategy': 'ARBITRAGE',
            'market': f"BTC {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'virtual_balance': virtual_free - amount
        }
    else:
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W3 #{trade_count} EDGE BTC {tf_label} | {opp['side']} @ {opp['price']:.3f} | Vel: {opp['velocity']:.2f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet3_trade',
            'strategy': 'EDGE',
            'market': f"BTC {tf_label}",
            'side': opp['side'],
            'amount': amount,
            'entry_price': opp['price'],
            'edge': opp['edge'],
            'virtual_balance': virtual_free - amount
        }
    
    virtual_free -= amount
    log_trade(trade)

def on_message(ws, message):
    global prices, last_prices, velocity, smoothed_velocity
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        # Only process BTC
        if symbol == 'BTC' and price:
            if symbol in prices:
                velocity = price - prices[symbol]
                # EMA smoothing
                if smoothed_velocity == 0:
                    smoothed_velocity = velocity
                else:
                    smoothed_velocity = (VELOCITY_SMOOTHING * velocity) + ((1 - VELOCITY_SMOOTHING) * smoothed_velocity)
            
            last_prices[symbol] = prices.get(symbol, price)
            prices[symbol] = price
            
            for tf in timeframes:
                evaluate_market(tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 3 BTC SPECIALIST - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Threshold: {VELOCITY_THRESHOLD} | Smoothed velocity enabled")

print("="*70)
print("WALLET 3 BOT - BTC SPECIALIST")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
