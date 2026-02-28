#!/usr/bin/env python3
"""
ULTIMATE BOT v3 - WITH REGIME DETECTION
Integrated: Exit Management + Regime Detection
"""

import websocket
import json
import time
import requests
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import defaultdict, deque
from scipy.stats import linregress

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

# Exit configuration
STOP_LOSS_PCT = 0.20
TAKE_PROFIT_PCT = 0.40
TRAILING_STOP_PCT = 0.15
TIME_STOP_MINUTES = 90
CHECK_INTERVAL = 15

# Regime detection
REGIME_WINDOW = 30
REGIME_THETA = 0.5

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
    """Microstructure-aware regime detection."""
    
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
        
        # Returns
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                r = np.log(prices[i] / prices[i-1])
                returns.append(r)
        
        if not returns:
            return self.last_regime
        
        # Volatility
        vol = np.std(returns) if len(returns) > 1 else 0
        self.vol_history.append(vol)
        
        vol_z = 0
        if len(self.vol_history) >= 30:
            vol_mean = np.mean(list(self.vol_history)[-100:])
            vol_std = np.std(list(self.vol_history)[-100:])
            if vol_std > 0:
                vol_z = (vol - vol_mean) / vol_std
        
        # Efficiency
        total_move = abs(prices[-1] - prices[0])
        path_length = sum(abs(prices[i] - prices[i-1]) for i in range(1, len(prices)))
        efficiency = total_move / path_length if path_length > 0 else 0
        
        # Trend
        x = np.arange(len(prices))
        try:
            slope, _, _, _, _ = linregress(x, prices)
            price_std = np.std(prices)
            trend_score = slope / price_std if price_std > 0 else 0
        except:
            trend_score = 0
        
        # Classify
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
    
    def get_params(self, regime: Regime) -> dict:
        params = {
            Regime.TREND_UP: {'side_bias': 'YES', 'velocity_mult': 0.8, 'size_mult': 1.3, 'timeframe': 5, 'max_price': 0.70},
            Regime.TREND_DOWN: {'side_bias': 'NO', 'velocity_mult': 0.8, 'size_mult': 1.3, 'timeframe': 5, 'max_price': 0.70},
            Regime.CHOPPY: {'side_bias': None, 'velocity_mult': 1.5, 'size_mult': 0.5, 'timeframe': 15, 'max_price': 0.40},
            Regime.HIGH_VOL: {'side_bias': None, 'velocity_mult': 0.9, 'size_mult': 0.6, 'timeframe': 5, 'max_price': 0.65},
            Regime.LOW_VOL: {'side_bias': None, 'velocity_mult': 0.7, 'size_mult': 1.2, 'timeframe': 15, 'max_price': 0.60},
        }
        return params.get(regime, params[Regime.CHOPPY])

# ============ POSITION & EXIT MANAGEMENT ============
@dataclass
class Position:
    market_id: str
    side: str
    entry_price: float
    shares: float
    entry_time: float = field(default_factory=time.time)
    stop_loss_pct: float = STOP_LOSS_PCT
    take_profit_pct: float = TAKE_PROFIT_PCT
    trailing_stop_pct: float = TRAILING_STOP_PCT
    time_stop_minutes: float = TIME_STOP_MINUTES
    peak_price: float = field(init=False)
    trailing_stop_price: float = field(init=False)
    
    def __post_init__(self):
        self.peak_price = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - self.trailing_stop_pct)

def check_stop_loss(position: Position, current_price: float) -> bool:
    stop_price = position.entry_price * (1 - position.stop_loss_pct)
    return current_price <= stop_price

def check_take_profit(position: Position, current_price: float) -> bool:
    target_price = position.entry_price * (1 + position.take_profit_pct)
    return current_price >= target_price

def check_trailing_stop(position: Position, current_price: float) -> bool:
    if current_price < position.entry_price * 1.10:
        return False
    if current_price > position.peak_price:
        position.peak_price = current_price
        position.trailing_stop_price = current_price * (1 - position.trailing_stop_pct)
    return current_price <= position.trailing_stop_price

def check_time_stop(position: Position) -> bool:
    elapsed = (time.time() - position.entry_time) / 60
    return elapsed >= position.time_stop_minutes

def evaluate_exits(position: Position, current_price: float) -> Optional[ExitReason]:
    if check_stop_loss(position, current_price):
        return ExitReason.STOP_LOSS
    if check_time_stop(position):
        return ExitReason.TIME_STOP
    if check_take_profit(position, current_price):
        return ExitReason.TAKE_PROFIT
    if check_trailing_stop(position, current_price):
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

# Regime detectors per coin
regime_detectors = {coin: RegimeDetector() for coin in COINS}
current_regimes = {coin: Regime.CHOPPY for coin in COINS}

log_file = "/root/.openclaw/workspace/wallet_ultimate_trades.json"
state_file = "/root/.openclaw/workspace/wallet_ultimate_state.json"

# ============ CORE FUNCTIONS ============
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
        return {'profit': (1.0 - total) * 100}
    return None

