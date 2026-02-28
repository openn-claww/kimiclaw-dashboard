#!/usr/bin/env python3
"""
ULTIMATE BOT v2 - WITH STOP LOSS / TAKE PROFIT
Integrated exit management from Claude 3.5
"""

import websocket
import json
import time
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
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

# Exit configuration
STOP_LOSS_PCT = 0.20      # Exit if down 20%
TAKE_PROFIT_PCT = 0.40    # Exit if up 40%
TRAILING_STOP_PCT = 0.15  # Trail by 15%
TIME_STOP_MINUTES = 90    # Exit after 90 minutes
CHECK_INTERVAL = 15       # Check exits every 15 seconds

# ============ EXIT MANAGEMENT ============
class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_STOP = "time_stop"

@dataclass
class Position:
    market_id: str
    side: str
    entry_price: float
    shares: float
    entry_time: float = field(default_factory=time.time)
    
    # Exit config
    stop_loss_pct: float = STOP_LOSS_PCT
    take_profit_pct: float = TAKE_PROFIT_PCT
    trailing_stop_pct: float = TRAILING_STOP_PCT
    time_stop_minutes: float = TIME_STOP_MINUTES
    
    # Runtime tracking
    peak_price: float = field(init=False)
    trailing_stop_price: float = field(init=False)
    
    def __post_init__(self):
        self.peak_price = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - self.trailing_stop_pct)

# ============ STATE ============
prices = {}
velocities_ema = {}
trade_count = 0
last_trade_time = 0
virtual_free = VIRTUAL_BANKROLL
open_positions = defaultdict(list)
active_positions: dict[str, Position] = {}  # For exit management
last_exit_check = 0

log_file = "/root/.openclaw/workspace/wallet_ultimate_trades.json"
state_file = "/root/.openclaw/workspace/wallet_ultimate_state.json"

# ============ EXIT CHECK FUNCTIONS ============
def check_stop_loss(position: Position, current_price: float) -> bool:
    """Exit if price drops X% below entry."""
    stop_price = position.entry_price * (1 - position.stop_loss_pct)
    triggered = current_price <= stop_price
    
    if triggered:
        loss_pct = (current_price - position.entry_price) / position.entry_price * 100
        print(f"  [STOP LOSS] {position.market_id} | Entry: {position.entry_price:.3f} | Current: {current_price:.3f} | Loss: {loss_pct:.1f}%")
    return triggered

def check_take_profit(position: Position, current_price: float) -> bool:
    """Exit if price rises Y% above entry."""
    target_price = position.entry_price * (1 + position.take_profit_pct)
    triggered = current_price >= target_price
    
    if triggered:
        gain_pct = (current_price - position.entry_price) / position.entry_price * 100
        print(f"  [TAKE PROFIT] {position.market_id} | Entry: {position.entry_price:.3f} | Current: {current_price:.3f} | Gain: {gain_pct:.1f}%")
    return triggered

def check_trailing_stop(position: Position, current_price: float) -> bool:
    """Ratchets stop price up as market moves in our favor."""
    # Only trail once we're in profit (10% buffer)
    if current_price < position.entry_price * 1.10:
        return False
    
    # Update peak and recalculate trailing stop
    if current_price > position.peak_price:
        position.peak_price = current_price
        position.trailing_stop_price = current_price * (1 - position.trailing_stop_pct)
    
    triggered = current_price <= position.trailing_stop_price
    
    if triggered:
        print(f"  [TRAILING STOP] {position.market_id} | Peak: {position.peak_price:.3f} | Stop: {position.trailing_stop_price:.3f} | Current: {current_price:.3f}")
    return triggered

def check_time_stop(position: Position) -> bool:
    """Exit if position held longer than Z minutes."""
    elapsed_minutes = (time.time() - position.entry_time) / 60
    triggered = elapsed_minutes >= position.time_stop_minutes
    
    if triggered:
        print(f"  [TIME STOP] {position.market_id} | Held: {elapsed_minutes:.1f} min | Limit: {position.time_stop_minutes} min")
    return triggered

def evaluate_exits(position: Position, current_price: float) -> Optional[ExitReason]:
    """Priority order: Stop loss and time stop first, then take profit, then trailing stop."""
    if check_stop_loss(position, current_price):
        return ExitReason.STOP_LOSS
    if check_time_stop(position):
        return ExitReason.TIME_STOP
    if check_take_profit(position, current_price):
        return ExitReason.TAKE_PROFIT
    if check_trailing_stop(position, current_price):
        return ExitReason.TRAILING_STOP
    return None

