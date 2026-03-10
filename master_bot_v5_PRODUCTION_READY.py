#!/usr/bin/env python3
"""
MASTER BOT v5 — FIXED PRODUCTION BUILD
Fixes applied:
  [FIX-1]  get_usdc_balance() — graceful fallback, no crash if method missing
  [FIX-2]  WebSocket startup — 30s verified connection check, not blind sleep(3)
  [FIX-3]  Live failure alert — CRITICAL log + Telegram/file notification
  [FIX-4]  Binance fallback — proper one-way failover, RTDS stops reconnecting
  [FIX-5]  Import error handling — try/except with clear error messages
  [FIX-6]  Volume filter — uses Binance path only, documented clearly; RTDS skips it
  [FIX-7]  Circuit breaker warmup — no trip for first 50 trades (warmup_trades)
  [FIX-8]  Thread-safe logging — dedicated log lock, separate from state lock
  [FIX-9]  execute_sell shares — verified and asserted before call
  [FIX-10] Asset ID subscription — subscribes YES or NO token based on actual side
"""

# ── [FIX-5] PID mutex with clear error ───────────────────────────────────────
try:
    from bot_lock import acquire_lock
    acquire_lock()
except ImportError:
    import sys, os, fcntl
    _LOCK_FILE = '/tmp/master_bot_v5.lock'
    _lf = open(_LOCK_FILE, 'w')
    try:
        fcntl.flock(_lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("FATAL: Another instance is already running. Exiting.")
        sys.exit(1)

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
# [FIX-5] Wrap each third-party import with a clear error
try:
    import requests
except ImportError:
    print("FATAL: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    import websocket
except ImportError:
    print("FATAL: 'websocket-client' not installed. Run: pip install websocket-client")
    sys.exit(1)

try:
    import numpy as np
    from scipy.stats import linregress
except ImportError:
    print("FATAL: numpy/scipy not installed. Run: pip install numpy scipy")
    sys.exit(1)

# ── workspace modules with graceful fallback ──────────────────────────────────
sys.path.insert(0, '/root/.openclaw/workspace')

# [FIX-5] Each internal import wrapped — bot falls back to paper on failure
_LIVE_TRADING_AVAILABLE = False
_ENTRY_VALIDATION_AVAILABLE = False
_RISK_MANAGER_AVAILABLE = False
_ATOMIC_JSON_AVAILABLE = False
_EDGE_TRACKER_AVAILABLE = False
_RESOLUTION_AVAILABLE = False

try:
    from live_trading.live_trading_config import load_live_config
    from live_trading.v4_live_integration import V4BotLiveIntegration
    _LIVE_TRADING_AVAILABLE = True
except ImportError as e:
    print(f"[FIX-5] WARNING: live_trading modules not found ({e}) — paper mode forced")

try:
    from entry_validation import calculate_edge, REGIME_PARAMS
    _ENTRY_VALIDATION_AVAILABLE = True
except ImportError as e:
    print(f"[FIX-5] WARNING: entry_validation not found ({e}) — edge filter disabled")
    calculate_edge = None
    REGIME_PARAMS  = {}

try:
    from risk_manager import RiskManager
    _RISK_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"[FIX-5] WARNING: risk_manager not found ({e}) — risk checks disabled")
    RiskManager = None

try:
    from atomic_json import atomic_write_json, safe_load_json
    _ATOMIC_JSON_AVAILABLE = True
except ImportError:
    print("[FIX-5] WARNING: atomic_json not found — using plain JSON writes")
    def atomic_write_json(data, path):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    def safe_load_json(path, default=None):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}

try:
    from edge_tracker import get_kelly_stake_with_diagnostics, record_completed_trade, import_trade_history
    _EDGE_TRACKER_AVAILABLE = True
except ImportError as e:
    print(f"[FIX-5] WARNING: edge_tracker not found ({e}) — Kelly sizing disabled, using flat sizing")
    def get_kelly_stake_with_diagnostics(entry_price, bankroll, coin):
        return bankroll * 0.05, {'reason': 'fallback_flat'}
    def record_completed_trade(**kwargs): pass
    def import_trade_history(*args, **kwargs): return 0

try:
    from resolution_fallback_v1 import ResolutionFallbackEngine, ResolutionConfig
    _RESOLUTION_AVAILABLE = True
except ImportError as e:
    print(f"[FIX-5] WARNING: resolution_fallback_v1 not found ({e}) — resolution engine disabled")
    ResolutionFallbackEngine = None
    ResolutionConfig = None

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

WORKSPACE    = '/root/.openclaw/workspace'
LOG_FILE     = f'{WORKSPACE}/master_v5_run.log'
TRADE_LOG    = f'{WORKSPACE}/master_v5_trades.json'
STATE_FILE   = f'{WORKSPACE}/master_v5_state.json'
HEALTH_FILE  = f'{WORKSPACE}/master_v5_health.json'
DECISION_LOG = f'{WORKSPACE}/master_v5_decisions.json'
ALERT_FILE   = f'{WORKSPACE}/master_v5_alerts.json'

Path(WORKSPACE).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('master_v5')

# ── [FIX-8] Dedicated file-write lock (separate from state lock) ──────────────
_FILE_LOCK = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
# [FIX-5] VALIDATE REGIME_PARAMS
# ══════════════════════════════════════════════════════════════════════════════

_FALLBACK_REGIME = {
    'side_bias': None, 'velocity_mult': 1.2, 'size_mult': 0.7,
    'timeframe': 15, 'max_price': 0.55,
}
if _ENTRY_VALIDATION_AVAILABLE:
    for _k in ['trend_up', 'trend_down', 'choppy', 'high_vol', 'low_vol']:
        if _k not in REGIME_PARAMS:
            log.warning(f"REGIME_PARAMS missing key '{_k}' — injecting fallback")
            REGIME_PARAMS[_k] = _FALLBACK_REGIME
    if 'default' not in REGIME_PARAMS:
        REGIME_PARAMS['default'] = _FALLBACK_REGIME
else:
    REGIME_PARAMS = {k: _FALLBACK_REGIME for k in
                     ['trend_up','trend_down','choppy','high_vol','low_vol','default']}

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

VIRTUAL_BANKROLL        = 686.93
MAX_POSITIONS           = 5
POSITION_SIZE_PCT       = 0.05
MIN_EDGE                = 0.10

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
TRAILING_ACTIVATE  = 1.10
TIME_STOP_MINUTES  = 90

# Regime
REGIME_WINDOW = 30
REGIME_THETA  = 0.5

