#!/usr/bin/env python3
"""
WORKAROUND BOT - Uses direct market lookup for live crypto markets
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

# Known live crypto market slugs (these rotate, need to find current ones)
# We'll try to discover them via the events endpoint

def log_trade(trade):
    try:
        with open(log_file, 'r') as f:
            log = json.load(f)
    except:
        log = []
    log.append(trade)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

def get_live_crypto_markets():
    """Try to find live crypto up/down markets"""
    markets = []
    
    # Try the events endpoint which might have live markets
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=50",
            timeout=3
        )
        if resp.status_code == 200:
            events = resp.json()
            for e in events:
                title = e.get('title', '').lower()
                if 'live crypto' in title or 'bitcoin up' in title or 'crypto up' in title:
                    for m in e.get('markets', []):
                        markets.append({
                            'id': m.get('id'),
                            'slug': m.get('slug'),
                            'question': m.get('question'),
                            'prices': m.get('outcomePrices', '[]'),
                            'end_date': m.get('endDate')
                        })
    except Exception as e:
        pass
    
    # Also try direct slug patterns for common live markets
    timeframes = ['5m', '15m', '30m', '1h']
    coins = ['btc', 'eth', 'sol', 'xrp']
    
    for coin in coins:
        for tf in timeframes:
            try:
                # Try to get market by slug pattern
                slot = int(time.time() // (int(tf.replace('m', '').replace('h', '0')) * 60)) * (int(tf.replace('m', '').replace('h', '0')) * 60)
                slug = f"{coin}-updown-{tf}-{slot}"
                
                resp = requests.get(
                    f"https://gamma-api.polymarket.com/markets/slug/{slug}",
                    timeout=2
                )
                if resp.status_code == 200:
                    m = resp.json()
                    markets.append({
                        'id': m.get('id'),
                        'slug': m.get('slug'),
                        'question': m.get('question'),
                        'prices': m.get('outcomePrices', '[]'),
                        'end_date': m.get('endDate')
                    })
            except:
                pass
    
    return markets

def calculate_edge(coin, yes_price, no_price, velocity):
    min_edge = 0.15
    
    edge = 0
    side = None
    
    if velocity > 0.8 and yes_price < 0.7:
        edge = velocity * (0.75 - yes_price)
        side = 'YES'
    elif velocity < -0.8 and no_price < 0.7:
        edge = abs(velocity) * (0.75 - no_price)
        side = 'NO'
    
    if edge >= min_edge:
        return {'coin': coin, 'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
    return None

def check_arbitrage(yes_price, no_price):
    total = yes_price + no_price
    if total < 0.99:
        return {'profit': (1.0 - total) * 100}
    return None

def execute_trade(opp, strategy):
    global trade_count, virtual_free
    
    amount = min(25.0, virtual_free * 0.036)
    if amount < 15:
        return
    
    trade_count += 1
    
    print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] W1 #{trade_count} {strategy} | {opp.get('coin', 'UNKNOWN')} | {opp.get('side', 'BOTH')} | ${virtual_free:.2f}")
    
    trade = {
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'event_type': 'wallet1_trade',
        'strategy': strategy,
        'market': opp.get('coin', 'UNKNOWN'),
        'side': opp.get('side', 'BOTH'),
        'amount': amount,
        'virtual_balance': virtual_free - amount,
        'edge': opp.get('edge', 0),
        'profit': opp.get('profit', 0)
    }
    
    virtual_free -= amount
    log_trade(trade)

def evaluate_markets():
    global last_trade_time
    
    current_time = time.time()
    if current_time - last_trade_time < 30:
        return
    
    if virtual_free < 15:
        return
    
    markets = get_live_crypto_markets()
    
    if not markets:
        return
    
    for m in markets:
        try:
            prices_str = m.get('prices', '[]')
            if isinstance(prices_str, str):
                prices_list = json.loads(prices_str)
            else:
                prices_list = prices_str
            
            if len(prices_list) == 2:
                yes_price = float(prices_list[0])
                no_price = float(prices_list[1])
                
                # Check arbitrage
                arb = check_arbitrage(yes_price, no_price)
                if arb:
                    execute_trade({'coin': m['question'][:20], 'profit': arb['profit']}, 'ARBITRAGE')
                    last_trade_time = current_time
                    return
                
                # Check edge
                coin = None
                q = m['question'].lower()
                if 'btc' in q or 'bitcoin' in q:
                    coin = 'BTC'
                elif 'eth' in q or 'ethereum' in q:
                    coin = 'ETH'
                elif 'sol' in q or 'solana' in q:
                    coin = 'SOL'
                elif 'xrp' in q or 'ripple' in q:
                    coin = 'XRP'
                
                if coin and coin in velocities:
                    edge_opp = calculate_edge(coin, yes_price, no_price, velocities[coin])
                    if edge_opp:
                        execute_trade(edge_opp, 'EDGE')
                        last_trade_time = current_time
                        return
                        
        except Exception as e:
            pass

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
            
            evaluate_markets()
                
    except Exception as e:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WORKAROUND Bot: WebSocket CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning for live crypto markets...")
    
    # Initial market scan
    markets = get_live_crypto_markets()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(markets)} live crypto markets")
    for m in markets:
        print(f"  - {m['question'][:50]}...")

print("="*70)
print("WORKAROUND WALLET 1 BOT - Events API + Direct Slug Lookup")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
