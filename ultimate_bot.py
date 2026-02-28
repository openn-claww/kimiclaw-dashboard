#!/usr/bin/env python3
"""
ULTIMATE BOT - COMBINED STRATEGY
Takes the best from Wallet 1, 3, and 4
"""

import websocket
import json
import time
import requests
from datetime import datetime
from collections import defaultdict

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 686.93
MAX_POSITIONS = 5
MAX_POSITIONS_PER_MARKET = 1
POSITION_SIZE_PCT = 0.05
MIN_EDGE = 0.10

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15, 'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
}

COINS = ['BTC', 'ETH']
TIMEFRAMES = [5, 15]

# ============ STATE ============
prices = {}
velocities_ema = {}
trade_count = 0
last_trade_time = 0
virtual_free = VIRTUAL_BANKROLL
open_positions = defaultdict(list)

log_file = "/root/.openclaw/workspace/wallet_ultimate_trades.json"
state_file = "/root/.openclaw/workspace/wallet_ultimate_state.json"

def save_state():
    state = {
        'balance': virtual_free,
        'positions': dict(open_positions),
        'trade_count': trade_count,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

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
    total = yes_price + no_price
    if total < 0.985:
        profit = (1.0 - total) * 100
        return {'profit': profit}
    return None

def calculate_edge(coin, yes_price, no_price, velocity):
    threshold = VELOCITY_THRESHOLDS[coin]['raw']
    edge = 0
    side = None
    
    if velocity > threshold and yes_price < 0.60:
        edge = velocity * (0.75 - yes_price)
        side = 'YES'
    elif velocity < -threshold and no_price < 0.60:
        edge = abs(velocity) * (0.75 - no_price)
        side = 'NO'
    
    if edge >= MIN_EDGE:
        return {'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
    return None

def can_trade(market, side):
    total_positions = sum(len(sides) for sides in open_positions.values())
    if total_positions >= MAX_POSITIONS:
        return False
    if market in open_positions:
        if side in open_positions[market]:
            return False
        if len(open_positions[market]) >= MAX_POSITIONS_PER_MARKET:
            return False
    return True

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free, open_positions
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        market_key = f"{coin}-{tf}m"
        
        resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                arb = check_arbitrage(yes_price, no_price)
                if arb:
                    execute_trade({'type': 'ARBITRAGE', 'coin': coin, 'profit': arb['profit']}, tf, market_key, slug)
                    last_trade_time = current_time
                    return
                
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    edge_trade = calculate_edge(coin, yes_price, no_price, velocities_ema[coin])
                    if edge_trade and can_trade(market_key, edge_trade['side']):
                        execute_trade({'type': 'EDGE', 'coin': coin, **edge_trade}, tf, market_key, slug)
                        last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp, tf, market_key, slug):
    global trade_count, virtual_free, open_positions
    
    edge = opp.get('edge', 0.1)
    size_multiplier = min(2.0, 1.0 + (edge * 2))
    amount = min(50.0, virtual_free * POSITION_SIZE_PCT * size_multiplier)
    if amount < 20:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {opp['coin']} {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'profit_pct': opp['profit'],
            'virtual_balance': virtual_free - amount
        }
        open_positions[market_key] = ['YES', 'NO']
    else:
        side = opp['side']
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {opp['coin']} {tf_label} | {side} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EDGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': side,
            'amount': amount,
            'entry_price': opp['price'],
            'edge': opp['edge'],
            'virtual_balance': virtual_free - amount
        }
        open_positions[market_key].append(side)
    
    virtual_free -= amount
    log_trade(trade)
    save_state()

def on_message(ws, message):
    global prices, velocities_ema
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol in COINS and price:
            if symbol in prices:
                velocity_raw = price - prices[symbol]
                ema_factor = VELOCITY_THRESHOLDS[symbol]['ema_factor']
                if symbol not in velocities_ema or velocities_ema[symbol] == 0:
                    velocities_ema[symbol] = velocity_raw
                else:
                    velocities_ema[symbol] = (ema_factor * velocity_raw) + ((1 - ema_factor) * velocities_ema[symbol])
            
            prices[symbol] = price
            
            for tf in TIMEFRAMES:
                evaluate_market(symbol, tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ULTIMATE BOT - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Features: EMA smoothing + Arb detection + Position limits")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Coins: {', '.join(COINS)} | Max positions: {MAX_POSITIONS}")

print("="*70)
print("ULTIMATE BOT - COMBINED STRATEGY")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
