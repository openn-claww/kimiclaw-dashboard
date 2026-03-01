#!/usr/bin/env python3
"""
ULTIMATE BOT v4 - WITH API OPTIMIZATION
Integrated: Exit Management + Regime Detection + WebSocket Optimization
"""

import websocket
import json
import time
import asyncio
import threading
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
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

# Regime detection
REGIME_WINDOW = 30
REGIME_THETA = 0.5

# WebSocket endpoints
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RTDS_WS = "wss://ws-live-data.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

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

# ============ WEBSOCKET MANAGERS ============
class CLOBWebSocketManager:
    """Manages CLOB WebSocket connection for real-time market data."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.connected = False
        self.subscribed_assets = set()
        self.market_data = {}
        self.reconnect_delay = 1
        
    def connect(self):
        """Connect to CLOB WebSocket."""
        def on_open(ws):
            print(f"[CLOB] Connected to market WebSocket")
            self.connected = True
            self.reconnect_delay = 1
            # Subscribe to markets
            self._subscribe_to_markets()
            
        def on_message(ws, message):
            try:
                msg = json.loads(message)
                self._handle_message(msg)
            except Exception as e:
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
        
        # Run in separate thread
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
    
    def _subscribe_to_markets(self):
        """Subscribe to market channels."""
        if not self.connected or not self.ws:
            return
            
        # Get current market asset IDs
        asset_ids = self.bot.get_active_asset_ids()
        if asset_ids:
            sub_msg = {
                "assets_ids": list(asset_ids),
                "type": "market",
                "custom_feature_enabled": True
            }
            self.ws.send(json.dumps(sub_msg))
    
    def _handle_message(self, msg: dict):
        """Handle incoming CLOB messages."""
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        
        if msg_type == "best_bid_ask":
            # Update market prices
            asset_id = payload.get("asset_id")
            if asset_id:
                self.market_data[asset_id] = {
                    "best_bid": payload.get("best_bid"),
                    "best_ask": payload.get("best_ask"),
                    "timestamp": time.time()
                }
                
        elif msg_type == "new_market":
            print(f"[CLOB] New market detected: {payload.get('slug', 'unknown')}")
            # Auto-subscribe to new markets
            
        elif msg_type == "market_resolved":
            print(f"[CLOB] Market resolved: {payload.get('slug', 'unknown')}")
            # Trigger settlement check
            self.bot.handle_market_resolved(payload)

class RTDSWebSocketManager:
    """Manages RTDS WebSocket for crypto price feeds."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.connected = False
        self.crypto_prices = {}
        self.reconnect_delay = 1
        
    def connect(self):
        """Connect to RTDS WebSocket."""
        def on_open(ws):
            print(f"[RTDS] Connected to live data feed")
            self.connected = True
            self.reconnect_delay = 1
            self._subscribe()
            # Start pinger
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
        """Send PING every 5 seconds to keep connection alive."""
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
        """Subscribe to crypto price feeds."""
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
        """Handle incoming RTDS messages."""
        topic = msg.get("topic")
        payload = msg.get("payload", {})
        
        if topic == "crypto_prices":
            symbol = payload.get("symbol", "").lower()
            price = payload.get("price")
            if symbol and price:
                self.crypto_prices[symbol] = {
                    "price": float(price),
                    "timestamp": time.time()
                }
                # Update bot's price data
                coin = symbol.replace("usdt", "").upper()
                if coin in COINS:
                    self.bot.update_crypto_price(coin, float(price))