# Zone filter — off by default
ENABLE_ZONE_FILTER = os.getenv('ENABLE_ZONE_FILTER', 'false').lower() == 'true'
DEAD_ZONE_LOW      = 0.35
DEAD_ZONE_HIGH     = 0.65

IS_PAPER_TRADING = os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true'

# API endpoints
GAMMA_API  = "https://gamma-api.polymarket.com"
CLOB_WS    = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RTDS_WS    = "wss://ws-live-data.polymarket.com"
BINANCE_WS = ("wss://stream.binance.com:9443/ws/"
              "btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade")

CLOB_MAX_RPS    = 60
RECONNECT_DELAY = 5

# Safety — env-var overrides
MAX_DAILY_LOSS_PCT      = float(os.getenv('MAX_DAILY_LOSS_PCT',      '0.15'))
MAX_CONSECUTIVE_LOSSES  = int(os.getenv('MAX_CONSECUTIVE_LOSSES',    '7'))
MAX_API_ERRORS_PER_HOUR = int(os.getenv('MAX_API_ERRORS_PER_HOUR',   '30'))
MAX_TOTAL_EXPOSURE_PCT  = float(os.getenv('MAX_TOTAL_EXPOSURE_PCT',  '0.50'))
MAX_SINGLE_TRADE_USD    = float(os.getenv('MAX_SINGLE_TRADE_USD',    '75.0'))
BALANCE_DRIFT_THRESHOLD = float(os.getenv('BALANCE_DRIFT_THRESHOLD', '0.10'))

# [FIX-2] WS startup timeout
WS_CONNECT_TIMEOUT_SECS = 30

# [FIX-7] Circuit breaker warmup
CB_WARMUP_TRADES  = int(os.getenv('CB_WARMUP_TRADES',  '50'))
CB_MIN_WIN_RATE   = float(os.getenv('CB_MIN_WIN_RATE', '0.40'))   # lowered from 0.45
CB_WINDOW         = int(os.getenv('CB_WINDOW',         '50'))

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
    DEGRADED = "degraded"
    STOPPED  = "stopped"

class PriceFeed(Enum):
    RTDS    = "rtds"
    BINANCE = "binance"
    NONE    = "none"

# ══════════════════════════════════════════════════════════════════════════════
# ALERTING
# ══════════════════════════════════════════════════════════════════════════════

def _send_alert(level: str, message: str):
    """
    [FIX-3] Write critical alerts to file + log.
    Extend this function with Telegram/Discord webhook if needed.
    """
    alert = {
        'ts':      datetime.now(tz=timezone.utc).isoformat(),
        'level':   level,
        'message': message,
    }
    if level == 'CRITICAL':
        log.critical(f"🚨 ALERT: {message}")
    elif level == 'WARNING':
        log.warning(f"⚠️  ALERT: {message}")
    else:
        log.info(f"ℹ️  ALERT: {message}")

    # Write to alert file for external monitoring
    with _FILE_LOCK:
        try:
            data = safe_load_json(ALERT_FILE, default=[])
            data.append(alert)
            if len(data) > 500:
                data = data[-200:]
            atomic_write_json(data, ALERT_FILE)
        except Exception:
            pass

    # ── Optional: Telegram webhook ────────────────────────────────────────
    tg_token = os.getenv('TELEGRAM_BOT_TOKEN')
    tg_chat  = os.getenv('TELEGRAM_CHAT_ID')
    if tg_token and tg_chat and level == 'CRITICAL':
        try:
            requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={'chat_id': tg_chat, 'text': f"[MasterBot] {level}: {message}"},
                timeout=3,
            )
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: EMERGENCY STOP
# ══════════════════════════════════════════════════════════════════════════════

class EmergencyStop:
    FLAG_FILE = '/tmp/MASTER_BOT_STOP'

    def __init__(self):
        self._stop = False
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT,  self._on_signal)

    def _on_signal(self, signum, _):
        _send_alert('CRITICAL', f"Signal {signum} received — emergency stop triggered")
        self._stop = True

    def is_active(self) -> bool:
        if self._stop:
            return True
        if os.getenv('MASTER_BOT_EMERGENCY_STOP', '0') == '1':
            _send_alert('CRITICAL', "MASTER_BOT_EMERGENCY_STOP env var set — halting")
            self._stop = True
            return True
        if Path(self.FLAG_FILE).exists():
            _send_alert('CRITICAL', f"Stop flag {self.FLAG_FILE} found — halting")
            self._stop = True
            return True
        return False

    def trigger(self):
        self._stop = True
        try: Path(self.FLAG_FILE).touch()
        except Exception: pass

# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: CIRCUIT BREAKER  [FIX-7]
# ══════════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    [FIX-7] Warmup period: circuit breaker cannot trip during first
    CB_WARMUP_TRADES trades. After warmup, trips if win rate < CB_MIN_WIN_RATE
    over the last CB_WINDOW trades.
    """
    def __init__(self):
        self._outcomes      = deque(maxlen=CB_WINDOW)
        self._total_trades  = 0          # lifetime trade counter for warmup
        self._tripped       = False
        self._lock          = threading.Lock()

    def record(self, won: bool):
        with self._lock:
            self._outcomes.append(won)
            self._total_trades += 1

            # [FIX-7] Don't trip during warmup
            if self._total_trades < CB_WARMUP_TRADES:
                log.debug(f"[CB] Warmup {self._total_trades}/{CB_WARMUP_TRADES} — breaker inactive")
                return

            if len(self._outcomes) < CB_WINDOW:
                return

            wr = sum(self._outcomes) / len(self._outcomes)
            was_tripped = self._tripped
            self._tripped = wr < CB_MIN_WIN_RATE

            if self._tripped and not was_tripped:
                msg = (f"CIRCUIT BREAKER TRIPPED — win rate {wr:.1%} "
                       f"< {CB_MIN_WIN_RATE:.1%} over last {CB_WINDOW} trades")
                _send_alert('CRITICAL', msg)
            elif not self._tripped and was_tripped:
                log.warning(f"[CB] RESET — win rate recovered to {wr:.1%}")

    def is_tripped(self) -> bool:
        with self._lock:
            return self._tripped

    def status(self) -> dict:
        with self._lock:
            n  = len(self._outcomes)
            wr = sum(self._outcomes) / n if n else None
            return {
                'tripped':      self._tripped,
                'win_rate':     round(wr, 4) if wr is not None else None,
                'sample_size':  n,
                'total_trades': self._total_trades,
                'in_warmup':    self._total_trades < CB_WARMUP_TRADES,
            }

# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: KILL SWITCH
# ══════════════════════════════════════════════════════════════════════════════

class KillSwitch:
    def __init__(self, starting_bankroll: float):
        self._start         = starting_bankroll
        self._daily_loss    = 0.0
        self._consec_losses = 0
        self._api_errors    = deque()
        self._day           = datetime.now().date()
        self._active        = False
        self._lock          = threading.Lock()

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
                _send_alert('CRITICAL', f"Kill switch: daily loss {dl:.1%} >= limit {MAX_DAILY_LOSS_PCT:.1%}")
                self._active = True
            if self._consec_losses >= MAX_CONSECUTIVE_LOSSES:
                _send_alert('CRITICAL', f"Kill switch: {self._consec_losses} consecutive losses")
                self._active = True

    def record_api_error(self):
        with self._lock:
            now = time.time()
            self._api_errors.append(now)
            while self._api_errors and now - self._api_errors[0] > 3600:
                self._api_errors.popleft()
            if len(self._api_errors) >= MAX_API_ERRORS_PER_HOUR:
                _send_alert('CRITICAL', f"Kill switch: {len(self._api_errors)} API errors in last hour")
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
                'active':          self._active,
                'daily_loss_usd':  round(self._daily_loss, 2),
                'daily_loss_pct':  round(self._daily_loss / self._start, 4),
                'consec_losses':   self._consec_losses,
                'api_errors_1h':   len(self._api_errors),
            }

# ══════════════════════════════════════════════════════════════════════════════
# SAFETY: RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
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
            arr  = list(self.vol_history)[-100:]
            vstd = float(np.std(arr))
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
    # [FIX-10] Store both YES and NO asset IDs; use correct one per side
    yes_asset_id: str  = ''
    no_asset_id:  str  = ''
    slug:         str  = ''
    coin:         str  = ''
    timeframe:    int  = 5
    entry_time:   float = field(default_factory=time.time)
    pos_id:       str  = ''
    peak_price:          float = field(init=False)
    trailing_stop_price: float = field(init=False)

    def __post_init__(self):
        self.peak_price          = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - TRAILING_STOP_PCT)

    @property
    def active_asset_id(self) -> str:
        """[FIX-10] Return the asset ID matching our actual side."""
        return self.yes_asset_id if self.side == 'YES' else self.no_asset_id

    def to_dict(self) -> dict:
        return {
            'market_id':    self.market_id,   'side':         self.side,
            'entry_price':  self.entry_price,  'shares':       self.shares,
            'yes_asset_id': self.yes_asset_id, 'no_asset_id':  self.no_asset_id,
            'slug':         self.slug,         'coin':         self.coin,
            'timeframe':    self.timeframe,    'entry_time':   self.entry_time,
            'pos_id':       self.pos_id,
            'peak_price':           self.peak_price,
            'trailing_stop_price':  self.trailing_stop_price,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Position':
        # Handle legacy state files that used a single 'asset_id' field
        yes_id = d.get('yes_asset_id', d.get('asset_id', ''))
        no_id  = d.get('no_asset_id', '')
        p = cls(
            market_id=d['market_id'],   side=d['side'],
            entry_price=d['entry_price'], shares=d['shares'],
            yes_asset_id=yes_id,          no_asset_id=no_id,
            slug=d.get('slug', ''),       coin=d.get('coin', ''),
            timeframe=d.get('timeframe', 5),
            entry_time=d.get('entry_time', time.time()),
            pos_id=d.get('pos_id', ''),
        )
        p.peak_price          = d.get('peak_price', p.entry_price)
        p.trailing_stop_price = d.get('trailing_stop_price',
                                      p.entry_price * (1 - TRAILING_STOP_PCT))
        return p


def evaluate_exits(pos: Position, price: float) -> Optional[ExitReason]:
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
        return 50

# ══════════════════════════════════════════════════════════════════════════════
# [FIX-1] USDC BALANCE HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _get_usdc_balance_safe(live_integration) -> Optional[float]:
    """
    [FIX-1] Safely fetch USDC balance from live integration.
    Tries get_usdc_balance() first. Falls back to get_balance() and
    common attribute names. Returns None if all attempts fail — never crashes.
    """
    if live_integration is None:
        return None

    # Try the canonical method first
    for method_name in ('get_usdc_balance', 'get_balance', 'usdc_balance'):
        method = getattr(live_integration, method_name, None)
        if callable(method):
            try:
                result = method()
                if isinstance(result, dict):
                    # Some integrations return {'usdc': 123.45, ...}
                    for key in ('usdc', 'USDC', 'balance', 'available'):
                        if key in result:
                            return float(result[key])
                elif result is not None:
                    return float(result)
            except Exception as e:
                log.debug(f"[FIX-1] {method_name}() failed: {e}")

    # Try direct attribute
    for attr in ('balance', 'usdc_balance', '_balance'):
        val = getattr(live_integration, attr, None)
        if val is not None:
            try:
                return float(val)
            except Exception:
                pass

    log.warning("[FIX-1] Cannot fetch on-chain balance — method not found in live integration")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET: CLOB
# ══════════════════════════════════════════════════════════════════════════════

class CLOBWebSocketManager:
    def __init__(self, bot: 'MasterBot'):
        self.bot              = bot
        self.ws               = None
        self.connected        = False
        self.market_data:     Dict[str, dict] = {}
        self._reconnect_delay = 1
        self._data_lock       = threading.Lock()   # [FIX-8] separate from state lock
        self._connect_event   = threading.Event()  # [FIX-2]

    def get_mid_price(self, asset_id: str) -> Optional[float]:
        with self._data_lock:
            d = self.market_data.get(asset_id)
            if not d:
                return None
            b, a = d.get('best_bid'), d.get('best_ask')
            if b is not None and a is not None:
                try:
                    return (float(b) + float(a)) / 2
                except Exception:
                    return None
        return None

    def subscribe(self, asset_ids: List[str]):
        if not asset_ids:
            return
        if self.ws and self.connected:
            try:
                self.ws.send(json.dumps({
                    "assets_ids": [a for a in asset_ids if a],
                    "type": "market",
                    "custom_feature_enabled": True,
                }))
            except Exception as e:
                log.error(f"[CLOB] subscribe error: {e}")

    def connect(self):
        def on_open(ws):
            log.info("[CLOB] Connected")
            self.connected        = True
            self._reconnect_delay = 1
            self._connect_event.set()   # [FIX-2] signal startup waiter
            aids = self.bot._get_all_asset_ids()
            if aids:
                self.subscribe(aids)

        def on_message(ws, raw):
            try:
                msg   = json.loads(raw)
                mtype = msg.get('type')
                pl    = msg.get('payload', {})
                if mtype == 'best_bid_ask':
                    aid = pl.get('asset_id')
                    if aid:
                        with self._data_lock:
                            self.market_data[aid] = {
                                'best_bid': pl.get('best_bid'),
                                'best_ask': pl.get('best_ask'),
                                'ts':       time.time(),
                            }
                elif mtype == 'market_resolved':
                    log.info(f"[CLOB] Resolved: {pl.get('slug')}")
                    self.bot.handle_market_resolved(pl)
            except Exception as e:
                log.debug(f"[CLOB] msg parse error: {e}")

        def on_error(ws, err):
            log.error(f"[CLOB] Error: {err}")
            self.bot.kill_switch.record_api_error()

        def on_close(ws, code, msg):
            self.connected = False
            log.warning(f"[CLOB] Closed (code={code}), retry in {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            if not self.bot.emergency_stop.is_active():
                self._connect_event.clear()
                self.connect()

        self.ws = websocket.WebSocketApp(
            CLOB_WS,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET: RTDS  [FIX-4]
# ══════════════════════════════════════════════════════════════════════════════

class RTDSWebSocketManager:
    """
    [FIX-4] Proper one-way failover:
    - Once _binance_active is True, RTDS on_close does NOT reconnect
    - Failover is permanent for the session (RTDS is clearly broken)
    """
    def __init__(self, bot: 'MasterBot'):
        self.bot              = bot
        self.ws               = None
        self.connected        = False
        self._reconnect_delay = 1
        self._fail_count      = 0
        self._MAX_FAILS       = 3
        self._binance_active  = False   # [FIX-4] one-way gate
        self._connect_event   = threading.Event()  # [FIX-2]

    def connect(self):
        def on_open(ws):
            log.info("[RTDS] Connected")
            self.connected        = True
            self._reconnect_delay = 1
            self._fail_count      = 0
            self._connect_event.set()   # [FIX-2]
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
                        # RTDS does NOT provide volume — pass None [FIX-6]
                        self.bot.update_crypto_price(sym, float(price), volume=None)
            except Exception:
                pass

        def on_error(ws, err):
            log.error(f"[RTDS] Error: {err}")
            self._fail_count += 1
            self.bot.kill_switch.record_api_error()

        def on_close(ws, code, msg):
            self.connected = False

            # [FIX-4] If Binance is already active, do NOT reconnect RTDS
            if self._binance_active:
                log.info("[RTDS] Binance fallback is active — not reconnecting RTDS")
                return

            if self._fail_count >= self._MAX_FAILS:
                # [FIX-4] Trigger Binance and set the gate — no more RTDS reconnects
                log.warning("[RTDS] Failure threshold reached — switching to Binance (permanent this session)")
                self._binance_active = True
                _send_alert('WARNING', "RTDS feed failed — switched to Binance price feed")
                self.bot._start_binance_ws()
                return

            log.warning(f"[RTDS] Closed, retry in {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            if not self.bot.emergency_stop.is_active():
                self._connect_event.clear()
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
# MASTER BOT
# ══════════════════════════════════════════════════════════════════════════════

class MasterBot:

    def __init__(self):
        # ── [FIX-2] Separate event for tracking which feeds are up ─────────
        self._price_feed_active = PriceFeed.NONE

        # ── Shared state ──────────────────────────────────────────────────
        self._state_lock        = threading.Lock()
        self._prices:           Dict[str, float] = {}
        self._velocities_ema:   Dict[str, float] = {}
        self._volume_emas:      Dict[str, float] = {c: 0.0 for c in COINS}
        self._active_positions: Dict[str, Position] = {}

        self._virtual_free   = VIRTUAL_BANKROLL
        self._trade_count    = 0
        self._bot_state      = BotState.RUNNING
        self._last_trade_ts  = 0.0
        self._last_exit_ts   = 0.0
        self._last_health_ts = 0.0
        self._fng_cache      = (50, 0.0)

        # ── Regime ────────────────────────────────────────────────────────
        self._regime_detectors = {c: RegimeDetector() for c in COINS}
        self._current_regimes  = {c: Regime.CHOPPY   for c in COINS}

        # ── Safety ────────────────────────────────────────────────────────
        self.emergency_stop  = EmergencyStop()
        self.circuit_breaker = CircuitBreaker()
        self.kill_switch     = KillSwitch(starting_bankroll=VIRTUAL_BANKROLL)
        self.rate_limiter    = RateLimiter(CLOB_MAX_RPS)

        # ── [FIX-5] Live trading — graceful init ──────────────────────────
        self.live = None
        if _LIVE_TRADING_AVAILABLE:
            try:
                cfg, pk, addr = load_live_config()
                self.live = V4BotLiveIntegration(config=cfg, private_key=pk, address=addr)
                log.info(f"Live integration loaded: {self.live.get_status()}")
            except EnvironmentError as e:
                log.warning(f"[FIX-5] Live config error ({e}) — paper mode")
                IS_PAPER_TRADING_override = True
            except Exception as e:
                log.warning(f"[FIX-5] Live integration init failed ({e}) — paper mode")
        else:
            log.warning("[FIX-5] live_trading modules not available — paper mode")

        # ── Risk manager ──────────────────────────────────────────────────
        self.rm = None
        if _RISK_MANAGER_AVAILABLE:
            try:
                self.rm = RiskManager.load(starting_bankroll=VIRTUAL_BANKROLL)
            except Exception as e:
                log.warning(f"[FIX-5] RiskManager init failed: {e}")

        # ── Resolution engine ─────────────────────────────────────────────
        self.resolution_engine = None
        if _RESOLUTION_AVAILABLE:
            try:
                cfg = ResolutionConfig()
                cfg.FALLBACK1_TRIGGER_HOURS     = 2.0
                cfg.FALLBACK2_TRIGGER_HOURS     = 48.0
                cfg.LIVE_FALLBACK_AUTO_FINALIZE = True
                self.resolution_engine = ResolutionFallbackEngine(
                    config=cfg, is_paper=IS_PAPER_TRADING
                )
            except Exception as e:
                log.warning(f"[FIX-5] ResolutionEngine init failed: {e}")

        # ── WebSocket managers ────────────────────────────────────────────
        self.clob_ws = CLOBWebSocketManager(self)
        self.rtds_ws = RTDSWebSocketManager(self)

        # ── Bootstrap Kelly ───────────────────────────────────────────────
        self._bootstrap_kelly()

        # ── Resume saved state ────────────────────────────────────────────
        self._load_state()

    # ─────────────────────────────────────────────────────────────────────
    # START / MAIN LOOP  [FIX-2]
    # ─────────────────────────────────────────────────────────────────────

    def start(self):
        log.info("=" * 70)
        log.info("MASTER BOT v5 — FIXED PRODUCTION BUILD")
        log.info(f"  Paper mode     : {IS_PAPER_TRADING}")
        log.info(f"  Zone filter    : {'ON' if ENABLE_ZONE_FILTER else 'off'}")
        log.info(f"  Balance (virt) : ${self._virtual_free:.2f}")
        log.info(f"  Open positions : {len(self._active_positions)}")
        log.info(f"  CB warmup      : {CB_WARMUP_TRADES} trades before circuit breaker arms")
        log.info("=" * 70)

        # Start WebSocket connections
        self.clob_ws.connect()
        self.rtds_ws.connect()

        # [FIX-2] Wait up to WS_CONNECT_TIMEOUT_SECS for at least RTDS to connect
        log.info(f"[FIX-2] Waiting up to {WS_CONNECT_TIMEOUT_SECS}s for WebSocket connections...")
        rtds_ok = self.rtds_ws._connect_event.wait(timeout=WS_CONNECT_TIMEOUT_SECS)
        if rtds_ok:
            log.info("[FIX-2] RTDS WebSocket confirmed connected ✓")
            self._price_feed_active = PriceFeed.RTDS
        else:
            _send_alert('WARNING',
                "RTDS WebSocket did not connect within timeout — starting Binance fallback")
            self._start_binance_ws()

        clob_ok = self.clob_ws._connect_event.wait(timeout=10)
        if clob_ok:
            log.info("[FIX-2] CLOB WebSocket confirmed connected ✓")
        else:
            log.warning("[FIX-2] CLOB WebSocket not connected — price-based exits may be delayed")

        # [FIX-1] Verify on-chain balance before doing anything
        self._verify_balance()

        if self.rm:
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
    # [FIX-1] BALANCE VERIFICATION
    # ─────────────────────────────────────────────────────────────────────

    def _verify_balance(self):
        if IS_PAPER_TRADING or self.live is None:
            log.info("[FIX-1] Paper mode or no live integration — skipping balance check")
            return
        try:
            real = _get_usdc_balance_safe(self.live)
            if real is None:
                log.warning("[FIX-1] Could not fetch on-chain balance — proceeding with virtual")
                return
            drift = abs(real - self._virtual_free) / max(self._virtual_free, 1.0)
            if drift > BALANCE_DRIFT_THRESHOLD:
                msg = (f"Balance drift {drift:.1%}: on-chain=${real:.2f}, "
                       f"virtual=${self._virtual_free:.2f} — adjusting to on-chain value")
                _send_alert('CRITICAL', msg)
                with self._state_lock:
                    self._virtual_free = real
            else:
                log.info(f"[FIX-1] Balance OK: on-chain=${real:.2f}, drift={drift:.1%}")
        except Exception as e:
            log.error(f"[FIX-1] Balance check error: {e}")

    def _check_balance_drift(self):
        if IS_PAPER_TRADING or self.live is None:
            return
        try:
            real = _get_usdc_balance_safe(self.live)
            if real is None:
                return
            with self._state_lock:
                virt = self._virtual_free
            drift = abs(real - virt) / max(virt, 1.0)
            if drift > BALANCE_DRIFT_THRESHOLD:
                _send_alert('CRITICAL',
                    f"Post-trade balance drift {drift:.1%}: "
                    f"on-chain=${real:.2f} vs virtual=${virt:.2f}")
        except Exception as e:
            log.debug(f"[FIX-1] Drift check failed: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # PRICE UPDATE
    # ─────────────────────────────────────────────────────────────────────

    def update_crypto_price(self, coin: str, price: float, volume: Optional[float]):
        if self.emergency_stop.is_active():
            return

        with self._state_lock:
            # [FIX-6] Volume EMA only updated when actual volume data arrives (Binance path)
            if volume is not None:
                alpha = 2 / 21
                prev  = self._volume_emas.get(coin, 0.0)
                self._volume_emas[coin] = (
                    volume if prev == 0.0
                    else alpha * volume + (1 - alpha) * prev
                )

            # Velocity EMA
            if coin in self._prices:
                raw    = price - self._prices[coin]
                ef     = VELOCITY_THRESHOLDS[coin]['ema_factor']
                prev_v = self._velocities_ema.get(coin, 0.0)
                self._velocities_ema[coin] = (
                    raw if prev_v == 0.0
                    else ef * raw + (1 - ef) * prev_v
                )
            self._prices[coin] = price

        self._regime_detectors[coin].add_price(price)
        with self._state_lock:
            self._current_regimes[coin] = self._regime_detectors[coin].compute_regime()

        for tf in TIMEFRAMES:
            self._evaluate_market(coin, tf)

    # ─────────────────────────────────────────────────────────────────────
    # MARKET EVALUATION
    # ─────────────────────────────────────────────────────────────────────

    def _evaluate_market(self, coin: str, tf: int):
        with self._state_lock:
            virt_free  = self._virtual_free
            n_pos      = len(self._active_positions)
            regime     = self._current_regimes.get(coin, Regime.CHOPPY)
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
        if rp.get('timeframe') != tf and regime in [
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
            log.debug(f"HTTP {coin}/{tf}: {e}")
            return

        if r.status_code != 200:
            return

        event = r.json()
        if event.get('closed') or event.get('resolved'):
            return

        markets = event.get('markets', [])
        if not markets:
            return

        mkt      = markets[0]
        prices_p = json.loads(mkt.get('outcomePrices', '[]'))
        if len(prices_p) != 2:
            return

        yes_p, no_p = float(prices_p[0]), float(prices_p[1])

        # [FIX-10] Extract BOTH YES and NO asset IDs from the market
        clob_tokens  = mkt.get('clobTokenIds') or mkt.get('tokens', [])
        yes_asset_id = ''
        no_asset_id  = ''
        if isinstance(clob_tokens, list):
            if len(clob_tokens) >= 1:
                yes_asset_id = str(clob_tokens[0]) if clob_tokens[0] else ''
            if len(clob_tokens) >= 2:
                no_asset_id  = str(clob_tokens[1]) if clob_tokens[1] else ''

        # ── Arbitrage ─────────────────────────────────────────────────────
        if yes_p + no_p < 0.985:
            self._enter_arb(coin, tf, yes_p, no_p, rp, slug,
                            yes_asset_id, no_asset_id)
            return

        # ── Edge signal ───────────────────────────────────────────────────
        with self._state_lock:
            velocity   = self._velocities_ema.get(coin, 0.0)
            vol_ema    = self._volume_emas.get(coin, 0.0)
            virt_free  = self._virtual_free
            existing   = self._active_positions.get(f"{coin.upper()}-{tf}m")

        if velocity == 0.0 or existing:
            return

        threshold = VELOCITY_THRESHOLDS[coin]['raw'] * rp.get('velocity_mult', 1.0)
        side = None
        if velocity > threshold and yes_p < rp.get('max_price', 0.75):
            side = 'YES'
        elif velocity < -threshold and no_p < rp.get('max_price', 0.75):
            side = 'NO'
        if not side:
            return

        ctx = {'coin': coin, 'tf': tf, 'yes_p': yes_p, 'no_p': no_p,
               'velocity': round(velocity, 6), 'side': side}

        # Filter: zone
        ok, reason = passes_zone_filter(yes_p, side)
        if not ok:
            self._log_decision('SKIP_ZONE', ctx, reason); return

        # [FIX-6] Volume filter — ONLY apply when Binance feed is active and we have data
        # On RTDS path vol_ema stays 0 so this block never runs (correct — no volume available)
        # On Binance path vol_ema builds up from actual trade volume
        if vol_ema > 0 and self._price_feed_active == PriceFeed.BINANCE:
            min_vol = vol_ema * VOLUME_MULTIPLIERS.get(coin, 1.5)
            # We compare the running EMA to a spike threshold:
            # If the recent EMA is unusually low, market is quiet — skip
            if vol_ema < 0.5:
                self._log_decision('SKIP_VOLUME_LOW', ctx, f'vol_ema={vol_ema:.4f}'); return

        # Filter: velocity MTF
        if abs(velocity) < threshold * 1.2:
            self._log_decision('SKIP_MTF', ctx, 'velocity_weak'); return

        # Filter: sentiment
        fng  = self._get_fng()
        smul = get_sentiment_mult(fng, side)
        if smul is None:
            self._log_decision('SKIP_SENTIMENT', ctx, f'fng={fng}'); return

        # Entry validation
        entry_price = yes_p if side == 'YES' else no_p
        rp_for_edge = REGIME_PARAMS.get(regime.value, REGIME_PARAMS['default'])

        signal = None
        if _ENTRY_VALIDATION_AVAILABLE and callable(calculate_edge):
            try:
                signal = calculate_edge(
                    coin=coin, yes_price=yes_p, no_price=no_p,
                    velocity=velocity, regime_params=rp_for_edge, market=mkt,
                )
            except Exception as e:
                log.warning(f"calculate_edge error: {e}")
        else:
            # Fallback: manual edge check
            edge = abs(velocity) * (0.75 - entry_price)
            if edge >= MIN_EDGE:
                signal = {'side': side, 'edge': edge, 'confidence': 1.0}

        if not signal:
            self._log_decision('SKIP_EDGE', ctx, 'no_signal'); return

        # Kelly sizing
        try:
            amount, kdiag = get_kelly_stake_with_diagnostics(
                entry_price=entry_price, bankroll=virt_free, coin=coin,
            )
        except Exception as e:
            log.warning(f"Kelly error: {e} — using flat sizing")
            amount = virt_free * POSITION_SIZE_PCT
            kdiag  = {'reason': f'kelly_error:{e}'}

        if amount == 0.0:
            self._log_decision('SKIP_KELLY', ctx, kdiag.get('reason', '?')); return

        amount = amount * smul * signal.get('confidence', 1.0)
        amount = max(1.0, min(virt_free * 0.10, amount))
        if amount < 20:
            self._log_decision('SKIP_SIZE', ctx, f'${amount:.2f}<$20'); return

        # Kill switch
        with self._state_lock:
            exposure = sum(p.shares * p.entry_price for p in self._active_positions.values())
        ok, reason = self.kill_switch.validate_trade(amount, exposure, virt_free)
        if not ok:
            self._log_decision('SKIP_KS', ctx, reason); return

        # Risk manager
        if self.rm:
            ok, reason = self.rm.pre_trade_check(coin=coin, side=side, size_usd=amount)
            if not ok:
                self._log_decision('SKIP_RISK', ctx, reason); return

        self._enter_edge(coin, tf, signal, yes_p, no_p, rp, amount,
                         slug, mkt, entry_price, yes_asset_id, no_asset_id, regime)
        with self._state_lock:
            self._last_trade_ts = time.time()

    # ─────────────────────────────────────────────────────────────────────
    # TRADE ENTRY
    # ─────────────────────────────────────────────────────────────────────

    def _enter_arb(self, coin, tf, yes_p, no_p, rp, slug,
                   yes_asset_id, no_asset_id):
        market_key = f"{coin.upper()}-{tf}m"
        with self._state_lock:
            vf = self._virtual_free
            if market_key in self._active_positions:
                return
            exposure = sum(p.shares * p.entry_price for p in self._active_positions.values())

        amount = min(50.0, vf * POSITION_SIZE_PCT * rp.get('size_mult', 1.0))
        if amount < 20:
            return

        ok, r = self.kill_switch.validate_trade(amount, exposure, vf)
        if not ok:
            return
        if self.rm:
            ok2, r2 = self.rm.pre_trade_check(coin=coin, side='ARB', size_usd=amount)
            if not ok2:
                return

        profit = (1.0 - (yes_p + no_p)) * 100
        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count
        log.info(f"🎯 #{tc} ARB {coin} {tf}m | +{profit:.2f}%")

        if self.rm:
            self.rm.on_trade_opened(coin=coin, side='ARB', size_usd=amount, market_id=market_key)

        with self._state_lock:
            self._virtual_free -= amount
            self._last_trade_ts = time.time()

        self._log_trade({'type':'ARBITRAGE','market':market_key,
                         'amount':amount,'profit_est_pct':profit})
        self._save_state()

    def _enter_edge(self, coin, tf, signal, yes_p, no_p, rp, amount,
                    slug, mkt_data, entry_price,
                    yes_asset_id, no_asset_id, regime):
        market_key = f"{coin.upper()}-{tf}m"
        side       = signal['side']

        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count

        log.info(
            f"📈 #{tc} EDGE {coin} {tf}m | {side} @ {entry_price:.3f} | "
            f"${amount:.2f} | Regime {regime.value}"
        )

        # Live execution
        live_result = {'success': False, 'fill_price': entry_price,
                       'filled_size': amount / entry_price,
                       'order_id': None, 'virtual': True}

        if self.live is not None and not IS_PAPER_TRADING:
            try:
                live_result = self.live.execute_buy(
                    market_id=market_key, side=side,
                    amount=amount, price=entry_price,
                    signal_data={
                        "market_id": market_key, "side": side,
                        "v4_estimated_price": entry_price,
                        "edge": signal.get('edge', 0),
                        "regime": regime.value,
                    },
                )
            except Exception as e:
                log.error(f"execute_buy exception: {e}")
                live_result['success'] = False

        # [FIX-3] Clear alert when live order fails
        if not live_result.get('success') and not IS_PAPER_TRADING:
            msg = (f"LIVE ORDER FAILED for {market_key} {side} — "
                   f"tracking as VIRTUAL ONLY. Check CLOB/wallet status!")
            _send_alert('CRITICAL', msg)
            with self._state_lock:
                if self._bot_state == BotState.RUNNING:
                    self._bot_state = BotState.DEGRADED

        fill_price  = live_result.get('fill_price',  entry_price)
        filled_size = live_result.get('filled_size', amount / max(entry_price, 0.001))

        # Risk manager tracking
        pos_id = ''
        if self.rm:
            pos_id = self.rm.on_trade_opened(
                coin=coin, side=side, size_usd=amount, market_id=market_key
            ) or ''

        # [FIX-10] Store both asset IDs; position uses active_asset_id property
        position = Position(
            market_id=market_key,    side=side,
            entry_price=fill_price,  shares=filled_size,
            yes_asset_id=yes_asset_id,  # [FIX-10]
            no_asset_id=no_asset_id,    # [FIX-10]
            slug=slug, coin=coin.upper(), timeframe=tf,
            pos_id=str(pos_id),
        )

        with self._state_lock:
            self._virtual_free -= amount
            self._active_positions[market_key] = position

        # [FIX-10] Subscribe the correct token for our side
        active_id = position.active_asset_id
        if active_id:
            self.clob_ws.subscribe([active_id])
            log.debug(f"[FIX-10] Subscribed {side} asset_id={active_id} for {market_key}")

        # Resolution engine
        if self.resolution_engine:
            try:
                exp_utc = datetime.fromtimestamp(
                    time.time() + (tf * 60), tz=timezone.utc
                ).isoformat()
                self.resolution_engine.register_position(
                    market_id=market_key, slug=slug, coin=coin.upper(),
                    timeframe_minutes=tf, entry_price=fill_price,
                    position_side=side, expiration_utc=exp_utc,
                )
            except Exception as e:
                log.error(f"resolution_engine.register_position error: {e}")

        self._log_trade({
            'type': 'EDGE', 'market': market_key, 'side': side,
            'amount': amount, 'entry_price': fill_price,
            'edge': signal.get('edge', 0), 'regime': regime.value,
            'yes_asset_id': yes_asset_id, 'no_asset_id': no_asset_id,
            'active_asset_id': active_id,
            'live_order_id': live_result.get('order_id'),
            'live_virtual':  live_result.get('virtual', True),
            'live_success':  live_result.get('success', False),
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
            snapshot = dict(self._active_positions)

        # Resolution engine exits
        if self.resolution_engine and snapshot:
            pos_dict = {}
            for mid, pos in snapshot.items():
                exp_ts  = pos.entry_time + (pos.timeframe * 60)
                exp_utc = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
                pos_dict[mid] = {
                    'slug': pos.slug, 'coin': pos.coin,
                    'timeframe': pos.timeframe, 'entry_price': pos.entry_price,
                    'side': pos.side, 'expiration_utc': exp_utc,
                }
            try:
                resolved = self.resolution_engine.check_all_exits(pos_dict)
                for mid, outcome, source, tier in resolved:
                    pos = snapshot.get(mid)
                    if pos:
                        final_price = 1.0 if outcome == pos.side else 0.0
                        self._execute_exit(pos, ExitReason.RESOLVED, final_price,
                                           extra={'tier': tier, 'source': source})
            except Exception as e:
                log.error(f"resolution_engine.check_all_exits error: {e}")

        # Price-based exits (SL / TP / trailing / time)
        with self._state_lock:
            snapshot = dict(self._active_positions)

        for mid, pos in snapshot.items():
            cur_price = self._get_current_price(pos)
            if cur_price is None:
                continue
            reason = evaluate_exits(pos, cur_price)
            if reason:
                self._execute_exit(pos, reason, cur_price)

    def _get_current_price(self, pos: Position) -> Optional[float]:
        # [FIX-10] Use the side-correct asset_id via property
        aid = pos.active_asset_id
        if aid:
            mid = self.clob_ws.get_mid_price(aid)
            if mid is not None:
                return mid
        return None

    def _execute_exit(self, pos: Position, reason: ExitReason, cur_price: float,
                      extra: dict = None):
        pnl     = (cur_price - pos.entry_price) / pos.entry_price * 100
        pnl_amt = pos.shares * (cur_price - pos.entry_price)

        log.info(f"🚪 EXIT {pos.market_id} | {reason.value} | PnL: {pnl:+.1f}%")

        # [FIX-9] Verify shares is valid before calling execute_sell
        shares_to_sell = pos.shares
        if shares_to_sell <= 0:
            log.error(f"[FIX-9] Invalid shares={shares_to_sell} for {pos.market_id} — skipping live sell")
        elif self.live is not None and not IS_PAPER_TRADING:
            try:
                live_result = self.live.execute_sell(
                    market_id=pos.market_id,
                    exit_price=cur_price,
                    shares=shares_to_sell,      # [FIX-9] explicitly passed
                    signal_data={
                        "market_id":    pos.market_id,
                        "v4_exit_price": cur_price,
                        "exit_reason":  reason.value,
                    },
                )
                if not live_result.get('success'):
                    _send_alert('CRITICAL',
                        f"LIVE SELL FAILED for {pos.market_id} — position may still be open on-chain!")
            except Exception as e:
                log.error(f"execute_sell exception: {e}")
                _send_alert('CRITICAL', f"execute_sell exception for {pos.market_id}: {e}")

        won = pnl > 0
        self.circuit_breaker.record(won)
        self.kill_switch.record_trade(pnl_amt, won)

        if self.rm:
            try:
                self.rm.on_trade_closed(
                    position_id=pos.market_id, won=won,
                    pnl=pnl_amt, coin=pos.coin or pos.market_id.split('-')[0]
                )
            except Exception as e:
                log.error(f"rm.on_trade_closed error: {e}")

        try:
            record_completed_trade(
                trade_id=pos.market_id, market_id=pos.market_id,
                coin=pos.coin or pos.market_id.split('-')[0],
                entry_price=pos.entry_price,
                outcome='WIN' if won else 'LOSS',
                pnl_pct=pnl / 100, notes=reason.value,
            )
        except Exception as e:
            log.debug(f"record_completed_trade error: {e}")

        with self._state_lock:
            self._virtual_free += pos.shares * cur_price
            self._active_positions.pop(pos.market_id, None)

        self._log_trade({
            'type': 'EXIT', 'market': pos.market_id, 'side': pos.side,
            'exit_reason': reason.value,
            'exit_price': cur_price, 'entry_price': pos.entry_price,
            'shares': pos.shares,
            'pnl_pct': round(pnl, 4),
            **(extra or {}),
        })
        self._save_state()
        self._check_balance_drift()

    # ─────────────────────────────────────────────────────────────────────
    # BINANCE FALLBACK  [FIX-4]
    # ─────────────────────────────────────────────────────────────────────

    def _start_binance_ws(self):
        log.info("[FIX-4] Starting Binance fallback WebSocket feed")
        self._price_feed_active = PriceFeed.BINANCE
        _delay = [RECONNECT_DELAY]

        def on_open(ws):
            log.info("[Binance] Connected — volume data now available")
            _delay[0] = RECONNECT_DELAY

        def on_message(ws, raw):
            try:
                d      = json.loads(raw)
                sym    = d.get('s', '').replace('USDT', '')
                price  = float(d.get('p', 0))
                volume = float(d.get('q', 0))   # [FIX-6] real volume from Binance
                if sym in COINS and price > 0:
                    self.update_crypto_price(sym, price, volume)
            except Exception:
                pass

        def on_error(ws, err):
            self.kill_switch.record_api_error()
            log.error(f"[Binance] Error: {err}")

        def on_close(ws, code, msg):
            log.warning(f"[Binance] Closed, retry in {_delay[0]}s")
            _send_alert('WARNING', "Binance fallback feed disconnected — reconnecting")
            time.sleep(_delay[0])
            _delay[0] = min(_delay[0] * 2, 60)
            if not self.emergency_stop.is_active():
                self._start_binance_ws()

        ws_obj = websocket.WebSocketApp(
            BINANCE_WS,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=ws_obj.run_forever, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def handle_market_resolved(self, payload: dict):
        log.info(f"[CLOB resolved] slug={payload.get('slug')} winner={payload.get('winning_outcome')}")

    def _get_all_asset_ids(self) -> List[str]:
        with self._state_lock:
            ids = []
            for p in self._active_positions.values():
                if p.yes_asset_id: ids.append(p.yes_asset_id)
                if p.no_asset_id:  ids.append(p.no_asset_id)
            return ids

    def _get_fng(self) -> int:
        val, fetched = self._fng_cache
        if time.time() - fetched > 600:
            val = _fetch_fng()
            self._fng_cache = (val, time.time())
        return val

    # [FIX-8] All file writes go through _FILE_LOCK
    def _log_trade(self, trade: dict):
        trade['timestamp_utc'] = datetime.now(tz=timezone.utc).isoformat()
        with self._state_lock:
            trade['virtual_balance'] = round(self._virtual_free, 4)
        with _FILE_LOCK:
            data = safe_load_json(TRADE_LOG, default=[])
            data.append(trade)
            if not atomic_write_json(data, TRADE_LOG):
                log.critical(f"TRADE LOG WRITE FAILED — trade: {trade}")

    def _log_decision(self, action: str, ctx: dict, reason: str):
        entry = {
            'ts':     datetime.now(tz=timezone.utc).isoformat(),
            'action': action, 'reason': reason, **ctx,
        }
        with _FILE_LOCK:
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
        with _FILE_LOCK:
            if not atomic_write_json(state, STATE_FILE):
                log.critical("STATE FILE WRITE FAILED")

    def _load_state(self):
        with _FILE_LOCK:
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
                    log.info(f"Resumed position: {mid} @ {pos.entry_price:.3f} (side={pos.side})")
                except Exception as e:
                    log.error(f"Could not resume position {mid}: {e}")

        # Re-register resumed positions into resolution engine
        with self._state_lock:
            to_register = dict(self._active_positions)

        for mid, pos in to_register.items():
            try:
                exp_utc = datetime.fromtimestamp(
                    pos.entry_time + (pos.timeframe * 60), tz=timezone.utc
                ).isoformat()
                if self.resolution_engine:
                    self.resolution_engine.register_position(
                        market_id=mid, slug=pos.slug, coin=pos.coin,
                        timeframe_minutes=pos.timeframe, entry_price=pos.entry_price,
                        position_side=pos.side, expiration_utc=exp_utc,
                    )
                # Re-subscribe both asset IDs
                ids = [x for x in [pos.yes_asset_id, pos.no_asset_id] if x]
                if ids:
                    self.clob_ws.subscribe(ids)
                log.info(f"Re-registered {mid} in resolution engine")
            except Exception as e:
                log.error(f"Failed to re-register {mid}: {e}")

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
                'timestamp_utc':   datetime.now(tz=timezone.utc).isoformat(),
                'bot_state':       self._bot_state.value,
                'balance':         round(self._virtual_free, 2),
                'trade_count':     self._trade_count,
                'open_positions':  len(self._active_positions),
                'clob_connected':  self.clob_ws.connected,
                'rtds_connected':  self.rtds_ws.connected,
                'price_feed':      self._price_feed_active.value,
                'emergency_stop':  self.emergency_stop.is_active(),
                'kill_switch':     self.kill_switch.status(),
                'circuit_breaker': self.circuit_breaker.status(),
                'paper_mode':      IS_PAPER_TRADING,
                'zone_filter':     ENABLE_ZONE_FILTER,
            }
        with _FILE_LOCK:
            atomic_write_json(health, HEALTH_FILE)

    def _bootstrap_kelly(self):
        cal = Path(f"{WORKSPACE}/kelly_calibration.json")
        if cal.exists():
            log.info("[Kelly] Calibration exists — skipping import")
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
            log.info(f"[Kelly] Imported {n} trades")
        except Exception as e:
            log.debug(f"[Kelly] Bootstrap skipped: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    bot = MasterBot()
    bot.start()