def calculate_edge(coin, yes_price, no_price, velocity, regime_params):
    threshold = VELOCITY_THRESHOLDS[coin]['raw'] * regime_params['velocity_mult']
    max_price = regime_params['max_price']
    side_bias = regime_params['side_bias']
    
    edge = 0
    side = None
    
    # Apply side bias if in trend regime
    if side_bias == 'YES' and velocity > threshold and yes_price < max_price:
        edge = velocity * (0.75 - yes_price)
        side = 'YES'
    elif side_bias == 'NO' and velocity < -threshold and no_price < max_price:
        edge = abs(velocity) * (0.75 - no_price)
        side = 'NO'
    elif side_bias is None:
        # No bias - trade both directions
        if velocity > threshold and yes_price < max_price:
            edge = velocity * (0.75 - yes_price)
            side = 'YES'
        elif velocity < -threshold and no_price < max_price:
            edge = abs(velocity) * (0.75 - no_price)
            side = 'NO'
    
    if edge >= MIN_EDGE:
        return {'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
    return None

def can_trade(market, side):
    total = sum(len(sides) for sides in open_positions.values())
    if total >= MAX_POSITIONS:
        return False
    if market in open_positions:
        if side in open_positions[market]:
            return False
        if len(open_positions[market]) >= MAX_POSITIONS_PER_MARKET:
            return False
    return True

def execute_exit(position, reason, current_price):
    global virtual_free
    
    pnl = (current_price - position.entry_price) / position.entry_price * 100
    pnl_amount = position.shares * (current_price - position.entry_price)
    
    print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {position.market_id} | {reason.value} | PnL: {pnl:+.1f}%")
    
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
    if now - last_exit_check < CHECK_INTERVAL:
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
            
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{slug}", timeout=2)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
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
                
        except:
            continue

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free, open_positions, active_positions, current_regimes
    
    if virtual_free < 20:
        return
    
    current_time = time.time()
    min_interval = 10 if tf == 5 else 20
    
    if current_time - last_trade_time < min_interval:
        return
    
    # Get regime params
    regime = current_regimes.get(coin, Regime.CHOPPY)
    regime_params = regime_detectors[coin].get_params(regime)
    
    # Skip if timeframe doesn't match regime preference
    if regime_params['timeframe'] != tf and regime in [Regime.TREND_UP, Regime.TREND_DOWN, Regime.LOW_VOL]:
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
                
                # Check arbitrage
                arb = check_arbitrage(yes_price, no_price)
                if arb:
                    execute_trade({'type': 'ARBITRAGE', 'coin': coin, 'profit': arb['profit']}, 
                                tf, market_key, slug, yes_price, no_price, regime_params)
                    last_trade_time = current_time
                    return
                
                # Check edge with regime params
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    edge_trade = calculate_edge(coin, yes_price, no_price, velocities_ema[coin], regime_params)
                    if edge_trade and can_trade(market_key, edge_trade['side']):
                        execute_trade({'type': 'EDGE', 'coin': coin, **edge_trade}, 
                                    tf, market_key, slug, yes_price, no_price, regime_params)
                        last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp, tf, market_key, slug, yes_price, no_price, regime_params):
    global trade_count, virtual_free, open_positions, active_positions
    
    edge = opp.get('edge', 0.1)
    base_size = POSITION_SIZE_PCT * regime_params['size_mult']
    size_multiplier = min(2.0, 1.0 + (edge * 2))
    amount = min(50.0, virtual_free * base_size * size_multiplier)
    
    if amount < 20:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    now = time.time()
    
    if opp.get('type') == 'ARBITRAGE':
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {opp['coin']} {tf_label} | +{opp['profit']:.2f}% | ${virtual_free:.2f}")
        log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'ARBITRAGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': 'BOTH',
            'amount': amount,
            'profit_pct': opp['profit'],
            'virtual_balance': virtual_free - amount
        })
        open_positions[market_key] = ['YES', 'NO']
        active_positions[market_key] = Position(market_key, 'BOTH', yes_price, amount / 2)
    else:
        side = opp['side']
        entry_price = opp['price']
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {opp['coin']} {tf_label} | {side} @ {entry_price:.3f} | Edge: {opp['edge']:.2f} | Regime: {current_regimes[opp['coin']].value} | ${virtual_free:.2f}")
        log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EDGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': side,
            'amount': amount,
            'entry_price': entry_price,
            'edge': opp['edge'],
            'regime': current_regimes[opp['coin']].value,
            'virtual_balance': virtual_free - amount
        })
        open_positions[market_key].append(side)
        active_positions[market_key] = Position(market_key, side, entry_price, amount)
    
    virtual_free -= amount
    save_state()

def on_message(ws, message):
    global prices, velocities_ema, current_regimes
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol in COINS and price:
            # Update regime detector
            if symbol in regime_detectors:
                regime_detectors[symbol].add_price(price)
                current_regimes[symbol] = regime_detectors[symbol].compute_regime()
            
            # EMA velocity
            if symbol in prices:
                velocity_raw = price - prices[symbol]
                ema_factor = VELOCITY_THRESHOLDS[symbol]['ema_factor']
                if symbol not in velocities_ema or velocities_ema[symbol] == 0:
                    velocities_ema[symbol] = velocity_raw
                else:
                    velocities_ema[symbol] = (ema_factor * velocity_raw) + ((1 - ema_factor) * velocities_ema[symbol])
            
            prices[symbol] = price
            
            # Check exits
            check_all_exits()
            
            # Evaluate markets
            for tf in TIMEFRAMES:
                evaluate_market(symbol, tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ULTIMATE BOT v3 - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Features: EMA + Arb + Exits + REGIME DETECTION")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regimes: TREND_UP/Down | CHOPPY | HIGH/LOW_VOL")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Coins: {', '.join(COINS)} | Max positions: {MAX_POSITIONS}")

print("="*70)
print("ULTIMATE BOT v3 - WITH REGIME DETECTION")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
