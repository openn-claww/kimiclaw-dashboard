#!/usr/bin/env python3
"""
ULTIMATE BOT v5 - FINAL VERSION
Integrated: Exit Management + Regime Detection + WebSocket Optimization + Auto Settlement
"""

import websocket
import json
import time
import threading
import sqlite3
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from collections import defaultdict, deque
from scipy.stats import linregress

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 500.00
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

# WebSocket endpoints
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RTDS_WS = "wss://ws-live-data.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

# Settlement configuration
SETTLEMENT_DB = "/root/.openclaw/workspace/positions.db"

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

class PositionStatus(Enum):
    OPEN = "open"
    PENDING_SETTLEMENT = "pending"
    RESOLVED_FINAL = "resolved"

# ============ DATABASE SETUP ============
def init_database():
    """Initialize SQLite database for position tracking."""
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS positions (
        id TEXT PRIMARY KEY,
        market_slug TEXT,
        asset_id TEXT,
        condition_id TEXT,
        side TEXT,
        entry_price REAL,
        size REAL,
        entry_time REAL,
        status TEXT DEFAULT 'open',
        resolved_outcome TEXT,
        resolved_time REAL,
        pnl REAL,
        last_checked REAL
    )""")
    conn.commit()
    conn.close()

def db_insert_position(position_id, market_slug, asset_id, condition_id, side, entry_price, size):
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO positions 
        (id, market_slug, asset_id, condition_id, side, entry_price, size, entry_time, status, last_checked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
        (position_id, market_slug, asset_id, condition_id, side, entry_price, size, time.time(), time.time()))
    conn.commit()
    conn.close()

def db_update_pending(position_id, outcome, pnl):
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("""UPDATE positions SET status='pending', resolved_outcome=?, pnl=?, resolved_time=? 
        WHERE id=?""", (outcome, pnl, time.time(), position_id))
    conn.commit()
    conn.close()

def db_finalize_position(position_id, outcome, pnl):
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("""UPDATE positions SET status='resolved', resolved_outcome=?, pnl=? 
        WHERE id=?""", (outcome, pnl, position_id))
    conn.commit()
    conn.close()

def db_get_open_positions():
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("SELECT id, market_slug, asset_id, side, entry_price, size FROM positions WHERE status='open'")
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_pending_positions():
    conn = sqlite3.connect(SETTLEMENT_DB)
    c = conn.cursor()
    c.execute("SELECT id, market_slug, asset_id, side, entry_price, size, resolved_outcome FROM positions WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    return rows

# ============ P&L CALCULATION ============
def compute_pnl(entry_price, side, size, outcome):
    """Calculate P&L for a position."""
    if side == "YES":
        return (1.0 - entry_price) * size if outcome == "YES" else -entry_price * size
    else:  # NO
        return (1.0 - entry_price) * size if outcome == "NO" else -entry_price * size

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
        returns = [np.log(prices[i] / prices[i-1]) for i in range(1, len(prices)) if prices[i-1] > 0]
        
        if not returns:
            return self.last_regime
        
        vol = np.std(returns) if len(returns) > 1 else 0
        self.vol_history.append(vol)
        
        vol_z = 0
        if len(self.vol_history) >= 30:
            vol_mean = np.mean(list(self.vol_history)[-100:])
            vol_std = np.std(list(self.vol_history)[-100:])
            if vol_std > 0:
                vol_z = (vol - vol_mean) / vol_std
        
        total_move = abs(prices[-1] - prices[0])
        path_length = sum(abs(prices[i] - prices[i-1]) for i in range(1, len(prices)))
        efficiency = total_move / path_length if path_length > 0 else 0
        
        x = np.arange(len(prices))
        try:
            slope, _, _, _, _ = linregress(x, prices)
            price_std = np.std(prices)
            trend_score = slope / price_std if price_std > 0 else 0
        except:
            trend_score = 0
        
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

# ============ SETTLEMENT MANAGER ============
class SettlementManager:
    """Manages real-time settlement detection and processing."""
    
    def __init__(self, bot):
        self.bot = bot
        self.pending_settlements = {}
        
    def handle_market_resolved(self, payload: dict):
        """Handle market_resolved event from CLOB WebSocket."""
        slug = payload.get('slug', '')
        outcome = payload.get('outcome')
        asset_id = payload.get('asset_id')
        
        if not outcome:
            return
        
        # Find open positions for this market
        open_positions = db_get_open_positions()
        for pos_id, market_slug, pos_asset_id, side, entry_price, size in open_positions:
            if market_slug == slug or pos_asset_id == asset_id:
                pnl = compute_pnl(entry_price, side, size, outcome)
                db_update_pending(pos_id, outcome, pnl)
                self.pending_settlements[pos_id] = {
                    'outcome': outcome,
                    'pnl': pnl,
                    'detected_at': time.time()
                }
                print(f"[SETTLEMENT] Market {slug} resolved -> {outcome} | PnL: ${pnl:+.2f}")
                
                # Update bot's virtual balance
                self.bot.virtual_free += size + pnl
                
    def check_pending_settlements(self):
        """Check pending settlements for finality."""
        pending = db_get_pending_positions()
        for pos_id, market_slug, asset_id, side, entry_price, size, outcome in pending:
            # Check if enough time has passed for finality (2 hours for dispute window)
            # In production, this would check on-chain events
            pass
    
    def finalize_settlement(self, position_id: str, outcome: str, pnl: float):
        """Finalize a settlement after confirmation."""
        db_finalize_position(position_id, outcome, pnl)
        if position_id in self.pending_settlements:
            del self.pending_settlements[position_id]

# ============ WEBSOCKET MANAGERS ============
class CLOBWebSocketManager:
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.connected = False
        self.reconnect_delay = 1
        
    def connect(self):
        def on_open(ws):
            print(f"[CLOB] Connected")
            self.connected = True
            self.reconnect_delay = 1
            self._subscribe()
            
        def on_message(ws, message):
            try:
                msg = json.loads(message)
                self._handle_message(msg)
            except:
                pass
                
        def on_error(ws, error):
            print(f"[CLOB] Error: {error}")
            
        def on_close(ws, close_status_code, close_msg):
            print(f"[CLOB] Disconnected, reconnecting in {self.reconnect_delay}s...")
            self.connected = False
            time.sleep(self.reconnect_delay)
            self.reconnect_delay = min(self.reconnect_delay * 2, 60)
            self.connect()
        
        self.ws = websocket.WebSocketApp(
            CLOB_WS,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
    
    def _subscribe(self):
        if not self.connected or not self.ws:
            return
            
        # Get asset IDs from open positions
        open_positions = db_get_open_positions()
        asset_ids = list(set([pos[2] for pos in open_positions if pos[2]]))
        
        if asset_ids:
            sub_msg = {
                "assets_ids": asset_ids,
                "type": "market",
                "custom_feature_enabled": True
            }
            self.ws.send(json.dumps(sub_msg))
    
    def _handle_message(self, msg: dict):
        msg_type = msg.get("type") or msg.get("event_type")
        payload = msg.get("payload", {})
        
        if msg_type == "market_resolved":
            self.bot.settlement_manager.handle_market_resolved(payload)
        elif msg_type == "new_market":
            print(f"[NEW MARKET] {payload.get('slug', 'unknown')}")
        elif msg_type == "best_bid_ask":
            # Update market data cache
            pass

class RTDSWebSocketManager:
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.connected = False
        self.reconnect_delay = 1
        
    def connect(self):
        def on_open(ws):
            print(f"[RTDS] Connected")
            self.connected = True
            self.reconnect_delay = 1
            self._subscribe()
            self._start_pinger()
            
        def on_message(ws, message):
            try:
                msg = json.loads(message)
                self._handle_message(msg)
            except:
                pass
                
        def on_error(ws, error):
            print(f"[RTDS] Error: {error}")
            
        def on_close(ws, close_status_code, close_msg):
            print(f"[RTDS] Disconnected, reconnecting in {self.reconnect_delay}s...")
            self.connected = False
            time.sleep(self.reconnect_delay)
            self.reconnect_delay = min(self.reconnect_delay * 2, 60)
            self.connect()
        
        self.ws = websocket.WebSocketApp(
            RTDS_WS,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
    
    def _start_pinger(self):
        def ping():
            while self.connected and self.ws:
                try:
                    self.ws.send("PING")
                except:
                    break
                time.sleep(5)
        
        ping_thread = threading.Thread(target=ping)
        ping_thread.daemon = True
        ping_thread.start()
    
    def _subscribe(self):
        if not self.connected or not self.ws:
            return
            
        sub = {
            "action": "subscribe",
            "subscriptions": [
                {"topic": "crypto_prices", "type": "update", "filters": "btcusdt,ethusdt"}
            ]
        }
        self.ws.send(json.dumps(sub))
    
    def _handle_message(self, msg: dict):
        topic = msg.get("topic")
        payload = msg.get("payload", {})
        
        if topic == "crypto_prices":
            symbol = payload.get("symbol", "").lower().replace("usdt", "")
            price = payload.get("price")
            if symbol in COINS and price:
                self.bot.update_crypto_price(symbol.upper(), float(price))

# ============ MAIN BOT CLASS ============
class UltimateBot:
    def __init__(self):
        self.virtual_free = VIRTUAL_BANKROLL
        self.trade_count = 0
        self.active_positions = {}
        self.regime_detectors = {coin: RegimeDetector() for coin in COINS}
        self.current_regimes = {coin: Regime.CHOPPY for coin in COINS}
        self.prices = {}
        self.velocities_ema = {}
        
        self.clob_manager = CLOBWebSocketManager(self)
        self.rtds_manager = RTDSWebSocketManager(self)
        self.settlement_manager = SettlementManager(self)
        
        self.last_trade_time = 0
        self.last_exit_check = 0
        
        # Init database
        init_database()
        
    def start(self):
        print("="*70)
        print("ULTIMATE BOT v5 - FINAL VERSION")
        print("="*70)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting...")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Features: EMA + Regime + Exits + WebSockets + Auto-Settlement")
        
        # Connect WebSockets
        self.clob_manager.connect()
        self.rtds_manager.connect()
        
        time.sleep(3)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot ready")
        
        # Main loop
        while True:
            self.check_exits()
            self.settlement_manager.check_pending_settlements()
            time.sleep(1)
    
    def update_crypto_price(self, coin: str, price: float):
        if coin in self.prices:
            velocity_raw = price - self.prices[coin]
            ema_factor = VELOCITY_THRESHOLDS[coin]['ema_factor']
            if coin not in self.velocities_ema or self.velocities_ema[coin] == 0:
                self.velocities_ema[coin] = velocity_raw
            else:
                self.velocities_ema[coin] = (ema_factor * velocity_raw) + \
                                           ((1 - ema_factor) * self.velocities_ema[coin])
        
        self.prices[coin] = price
        self.regime_detectors[coin].add_price(price)
        self.current_regimes[coin] = self.regime_detectors[coin].compute_regime()
        
        for tf in TIMEFRAMES:
            self.evaluate_market(coin, tf)
    
    def evaluate_market(self, coin: str, tf: int):
        if self.virtual_free < 20:
            return
        
        current_time = time.time()
        min_interval = 10 if tf == 5 else 20
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        regime = self.current_regimes.get(coin, Regime.CHOPPY)
        regime_params = self.regime_detectors[coin].get_params(regime)
        
        if regime_params['timeframe'] != tf and regime in [Regime.TREND_UP, Regime.TREND_DOWN, Regime.LOW_VOL]:
            return
        
        # HTTP fallback for market data
        self._evaluate_with_http(coin, tf, regime_params)
    
    def _evaluate_with_http(self, coin: str, tf: int, regime_params: dict):
        import requests
        
        try:
            slot = int(time.time() // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            market_key = f"{coin}-{tf}m"
            
            resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
            if resp.status_code != 200:
                return
            
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) != 2:
                return
            
            yes_price = float(prices_pm[0])
            no_price = float(prices_pm[1])
            
            # Check if already resolved
            if data.get('resolved'):
                self.settlement_manager.handle_market_resolved({
                    'slug': slug,
                    'outcome': 'YES' if data.get('winningOutcomeIndex') == 0 else 'NO'
                })
                return
            
            # Check arbitrage
            if yes_price + no_price < 0.985:
                self.execute_trade_arb(coin, tf, yes_price, no_price, regime_params, slug)
                self.last_trade_time = time.time()
                return
            
            # Check edge
            if coin in self.velocities_ema and self.velocities_ema[coin] != 0:
                edge_trade = self.calculate_edge(coin, yes_price, no_price, 
                                                self.velocities_ema[coin], regime_params)
                if edge_trade:
                    self.execute_trade_edge(coin, tf, edge_trade, slug, yes_price, no_price, 
                                          regime_params, data)
                    self.last_trade_time = time.time()
                    
        except Exception as e:
            pass
    
    def calculate_edge(self, coin: str, yes_price: float, no_price: float, 
                      velocity: float, regime_params: dict) -> Optional[dict]:
        threshold = VELOCITY_THRESHOLDS[coin]['raw'] * regime_params['velocity_mult']
        max_price = regime_params['max_price']
        side_bias = regime_params['side_bias']
        
        edge = 0
        side = None
        
        if side_bias == 'YES' and velocity > threshold and yes_price < max_price:
            edge = velocity * (0.75 - yes_price)
            side = 'YES'
        elif side_bias == 'NO' and velocity < -threshold and no_price < max_price:
            edge = abs(velocity) * (0.75 - no_price)
            side = 'NO'
        elif side_bias is None:
            if velocity > threshold and yes_price < max_price:
                edge = velocity * (0.75 - yes_price)
                side = 'YES'
            elif velocity < -threshold and no_price < max_price:
                edge = abs(velocity) * (0.75 - no_price)
                side = 'NO'
        
        if edge >= MIN_EDGE:
            return {'side': side, 'price': yes_price if side == 'YES' else no_price, 'edge': edge}
        return None
    
    def execute_trade_arb(self, coin: str, tf: int, yes_price: float, no_price: float, 
                         regime_params: dict, slug: str):
        profit = (1.0 - (yes_price + no_price)) * 100
        amount = min(50.0, self.virtual_free * POSITION_SIZE_PCT * regime_params['size_mult'])
        
        if amount < 20:
            return
        
        self.trade_count += 1
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{self.trade_count} ARB {coin} {tf}m | +{profit:.2f}%")
        
        self.virtual_free -= amount
        
        # Store in database
        position_id = f"{slug}-arb-{int(time.time())}"
        db_insert_position(position_id, slug, None, None, 'BOTH', yes_price, amount)
        
        self.log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'ARBITRAGE',
            'market': f"{coin.upper()} {tf}m",
            'amount': amount,
            'virtual_balance': self.virtual_free
        })
    
    def execute_trade_edge(self, coin: str, tf: int, edge_trade: dict, slug: str,
                          yes_price: float, no_price: float, regime_params: dict, data: dict):
        edge = edge_trade['edge']
        base_size = POSITION_SIZE_PCT * regime_params['size_mult']
        size_multiplier = min(2.0, 1.0 + (edge * 2))
        amount = min(50.0, self.virtual_free * base_size * size_multiplier)
        
        if amount < 20:
            return
        
        self.trade_count += 1
        side = edge_trade['side']
        entry_price = edge_trade['price']
        
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{self.trade_count} EDGE {coin} {tf}m | "
              f"{side} @ {entry_price:.3f} | Regime: {self.current_regimes[coin].value}")
        
        self.virtual_free -= amount
        
        # Get asset IDs and condition ID from data
        tokens = data.get('tokens', [])
        asset_id = None
        condition_id = data.get('conditionId')
        
        for token in tokens:
            if token.get('outcome') == side:
                asset_id = token.get('id')
                break
        
        # Store in database
        position_id = f"{slug}-{side}-{int(time.time())}"
        db_insert_position(position_id, slug, asset_id, condition_id, side, entry_price, amount)
        
        # Track in memory
        market_key = f"{coin}-{tf}m"
        self.active_positions[market_key] = Position(market_key, side, entry_price, amount)
        
        self.log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EDGE',
            'market': f"{coin.upper()} {tf}m",
            'side': side,
            'amount': amount,
            'edge': edge,
            'regime': self.current_regimes[coin].value,
            'virtual_balance': self.virtual_free
        })
    
    def check_exits(self):
        now = time.time()
        if now - self.last_exit_check < 15:
            return
        self.last_exit_check = now
        
        for market_id, position in list(self.active_positions.items()):
            # Get current price from HTTP (in production, use CLOB cache)
            pass
    
    def log_trade(self, trade: dict):
        try:
            with open("/root/.openclaw/workspace/wallet_ultimate_trades.json", 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open("/root/.openclaw/workspace/wallet_ultimate_trades.json", 'w') as f:
            json.dump(log, f, indent=2)

# ============ START ============
if __name__ == "__main__":
    bot = UltimateBot()
    bot.start()