# ============ MAIN BOT CLASS ============
class UltimateBot:
    def __init__(self):
        self.virtual_free = VIRTUAL_BANKROLL
        self.trade_count = 0
        self.open_positions = defaultdict(list)
        self.active_positions = {}
        self.regime_detectors = {coin: RegimeDetector() for coin in COINS}
        self.current_regimes = {coin: Regime.CHOPPY for coin in COINS}
        self.prices = {}
        self.velocities_ema = {}
        self.asset_ids = {}  # market_key -> asset_id mapping
        
        # WebSocket managers
        self.clob_manager = CLOBWebSocketManager(self)
        self.rtds_manager = RTDSWebSocketManager(self)
        
        # State
        self.last_trade_time = 0
        self.last_exit_check = 0
        
    def start(self):
        """Start the bot."""
        print("="*70)
        print("ULTIMATE BOT v4 - WEBSOCKET OPTIMIZED")
        print("="*70)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting WebSocket connections...")
        
        # Connect WebSockets
        self.clob_manager.connect()
        self.rtds_manager.connect()
        
        # Wait for connections
        time.sleep(3)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot ready. Monitoring markets...")
        
        # Main loop
        while True:
            self.check_exits()
            time.sleep(1)
    
    def update_crypto_price(self, coin: str, price: float):
        """Update price from RTDS feed."""
        if coin in self.prices:
            # Calculate velocity
            velocity_raw = price - self.prices[coin]
            ema_factor = VELOCITY_THRESHOLDS[coin]['ema_factor']
            
            if coin not in self.velocities_ema or self.velocities_ema[coin] == 0:
                self.velocities_ema[coin] = velocity_raw
            else:
                self.velocities_ema[coin] = (ema_factor * velocity_raw) + \
                                           ((1 - ema_factor) * self.velocities_ema[coin])
        
        self.prices[coin] = price
        
        # Update regime detector
        self.regime_detectors[coin].add_price(price)
        self.current_regimes[coin] = self.regime_detectors[coin].compute_regime()
        
        # Evaluate markets
        for tf in TIMEFRAMES:
            self.evaluate_market(coin, tf)
    
    def evaluate_market(self, coin: str, tf: int):
        """Evaluate trading opportunity."""
        if self.virtual_free < 20:
            return
        
        current_time = time.time()
        min_interval = 10 if tf == 5 else 20
        
        if current_time - self.last_trade_time < min_interval:
            return
        
        regime = self.current_regimes.get(coin, Regime.CHOPPY)
        regime_params = self.regime_detectors[coin].get_params(regime)
        
        # Skip if timeframe doesn't match regime preference
        if regime_params['timeframe'] != tf and regime in [Regime.TREND_UP, Regime.TREND_DOWN, Regime.LOW_VOL]:
            return
        
        # Get market data from CLOB
        market_key = f"{coin}-{tf}m"
        
        # For now, use HTTP fallback for market discovery
        # In production, this would use cached CLOB data
        self._evaluate_with_http(coin, tf, regime_params)
    
    def _evaluate_with_http(self, coin: str, tf: int, regime_params: dict):
        """Fallback HTTP evaluation (to be replaced with WebSocket data)."""
        import requests
        
        try:
            slot = int(time.time() // (tf * 60)) * (tf * 60)
            slug = f"{coin.lower()}-updown-{tf}m-{slot}"
            
            resp = requests.get(f"{GAMMA_API}/markets/slug/{slug}", timeout=2)
            if resp.status_code != 200:
                return
            
            data = resp.json()
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            
            if len(prices_pm) != 2:
                return
            
            yes_price = float(prices_pm[0])
            no_price = float(prices_pm[1])
            
            # Check arbitrage
            if yes_price + no_price < 0.985:
                self.execute_trade_arb(coin, tf, yes_price, no_price, regime_params)
                self.last_trade_time = time.time()
                return
            
            # Check edge
            if coin in self.velocities_ema and self.velocities_ema[coin] != 0:
                edge_trade = self.calculate_edge(coin, yes_price, no_price, 
                                                self.velocities_ema[coin], regime_params)
                if edge_trade:
                    self.execute_trade_edge(coin, tf, edge_trade, yes_price, no_price, regime_params)
                    self.last_trade_time = time.time()
                    
        except Exception as e:
            pass
    
    def calculate_edge(self, coin: str, yes_price: float, no_price: float, 
                      velocity: float, regime_params: dict) -> Optional[dict]:
        """Calculate trading edge."""
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
    
    def execute_trade_arb(self, coin: str, tf: int, yes_price: float, no_price: float, regime_params: dict):
        """Execute arbitrage trade."""
        profit = (1.0 - (yes_price + no_price)) * 100
        amount = min(50.0, self.virtual_free * POSITION_SIZE_PCT * regime_params['size_mult'])
        
        if amount < 20:
            return
        
        self.trade_count += 1
        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{self.trade_count} ARB {coin} {tf}m | +{profit:.2f}%")
        
        self.virtual_free -= amount
        self.log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'ARBITRAGE',
            'market': f"{coin.upper()} {tf}m",
            'amount': amount,
            'virtual_balance': self.virtual_free
        })
    
    def execute_trade_edge(self, coin: str, tf: int, edge_trade: dict, yes_price: float, 
                          no_price: float, regime_params: dict):
        """Execute edge trade."""
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
        """Check for position exits."""
        now = time.time()
        if now - self.last_exit_check < 15:
            return
        self.last_exit_check = now
        
        # Check each active position
        for market_id, position in list(self.active_positions.items()):
            # Get current price (from CLOB manager or HTTP fallback)
            current_price = self._get_current_price(position)
            if current_price is None:
                continue
            
            exit_reason = evaluate_exits(position, current_price)
            if exit_reason:
                self.execute_exit(position, exit_reason, current_price)
    
    def _get_current_price(self, position: Position) -> Optional[float]:
        """Get current price for position."""
        # Try CLOB manager first
        # Fallback to HTTP
        return None
    
    def execute_exit(self, position: Position, reason: ExitReason, current_price: float):
        """Execute position exit."""
        pnl = (current_price - position.entry_price) / position.entry_price * 100
        
        print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {position.market_id} | "
              f"{reason.value} | PnL: {pnl:+.1f}%")
        
        self.virtual_free += position.shares * current_price
        
        self.log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EXIT',
            'market': position.market_id,
            'exit_reason': reason.value,
            'pnl_pct': pnl,
            'virtual_balance': self.virtual_free
        })
        
        if position.market_id in self.active_positions:
            del self.active_positions[position.market_id]
    
    def log_trade(self, trade: dict):
        """Log trade to file."""
        try:
            with open("/root/.openclaw/workspace/wallet_ultimate_trades.json", 'r') as f:
                log = json.load(f)
        except:
            log = []
        log.append(trade)
        with open("/root/.openclaw/workspace/wallet_ultimate_trades.json", 'w') as f:
            json.dump(log, f, indent=2)
    
    def get_active_asset_ids(self) -> List[str]:
        """Get list of active asset IDs for subscription."""
        return list(self.asset_ids.values())
    
    def handle_market_resolved(self, payload: dict):
        """Handle market resolution event."""
        slug = payload.get('slug', '')
        winner = payload.get('winning_outcome')
        print(f"[RESOLVED] {slug} | Winner: {winner}")
        # Trigger settlement logic

# ============ START BOT ============
if __name__ == "__main__":
    bot = UltimateBot()
    bot.start()
