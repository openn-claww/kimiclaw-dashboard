#!/usr/bin/env python3
"""
ULTIMATE BOT v6 - WITH RISK MANAGEMENT
Integrated: Circuit Breaker + Correlation Limiter + Auto-Reconnection
"""

import websocket
import json
import time
import statistics
from datetime import datetime
from collections import defaultdict, deque

# Import risk management and volume filter
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from entry_validation import calculate_edge, REGIME_PARAMS
from risk_manager import RiskManager
from volume_filter import (
    make_volume_state, parse_binance_trade, 
    update_volume_ema, is_volume_confirmed
)

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 479.84  # Current balance
MAX_POSITIONS = 5
POSITION_SIZE_PCT = 0.05
MIN_EDGE = 0.10

# RECONNECTION SETTINGS
RECONNECT_DELAY = 5

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15, 'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
    'SOL': {'raw': 0.25, 'ema_factor': 0.3},
    'XRP': {'raw': 0.08, 'ema_factor': 0.3},
}

COINS = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES = [5, 15]

# Exit configuration
STOP_LOSS_PCT = 0.20
TAKE_PROFIT_PCT = 0.40
TIME_STOP_MINUTES = 90

# Regime detection
REGIME_WINDOW = 30
REGIME_THETA = 0.5

GAMMA_API = "https://gamma-api.polymarket.com"
STATE_FILE = "/root/.openclaw/workspace/wallet_ultimate_state.json"
LOG_FILE = "/root/.openclaw/workspace/wallet_ultimate_trades.json"

# ============ INITIALIZE RISK MANAGER ============
rm = RiskManager(starting_balance=VIRTUAL_BANKROLL)

# ============ STATE ============
prices = {}
velocities_ema = {}
volume_states = {}  # NEW: Volume filter states
trade_count = 0
last_trade_time = 0
virtual_free = VIRTUAL_BANKROLL
open_positions = defaultdict(list)
active_positions = {}
last_exit_check = 0
reconnect_count = 0

regime_detectors = {coin: deque(maxlen=REGIME_WINDOW*2) for coin in COINS}
current_regimes = {coin: 'choppy' for coin in COINS}

def get_volume_state(coin: str):
    """Get or create volume state for coin."""
    if coin not in volume_states:
        volume_states[coin] = make_volume_state(coin)
    return volume_states[coin]

def save_state():
    state = {
        'balance': virtual_free,
        'positions': dict(open_positions),
        'trade_count': trade_count,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def log_trade(trade):
    try:
        with open(LOG_FILE, 'r') as f:
            log = json.load(f)
    except:
        log = []
    log.append(trade)
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)

def detect_regime(coin):
    """Simple regime detection."""
    hist = regime_detectors[coin]
    if len(hist) < 10:
        return 'choppy'
    
    recent = list(hist)[-10:]
    returns = [(recent[i] - recent[i-1]) / recent[i-1] 
               for i in range(1, len(recent)) if recent[i-1] > 0]
    
    if not returns:
        return 'choppy'
    
    vol = statistics.stdev(returns) if len(returns) > 1 else 0
    trend = sum(returns)
    
    if vol > 0.005:
        return 'high_vol'
    if abs(trend) > 0.01:
        return 'trend_up' if trend > 0 else 'trend_down'
    return 'choppy'

def evaluate_exits(position, current_price):
    """Check if position should exit."""
    stop_price = position['entry_price'] * (1 - STOP_LOSS_PCT)
    if current_price <= stop_price:
        return 'stop_loss'
    
    if (time.time() - position['entry_time']) / 60 >= TIME_STOP_MINUTES:
        return 'time_stop'
    
    target_price = position['entry_price'] * (1 + TAKE_PROFIT_PCT)
    if current_price >= target_price:
        return 'take_profit'
    
    return None

def execute_exit(position, market_id, reason, current_price):
    """Execute position exit with risk manager."""
    global virtual_free
    
    pnl = (current_price - position['entry_price']) / position['entry_price'] * 100
    pnl_amount = position['shares'] * (current_price - position['entry_price'])
    
    print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {market_id} | {reason} | PnL: {pnl:+.1f}%")
    
    virtual_free += position['shares'] * current_price
    
    # Update risk manager
    won = pnl > 0
    rm.on_trade_closed(position_id=market_id, won=won, pnl=pnl_amount, coin=market_id.split('-')[0])
    
    log_trade({
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': 'EXIT',
        'market': market_id,
        'side': position['side'],
        'exit_price': current_price,
        'entry_price': position['entry_price'],
        'exit_reason': reason,
        'pnl_pct': pnl,
        'virtual_balance': virtual_free
    })
    
    if market_id in active_positions:
        del active_positions[market_id]
    if market_id in open_positions:
        del open_positions[market_id]
    
    save_state()

