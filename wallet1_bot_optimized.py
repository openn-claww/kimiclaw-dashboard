#!/usr/bin/env python3
"""
WALLET 1 BOT - OPTIMIZED VERSION
Conservative approach, lower thresholds for current market conditions
"""

import websocket
import json
import time
import requests
from datetime import datetime

prices = {}
last_prices = {}
velocities = {}
trade_count = 0
last_trade_time = 0
virtual_free = 686.93
log_file = "/root/.openclaw/workspace/wallet1_new_trades.json"

# OPTIMIZED THRESHOLDS based on market analysis
VELOCITY_THRESHOLDS = {
    'BTC': 0.15,   # ~$150 move on $67k BTC
    'ETH': 0.015,  # ~$15 move on $2k ETH
    'SOL': 0.005,  # ~$0.50 move on $87 SOL
    'XRP': 0.001   # ~$0.001 move on $1.41 XRP
}

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

def calculate_edge(coin, yes_price, no_price, velocity):
    threshold = VELOCITY_THRESHOLDS.get(coin, 0.1)
    min_edge = 0.08
    
    edge = 0
    side = None
    
    if velocity > threshold and yes_price < 0.65:
        edge = abs(velocity) * (0.75 - yes_price)
        side = 'YES'
    elif velocity < -threshold and no_price < 0.65:
        edge = abs(velocity) * (0.75 - no_price)
        side = 'NO'
    
    if edge >= min_edge:
        return {'type': 'EDGE', 'coin': coin, 'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge, 'velocity': velocity}
    return None

def check_arbitrage(yes_price, no_price):
    total = yes_price + no_price
    if total < 0.995:
        return {'profit': (1.0 - total) * 100}
    return None

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 15:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        
        resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                opportunity = check_arbitrage(yes_price, no_price)
                
                if not opportunity and coin in velocities:
                    opportunity = calculate_edge(coin, yes_price, no_price, velocities[coin])
                
                if opportunity:
                    execute_trade(opportunity, tf)
                    last_trade_time = current_time
                    
    except Exception as e:
        pass

def execute_trade(opp, tf):
    global trade_count, virtual_free
    
    amount = min(25.0, virtual_free * 0.036)
    if amount < 15:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W1 #{trade_count} ARBITRAGE {opp['coin']} {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet1_trade',
            'strategy': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'virtual_balance': virtual_free - amount
        }
    else:
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W1 #{trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet1_trade',
            'strategy': 'EDGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': opp['side'],
            'amount': amount,
            'entry_price': opp['price'],
            'edge': opp['edge'],
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
                
    except Exception as e:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1 OPTIMIZED - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Thresholds: BTC={VELOCITY_THRESHOLDS['BTC']}, ETH={VELOCITY_THRESHOLDS['ETH']}, SOL={VELOCITY_THRESHOLDS['SOL']}, XRP={VELOCITY_THRESHOLDS['XRP']}")

print("="*70)
print("WALLET 1 BOT - OPTIMIZED")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
