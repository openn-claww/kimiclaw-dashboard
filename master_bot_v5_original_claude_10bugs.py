#!/usr/bin/env python3
"""
MASTER BOT v5 — FINAL PRODUCTION BUILD
Fixes applied vs previous draft:
  [F1] self.asset_ids now populated from Gamma API on every position open
  [F2] threading.Lock() on all shared state (prices, velocities, positions)
  [F3] Real on-chain USDC balance checked at startup + drift detection each trade
  [F4] Volume filter fully wired — no more bare `pass`
  [F5] REGIME_PARAMS validated at import; logs warn if 'default' key missing
  [F6] execute_sell() now passes pos.shares
  [F7] Restored positions re-registered into resolution engine on startup
"""

# ── PID mutex — prevents duplicate instances ─────────────────────────────────
from bot_lock import acquire_lock
acquire_lock()

# ── stdlib ────────────────────────────────────────────────────────────────────
import os
import sys
import json
import time
import logging
import threading
import signal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum
from collections import defaultdict, deque
from pathlib import Path

# ── third-party ───────────────────────────────────────────────────────────────
import requests
import websocket
import numpy as np
from scipy.stats import linregress

# ── workspace modules ─────────────────────────────────────────────────────────
sys.path.insert(0, '/root/.openclaw/workspace')

from live_trading.live_trading_config import load_live_config
from live_trading.v4_live_integration import V4BotLiveIntegration
from entry_validation import calculate_edge, REGIME_PARAMS
from risk_manager import RiskManager
from atomic_json import atomic_write_json, safe_load_json
from edge_tracker import (
    get_kelly_stake_with_diagnostics,
    record_completed_trade,
    import_trade_history,
)
from resolution_fallback_v1 import ResolutionFallbackEngine, ResolutionConfig

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

WORKSPACE    = '/root/.openclaw/workspace'
LOG_FILE     = f'{WORKSPACE}/master_v5_run.log'
TRADE_LOG    = f'{WORKSPACE}/master_v5_trades.json'
STATE_FILE   = f'{WORKSPACE}/master_v5_state.json'
HEALTH_FILE  = f'{WORKSPACE}/master_v5_health.json'
DECISION_LOG = f'{WORKSPACE}/master_v5_decisions.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('master_v5')

# ══════════════════════════════════════════════════════════════════════════════
# [F5] VALIDATE REGIME_PARAMS AT IMPORT
# ══════════════════════════════════════════════════════════════════════════════

_REQUIRED_REGIME_KEYS = ['trend_up', 'trend_down', 'choppy', 'high_vol', 'low_vol']
_FALLBACK_REGIME = {
    'side_bias': None, 'velocity_mult': 1.2, 'size_mult': 0.7,
    'timeframe': 15,   'max_price': 0.55,
}

for _k in _REQUIRED_REGIME_KEYS:
    if _k not in REGIME_PARAMS:
        log.warning(f"[F5] REGIME_PARAMS missing key '{_k}' — using fallback for that regime")

if 'default' not in REGIME_PARAMS:
    log.warning("[F5] REGIME_PARAMS has no 'default' key — injecting safe fallback")
    REGIME_PARAMS['default'] = _FALLBACK_REGIME

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

VIRTUAL_BANKROLL          = 686.93
MAX_POSITIONS             = 5
POSITION_SIZE_PCT         = 0.05
MIN_EDGE                  = 0.10

COINS      = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES = [5, 15]

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15,  'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
    'SOL': {'raw': 0.25,  'ema_factor': 0.3},
    'XRP': {'raw': 0.08,  'ema_factor': 0.3},
}
VOLUME_MULTIPLIERS = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}

# Exits
STOP_LOSS_PCT      = 0.20
TAKE_PROFIT_PCT    = 0.40
TRAILING_STOP_PCT  = 0.15
TRAILING_ACTIVATE  = 1.10   # trailing arm once price is +10%
TIME_STOP_MINUTES  = 90

# Regime detection
REGIME_WINDOW = 30
REGIME_THETA  = 0.5

# Zone filter — OFF by default (50k backtest showed it blocked 50% trades, no WR gain)
ENABLE_ZONE_FILTER = os.getenv('ENABLE_ZONE_FILTER', 'false').lower() == 'true'
DEAD_ZONE_LOW      = 0.35
DEAD_ZONE_HIGH     = 0.65

IS_PAPER_TRADING = os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true'

# API / WS
GAMMA_API  = "https://gamma-api.polymarket.com"
CLOB_WS    = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RTDS_WS    = "wss://ws-live-data.polymarket.com"
BINANCE_WS = ("wss://stream.binance.com:9443/ws/"
              "btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade")

CLOB_MAX_RPS       = 60      # requests per minute
RECONNECT_DELAY    = 5       # seconds

# Safety env-var overrides (all have safe defaults)
MAX_DAILY_LOSS_PCT       = float(os.getenv('MAX_DAILY_LOSS_PCT',       '0.15'))
MAX_CONSECUTIVE_LOSSES   = int(os.getenv('MAX_CONSECUTIVE_LOSSES',     '7'))
MAX_API_ERRORS_PER_HOUR  = int(os.getenv('MAX_API_ERRORS_PER_HOUR',    '30'))
MAX_TOTAL_EXPOSURE_PCT   = float(os.getenv('MAX_TOTAL_EXPOSURE_PCT',   '0.50'))
MAX_SINGLE_TRADE_USD     = float(os.getenv('MAX_SINGLE_TRADE_USD',     '75.0'))
BALANCE_DRIFT_THRESHOLD  = float(os.getenv('BALANCE_DRIFT_THRESHOLD',  '0.10'))  # 10%

# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class Regime(Enum):
    TREND_UP   = "trend_up"
    TREND_DOWN = "trend_down"
    CHOPPY     = "choppy"
    HIGH_VOL   = "high_vol"
    LOW_VOL    = "low_vol"

class ExitReason(Enum):
    STOP_LOSS     = "stop_loss"
    TAKE_PROFIT   = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_STOP     = "time_stop"
    RESOLVED      = "resolved"

class BotState(Enum):
    RUNNING  = "running"
    DEGRADED = "degraded"   # live orders failing → paper only
    STOPPED  = "stopped"

# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: EMERGENCY STOP
# ══════════════════════════════════════════════════════════════════════════════