def check_all_exits():
    """Check all positions for exit conditions."""
    global last_exit_check
    
    now = time.time()
    if now - last_exit_check < 15:
        return
    last_exit_check = now
    
    for market_id, position in list(active_positions.items()):
        try:
            parts = market_id.split('-')
            coin = parts[0]
            tf = int(parts[1].replace('m', ''))
            
            slot = int(now // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            import requests
            resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            
            if data.get('resolved'):
                winner = data.get('winningOutcomeIndex')
                outcome = 'YES' if winner == 0 else 'NO'
                final_price = 1.0 if outcome == position['side'] else 0.0
                
                pnl = (final_price - position['entry_price']) / position['entry_price'] * 100
                print(f"💰 [{datetime.now().strftime('%H:%M:%S')}] SETTLED {market_id} | {outcome} wins | PnL: {pnl:+.1f}%")
                
                virtual_free += position['shares'] + (position['shares'] * pnl / 100)
                
                # Update risk manager
                won = outcome == position['side']
                pnl_amount = position['shares'] * (final_price - position['entry_price'])
                rm.on_trade_closed(position_id=market_id, won=won, pnl=pnl_amount, coin=coin)
                
                if market_id in active_positions:
                    del active_positions[market_id]
                if market_id in open_positions:
                    del open_positions[market_id]
                
                save_state()
                continue
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            if len(prices_pm) != 2:
                continue
            
            if position['side'] == 'YES':
                current_price = float(prices_pm[0])
            else:
                current_price = float(prices_pm[1])
            
            exit_reason = evaluate_exits(position, current_price)
            if exit_reason:
                execute_exit(position, market_id, exit_reason, current_price)
                
        except Exception as e:
            pass

def evaluate_market(coin, tf):
    """Evaluate trading opportunity with risk checks."""
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    our_regime = current_regimes.get(coin, 'choppy')
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        market_key = f"{coin}-{tf}m"
        
        import requests
        resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            
            if data.get('resolved'):
                return
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                # Check arbitrage
                if yes_price + no_price < 0.985:
                    amount = min(50.0, virtual_free * POSITION_SIZE_PCT)
                    if amount >= 20:
                        # Risk check
                        ok, reason = rm.pre_trade_check(coin=coin, side="ARB", size_usd=amount)
                        if not ok:
                            print(f"⛔ RISK BLOCK: {reason[:60]}")
                            return
                        
                        trade_count += 1
                        profit = (1.0 - (yes_price + no_price)) * 100
                        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {coin} {tf}m | +{profit:.2f}%")
                        
                        pos_id = rm.on_trade_opened(coin=coin, side="ARB", size_usd=amount, market_id=market_key)
                        
                        virtual_free -= amount
                        save_state()
                        last_trade_time = current_time
                    return
                
                # Use FIXED calculate_edge
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    signal = calculate_edge(
                        coin=coin,
                        yes_price=yes_price,
                        no_price=no_price,
                        velocity=velocities_ema[coin],
                        regime_params=REGIME_PARAMS.get(our_regime, REGIME_PARAMS['default']),
                        market=data
                    )
                    
                    if signal:
                        amount = min(50.0, virtual_free * POSITION_SIZE_PCT * signal.get('confidence', 1.0))
                        if amount < 20:
                            return
                        
                        # RISK MANAGER CHECK
                        ok, reason = rm.pre_trade_check(coin=coin, side=signal['side'], size_usd=amount)
                        if not ok:
                            print(f"⛔ RISK BLOCK: {reason[:60]}")
                            return
                        
                        trade_count += 1
                        side = signal['side']
                        entry_price = signal['yes_price']
                        
                        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {coin} {tf}m | {side} @ {entry_price:.3f}")
                        
                        # Register with risk manager
                        pos_id = rm.on_trade_opened(coin=coin, side=side, size_usd=amount, market_id=market_key)
                        
                        virtual_free -= amount
                        
                        active_positions[market_key] = {
                            'side': side,
                            'entry_price': entry_price,
                            'shares': amount,
                            'entry_time': time.time(),
                            'pos_id': pos_id
                        }
                        open_positions[market_key].append(side)
                        
                        log_trade({
                            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'type': 'EDGE',
                            'market': f"{coin.upper()} {tf}m",
                            'side': side,
                            'amount': amount,
                            'entry_price': entry_price,
                            'edge': signal['edge'],
                            'virtual_balance': virtual_free
                        })
                        
                        save_state()
                        last_trade_time = current_time
                    
    except Exception as e:
        pass

def evaluate_market_with_volume(coin, tf, current_volume):
    """Evaluate trading opportunity with volume confirmation."""
    global trade_count, last_trade_time, virtual_free
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    our_regime = current_regimes.get(coin, 'choppy')
    
    # Check volume confirmation
    vs = get_volume_state(coin)
    confirmed, debug = is_volume_confirmed(vs, current_volume)
    
    if not confirmed:
        if debug.get('block_reason'):
            print(f"[VOLUME BLOCKED] {coin} {tf}m | {debug['block_reason']}")
        return
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        market_key = f"{coin}-{tf}m"
        
        import requests
        resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            
            if data.get('resolved'):
                return
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                # Check arbitrage
                if yes_price + no_price < 0.985:
                    amount = min(50.0, virtual_free * POSITION_SIZE_PCT)
                    if amount >= 20:
                        # Risk check
                        ok, reason = rm.pre_trade_check(coin=coin, side="ARB", size_usd=amount)
                        if not ok:
                            print(f"⛔ RISK BLOCK: {reason[:60]}")
                            return
                        
                        trade_count += 1
                        profit = (1.0 - (yes_price + no_price)) * 100
                        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {coin} {tf}m | +{profit:.2f}% | VOL✓")
                        
                        pos_id = rm.on_trade_opened(coin=coin, side="ARB", size_usd=amount, market_id=market_key)
                        
                        virtual_free -= amount
                        save_state()
                        last_trade_time = current_time
                    return
                
                # Use FIXED calculate_edge with volume confirmation
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    signal = calculate_edge(
                        coin=coin,
                        yes_price=yes_price,
                        no_price=no_price,
                        velocity=velocities_ema[coin],
                        regime_params=REGIME_PARAMS.get(our_regime, REGIME_PARAMS['default']),
                        market=data
                    )
                    
                    if signal:
                        amount = min(50.0, virtual_free * POSITION_SIZE_PCT * signal.get('confidence', 1.0))
                        if amount < 20:
                            return
                        
                        # RISK MANAGER CHECK
                        ok, reason = rm.pre_trade_check(coin=coin, side=signal['side'], size_usd=amount)
                        if not ok:
                            print(f"⛔ RISK BLOCK: {reason[:60]}")
                            return
                        
                        trade_count += 1
                        side = signal['side']
                        entry_price = signal['yes_price']
                        volume_ratio = debug.get('volume_ratio', 0)
                        
                        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {coin} {tf}m | {side} @ {entry_price:.3f} | VOL {volume_ratio:.1f}x✓")
                        
                        # Register with risk manager
                        pos_id = rm.on_trade_opened(coin=coin, side=side, size_usd=amount, market_id=market_key)
                        
                        virtual_free -= amount
                        
                        active_positions[market_key] = {
                            'side': side,
                            'entry_price': entry_price,
                            'shares': amount,
                            'entry_time': time.time(),
                            'pos_id': pos_id
                        }
                        open_positions[market_key].append(side)
                        
                        log_trade({
                            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'type': 'EDGE',
                            'market': f"{coin.upper()} {tf}m",
                            'side': side,
                            'amount': amount,
                            'entry_price': entry_price,
                            'edge': signal['edge'],
                            'volume_ratio': volume_ratio,
                            'virtual_balance': virtual_free
                        })
                        
                        save_state()
                        last_trade_time = current_time
                    
    except Exception as e:
        pass

def on_message(ws, message):
    """Handle WebSocket message with volume filter."""
    global prices, velocities_ema, current_regimes
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        
        # Parse price AND volume
        price = float(data.get('p', 0))
        volume = float(data.get('q', 0))
        timestamp = data.get('T', 0) / 1000.0
        
        if symbol in COINS and price > 0:
            # Update volume EMA
            vs = get_volume_state(symbol)
            update_volume_ema(vs, volume, timestamp)
            
            if symbol in regime_detectors:
                regime_detectors[symbol].append(price)
                current_regimes[symbol] = detect_regime(symbol)
            
            if symbol in prices:
                velocity_raw = price - prices[symbol]
                ema_factor = VELOCITY_THRESHOLDS[symbol]['ema_factor']
                if symbol not in velocities_ema or velocities_ema[symbol] == 0:
                    velocities_ema[symbol] = velocity_raw
                else:
                    velocities_ema[symbol] = (ema_factor * velocity_raw) + \
                                           ((1 - ema_factor) * velocities_ema[symbol])
            
            prices[symbol] = price
            
            check_all_exits()
            
            for tf in TIMEFRAMES:
                evaluate_market_with_volume(symbol, tf, volume)
                
    except Exception as e:
        pass

def on_error(ws, error):
    print(f"⚠️  [{datetime.now().strftime('%H:%M:%S')}] WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    global reconnect_count
    reconnect_count += 1
    print(f"🔌 [{datetime.now().strftime('%H:%M:%S')}] Connection closed. Reconnecting in {RECONNECT_DELAY}s...")
    time.sleep(RECONNECT_DELAY)
    start_bot()

def on_open(ws):
    global reconnect_count
    if reconnect_count > 0:
        print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Reconnected! (attempt #{reconnect_count})")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ ULTIMATE BOT v6 - RISK MANAGEMENT - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Circuit Breaker: 3 losses / 5% drawdown")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Correlation Limit: Max 2 correlated coins")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Balance: ${VIRTUAL_BANKROLL:.2f}")
    
    # Print risk status
    rm.print_status()

def start_bot():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

print("="*70)
print("ULTIMATE BOT v6 - WITH RISK MANAGEMENT")
print("Circuit Breaker + Correlation Limiter + Auto-Reconnect")
print("="*70)

start_bot()
