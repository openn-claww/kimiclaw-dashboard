#!/usr/bin/env python3
"""
ULTIMATE BOT v5 - FIXED VERSION
With entry validation to prevent 0.015 price bug
"""

import websocket
import json
import time
import threading
import sqlite3
import statistics
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import defaultdict, deque

# Import the fix
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from entry_validation import (
    calculate_edge, validate_trade, check_market_status,
    MIN_YES_PRICE, MAX_YES_PRICE, REGIME_PARAMS
)

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 453.08  # Current balance after losses
MAX_POSITIONS = 5
POSITION_SIZE_PCT = 0.05
MIN_EDGE = 0.10

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15, 'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
}

COINS = ['BTC', 'ETH']
TIMEFRAMES = [5, 15]

# Exit configuration
STOP_LOSS_PCT = 0.20
TAKE_PROFIT_PCT = 0.40
TRAILING_STOP_PCT = 0.15
TIME_STOP_MINUTES = 90

# Regime detection
REGIME_WINDOW = 30
REGIME_THETA = 0.5

GAMMA_API = "https://gamma-api.polymarket.com"
SETTLEMENT_DB = "/root/.openclaw/workspace/positions.db"
STATE_FILE = "/root/.openclaw/workspace/wallet_ultimate_state.json"
LOG_FILE = "/root/.openclaw/workspace/wallet_ultimate_trades.json"

# ============ ENUMS ============
class Regime(Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    CHOPPY = "choppy"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"

class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_STOP = "time_stop"

# ============ REGIME DETECTOR ============
class RegimeDetector:
    def __init__(self, window=REGIME_WINDOW):
        self.window = window
        self.price_history = deque(maxlen=window * 2)
        self.vol_history = deque(maxlen=200)
        self.last_regime = Regime.CHOPPY
        
    def add_price(self, price: float):
        self.price_history.append(price)
        
    def compute_regime(self) -> Regime:
        if len(self.price_history) < self.window:
            return self.last_regime
        
        prices = list(self.price_history)[-self.window:]
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] > 0]
        
        if not returns:
            return self.last_regime
        
        vol = statistics.stdev(returns) if len(returns) > 1 else 0
        self.vol_history.append(vol)
        
        vol_z = 0
        if len(self.vol_history) >= 30:
            vol_list = list(self.vol_history)[-100:]
            vol_mean = statistics.mean(vol_list)
            vol_std = statistics.stdev(vol_list) if len(vol_list) > 1 else 0
            if vol_std > 0:
                vol_z = (vol - vol_mean) / vol_std
        
        total_move = abs(prices[-1] - prices[0])
        path_length = sum(abs(prices[i] - prices[i-1]) for i in range(1, len(prices)))
        efficiency = total_move / path_length if path_length > 0 else 0
        
        n = len(prices)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(prices)
        numerator = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        
        price_std = statistics.stdev(prices) if len(prices) > 1 else 0
        trend_score = slope / price_std if price_std > 0 else 0
        
        regime = self._classify(vol_z, efficiency, trend_score)
        self.last_regime = regime
        return regime
    
    def _classify(self, vol_z: float, efficiency: float, trend_score: float) -> Regime:
        if vol_z > 1.5:
            return Regime.HIGH_VOL
        if vol_z < -1:
            return Regime.LOW_VOL
        if efficiency > 0.6:
            if trend_score > REGIME_THETA:
                return Regime.TREND_UP
            elif trend_score < -REGIME_THETA:
                return Regime.TREND_DOWN
        return Regime.CHOPPY

# ============ POSITION MANAGEMENT ============
@dataclass
class Position:
    market_id: str
    side: str
    entry_price: float
    shares: float
    entry_time: float = field(default_factory=time.time)
    peak_price: float = field(init=False)
    trailing_stop_price: float = field(init=False)
    
    def __post_init__(self):
        self.peak_price = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - TRAILING_STOP_PCT)