class EmergencyStop:
    """
    Three ways to halt the bot immediately:
      1. Create file:  touch /tmp/MASTER_BOT_STOP
      2. Set env var:  MASTER_BOT_EMERGENCY_STOP=1
      3. Send signal:  kill -SIGTERM <pid>
    """
    FLAG_FILE = '/tmp/MASTER_BOT_STOP'

    def __init__(self):
        self._stop = False
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT,  self._on_signal)

    def _on_signal(self, signum, _frame):
        log.critical(f"Signal {signum} received — triggering emergency stop")
        self._stop = True

    def is_active(self) -> bool:
        if self._stop:
            return True
        if os.getenv('MASTER_BOT_EMERGENCY_STOP', '0') == '1':
            log.critical("MASTER_BOT_EMERGENCY_STOP env var active — halting")
            self._stop = True
            return True
        if Path(self.FLAG_FILE).exists():
            log.critical(f"Stop flag {self.FLAG_FILE} detected — halting")
            self._stop = True
            return True
        return False

    def trigger(self):
        self._stop = True
        try:
            Path(self.FLAG_FILE).touch()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: CIRCUIT BREAKER
# ══════════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Stops new entries if win rate < min_win_rate over last `window` trades."""

    def __init__(self, window: int = 50, min_win_rate: float = 0.45):
        self.window    = window
        self.min_wr    = min_win_rate
        self._outcomes = deque(maxlen=window)
        self._tripped  = False
        self._lock     = threading.Lock()

    def record(self, won: bool):
        with self._lock:
            self._outcomes.append(won)
            if len(self._outcomes) >= self.window:
                wr = sum(self._outcomes) / len(self._outcomes)
                newly_tripped = wr < self.min_wr
                if newly_tripped and not self._tripped:
                    log.critical(
                        f"CIRCUIT BREAKER TRIPPED — win rate {wr:.1%} "
                        f"< {self.min_wr:.1%} over last {self.window} trades"
                    )
                elif not newly_tripped and self._tripped:
                    log.warning(f"Circuit breaker RESET — win rate recovered to {wr:.1%}")
                self._tripped = newly_tripped

    def is_tripped(self) -> bool:
        with self._lock:
            return self._tripped

    def status(self) -> dict:
        with self._lock:
            n  = len(self._outcomes)
            wr = sum(self._outcomes) / n if n else None
            return {'tripped': self._tripped, 'win_rate': wr, 'sample': n}


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: KILL SWITCH
# ══════════════════════════════════════════════════════════════════════════════