# ============ CORE FUNCTIONS ============
def save_state():
    state = {
        'balance': virtual_free,
        'positions': dict(open_positions),
        'active_positions': {k: {
            'market_id': v.market_id,
            'side': v.side,
            'entry_price': v.entry_price,
            'shares': v.shares,
            'entry_time': v.entry_time,
            'peak_price': v.peak_price
        } for k, v in active_positions.items()},
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

def execute_exit(position: Position, reason: ExitReason, current_price: float):
    """Execute an exit trade."""
    global virtual_free
    
    pnl = (current_price - position.entry_price) / position.entry_price * 100
    pnl_amount = position.shares * (current_price - position.entry_price)
    
    print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {position.market_id} | Reason: {reason.value} | PnL: {pnl:+.1f}% (${pnl_amount:+.2f})")
    
    # Return funds to virtual balance (simulated)
    virtual_free += position.shares * current_price
    
    trade = {
        'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': 'EXIT',
        'market': position.market_id,
        'side': position.side,
        'exit_price': current_price,
        'entry_price': position.entry_price,
        'shares': position.shares,
        'exit_reason': reason.value,
        'pnl_pct': pnl,
        'pnl_amount': pnl_amount,
        'virtual_balance': virtual_free
    }
    log_trade(trade)
    
    # Remove from tracking
    if position.market_id in active_positions:
        del active_positions[position.market_id]
    if position.market_id in open_positions:
        del open_positions[position.market_id]
    
    save_state()

def check_all_exits():
    """Check all active positions for exit conditions."""
    global last_exit_check
    
    now = time.time()
    if now - last_exit_check < CHECK_INTERVAL:
        return
    last_exit_check = now
    
    if not active_positions:
        return
    
    to_close = []
    
    for market_id, position in list(active_positions.items()):
        # Get current market price
        try:
            # Parse market_id (e.g., "BTC-5m")
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
            
            # Get current price based on position side
            if position.side == 'YES':
                current_price = float(prices_pm[0])
            else:
                current_price = float(prices_pm[1])
            
            exit_reason = evaluate_exits(position, current_price)
            if exit_reason:
                to_close.append((position, exit_reason, current_price))
                
        except Exception as e:
            continue
    
    # Execute closes
    for position, reason, price in to_close:
        execute_exit(position, reason, price)

def evaluate_market(coin, tf):
    global trade_count, last_trade_time, virtual_free, open_positions, active_positions
    
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
                    execute_trade({'type': 'ARBITRAGE', 'coin': coin, 'profit': arb['profit']}, tf, market_key, slug, yes_price, no_price)
                    last_trade_time = current_time
                    return
                
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    edge_trade = calculate_edge(coin, yes_price, no_price, velocities_ema[coin])
                    if edge_trade and can_trade(market_key, edge_trade['side']):
                        execute_trade({'type': 'EDGE', 'coin': coin, **edge_trade}, tf, market_key, slug, yes_price, no_price)
                        last_trade_time = current_time
                    
    except:
        pass

def execute_trade(opp, tf, market_key, slug, yes_price, no_price):
    global trade_count, virtual_free, open_positions, active_positions
    
    edge = opp.get('edge', 0.1)
    size_multiplier = min(2.0, 1.0 + (edge * 2))
    amount = min(50.0, virtual_free * POSITION_SIZE_PCT * size_multiplier)
    if amount < 20:
        return
    
    trade_count += 1
    tf_label = f"{tf}m"
    now = time.time()
    
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
        
        # Track both sides for arb
        active_positions[market_key] = Position(
            market_id=market_key,
            side='BOTH',
            entry_price=yes_price,
            shares=amount / 2
        )
    else:
        side = opp['side']
        entry_price = opp['price']
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {opp['coin']} {tf_label} | {side} @ {entry_price:.3f} | Edge: {opp['edge']:.2f} | ${virtual_free:.2f}")
        trade = {
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EDGE',
            'market': f"{opp['coin'].upper()} {tf_label}",
            'side': side,
            'amount': amount,
            'entry_price': entry_price,
            'edge': opp['edge'],
            'virtual_balance': virtual_free - amount
        }
        open_positions[market_key].append(side)
        
        # Track position for exit management
        active_positions[market_key] = Position(
            market_id=market_key,
            side=side,
            entry_price=entry_price,
            shares=amount
        )
    
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
            
            # Check exits on every message (prices updated)
            check_all_exits()
            
            for tf in TIMEFRAMES:
                evaluate_market(symbol, tf)
                
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ULTIMATE BOT v2 - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Features: EMA + Arb + Position Limits + EXIT MANAGEMENT")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Exit Config: SL {STOP_LOSS_PCT*100:.0f}% | TP {TAKE_PROFIT_PCT*100:.0f}% | Trail {TRAILING_STOP_PCT*100:.0f}% | Time {TIME_STOP_MINUTES}min")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Coins: {', '.join(COINS)} | Max positions: {MAX_POSITIONS}")

print("="*70)
print("ULTIMATE BOT v2 - WITH EXIT MANAGEMENT")
print("="*70)

ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade",
    on_open=on_open,
    on_message=on_message
)
ws.run_forever()
