#!/usr/bin/env python3
"""
WALLET 2 BOT - AGGRESSIVE MOMENTUM
Higher risk, higher frequency trading
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
virtual_free = 480.00
log_file = "/root/.openclaw/workspace/wallet2_trades.json"

# AGGRESSIVE THRESHOLDS - 2x average velocity
VELOCITY_THRESHOLDS = {
    'BTC': 0.08,   # ~$80 move
    'ETH': 0.010,  # ~$10 move
    'SOL': 0.003,  # ~$0.30 move
    'XRP': 0.0005  # ~$0.0005 move
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
    threshold = VELOCITY_THRESHOLDS.get(coin, 0.05)
    min_edge = 0.05  # Lower edge requirement
    
    edge = 0
    side = None
    
    # Trade on any significant momentum with decent price
    if velocity > threshold and yes_price < 0.70:
        edge = abs(velocity) * (0.75 - yes_price)
        side = 'YES'
    elif velocity < -threshold and no_price < 0.70:
        edge = abs(velocity) * (0.75 - no_price)
        side = 'NO'
    
    if edge >= min_edge:
        return {'type': 'EDGE', 'coin': coin, 'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
    return None

def check_arbitrage(yes_price, no_price):
    total = yes_price + no_price
    if total < 0.998:  # Even tighter for arb
        return {'profit': (1.0 - total) * 100}
    return None

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 5 if tf == 5 else 15  # More frequent
    
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
                    
    except:
        pass

def execute_trade(opp, tf):
    global trade_count, virtual_free
    
    amount = min(20.0, virtual_free * 0.042)  # Slightly larger bets
    if amount < 20:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W2 #{trade_count} ARB {opp['coin']} {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet2_trade',
            'strategy': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'virtual_balance': virtual_free - amount
        }
    else:
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W2 #{trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet2_trade',
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
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 2 AGGRESSIVE - CONNECTED!")

print("="*70)
print("WALLET 2 BOT - AGGRESSIVE MOMENTUM")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