def evaluate_exits(position: Position, current_price: float) -> Optional[ExitReason]:
    stop_price = position.entry_price * (1 - STOP_LOSS_PCT)
    if current_price <= stop_price:
        return ExitReason.STOP_LOSS
    
    if (time.time() - position.entry_time) / 60 >= TIME_STOP_MINUTES:
        return ExitReason.TIME_STOP
    
    target_price = position.entry_price * (1 + TAKE_PROFIT_PCT)
    if current_price >= target_price:
        return ExitReason.TAKE_PROFIT
    
    if current_price >= position.entry_price * 1.10:
        if current_price > position.peak_price:
            position.peak_price = current_price
            position.trailing_stop_price = current_price * (1 - TRAILING_STOP_PCT)
        if current_price <= position.trailing_stop_price:
            return ExitReason.TRAILING_STOP
    
    return None

# ============ STATE ============
prices = {}
velocities_ema = {}
trade_count = 0
last_trade_time = 0
virtual_free = VIRTUAL_BANKROLL
open_positions = defaultdict(list)
active_positions = {}
last_exit_check = 0

regime_detectors = {coin: RegimeDetector() for coin in COINS}
current_regimes = {coin: Regime.CHOPPY for coin in COINS}

def save_state():
    state = {
        'balance': virtual_free,
        'positions': {k: list(v) for k, v in open_positions.items()},
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

def check_arbitrage(yes_price, no_price):
    total = yes_price + no_price
    if total < 0.985:
        return {'profit': (1.0 - total) * 100}
    return None

def can_trade(market, side):
    total = sum(len(sides) for sides in open_positions.values())
    if total >= MAX_POSITIONS:
        return False
    if market in open_positions:
        if side in open_positions[market]:
            return False
        if len(open_positions[market]) >= 1:
            return False
    return True

def execute_exit(position, reason, current_price):
    global virtual_free
    
    pnl = (current_price - position.entry_price) / position.entry_price * 100
    pnl_amount = position.shares * (current_price - position.entry_price)
    
    print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {position.market_id} | {reason.value} | PnL: {pnl:+.1f}% (${pnl_amount:+.2f})")
    
    virtual_free += position.shares * current_price
    
    log_trade({
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': 'EXIT',
        'market': position.market_id,
        'side': position.side,
        'exit_price': current_price,
        'entry_price': position.entry_price,
        'exit_reason': reason.value,
        'pnl_pct': pnl,
        'virtual_balance': virtual_free
    })
    
    if position.market_id in active_positions:
        del active_positions[position.market_id]
    if position.market_id in open_positions:
        del open_positions[position.market_id]
    
    save_state()

def check_all_exits():
    global last_exit_check
    
    now = time.time()
    if now - last_exit_check < 15:
        return
    last_exit_check = now
    
    if not active_positions:
        return
    
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
                final_price = 1.0 if outcome == position.side else 0.0
                
                pnl = (final_price - position.entry_price) / position.entry_price * 100
                print(f"💰 [{datetime.now().strftime('%H:%M:%S')}] SETTLED {market_id} | {outcome} wins | PnL: {pnl:+.1f}%")
                
                virtual_free += position.shares + (position.shares * pnl / 100)
                
                log_trade({
                    'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'type': 'SETTLEMENT',
                    'market': market_id,
                    'side': position.side,
                    'outcome': outcome,
                    'pnl': pnl,
                    'virtual_balance': virtual_free
                })
                
                if position.market_id in active_positions:
                    del active_positions[position.market_id]
                if position.market_id in open_positions:
                    del open_positions[position.market_id]
                
                save_state()
                continue
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            if len(prices_pm) != 2:
                continue
            
            if position.side == 'YES':
                current_price = float(prices_pm[0])
            else:
                current_price = float(prices_pm[1])
            
            exit_reason = evaluate_exits(position, current_price)
            if exit_reason:
                execute_exit(position, exit_reason, current_price)
                
        except Exception as e:
            pass

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free, open_positions, active_positions
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    # Map our regime to entry_validation regime
    regime_map = {
        Regime.TREND_UP: 'trending',
        Regime.TREND_DOWN: 'trending',
        Regime.CHOPPY: 'ranging',
        Regime.HIGH_VOL: 'volatile',
        Regime.LOW_VOL: 'default'
    }
    
    our_regime = current_regimes.get(coin, Regime.CHOPPY)
    val_regime = regime_map.get(our_regime, 'default')
    
    try:
        slot = int(current_time // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        market_key = f"{coin}-{tf}m"
        
        import requests
        resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Skip if resolved
            if data.get('resolved'):
                return
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                # Check arbitrage
                if yes_price + no_price < 0.985:
                    execute_trade_arb(coin, tf, yes_price, no_price, slug, data)
                    last_trade_time = current_time
                    return
                
                # Use FIXED calculate_edge with validation
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    signal = calculate_edge(
                        coin=coin,
                        yes_price=yes_price,
                        no_price=no_price,
                        velocity=velocities_ema[coin],
                        regime_params=REGIME_PARAMS[val_regime],
                        market=data  # Pass market for full validation
                    )
                    
                    if signal and can_trade(market_key, signal['side']):
                        execute_trade_edge(coin, tf, signal, slug, data)
                        last_trade_time = current_time
                    
    except Exception as e:
        pass

def execute_trade_arb(coin, tf, yes_price, no_price, slug, data):
    global trade_count, virtual_free
    
    profit = (1.0 - (yes_price + no_price)) * 100
    amount = min(50.0, virtual_free * POSITION_SIZE_PCT)
    
    if amount < 20:
        return
    
    trade_count += 1
    print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {coin} {tf}m | +{profit:.2f}% | Balance: ${virtual_free:.2f}")
    
    virtual_free -= amount
    
    log_trade({
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': 'ARBITRAGE',
        'market': f"{coin.upper()} {tf}m",
        'amount': amount,
        'virtual_balance': virtual_free
    })
    
    save_state()

def execute_trade_edge(coin, tf, signal, slug, data):
    global trade_count, virtual_free, open_positions, active_positions
    
    edge = signal['edge']
    amount = min(50.0, virtual_free * POSITION_SIZE_PCT * signal.get('confidence', 1.0))
    
    if amount < 20:
        return
    
    trade_count += 1
    side = signal['side']
    entry_price = signal['yes_price']
    
    print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {coin} {tf}m | {side} @ {entry_price:.3f} | Edge: {edge:.2f} | Balance: ${virtual_free:.2f}")
    
    virtual_free -= amount
    
    market_key = f"{coin}-{tf}m"
    open_positions[market_key].append(side)
    active_positions[market_key] = Position(market_key, side, entry_price, amount)
    
    log_trade({
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': 'EDGE',
        'market': f"{coin.upper()} {tf}m",
        'side': side,
        'amount': amount,
        'entry_price': entry_price,
        'edge': edge,
        'virtual_balance': virtual_free
    })
    
    save_state()

def on_message(ws, message):
    global prices, velocities_ema, current_regimes
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol in COINS and price:
            if symbol in regime_detectors:
                regime_detectors[symbol].add_price(price)
                current_regimes[symbol] = regime_detectors[symbol].compute_regime()
            
            if symbol in prices:
                velocity_raw = price - prices[symbol]
                ema_factor = VELOCITY_THRESHOLDS[symbol]['ema_factor']
                if symbol not in velocities_ema or velocities_ema[symbol] == 0:
                    velocities_ema[symbol] = velocity_raw
                else:
                    velocities_ema[symbol] = (ema_factor * velocity_raw) + ((1 - ema_factor) * velocities_ema[symbol])
            
            prices[symbol] = price
            
            check_all_exits()
            
            for tf in TIMEFRAMES:
                evaluate_market(symbol, tf)
                
    except Exception as e:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ ULTIMATE BOT v5 - FIXED - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Entry validation: MIN_PRICE={MIN_YES_PRICE}, MAX_PRICE={MAX_YES_PRICE}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Balance: ${VIRTUAL_BANKROLL:.2f}")

print("="*70)
print("ULTIMATE BOT v5 - FIXED WITH ENTRY VALIDATION")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