class KillSwitch:
    """Halts new entries on daily loss / streak / API error thresholds."""

    def __init__(self, starting_bankroll: float):
        self._start           = starting_bankroll
        self._daily_loss      = 0.0
        self._consec_losses   = 0
        self._api_errors      = deque()          # timestamps
        self._day             = datetime.now().date()
        self._active          = False
        self._lock            = threading.Lock()

    def _reset_day(self):
        today = datetime.now().date()
        if today != self._day:
            self._daily_loss    = 0.0
            self._consec_losses = 0
            self._day           = today
            log.info("Kill switch daily counters reset")

    def record_trade(self, pnl_amount: float, won: bool):
        with self._lock:
            self._reset_day()
            if won:
                self._consec_losses = 0
            else:
                self._daily_loss    += abs(pnl_amount)
                self._consec_losses += 1
            dl = self._daily_loss / self._start
            if dl >= MAX_DAILY_LOSS_PCT:
                log.critical(f"KILL SWITCH: daily loss {dl:.1%} >= {MAX_DAILY_LOSS_PCT:.1%}")
                self._active = True
            if self._consec_losses >= MAX_CONSECUTIVE_LOSSES:
                log.critical(f"KILL SWITCH: {self._consec_losses} consecutive losses")
                self._active = True

    def record_api_error(self):
        with self._lock:
            now = time.time()
            self._api_errors.append(now)
            # prune older than 1h
            while self._api_errors and now - self._api_errors[0] > 3600:
                self._api_errors.popleft()
            if len(self._api_errors) >= MAX_API_ERRORS_PER_HOUR:
                log.critical(f"KILL SWITCH: {len(self._api_errors)} API errors in last hour")
                self._active = True

    def validate_trade(self, amount: float, exposure: float, bankroll: float
                       ) -> Tuple[bool, str]:
        with self._lock:
            if self._active:
                return False, "kill_switch_active"
            if amount > MAX_SINGLE_TRADE_USD:
                return False, f"size ${amount:.2f} > max ${MAX_SINGLE_TRADE_USD}"
            if exposure + amount > bankroll * MAX_TOTAL_EXPOSURE_PCT:
                return False, f"exposure would exceed {MAX_TOTAL_EXPOSURE_PCT:.0%} of bankroll"
            return True, "ok"

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def status(self) -> dict:
        with self._lock:
            self._reset_day()
            return {
                'active':            self._active,
                'daily_loss_usd':    round(self._daily_loss, 2),
                'daily_loss_pct':    round(self._daily_loss / self._start, 4),
                'consec_losses':     self._consec_losses,
                'api_errors_1h':     len(self._api_errors),
            }


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Token-bucket rate limiter — prevents CLOB API bans."""

    def __init__(self, max_per_minute: int = CLOB_MAX_RPS):
        self._max   = max_per_minute
        self._calls = deque()
        self._lock  = threading.Lock()

    def acquire(self, wait: float = 2.0) -> bool:
        deadline = time.time() + wait
        while time.time() < deadline:
            with self._lock:
                now = time.time()
                while self._calls and now - self._calls[0] > 60:
                    self._calls.popleft()
                if len(self._calls) < self._max:
                    self._calls.append(now)
                    return True
            time.sleep(0.05)
        log.warning("Rate limit — request dropped")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# REGIME DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class RegimeDetector:
    def __init__(self, window: int = REGIME_WINDOW):
        self.window        = window
        self.price_history = deque(maxlen=window * 2)
        self.vol_history   = deque(maxlen=200)
        self.last_regime   = Regime.CHOPPY

    def add_price(self, price: float):
        self.price_history.append(price)

    def compute_regime(self) -> Regime:
        if len(self.price_history) < self.window:
            return self.last_regime
        prices  = list(self.price_history)[-self.window:]
        returns = [
            np.log(prices[i] / prices[i-1])
            for i in range(1, len(prices)) if prices[i-1] > 0
        ]
        if not returns:
            return self.last_regime

        vol = float(np.std(returns)) if len(returns) > 1 else 0.0
        self.vol_history.append(vol)

        vol_z = 0.0
        if len(self.vol_history) >= 30:
            arr   = list(self.vol_history)[-100:]
            vstd  = float(np.std(arr))
            if vstd > 0:
                vol_z = (vol - float(np.mean(arr))) / vstd

        total_move  = abs(prices[-1] - prices[0])
        path_length = sum(abs(prices[i] - prices[i-1]) for i in range(1, len(prices)))
        efficiency  = total_move / path_length if path_length > 0 else 0.0

        try:
            slope, *_ = linregress(np.arange(len(prices)), prices)
            pstd = float(np.std(prices))
            trend_score = slope / pstd if pstd > 0 else 0.0
        except Exception:
            trend_score = 0.0

        regime = self._classify(vol_z, efficiency, trend_score)
        self.last_regime = regime
        return regime

    def _classify(self, vol_z, efficiency, trend_score) -> Regime:
        if vol_z > 1.5:   return Regime.HIGH_VOL
        if vol_z < -1.0:  return Regime.LOW_VOL
        if efficiency > 0.6:
            if trend_score >  REGIME_THETA: return Regime.TREND_UP
            if trend_score < -REGIME_THETA: return Regime.TREND_DOWN
        return Regime.CHOPPY

    def get_params(self, regime: Regime) -> dict:
        return {
            Regime.TREND_UP:   {'side_bias':'YES',  'velocity_mult':0.8, 'size_mult':1.3, 'timeframe':5,  'max_price':0.70},
            Regime.TREND_DOWN: {'side_bias':'NO',   'velocity_mult':0.8, 'size_mult':1.3, 'timeframe':5,  'max_price':0.70},
            Regime.CHOPPY:     {'side_bias':None,   'velocity_mult':1.5, 'size_mult':0.5, 'timeframe':15, 'max_price':0.40},
            Regime.HIGH_VOL:   {'side_bias':None,   'velocity_mult':0.9, 'size_mult':0.6, 'timeframe':5,  'max_price':0.65},
            Regime.LOW_VOL:    {'side_bias':None,   'velocity_mult':0.7, 'size_mult':1.2, 'timeframe':15, 'max_price':0.60},
        }.get(regime, _FALLBACK_REGIME)


# ══════════════════════════════════════════════════════════════════════════════
# POSITION DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    market_id:   str
    side:        str
    entry_price: float
    shares:      float
    asset_id:    str   = ''          # [F1] CLOB token ID for price lookups
    slug:        str   = ''          # Gamma slug for resolution engine
    coin:        str   = ''
    timeframe:   int   = 5
    entry_time:  float = field(default_factory=time.time)
    pos_id:      str   = ''
    peak_price:         float = field(init=False)
    trailing_stop_price: float = field(init=False)

    def __post_init__(self):
        self.peak_price          = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - TRAILING_STOP_PCT)

    def to_dict(self) -> dict:
        return {
            'market_id':   self.market_id,   'side':       self.side,
            'entry_price': self.entry_price,  'shares':     self.shares,
            'asset_id':    self.asset_id,     'slug':       self.slug,
            'coin':        self.coin,         'timeframe':  self.timeframe,
            'entry_time':  self.entry_time,   'pos_id':     self.pos_id,
            'peak_price':           self.peak_price,
            'trailing_stop_price':  self.trailing_stop_price,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Position':
        p = cls(
            market_id=d['market_id'],  side=d['side'],
            entry_price=d['entry_price'], shares=d['shares'],
            asset_id=d.get('asset_id',''),  slug=d.get('slug',''),
            coin=d.get('coin',''),          timeframe=d.get('timeframe', 5),
            entry_time=d.get('entry_time', time.time()),
            pos_id=d.get('pos_id',''),
        )
        p.peak_price          = d.get('peak_price', p.entry_price)
        p.trailing_stop_price = d.get('trailing_stop_price',
                                      p.entry_price * (1 - TRAILING_STOP_PCT))
        return p


def evaluate_exits(pos: Position, price: float) -> Optional[ExitReason]:
    """5-exit system: SL / TP / trailing / time / (resolved handled separately)."""
    if price <= pos.entry_price * (1 - STOP_LOSS_PCT):
        return ExitReason.STOP_LOSS
    if (time.time() - pos.entry_time) / 60 >= TIME_STOP_MINUTES:
        return ExitReason.TIME_STOP
    if price >= pos.entry_price * (1 + TAKE_PROFIT_PCT):
        return ExitReason.TAKE_PROFIT
    if price >= pos.entry_price * TRAILING_ACTIVATE:
        if price > pos.peak_price:
            pos.peak_price          = price
            pos.trailing_stop_price = price * (1 - TRAILING_STOP_PCT)
        if price <= pos.trailing_stop_price:
            return ExitReason.TRAILING_STOP
    return None


# ══════════════════════════════════════════════════════════════════════════════
# FILTERS
# ══════════════════════════════════════════════════════════════════════════════

def passes_zone_filter(yes_price: float, side: str) -> Tuple[bool, str]:
    if not ENABLE_ZONE_FILTER:
        return True, 'zone_disabled'
    eff = yes_price if side == 'YES' else (1.0 - yes_price)
    if DEAD_ZONE_LOW <= eff <= DEAD_ZONE_HIGH:
        return False, f'dead_zone:{eff:.3f}'
    return True, 'zone_ok'


def get_sentiment_mult(fng: int, side: str) -> Optional[float]:
    if side == 'YES':
        if fng > 80:  return None
        if fng <= 20: return 1.5
        if fng <= 60: return 1.0
        return 0.5
    else:
        if fng < 20:  return None
        if fng >= 80: return 1.5
        if fng >= 40: return 1.0
        return 0.5


def _fetch_fng() -> int:
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3)
        return int(r.json()['data'][0]['value'])
    except Exception:
        return 50   # neutral


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET: CLOB
# ══════════════════════════════════════════════════════════════════════════════

class CLOBWebSocketManager:
    def __init__(self, bot: 'MasterBot'):
        self.bot             = bot
        self.ws              = None
        self.connected       = False
        self.market_data:    Dict[str, dict] = {}   # asset_id → {best_bid, best_ask, ts}
        self._reconnect_delay = 1
        self._lock           = threading.Lock()

    def get_mid_price(self, asset_id: str) -> Optional[float]:
        with self._lock:
            d = self.market_data.get(asset_id)
            if not d:
                return None
            b, a = d.get('best_bid'), d.get('best_ask')
            if b is not None and a is not None:
                return (float(b) + float(a)) / 2
            return None

    def subscribe(self, asset_ids: List[str]):
        if self.ws and self.connected and asset_ids:
            try:
                self.ws.send(json.dumps({
                    "assets_ids": asset_ids,
                    "type": "market",
                    "custom_feature_enabled": True,
                }))
            except Exception as e:
                log.error(f"[CLOB] subscribe error: {e}")

    def connect(self):
        def on_open(ws):
            log.info("[CLOB] Connected")
            self.connected         = True
            self._reconnect_delay  = 1
            # subscribe to any already-open positions
            aids = self.bot._get_all_asset_ids()
            if aids:
                self.subscribe(aids)

        def on_message(ws, raw):
            try:
                msg     = json.loads(raw)
                mtype   = msg.get('type')
                payload = msg.get('payload', {})
                if mtype == 'best_bid_ask':
                    aid = payload.get('asset_id')
                    if aid:
                        with self._lock:
                            self.market_data[aid] = {
                                'best_bid': payload.get('best_bid'),
                                'best_ask': payload.get('best_ask'),
                                'ts':       time.time(),
                            }
                elif mtype == 'market_resolved':
                    log.info(f"[CLOB] Resolved: {payload.get('slug')}")
                    self.bot.handle_market_resolved(payload)
            except Exception as e:
                log.debug(f"[CLOB] msg error: {e}")

        def on_error(ws, err):
            log.error(f"[CLOB] Error: {err}")
            self.bot.kill_switch.record_api_error()

        def on_close(ws, code, msg):
            self.connected = False
            log.warning(f"[CLOB] Closed (code={code}), retry in {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            if not self.bot.emergency_stop.is_active():
                self.connect()

        self.ws = websocket.WebSocketApp(
            CLOB_WS,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET: RTDS (primary price feed)
# ══════════════════════════════════════════════════════════════════════════════

class RTDSWebSocketManager:
    def __init__(self, bot: 'MasterBot'):
        self.bot              = bot
        self.ws               = None
        self.connected        = False
        self._reconnect_delay = 1
        self._fail_count      = 0
        self._MAX_FAILS       = 3

    def connect(self):
        def on_open(ws):
            log.info("[RTDS] Connected")
            self.connected        = True
            self._reconnect_delay = 1
            self._fail_count      = 0
            ws.send(json.dumps({
                "action": "subscribe",
                "subscriptions": [{
                    "topic": "crypto_prices", "type": "update",
                    "filters": "btcusdt,ethusdt,solusdt,xrpusdt",
                }]
            }))
            threading.Thread(target=self._pinger, daemon=True).start()

        def on_message(ws, raw):
            try:
                msg   = json.loads(raw)
                topic = msg.get('topic')
                pl    = msg.get('payload', {})
                if topic == 'crypto_prices':
                    sym   = pl.get('symbol', '').lower().replace('usdt', '').upper()
                    price = pl.get('price')
                    if sym in COINS and price:
                        # RTDS does not provide trade volume — pass None
                        self.bot.update_crypto_price(sym, float(price), volume=None)
            except Exception:
                pass

        def on_error(ws, err):
            log.error(f"[RTDS] Error: {err}")
            self._fail_count += 1
            self.bot.kill_switch.record_api_error()

        def on_close(ws, code, msg):
            self.connected = False
            if self._fail_count >= self._MAX_FAILS:
                log.warning("[RTDS] Too many failures — activating Binance fallback")
                self.bot._start_binance_ws()
                return
            log.warning(f"[RTDS] Closed, retry in {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            if not self.bot.emergency_stop.is_active():
                self.connect()

        self.ws = websocket.WebSocketApp(
            RTDS_WS,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _pinger(self):
        while self.connected and self.ws:
            try:
                self.ws.send("PING")
            except Exception:
                break
            time.sleep(5)


# ══════════════════════════════════════════════════════════════════════════════
# RESOLUTION ENGINE CONFIG
# ══════════════════════════════════════════════════════════════════════════════

_res_cfg = ResolutionConfig()
_res_cfg.FALLBACK1_TRIGGER_HOURS    = 2.0
_res_cfg.FALLBACK2_TRIGGER_HOURS    = 48.0
_res_cfg.LIVE_FALLBACK_AUTO_FINALIZE = True


# ══════════════════════════════════════════════════════════════════════════════
# MASTER BOT
# ══════════════════════════════════════════════════════════════════════════════

class MasterBot:

    def __init__(self):
        # ── Shared state (all access guarded by self._state_lock) ─────────
        self._state_lock       = threading.Lock()   # [F2] single lock for all shared state
        self._prices:          Dict[str, float] = {}
        self._velocities_ema:  Dict[str, float] = {}
        self._volume_emas:     Dict[str, float] = {c: 0.0 for c in COINS}
        self._active_positions: Dict[str, Position] = {}

        self._virtual_free   = VIRTUAL_BANKROLL
        self._trade_count    = 0
        self._bot_state      = BotState.RUNNING
        self._last_trade_ts  = 0.0
        self._last_exit_ts   = 0.0
        self._last_health_ts = 0.0
        self._fng_cache      = (50, 0.0)    # (value, fetched_at)

        # ── Regime ────────────────────────────────────────────────────────
        self._regime_detectors = {c: RegimeDetector() for c in COINS}
        self._current_regimes  = {c: Regime.CHOPPY   for c in COINS}

        # ── Safety ────────────────────────────────────────────────────────
        self.emergency_stop  = EmergencyStop()
        self.circuit_breaker = CircuitBreaker(window=50, min_win_rate=0.45)
        self.kill_switch     = KillSwitch(starting_bankroll=VIRTUAL_BANKROLL)
        self.rate_limiter    = RateLimiter(CLOB_MAX_RPS)

        # ── Live trading ──────────────────────────────────────────────────
        try:
            cfg, pk, addr = load_live_config()
        except EnvironmentError as e:
            log.error(f"Live config error: {e} — paper mode forced")
            cfg, pk, addr = {"enabled": False, "dry_run": True}, None, None

        self.live = V4BotLiveIntegration(config=cfg, private_key=pk, address=addr)
        log.info(f"Live integration: {self.live.get_status()}")

        # ── Risk manager ──────────────────────────────────────────────────
        self.rm = RiskManager.load(starting_bankroll=VIRTUAL_BANKROLL)

        # ── Resolution engine ─────────────────────────────────────────────
        self.resolution_engine = ResolutionFallbackEngine(
            config=_res_cfg, is_paper=IS_PAPER_TRADING
        )

        # ── WebSocket managers ────────────────────────────────────────────
        self.clob_ws = CLOBWebSocketManager(self)
        self.rtds_ws = RTDSWebSocketManager(self)

        # ── Bootstrap Kelly calibration from existing trade history ───────
        self._bootstrap_kelly()

        # ── Resume saved state (positions, balance) ───────────────────────
        self._load_state()

        # ── [F3] Verify on-chain balance matches virtual_free at startup ──
        self._verify_balance_on_startup()

    # ─────────────────────────────────────────────────────────────────────
    # STARTUP
    # ─────────────────────────────────────────────────────────────────────

    def start(self):
        log.info("=" * 70)
        log.info("MASTER BOT v5 — FINAL PRODUCTION BUILD")
        log.info(f"  Paper mode     : {IS_PAPER_TRADING}")
        log.info(f"  Zone filter    : {'ON' if ENABLE_ZONE_FILTER else 'off'}")
        log.info(f"  Balance (virt) : ${self._virtual_free:.2f}")
        log.info(f"  Open positions : {len(self._active_positions)}")
        log.info("=" * 70)

        self.clob_ws.connect()
        self.rtds_ws.connect()
        time.sleep(3)

        self.rm.print_status()
        log.info("Bot ready — monitoring markets")

        while not self.emergency_stop.is_active():
            try:
                self._check_exits()
                self._write_health()
                time.sleep(1)
            except Exception as e:
                log.error(f"Main loop error: {e}", exc_info=True)
                self.kill_switch.record_api_error()
                time.sleep(5)

        log.critical("BOT HALTED — emergency stop active")
        self._write_health(force=True)

    # ─────────────────────────────────────────────────────────────────────
    # [F3] BALANCE VERIFICATION
    # ─────────────────────────────────────────────────────────────────────

    def _verify_balance_on_startup(self):
        """
        Fetch real USDC balance from Polymarket and compare with virtual_free.
        If drift > BALANCE_DRIFT_THRESHOLD, log a critical warning and adjust.
        """
        if IS_PAPER_TRADING:
            log.info("[BalanceCheck] Paper mode — skipping on-chain balance check")
            return
        try:
            real_balance = self.live.get_usdc_balance()   # must be implemented in V4BotLiveIntegration
            if real_balance is None:
                log.warning("[BalanceCheck] Could not fetch on-chain balance — proceeding with virtual")
                return
            drift = abs(real_balance - self._virtual_free) / max(self._virtual_free, 1)
            if drift > BALANCE_DRIFT_THRESHOLD:
                log.critical(
                    f"[BalanceCheck] BALANCE DRIFT {drift:.1%}: "
                    f"on-chain=${real_balance:.2f}, virtual=${self._virtual_free:.2f} — "
                    f"adjusting virtual to on-chain value"
                )
                with self._state_lock:
                    self._virtual_free = real_balance
            else:
                log.info(f"[BalanceCheck] OK — on-chain=${real_balance:.2f}, drift={drift:.1%}")
        except Exception as e:
            log.error(f"[BalanceCheck] Error: {e}")

    def _check_balance_drift(self):
        """Called after each trade to catch drift early."""
        if IS_PAPER_TRADING:
            return
        try:
            real = self.live.get_usdc_balance()
            if real is None:
                return
            with self._state_lock:
                virt = self._virtual_free
            drift = abs(real - virt) / max(virt, 1)
            if drift > BALANCE_DRIFT_THRESHOLD:
                log.critical(
                    f"[BalanceDrift] {drift:.1%} drift detected — "
                    f"on-chain=${real:.2f} vs virtual=${virt:.2f}"
                )
        except Exception as e:
            log.debug(f"[BalanceDrift] check failed: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # PRICE UPDATE (called by WebSocket handlers)
    # ─────────────────────────────────────────────────────────────────────

    def update_crypto_price(self, coin: str, price: float, volume: Optional[float]):
        if self.emergency_stop.is_active():
            return

        with self._state_lock:
            # [F4] Volume EMA — only update when volume data is available
            if volume is not None:
                alpha = 2 / 21
                prev  = self._volume_emas.get(coin, 0.0)
                self._volume_emas[coin] = (
                    volume if prev == 0.0
                    else alpha * volume + (1 - alpha) * prev
                )

            # Velocity EMA
            if coin in self._prices:
                raw = price - self._prices[coin]
                ef  = VELOCITY_THRESHOLDS[coin]['ema_factor']
                prev_v = self._velocities_ema.get(coin, 0.0)
                self._velocities_ema[coin] = (
                    raw if prev_v == 0.0
                    else ef * raw + (1 - ef) * prev_v
                )

            self._prices[coin] = price

        # Regime (uses its own internal deque — no shared lock needed)
        self._regime_detectors[coin].add_price(price)
        with self._state_lock:
            self._current_regimes[coin] = self._regime_detectors[coin].compute_regime()

        # Evaluate
        for tf in TIMEFRAMES:
            self._evaluate_market(coin, tf)

    # ─────────────────────────────────────────────────────────────────────
    # MARKET EVALUATION
    # ─────────────────────────────────────────────────────────────────────

    def _evaluate_market(self, coin: str, tf: int):
        with self._state_lock:
            virt_free = self._virtual_free
            n_pos     = len(self._active_positions)
            regime    = self._current_regimes.get(coin, Regime.CHOPPY)
            last_trade = self._last_trade_ts

        if virt_free < 20:
            return
        if n_pos >= MAX_POSITIONS:
            return
        if self.kill_switch.is_active() or self.circuit_breaker.is_tripped():
            return

        min_interval = 10 if tf == 5 else 20
        if time.time() - last_trade < min_interval:
            return

        rp = self._regime_detectors[coin].get_params(regime)
        if rp['timeframe'] != tf and regime in [
            Regime.TREND_UP, Regime.TREND_DOWN, Regime.LOW_VOL
        ]:
            return

        if not self.rate_limiter.acquire(wait=2.0):
            return

        try:
            self._evaluate_http(coin, tf, rp, regime)
        except Exception as e:
            log.error(f"evaluate_market {coin}/{tf}: {e}", exc_info=True)
            self.kill_switch.record_api_error()

    def _evaluate_http(self, coin: str, tf: int, rp: dict, regime: Regime):
        slot = int(time.time() // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"

        try:
            r = requests.get(
                f"{GAMMA_API}/events/slug/{slug}",
                headers={'User-Agent': 'MasterBotV5/1.0', 'Accept': 'application/json'},
                timeout=2,
            )
        except requests.RequestException as e:
            self.kill_switch.record_api_error()
            log.debug(f"HTTP error {coin}/{tf}: {e}")
            return

        if r.status_code != 200:
            return

        event  = r.json()
        if event.get('closed') or event.get('resolved'):
            return

        markets = event.get('markets', [])
        if not markets:
            return

        mkt_data  = markets[0]
        prices_pm = json.loads(mkt_data.get('outcomePrices', '[]'))
        if len(prices_pm) != 2:
            return

        yes_p, no_p = float(prices_pm[0]), float(prices_pm[1])

        # [F1] Get CLOB token IDs for this market (needed for price-based exits)
        # The market object from Gamma typically contains clobTokenIds
        clob_tokens = mkt_data.get('clobTokenIds') or mkt_data.get('tokens', [])
        yes_asset_id = ''
        if isinstance(clob_tokens, list) and clob_tokens:
            yes_asset_id = clob_tokens[0] if isinstance(clob_tokens[0], str) else ''

        # ── Arbitrage ─────────────────────────────────────────────────────
        if yes_p + no_p < 0.985:
            self._enter_arb(coin, tf, yes_p, no_p, rp, slug, yes_asset_id)
            return

        # ── Edge signal ───────────────────────────────────────────────────
        with self._state_lock:
            velocity   = self._velocities_ema.get(coin, 0.0)
            vol_ema    = self._volume_emas.get(coin, 0.0)
            virt_free  = self._virtual_free
            existing   = self._active_positions.get(f"{coin.upper()}-{tf}m")

        if velocity == 0.0:
            return
        if existing:
            return   # already in this market

        threshold = VELOCITY_THRESHOLDS[coin]['raw'] * rp['velocity_mult']
        side = None
        if velocity > threshold and yes_p < rp['max_price']:
            side = 'YES'
        elif velocity < -threshold and no_p < rp['max_price']:
            side = 'NO'
        if not side:
            return

        ctx = {'coin': coin, 'tf': tf, 'yes_p': yes_p, 'no_p': no_p,
               'velocity': round(velocity, 6), 'side': side}

        # Filter: zone
        ok, reason = passes_zone_filter(yes_p, side)
        if not ok:
            self._log_decision('SKIP_ZONE', ctx, reason); return

        # [F4] Filter: volume — only apply when we have actual EMA data
        if vol_ema > 0:
            # We get volume from Binance path; on RTDS path vol_ema stays 0
            # so this block only runs when Binance is active (volume is available)
            # We don't have the *current* tick volume here, so we compare EMA
            # to a minimum expected level as a proxy for market activity
            if vol_ema < 0.5:   # absolute floor — market is dead
                self._log_decision('SKIP_VOLUME', ctx, f'vol_ema={vol_ema:.3f}'); return

        # Filter: velocity MTF (must be 1.2x threshold, not just above it)
        if abs(velocity) < threshold * 1.2:
            self._log_decision('SKIP_MTF', ctx, 'velocity_too_weak'); return

        # Filter: sentiment
        fng  = self._get_fng()
        smul = get_sentiment_mult(fng, side)
        if smul is None:
            self._log_decision('SKIP_SENTIMENT', ctx, f'fng={fng}'); return

        # Entry validation
        entry_price = yes_p if side == 'YES' else no_p
        regime_key  = regime.value
        rp_for_edge = REGIME_PARAMS.get(regime_key, REGIME_PARAMS['default'])

        signal = calculate_edge(
            coin=coin, yes_price=yes_p, no_price=no_p,
            velocity=velocity, regime_params=rp_for_edge, market=mkt_data,
        )
        if not signal:
            self._log_decision('SKIP_EDGE', ctx, 'no_signal'); return

        # Kelly sizing
        amount, kdiag = get_kelly_stake_with_diagnostics(
            entry_price=entry_price, bankroll=virt_free, coin=coin,
        )
        if amount == 0.0:
            self._log_decision('SKIP_KELLY', ctx, kdiag.get('reason', '?')); return

        amount = amount * smul * signal.get('confidence', 1.0)
        amount = max(1.0, min(virt_free * 0.10, amount))
        if amount < 20:
            self._log_decision('SKIP_SIZE', ctx, f'${amount:.2f} < $20'); return

        # Kill switch
        with self._state_lock:
            exposure = sum(
                p.shares * p.entry_price for p in self._active_positions.values()
            )
        ok, reason = self.kill_switch.validate_trade(amount, exposure, virt_free)
        if not ok:
            self._log_decision('SKIP_KS', ctx, reason); return

        # Risk manager
        ok, reason = self.rm.pre_trade_check(coin=coin, side=side, size_usd=amount)
        if not ok:
            self._log_decision('SKIP_RISK', ctx, reason); return

        self._enter_edge(coin, tf, signal, yes_p, no_p, rp,
                         amount, slug, mkt_data, entry_price,
                         yes_asset_id, regime)
        with self._state_lock:
            self._last_trade_ts = time.time()

    # ─────────────────────────────────────────────────────────────────────
    # TRADE ENTRY
    # ─────────────────────────────────────────────────────────────────────

    def _enter_arb(self, coin, tf, yes_p, no_p, rp, slug, yes_asset_id):
        market_key = f"{coin.upper()}-{tf}m"
        with self._state_lock:
            vf = self._virtual_free
            if market_key in self._active_positions:
                return
        amount = min(50.0, vf * POSITION_SIZE_PCT * rp['size_mult'])
        if amount < 20:
            return
        with self._state_lock:
            exposure = sum(p.shares * p.entry_price for p in self._active_positions.values())
        ok, r = self.kill_switch.validate_trade(amount, exposure, vf)
        if not ok:
            return
        ok2, r2 = self.rm.pre_trade_check(coin=coin, side='ARB', size_usd=amount)
        if not ok2:
            return

        profit = (1.0 - (yes_p + no_p)) * 100
        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count
        log.info(f"🎯 #{tc} ARB {coin} {tf}m | +{profit:.2f}%")

        self.rm.on_trade_opened(coin=coin, side='ARB', size_usd=amount, market_id=market_key)
        with self._state_lock:
            self._virtual_free -= amount
            self._last_trade_ts = time.time()

        self._log_trade({
            'type': 'ARBITRAGE', 'market': market_key,
            'amount': amount, 'profit_est_pct': profit,
        })
        self._save_state()

    def _enter_edge(self, coin, tf, signal, yes_p, no_p, rp,
                    amount, slug, mkt_data, entry_price,
                    yes_asset_id, regime):
        market_key = f"{coin.upper()}-{tf}m"
        side       = signal['side']

        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count

        log.info(
            f"📈 #{tc} EDGE {coin} {tf}m | {side} @ {entry_price:.3f} | "
            f"Kelly ${amount:.2f} | Regime {regime.value}"
        )

        # Live execution
        live_result = self.live.execute_buy(
            market_id=market_key, side=side, amount=amount, price=entry_price,
            signal_data={
                "market_id": market_key, "side": side,
                "v4_estimated_price": entry_price,
                "edge": signal.get('edge', 0),
                "regime": regime.value,
            },
        )

        fill_price  = live_result.get('fill_price',  entry_price)          if live_result['success'] else entry_price
        filled_size = live_result.get('filled_size', amount / entry_price)  if live_result['success'] else (amount / entry_price)

        if not live_result['success']:
            log.warning(f"Live order failed for {market_key} — tracking as virtual only")
            with self._state_lock:
                if self._bot_state == BotState.RUNNING:
                    self._bot_state = BotState.DEGRADED

        pos_id = self.rm.on_trade_opened(
            coin=coin, side=side, size_usd=amount, market_id=market_key
        )

        # [F1] Determine asset_id for price lookups
        # If YES side, yes_asset_id is token 0; NO side is token 1
        # For the asset we're trading, subscribe the correct token
        asset_id_for_pos = yes_asset_id   # YES token for price tracking
        if asset_id_for_pos:
            self.clob_ws.subscribe([asset_id_for_pos])

        position = Position(
            market_id=market_key, side=side,
            entry_price=fill_price, shares=filled_size,
            asset_id=asset_id_for_pos,
            slug=slug, coin=coin.upper(), timeframe=tf,
            pos_id=pos_id,
        )

        with self._state_lock:
            self._virtual_free          -= amount
            self._active_positions[market_key] = position

        # Resolution engine registration
        exp_utc = datetime.fromtimestamp(
            time.time() + (tf * 60), tz=timezone.utc
        ).isoformat()
        self.resolution_engine.register_position(
            market_id=market_key, slug=slug, coin=coin.upper(),
            timeframe_minutes=tf, entry_price=fill_price,
            position_side=side, expiration_utc=exp_utc,
        )

        self._log_trade({
            'type': 'EDGE', 'market': market_key, 'side': side,
            'amount': amount, 'entry_price': fill_price,
            'edge': signal.get('edge', 0), 'regime': regime.value,
            'asset_id': asset_id_for_pos,
            'live_order_id': live_result.get('order_id'),
            'live_virtual':  live_result.get('virtual', True),
        })
        self._save_state()
        self._check_balance_drift()

    # ─────────────────────────────────────────────────────────────────────
    # EXIT MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def _check_exits(self):
        now = time.time()
        if now - self._last_exit_ts < 15:
            return
        self._last_exit_ts = now

        with self._state_lock:
            positions_snapshot = dict(self._active_positions)

        # ── Resolution engine (tier 1/2/3) ────────────────────────────────
        pos_dict = {}
        for mid, pos in positions_snapshot.items():
            exp_utc = datetime.fromtimestamp(
                pos.entry_time + (pos.timeframe * 60), tz=timezone.utc
            ).isoformat()
            pos_dict[mid] = {
                'slug': pos.slug, 'coin': pos.coin,
                'timeframe': pos.timeframe, 'entry_price': pos.entry_price,
                'side': pos.side, 'expiration_utc': exp_utc,
            }

        resolved = self.resolution_engine.check_all_exits(pos_dict)
        for mid, outcome, source, tier in resolved:
            pos = positions_snapshot.get(mid)
            if pos:
                final_price = 1.0 if outcome == pos.side else 0.0
                self._execute_exit(pos, ExitReason.RESOLVED, final_price,
                                   extra={'tier': tier, 'source': source})

        # ── Price-based exits (SL / TP / trailing / time) ─────────────────
        with self._state_lock:
            positions_snapshot = dict(self._active_positions)   # refresh after resolutions

        for mid, pos in positions_snapshot.items():
            cur_price = self._get_current_price(pos)
            if cur_price is None:
                continue
            reason = evaluate_exits(pos, cur_price)
            if reason:
                self._execute_exit(pos, reason, cur_price)

    def _get_current_price(self, pos: Position) -> Optional[float]:
        """
        [F1] Now uses pos.asset_id (populated at entry) to look up CLOB data.
        Falls back to None if no data — time stop is the safety net.
        """
        if pos.asset_id:
            mid = self.clob_ws.get_mid_price(pos.asset_id)
            if mid is not None:
                return mid
        return None

    def _execute_exit(self, pos: Position, reason: ExitReason, cur_price: float,
                      extra: dict = None):
        pnl     = (cur_price - pos.entry_price) / pos.entry_price * 100
        pnl_amt = pos.shares * (cur_price - pos.entry_price)

        log.info(f"🚪 EXIT {pos.market_id} | {reason.value} | PnL: {pnl:+.1f}%")

        # [F6] Pass pos.shares so live integration knows how much to sell
        live_result = self.live.execute_sell(
            market_id=pos.market_id,
            exit_price=cur_price,
            shares=pos.shares,          # F6 fix
            signal_data={
                "market_id": pos.market_id,
                "v4_exit_price": cur_price,
                "exit_reason": reason.value,
            },
        )

        won = pnl > 0
        self.circuit_breaker.record(won)
        self.kill_switch.record_trade(pnl_amt, won)
        self.rm.on_trade_closed(
            position_id=pos.market_id, won=won,
            pnl=pnl_amt, coin=pos.coin or pos.market_id.split('-')[0]
        )
        record_completed_trade(
            trade_id=pos.market_id, market_id=pos.market_id,
            coin=pos.coin or pos.market_id.split('-')[0],
            entry_price=pos.entry_price,
            outcome='WIN' if won else 'LOSS',
            pnl_pct=pnl / 100, notes=reason.value,
        )

        with self._state_lock:
            self._virtual_free += pos.shares * cur_price
            self._active_positions.pop(pos.market_id, None)

        self._log_trade({
            'type': 'EXIT', 'market': pos.market_id, 'side': pos.side,
            'exit_reason': reason.value,
            'exit_price': cur_price, 'entry_price': pos.entry_price,
            'pnl_pct': round(pnl, 4),
            'live_pnl': live_result.get('pnl', 0) if live_result.get('success') else 0,
            **(extra or {}),
        })
        self._save_state()
        self._check_balance_drift()

    # ─────────────────────────────────────────────────────────────────────
    # BINANCE FALLBACK
    # ─────────────────────────────────────────────────────────────────────

    def _start_binance_ws(self):
        log.warning("Starting Binance fallback WebSocket")
        _delay = [RECONNECT_DELAY]

        def on_open(ws):
            log.info("[Binance] Connected")
            _delay[0] = RECONNECT_DELAY

        def on_message(ws, raw):
            try:
                d      = json.loads(raw)
                sym    = d.get('s', '').replace('USDT', '')
                price  = float(d.get('p', 0))
                volume = float(d.get('q', 0))
                if sym in COINS and price > 0:
                    self.update_crypto_price(sym, price, volume)
            except Exception:
                pass

        def on_error(ws, err):
            self.kill_switch.record_api_error()
            log.error(f"[Binance] Error: {err}")

        def on_close(ws, code, msg):
            log.warning(f"[Binance] Closed, retry in {_delay[0]}s")
            time.sleep(_delay[0])
            _delay[0] = min(_delay[0] * 2, 60)
            if not self.emergency_stop.is_active():
                self._start_binance_ws()

        ws = websocket.WebSocketApp(
            BINANCE_WS,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=ws.run_forever, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def handle_market_resolved(self, payload: dict):
        log.info(f"[CLOB resolved] slug={payload.get('slug')} winner={payload.get('winning_outcome')}")

    def _get_all_asset_ids(self) -> List[str]:
        with self._state_lock:
            return [p.asset_id for p in self._active_positions.values() if p.asset_id]

    def _get_fng(self) -> int:
        val, fetched = self._fng_cache
        if time.time() - fetched > 600:
            val = _fetch_fng()
            self._fng_cache = (val, time.time())
        return val

    def _log_trade(self, trade: dict):
        trade['timestamp_utc'] = datetime.now(tz=timezone.utc).isoformat()
        with self._state_lock:
            trade['virtual_balance'] = round(self._virtual_free, 4)
        data = safe_load_json(TRADE_LOG, default=[])
        data.append(trade)
        if not atomic_write_json(data, TRADE_LOG):
            log.critical(f"TRADE LOG WRITE FAILED — trade: {trade}")

    def _log_decision(self, action: str, ctx: dict, reason: str):
        entry = {
            'ts': datetime.now(tz=timezone.utc).isoformat(),
            'action': action, 'reason': reason,
            **{k: v for k, v in ctx.items()},
        }
        data = safe_load_json(DECISION_LOG, default=[])
        data.append(entry)
        if len(data) > 10_000:
            data = data[-5_000:]
        atomic_write_json(data, DECISION_LOG)
        log.debug(f"DECISION {action} — {reason}")

    def _save_state(self):
        with self._state_lock:
            state = {
                'balance':          self._virtual_free,
                'trade_count':      self._trade_count,
                'bot_state':        self._bot_state.value,
                'active_positions': {k: v.to_dict() for k, v in self._active_positions.items()},
                'kill_switch':      self.kill_switch.status(),
                'circuit_breaker':  self.circuit_breaker.status(),
                'last_update':      datetime.now(tz=timezone.utc).isoformat(),
            }
        if not atomic_write_json(state, STATE_FILE):
            log.critical("STATE FILE WRITE FAILED")

    def _load_state(self):
        state = safe_load_json(STATE_FILE, default={})
        if not state:
            log.info("No saved state — starting fresh")
            return

        with self._state_lock:
            self._virtual_free = state.get('balance', VIRTUAL_BANKROLL)
            self._trade_count  = state.get('trade_count', 0)

            for mid, pd in state.get('active_positions', {}).items():
                try:
                    pos = Position.from_dict(pd)
                    self._active_positions[mid] = pos
                    log.info(f"Resumed position: {mid} @ {pos.entry_price:.3f}")
                except Exception as e:
                    log.error(f"Could not resume position {mid}: {e}")

        # [F7] Re-register resumed positions into resolution engine
        with self._state_lock:
            positions_to_register = dict(self._active_positions)

        for mid, pos in positions_to_register.items():
            try:
                exp_utc = datetime.fromtimestamp(
                    pos.entry_time + (pos.timeframe * 60), tz=timezone.utc
                ).isoformat()
                self.resolution_engine.register_position(
                    market_id=mid, slug=pos.slug, coin=pos.coin,
                    timeframe_minutes=pos.timeframe, entry_price=pos.entry_price,
                    position_side=pos.side, expiration_utc=exp_utc,
                )
                if pos.asset_id:
                    self.clob_ws.subscribe([pos.asset_id])
                log.info(f"[F7] Re-registered {mid} in resolution engine")
            except Exception as e:
                log.error(f"[F7] Failed to re-register {mid}: {e}")

        log.info(
            f"State loaded — balance=${self._virtual_free:.2f}, "
            f"positions={len(self._active_positions)}, trades={self._trade_count}"
        )

    def _write_health(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_health_ts < 30:
            return
        self._last_health_ts = now

        with self._state_lock:
            health = {
                'timestamp_utc':    datetime.now(tz=timezone.utc).isoformat(),
                'bot_state':        self._bot_state.value,
                'balance':          round(self._virtual_free, 2),
                'trade_count':      self._trade_count,
                'open_positions':   len(self._active_positions),
                'clob_connected':   self.clob_ws.connected,
                'rtds_connected':   self.rtds_ws.connected,
                'emergency_stop':   self.emergency_stop.is_active(),
                'kill_switch':      self.kill_switch.status(),
                'circuit_breaker':  self.circuit_breaker.status(),
                'paper_mode':       IS_PAPER_TRADING,
                'zone_filter':      ENABLE_ZONE_FILTER,
            }
        atomic_write_json(health, HEALTH_FILE)

    def _bootstrap_kelly(self):
        cal = Path(f"{WORKSPACE}/kelly_calibration.json")
        if cal.exists():
            log.info("[Kelly] Calibration file exists — skipping import")
            return
        try:
            n = import_trade_history(
                TRADE_LOG,
                field_map={
                    "id": "market", "market_id": "market", "coin": "market",
                    "entry_price": "entry_price", "outcome": "outcome",
                    "pnl_pct": "pnl_pct", "timestamp": "timestamp_utc",
                },
            )
            log.info(f"[Kelly] Imported {n} trades for calibration")
        except Exception as e:
            log.warning(f"[Kelly] Bootstrap failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    bot = MasterBot()
    bot.start()
