#!/usr/bin/env python3
"""
WALLET 4 BOT - ARBITRAGE HUNTER
Focus on arbitrage opportunities only
"""

import websocket
import json
import time
import requests
from datetime import datetime

prices = {}
velocities = {}
trade_count = 0
last_trade_time = 0
virtual_free = 400.00
log_file = "/root/.openclaw/workspace/wallet4_trades.json"

timeframes = [5, 15]
coins = ['BTC', 'ETH', 'SOL', 'XRP']

def log_trade(trade):
    try:
        with open(log_file, 'r') as f:
            log = json.load(f)
    except:
        log = []
    log.append(trade)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

def check_arbitrage(yes_price, no_price):
    """Arbitrage when sum of prices < 1.0 (risk-free profit)"""
    total = yes_price + no_price
    if total < 0.99:
        profit = (1.0 - total) * 100
        # Only trade if profit > 0.5%
        if profit > 0.5:
            return {'profit': profit}
    return None

def check_momentum_arbitrage(coin, yes_price, no_price, velocity):
    """Trade when price is mispriced due to momentum"""
    threshold = 0.10  # 10% momentum
    
    # If strong up momentum but YES is cheap
    if velocity > threshold and yes_price < 0.45:
        edge = (0.50 - yes_price) * 2  # Expected reversion to 0.50
        if edge > 0.10:
            return {'side': 'YES', 'price': yes_price, 'edge': edge, 'type': 'MOMENTUM'}
    
    # If strong down momentum but NO is cheap
    if velocity < -threshold and no_price < 0.45:
        edge = (0.50 - no_price) * 2
        if edge > 0.10:
            return {'side': 'NO', 'price': no_price, 'edge': edge, 'type': 'MOMENTUM'}
    
    return None

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 5  # Very frequent checks for arb
    
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
                
                # Check pure arbitrage first
                opportunity = check_arbitrage(yes_price, no_price)
                if opportunity:
                    execute_trade({'type': 'ARBITRAGE', 'coin': coin, **opportunity}, tf)
                    last_trade_time = current_time
                    return
                
                # Check momentum arbitrage
                if coin in velocities:
                    opportunity = check_momentum_arbitrage(coin, yes_price, no_price, velocities[coin])
                    if opportunity:
                        execute_trade({'coin': coin, **opportunity}, tf)
                        last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp, tf):
    global trade_count, virtual_free
    
    amount = min(25.0, virtual_free * 0.0625)  # 6.25% of bankroll
    if amount < 20:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W4 #{trade_count} ARB {opp['coin']} {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet4_trade',
            'strategy': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'profit_pct': opp['profit'],
            'virtual_balance': virtual_free - amount
        }
    else:
        print(f"⚡ [{datetime.now().strftime('%H:%M:%S')}] W4 #{trade_count} MOM {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': 'wallet4_trade',
            'strategy': 'MOMENTUM_ARB',
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
    global prices, velocities
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol and price:
            if symbol in prices:
                velocities[symbol] = price - prices[symbol]
            
            prices[symbol] = price
            
            # Check all markets on each price update
            for coin in coins:
                for tf in timeframes:
                    evaluate_market(coin, tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 4 ARBITRAGE HUNTER - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning for arb opportunities every 5 seconds...")

print("="*70)
print("WALLET 4 BOT - ARBITRAGE HUNTER")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
