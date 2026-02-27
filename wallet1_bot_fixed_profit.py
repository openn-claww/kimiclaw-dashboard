#!/usr/bin/env python3
"""
WALLET 1 BOT - FIXED WITH PROPER P&L TRACKING
Tracks open positions and settles them when markets resolve
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

# Virtual wallet state
virtual_balance = 686.93
virtual_bankroll = 686.93
open_positions = []  # Track bets that haven't settled yet

# Files
log_file = "/root/.openclaw/workspace/wallet1_new_trades.json"
positions_file = "/root/.openclaw/workspace/wallet1_positions.json"
state_file = "/root/.openclaw/workspace/wallet1_state.json"

# Thresholds
VELOCITY_THRESHOLDS = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.005, 'XRP': 0.001}
timeframes = [5, 15]

def load_state():
    global virtual_balance, open_positions, trade_count
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
            virtual_balance = state.get('balance', 686.93)
            open_positions = state.get('positions', [])
            trade_count = state.get('trade_count', 0)
            print(f"[STATE] Loaded: Balance=${virtual_balance:.2f}, Open positions={len(open_positions)}, Trades={trade_count}")
    except:
        virtual_balance = 686.93
        open_positions = []
        trade_count = 0

def save_state():
    state = {
        'balance': virtual_balance,
        'positions': open_positions,
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

def check_settlements():
    """Check if any open positions have resolved and settle them"""
    global virtual_balance, open_positions
    
    settled = []
    for pos in open_positions:
        try:
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{pos['slug']}", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('resolved', False):
                    winner = data.get('winningOutcomeIndex')  # 0 = YES/UP, 1 = NO/DOWN
                    
                    # Determine if we won
                    our_side = 0 if pos['side'] == 'YES' else 1
                    won = (winner == our_side)
                    
                    if won:
                        # Win: get back stake + profit (assuming ~0.95 payout after fees)
                        payout = pos['amount'] * (1 / pos['entry_price']) * 0.95
                        profit = payout - pos['amount']
                        virtual_balance += payout
                        print(f"💰 [SETTLED] WON {pos['market']} {pos['side']} | Profit: +${profit:.2f} | Balance: ${virtual_balance:.2f}")
                    else:
                        # Loss: already deducted, just confirm
                        print(f"❌ [SETTLED] LOST {pos['market']} {pos['side']} | Loss: -${pos['amount']:.2f} | Balance: ${virtual_balance:.2f}")
                    
                    settled.append(pos)
        except:
            pass
    
    # Remove settled positions
    for s in settled:
        open_positions.remove(s)
    
    if settled:
        save_state()

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
        return {'type': 'EDGE', 'coin': coin, 'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
    return None

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_balance, open_positions
    
    if virtual_balance < 15:
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
                
                opportunity = None
                if coin in velocities:
                    opportunity = calculate_edge(coin, yes_price, no_price, velocities[coin])
                
                if opportunity:
                    execute_trade(opportunity, tf, slug)
                    last_trade_time = current_time
                    
    except Exception as e:
        pass

def execute_trade(opp, tf, slug):
    global trade_count, virtual_balance, open_positions
    
    amount = min(25.0, virtual_balance * 0.036)
    if amount < 15:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    
    print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] W1 #{trade_count} EDGE {opp['coin']} {tf_label} | {opp['side']} @ {opp['price']:.3f} | Edge: {opp['edge']:.2f} | Bet: ${amount:.2f} | Balance: ${virtual_balance:.2f}")
    
    # Record position
    position = {
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market': f"{opp['coin'].upper()} {tf_label}",
        'side': opp['side'],
        'amount': amount,
        'entry_price': opp['price'],
        'edge': opp['edge'],
        'slug': slug
    }
    open_positions.append(position)
    
    # Deduct from balance
    virtual_balance -= amount
    
    trade = {
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'event_type': 'wallet1_trade',
        'strategy': 'EDGE',
        'market': f"{opp['coin'].upper()} {tf_label}",
        'side': opp['side'],
        'amount': amount,
        'entry_price': opp['price'],
        'edge': opp['edge'],
        'virtual_balance': virtual_balance,
        'open_positions': len(open_positions)
    }
    
    log_trade(trade)
    save_state()

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
            
            # Check settlements every 30 messages
            if len(prices) % 30 == 0:
                check_settlements()
            
            for tf in timeframes:
                evaluate_market(symbol, tf)
                
    except Exception as e:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Wallet 1 FIXED - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Balance: ${virtual_balance:.2f} | Open positions: {len(open_positions)}")
    check_settlements()

# Load state on startup
load_state()

print("="*70)
print("WALLET 1 BOT - FIXED WITH P&L TRACKING")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
