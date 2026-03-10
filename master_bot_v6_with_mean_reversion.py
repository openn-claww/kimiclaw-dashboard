#!/usr/bin/env python3
"""
master_bot_v6_with_mean_reversion.py — V6 + Mean Reversion Strategy Integration
Deploys mean reversion alongside momentum and arbitrage strategies.
Paper trading mode enabled for 1-2 hour testing phase.
"""

# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS & SETUP (same as master_bot_v6_polyclaw_integration.py)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from bot_lock import acquire_lock
    acquire_lock()
except ImportError:
    import fcntl as _fcntl, sys as _sys, os as _os, signal as _signal
    from pathlib import Path
    _LOCK_FILE = '/tmp/master_bot_v6_meanrev.lock'

    def _is_stale_lock(path):
        try:
            pid = int(Path(path).read_text().strip())
            _os.kill(pid, 0)
            return False
        except (ValueError, FileNotFoundError):
            return True
        except ProcessLookupError:
            return True
        except PermissionError:
            return False

    if Path(_LOCK_FILE).exists() and _is_stale_lock(_LOCK_FILE):
        _os.unlink(_LOCK_FILE)

    _lf = open(_LOCK_FILE, 'w')
    try:
        _fcntl.flock(_lf, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _lf.write(str(_os.getpid()))
        _lf.flush()
    except IOError:
        pid_in_file = None
        try:
            pid_in_file = int(Path(_LOCK_FILE).read_text().strip())
        except Exception:
            pass
        print(f"FATAL: Another instance running (PID {pid_in_file}). Delete {_LOCK_FILE} to override.")
        _sys.exit(1)

import os, sys, json, time, logging, threading, signal, requests
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum
from collections import deque
from pathlib import Path

try:
    import websocket
    import numpy as np
    from scipy.stats import linregress
except ImportError as e:
    print(f"FATAL: missing package — {e}\nRun: pip install websocket-client numpy scipy")
    sys.exit(1)

WORKSPACE = os.getenv('BOT_WORKSPACE', '/root/.openclaw/workspace')
sys.path.insert(0, WORKSPACE)

# ══════════════════════════════════════════════════════════════════════════════
# [MEAN REVERSION] Import the integration module
# ══════════════════════════════════════════════════════════════════════════════
try:
    from mean_reversion_integration import MeanReversionIntegration, MeanRevTradeResult
    _MEANREV_AVAILABLE = True
    print("[MEAN REV] ✅ Mean Reversion Integration loaded")
except ImportError as e:
    print(f"[MEAN REV] ⚠️  Mean Reversion Integration not available: {e}")
    _MEANREV_AVAILABLE = False
    MeanReversionIntegration = None
    MeanRevTradeResult = None

# Other imports (proxy, auto-redeem, arb, etc.)
try:
    from proxy_manager import ProxyManager, ManualSellQueue
    _PROXY_AVAILABLE = True
except ImportError as e:
    _PROXY_AVAILABLE = False
    ProxyManager = None
    ManualSellQueue = None

try:
    from auto_redeem import AutoRedeemEngine
    _REDEEM_AVAILABLE = True
except ImportError:
    _REDEEM_AVAILABLE = False
    AutoRedeemEngine = None

try:
    from cross_market_arb import CrossMarketArbitrage
    _ARB_AVAILABLE = True
except ImportError:
    _ARB_AVAILABLE = False
    CrossMarketArbitrage = None

try:
    from dual_strategy import DualStrategyEngine
    _DUAL_AVAILABLE = True
except ImportError:
    _DUAL_AVAILABLE = False
    DualStrategyEngine = None

try:
    from pnl_tracker import PnLTracker
    _PNL_AVAILABLE = True
except ImportError:
    _PNL_AVAILABLE = False
    PnLTracker = None

try:
    from news_feed_compact import NewsFeed
    _NEWS_AVAILABLE = True
except ImportError:
    _NEWS_AVAILABLE = False
    NewsFeed = None

# Internal modules
def _try_import(name, fromlist=None):
    try:
        if fromlist:
            m = __import__(name, fromlist=fromlist)
            return m, True
        return __import__(name), True
    except ImportError:
        return None, False

_live_mod,  _LIVE_OK   = _try_import('live_trading.live_trading_config', ['load_live_config'])
_live_int,  _LIVE_INT  = _try_import('live_trading.v4_live_integration', ['V4BotLiveIntegration'])
_entry_val, _ENTRY_OK  = _try_import('entry_validation', ['calculate_edge', 'REGIME_PARAMS'])
_risk_mod,  _RISK_OK   = _try_import('risk_manager', ['RiskManager'])
_atomic,    _ATOM_OK   = _try_import('atomic_json', ['atomic_write_json', 'safe_load_json'])
_edge_mod,  _EDGE_OK   = _try_import('edge_tracker', ['get_kelly_stake_with_diagnostics', 'record_completed_trade', 'import_trade_history'])
_res_mod,   _RES_OK    = _try_import('resolution_fallback_v1', ['ResolutionFallbackEngine', 'ResolutionConfig'])

load_live_config = getattr(_live_mod, 'load_live_config', None)
V4BotLiveIntegration = getattr(_live_int, 'V4BotLiveIntegration', None)
calculate_edge = getattr(_entry_val, 'calculate_edge', None)
REGIME_PARAMS = getattr(_entry_val, 'REGIME_PARAMS', {})
RiskManager = getattr(_risk_mod, 'RiskManager', None)
ResolutionFallbackEngine = getattr(_res_mod, 'ResolutionFallbackEngine', None)
ResolutionConfig = getattr(_res_mod, 'ResolutionConfig', None)

if _ATOM_OK:
    atomic_write_json = _atomic.atomic_write_json
    safe_load_json = _atomic.safe_load_json
else:
    def atomic_write_json(data, path):
        try:
            with open(path, 'w') as f: json.dump(data, f, indent=2)
            return True
        except Exception: return False
    def safe_load_json(path, default=None):
        try:
            with open(path) as f: return json.load(f)
        except Exception: return default if default is not None else {}

if _EDGE_OK:
    get_kelly_stake_with_diagnostics = _edge_mod.get_kelly_stake_with_diagnostics
    record_completed_trade = _edge_mod.record_completed_trade
    import_trade_history = _edge_mod.import_trade_history
else:
    def get_kelly_stake_with_diagnostics(entry_price, bankroll, coin):
        return bankroll * 0.05, {'reason': 'fallback_flat'}
    def record_completed_trade(**kw): pass
    def import_trade_history(*a, **kw): return 0

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

Path(WORKSPACE).mkdir(parents=True, exist_ok=True)

LOG_FILE      = f'{WORKSPACE}/master_v6_meanrev_run.log'
TRADE_LOG     = f'{WORKSPACE}/master_v6_meanrev_trades.json'
STATE_FILE    = f'{WORKSPACE}/master_v6_meanrev_state.json'
HEALTH_FILE   = f'{WORKSPACE}/master_v6_meanrev_health.json'
DECISION_LOG  = f'{WORKSPACE}/master_v6_meanrev_decisions.json'
ALERT_FILE    = f'{WORKSPACE}/master_v6_meanrev_alerts.json'
MEANREV_LOG   = f'{WORKSPACE}/mean_reversion_trades.json'  # [MEAN REV] Separate log

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger('master_v6_meanrev')
_FILE_LOCK = threading.Lock()

_FALLBACK_REGIME = {'side_bias': None, 'velocity_mult': 1.2, 'size_mult': 0.7, 'timeframe': 15, 'max_price': 0.55}
for _k in ['trend_up', 'trend_down', 'choppy', 'high_vol', 'low_vol', 'default']:
    if _k not in REGIME_PARAMS:
        REGIME_PARAMS[_k] = _FALLBACK_REGIME

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# [MEAN REV] Strategy allocation
MEANREV_ENABLED = os.getenv('MEANREV_ENABLED', 'true').lower() == 'true'
MEANREV_BANKROLL_PCT = float(os.getenv('MEANREV_BANKROLL_PCT', '0.20'))  # 20% of bankroll
MEANREV_PAPER_MODE = os.getenv('MEANREV_PAPER_MODE', 'true').lower() == 'true'

VIRTUAL_BANKROLL        = float(os.getenv('VIRTUAL_BANKROLL', '686.93'))
MAX_POSITIONS           = int(os.getenv('MAX_POSITIONS', '5'))
POSITION_SIZE_PCT       = float(os.getenv('POSITION_SIZE_PCT', '0.05'))
MIN_EDGE                = float(os.getenv('MIN_EDGE', '0.10'))
COINS                   = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES              = [5, 15]
IS_PAPER_TRADING        = os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true'
ENABLE_ZONE_FILTER      = os.getenv('ENABLE_ZONE_FILTER', 'false').lower() == 'true'

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15,  'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
    'SOL': {'raw': 0.25,  'ema_factor': 0.3},
    'XRP': {'raw': 0.08,  'ema_factor': 0.3},
}
VOLUME_MULTIPLIERS = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}

STOP_LOSS_PCT      = 0.20
TAKE_PROFIT_PCT    = 0.40
TRAILING_STOP_PCT  = 0.15
TRAILING_ACTIVATE  = 1.10
TIME_STOP_MINUTES  = 90
REGIME_WINDOW      = 30
REGIME_THETA       = 0.5
DEAD_ZONE_LOW      = 0.35
DEAD_ZONE_HIGH     = 0.65

GAMMA_API   = os.getenv('GAMMA_API', 'https://gamma-api.polymarket.com')
CLOB_WS     = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RTDS_WS     = "wss://ws-live-data.polymarket.com"
BINANCE_WS  = "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade"
CLOB_MAX_RPS = 60

MAX_DAILY_LOSS_PCT      = float(os.getenv('MAX_DAILY_LOSS_PCT',     '0.15'))
MAX_CONSECUTIVE_LOSSES  = int(os.getenv('MAX_CONSECUTIVE_LOSSES',   '7'))
MAX_API_ERRORS_PER_HOUR = int(os.getenv('MAX_API_ERRORS_PER_HOUR',  '30'))
MAX_TOTAL_EXPOSURE_PCT  = float(os.getenv('MAX_TOTAL_EXPOSURE_PCT', '0.50'))
MAX_SINGLE_TRADE_USD    = float(os.getenv('MAX_SINGLE_TRADE_USD',   '75.0'))
BALANCE_DRIFT_THRESHOLD = float(os.getenv('BALANCE_DRIFT_THRESHOLD','0.10'))
WS_CONNECT_TIMEOUT      = int(os.getenv('WS_CONNECT_TIMEOUT',       '30'))
CB_WARMUP_TRADES        = int(os.getenv('CB_WARMUP_TRADES',          '50'))
CB_MIN_WIN_RATE         = float(os.getenv('CB_MIN_WIN_RATE',         '0.40'))
CB_WINDOW               = int(os.getenv('CB_WINDOW',                 '50'))
RECONNECT_DELAY         = int(os.getenv('RECONNECT_DELAY',           '5'))

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
# ALERTING (same as original)
# ══════════════════════════════════════════════════════════════════════════════

_ALERT_LOCK = threading.Lock()

def _send_alert(level: str, message: str):
    if level == 'CRITICAL':
        log.critical(f"🚨 {message}")
    elif level == 'WARNING':
        log.warning(f"⚠️  {message}")
    else:
        log.info(f"ℹ️  {message}")
    
    tg_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    tg_chat  = os.getenv('TELEGRAM_CHAT_ID', '')
    if tg_token and tg_chat and level in ('CRITICAL', 'WARNING'):
        def _tg():
            try:
                import requests as _r
                emoji = {'CRITICAL': '🚨', 'WARNING': '⚠️'}.get(level, 'ℹ️')
                _r.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={'chat_id': tg_chat, 'text': f"{emoji} *[BotV6-MeanRev]* {level}\n{message}", 'parse_mode': 'Markdown'},
                    timeout=5,
                )
            except Exception:
                pass
        threading.Thread(target=_tg, daemon=True).start()

    discord_webhook = os.getenv('DISCORD_WEBHOOK_URL', '')
    if discord_webhook and level in ('CRITICAL', 'WARNING', 'INFO'):
        def _discord():
            try:
                import requests as _r
                emoji = {'CRITICAL': '🚨', 'WARNING': '⚠️', 'INFO': '✅'}.get(level, 'ℹ️')
                color = {'CRITICAL': 0xff0000, 'WARNING': 0xffaa00, 'INFO': 0x00ff00}.get(level, 0x0099ff)
                embed = {
                    'title': f'{emoji} MasterBot v6 + Mean Reversion',
                    'description': message,
                    'color': color,
                    'timestamp': datetime.now(tz=timezone.utc).isoformat(),
                    'footer': {'text': f'Level: {level}'}
                }
                _r.post(discord_webhook, json={'embeds': [embed]}, timeout=5)
            except Exception:
                pass
        threading.Thread(target=_discord, daemon=True).start()
    
    try:
        with _ALERT_LOCK:
            try:
                raw = Path(ALERT_FILE).read_text()
                data = json.loads(raw)
                if not isinstance(data, list): data = []
            except Exception:
                data = []
            entry = {'ts': datetime.now(tz=timezone.utc).isoformat(), 'level': level, 'message': message}
            data.append(entry)
            if len(data) > 500: data = data[-200:]
            tmp = ALERT_FILE + '.tmp'
            Path(tmp).write_text(json.dumps(data, indent=2))
            Path(tmp).replace(ALERT_FILE)
    except Exception as e:
        log.error(f"[Alert] File write failed (non-fatal): {e}")

class EmergencyStop:
    FLAG_FILE = '/tmp/MASTER_BOT_STOP'
    def __init__(self):
        self._stop = False
        signal.signal(signal.SIGTERM, self._sig)
        signal.signal(signal.SIGINT,  self._sig)
    def _sig(self, n, _):
        _send_alert('CRITICAL', f"Signal {n} — emergency stop")
        self._stop = True
    def is_active(self) -> bool:
        if self._stop: return True
        if os.getenv('MASTER_BOT_EMERGENCY_STOP','0') == '1':
            self._stop = True; return True
        if Path(self.FLAG_FILE).exists():
            self._stop = True; return True
        return False
    def trigger(self):
        self._stop = True
        try: Path(self.FLAG_FILE).touch()
        except Exception: pass

class CircuitBreaker:
    def __init__(self):
        self._outcomes = deque(maxlen=CB_WINDOW)
        self._total_trades = 0
        self._tripped = False
        self._lock = threading.Lock()
    def record(self, won: bool):
        with self._lock:
            self._outcomes.append(won)
            self._total_trades += 1
            if self._total_trades < CB_WARMUP_TRADES: return
            if len(self._outcomes) < CB_WINDOW: return
            wr = sum(self._outcomes) / len(self._outcomes)
            was = self._tripped
            self._tripped = wr < CB_MIN_WIN_RATE
            if self._tripped and not was:
                _send_alert('CRITICAL', f"Circuit breaker: win rate {wr:.1%} < {CB_MIN_WIN_RATE:.1%}")
            elif not self._tripped and was:
                log.warning(f"[CB] Reset — win rate {wr:.1%}")
    def is_tripped(self) -> bool:
        with self._lock: return self._tripped
    def status(self) -> dict:
        with self._lock:
            n = len(self._outcomes)
            return {'tripped': self._tripped, 'win_rate': sum(self._outcomes)/n if n else None,
                    'sample': n, 'total': self._total_trades, 'warmup': self._total_trades < CB_WARMUP_TRADES}

class KillSwitch:
    def __init__(self, bankroll: float):
        self._start = bankroll; self._daily_loss = 0.0
        self._consec = 0; self._api_errors = deque()
        self._day = datetime.now().date(); self._active = False
        self._lock = threading.Lock()
    def _reset(self):
        t = datetime.now().date()
        if t != self._day: self._daily_loss = 0.0; self._consec = 0; self._day = t
    def record_trade(self, pnl: float, won: bool):
        with self._lock:
            self._reset()
            if won: self._consec = 0
            else: self._daily_loss += abs(pnl); self._consec += 1
            if self._daily_loss/self._start >= MAX_DAILY_LOSS_PCT:
                _send_alert('CRITICAL', f"Kill switch: daily loss {self._daily_loss/self._start:.1%}"); self._active = True
            if self._consec >= MAX_CONSECUTIVE_LOSSES:
                _send_alert('CRITICAL', f"Kill switch: {self._consec} consecutive losses"); self._active = True
    def record_api_error(self):
        with self._lock:
            now = time.time(); self._api_errors.append(now)
            while self._api_errors and now - self._api_errors[0] > 3600: self._api_errors.popleft()
            if len(self._api_errors) >= MAX_API_ERRORS_PER_HOUR:
                _send_alert('CRITICAL', f"Kill switch: {len(self._api_errors)} API errors/hr"); self._active = True
    def reset_if_stale(self, quiet_window_secs: int = 900):
        with self._lock:
            if not self._active: return False
            if not self._api_errors:
                self._active = False
                log.warning("[KillSwitch] Auto-reset: no errors in window")
                return True
            last_error = max(self._api_errors)
            if time.time() - last_error > quiet_window_secs:
                self._active = False
                self._api_errors.clear()
                log.warning(f"[KillSwitch] Auto-reset after {quiet_window_secs}s quiet window")
                _send_alert('WARNING', 'Kill switch auto-reset after quiet period')
                return True
            return False
    def validate_trade(self, amount: float, exposure: float, bankroll: float) -> Tuple[bool, str]:
        with self._lock:
            if self._active: return False, "kill_switch_active"
            if amount > MAX_SINGLE_TRADE_USD: return False, f"size ${amount:.2f} > max"
            if exposure + amount > bankroll * MAX_TOTAL_EXPOSURE_PCT: return False, "exposure_limit"
            return True, "ok"
    def is_active(self) -> bool:
        with self._lock: return self._active
    def status(self) -> dict:
        with self._lock:
            self._reset()
            return {'active': self._active, 'daily_loss_usd': round(self._daily_loss,2),
                    'daily_loss_pct': round(self._daily_loss/self._start,4), 'consec': self._consec}

class RateLimiter:
    def __init__(self, rps: int = CLOB_MAX_RPS):
        self._max = rps; self._calls = deque(); self._lock = threading.Lock()
    def acquire(self, wait: float = 2.0) -> bool:
        deadline = time.time() + wait
        while time.time() < deadline:
            with self._lock:
                now = time.time()
                while self._calls and now - self._calls[0] > 60: self._calls.popleft()
                if len(self._calls) < self._max: self._calls.append(now); return True
            time.sleep(0.05)
        return False

class RegimeDetector:
    def __init__(self, window: int = REGIME_WINDOW):
        self.window = window
        self.price_history = deque(maxlen=window*2)
        self.vol_history   = deque(maxlen=200)
        self.last_regime   = Regime.CHOPPY
    def add_price(self, price: float): self.price_history.append(price)
    def compute_regime(self) -> Regime:
        if len(self.price_history) < self.window: return self.last_regime
        prices = list(self.price_history)[-self.window:]
        returns = [np.log(prices[i]/prices[i-1]) for i in range(1,len(prices)) if prices[i-1]>0]
        if not returns: return self.last_regime
        vol = float(np.std(returns)) if len(returns)>1 else 0.0
        self.vol_history.append(vol)
        vol_z = 0.0
        if len(self.vol_history) >= 30:
            arr = list(self.vol_history)[-100:]
            vstd = float(np.std(arr))
            if vstd > 0: vol_z = (vol - float(np.mean(arr))) / vstd
        total = abs(prices[-1]-prices[0])
        path = sum(abs(prices[i]-prices[i-1]) for i in range(1,len(prices)))
        eff = total/path if path>0 else 0.0
        try:
            slope,*_ = linregress(np.arange(len(prices)), prices)
            pstd = float(np.std(prices))
            ts = slope/pstd if pstd>0 else 0.0
        except Exception: ts = 0.0
        if vol_z > 1.5: r = Regime.HIGH_VOL
        elif vol_z < -1: r = Regime.LOW_VOL
        elif eff > 0.6:
            if ts > REGIME_THETA: r = Regime.TREND_UP
            elif ts < -REGIME_THETA: r = Regime.TREND_DOWN
            else: r = Regime.CHOPPY
        else: r = Regime.CHOPPY
        self.last_regime = r; return r
    def get_params(self, regime: Regime) -> dict:
        return {
            Regime.TREND_UP:   {'side_bias':'YES', 'velocity_mult':0.8, 'size_mult':1.3, 'timeframe':5, 'max_price':0.70},
            Regime.TREND_DOWN: {'side_bias':'NO',  'velocity_mult':0.8, 'size_mult':1.3, 'timeframe':5, 'max_price':0.70},
            Regime.CHOPPY:     {'side_bias':None,  'velocity_mult':1.5, 'size_mult':0.5, 'timeframe':15,'max_price':0.40},
            Regime.HIGH_VOL:   {'side_bias':None,  'velocity_mult':0.9, 'size_mult':0.6, 'timeframe':5, 'max_price':0.65},
            Regime.LOW_VOL:    {'side_bias':None,  'velocity_mult':0.7, 'size_mult':1.2, 'timeframe':15,'max_price':0.60},
        }.get(regime, _FALLBACK_REGIME)

@dataclass
class Position:
    market_id:    str
    side:         str
    entry_price:  float
    shares:       float
    yes_asset_id: str = ''
    no_asset_id:  str = ''
    slug:         str = ''
    coin:         str = ''
    timeframe:    int = 5
    entry_time:   float = field(default_factory=time.time)
    pos_id:       str = ''
    token_id:     str = ''
    strategy:     str = 'momentum'  # [MEAN REV] Track which strategy opened position
    peak_price:          float = field(init=False)
    trailing_stop_price: float = field(init=False)
    def __post_init__(self):
        self.peak_price = self.entry_price
        self.trailing_stop_price = self.entry_price * (1 - TRAILING_STOP_PCT)
    @property
    def active_asset_id(self) -> str:
        return self.yes_asset_id if self.side == 'YES' else self.no_asset_id
    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ['market_id','side','entry_price','shares','yes_asset_id','no_asset_id',
                 'slug','coin','timeframe','entry_time','pos_id','token_id','strategy',
                 'peak_price','trailing_stop_price']}
    @classmethod
    def from_dict(cls, d: dict) -> 'Position':
        yes_id = d.get('yes_asset_id', d.get('asset_id', ''))
        p = cls(market_id=d['market_id'], side=d['side'], entry_price=d['entry_price'],
                shares=d['shares'], yes_asset_id=yes_id, no_asset_id=d.get('no_asset_id',''),
                slug=d.get('slug',''), coin=d.get('coin',''), timeframe=d.get('timeframe',5),
                entry_time=d.get('entry_time', time.time()), pos_id=d.get('pos_id',''),
                token_id=d.get('token_id',''), strategy=d.get('strategy', 'momentum'))
        p.peak_price = d.get('peak_price', p.entry_price)
        p.trailing_stop_price = d.get('trailing_stop_price', p.entry_price*(1-TRAILING_STOP_PCT))
        return p

def evaluate_exits(pos: Position, price: float) -> Optional[ExitReason]:
    if price <= pos.entry_price*(1-STOP_LOSS_PCT): return ExitReason.STOP_LOSS
    if (time.time()-pos.entry_time)/60 >= TIME_STOP_MINUTES: return ExitReason.TIME_STOP
    if price >= pos.entry_price*(1+TAKE_PROFIT_PCT): return ExitReason.TAKE_PROFIT
    if price >= pos.entry_price*TRAILING_ACTIVATE:
        if price > pos.peak_price:
            pos.peak_price = price
            pos.trailing_stop_price = price*(1-TRAILING_STOP_PCT)
        if price <= pos.trailing_stop_price: return ExitReason.TRAILING_STOP
    return None

def passes_zone_filter(yes_p: float, side: str) -> Tuple[bool, str]:
    if not ENABLE_ZONE_FILTER: return True, 'zone_disabled'
    eff = yes_p if side=='YES' else (1.0-yes_p)
    if DEAD_ZONE_LOW <= eff <= DEAD_ZONE_HIGH: return False, f'dead_zone:{eff:.3f}'
    return True, 'zone_ok'

def get_sentiment_mult(fng: int, side: str) -> Optional[float]:
    if side=='YES':
        if fng>80: return None
        return 1.5 if fng<=20 else (1.0 if fng<=60 else 0.5)
    else:
        if fng<20: return None
        return 1.5 if fng>=80 else (1.0 if fng>=40 else 0.5)

_fng_cache = (50, 0.0)
def _get_fng() -> int:
    global _fng_cache
    val, ts = _fng_cache
    if time.time()-ts > 600:
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3)
            val = int(r.json()['data'][0]['value'])
        except Exception: val = 50
        _fng_cache = (val, time.time())
    return val

def _get_usdc_balance_safe(live) -> Optional[float]:
    try:
        import sys
        from pathlib import Path
        POLYCLAW_LIB = Path('/root/.openclaw/skills/polyclaw')
        if str(POLYCLAW_LIB) not in sys.path:
            sys.path.insert(0, str(POLYCLAW_LIB))
        from dotenv import load_dotenv
        load_dotenv(POLYCLAW_LIB / ".env")
        from lib.wallet_manager import WalletManager
        manager = WalletManager()
        if manager.address:
            balances = manager.get_balances()
            return float(balances.usdc_e)
    except Exception as e:
        log.debug(f"[Balance] PolyClaw WalletManager failed: {e}")
    if live is not None:
        for name in ('get_usdc_balance', 'get_balance', 'usdc_balance', 'get_wallet_balance'):
            fn = getattr(live, name, None)
            if callable(fn):
                try:
                    res = fn()
                    if isinstance(res, dict):
                        for k in ('usdc', 'USDC', 'USDC.e', 'balance', 'available'):
                            if k in res: return float(res[k])
                    elif res is not None: return float(res)
                except Exception: pass
        try:
            status = live.get_status() if callable(getattr(live, 'get_status', None)) else {}
            if 'usdc_balance' in status and status['usdc_balance'] is not None:
                return float(status['usdc_balance'])
        except Exception: pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET MANAGERS (same as original)
# ══════════════════════════════════════════════════════════════════════════════

class CLOBWebSocketManager:
    def __init__(self, bot: 'MasterBotV6'):
        self.bot = bot; self.ws = None
        self.connected = False; self.market_data: Dict[str,dict] = {}
        self._reconnect_delay = 1; self._data_lock = threading.Lock()
        self._connect_event = threading.Event()
    def get_mid_price(self, asset_id: str) -> Optional[float]:
        with self._data_lock:
            d = self.market_data.get(asset_id)
            if d:
                b,a = d.get('best_bid'), d.get('best_ask')
                if b and a:
                    try: return (float(b)+float(a))/2
                    except Exception: pass
        return None
    def subscribe(self, asset_ids: List[str]):
        ids = [a for a in asset_ids if a]
        if ids and self.ws and self.connected:
            try: self.ws.send(json.dumps({"assets_ids":ids,"type":"market","custom_feature_enabled":True}))
            except Exception as e: log.error(f"[CLOB] subscribe error: {e}")
    def connect(self):
        def on_open(ws):
            log.info("[CLOB] Connected"); self.connected=True; self._reconnect_delay=1
            self._connect_event.set()
            aids = self.bot._get_all_asset_ids()
            if aids: self.subscribe(aids)
        def on_message(ws, raw):
            try:
                msg=json.loads(raw); pl=msg.get('payload',{})
                if msg.get('type')=='best_bid_ask':
                    aid=pl.get('asset_id')
                    if aid:
                        with self._data_lock:
                            self.market_data[aid]={'best_bid':pl.get('best_bid'),'best_ask':pl.get('best_ask'),'ts':time.time()}
                elif msg.get('type')=='market_resolved':
                    self.bot.handle_market_resolved(pl)
            except Exception as e: log.debug(f"[CLOB] parse: {e}")
        def on_error(ws, err):
            err_str = str(err)
            log.warning(f"[CLOB] WS error: {err_str}")
            TRADING_ERRORS = ('401', '403', '429', 'insufficient', 'rejected', 'invalid')
            if any(e in err_str.lower() for e in TRADING_ERRORS):
                self.bot.kill_switch.record_api_error()
        def on_close(ws,code,msg):
            self.connected=False; log.warning(f"[CLOB] Closed ({code}), retry {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay); self._reconnect_delay=min(self._reconnect_delay*2,60)
            if not self.bot.emergency_stop.is_active(): self._connect_event.clear(); self.connect()
        self.ws=websocket.WebSocketApp(CLOB_WS,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
        threading.Thread(target=lambda: self.ws.run_forever(ping_interval=20, ping_timeout=10, reconnect=5), daemon=True).start()

class RTDSWebSocketManager:
    def __init__(self, bot: 'MasterBotV6'):
        self.bot=bot; self.ws=None; self.connected=False
        self._reconnect_delay=1; self._fail_count=0; self._MAX_FAILS=3
        self._binance_active=False; self._connect_event=threading.Event()
    def connect(self):
        def on_open(ws):
            log.info("[RTDS] Connected"); self.connected=True
            self._reconnect_delay=1; self._fail_count=0; self._connect_event.set()
            ws.send(json.dumps({"action":"subscribe","subscriptions":[
                {"topic":"crypto_prices","type":"update","filters":"btcusdt,ethusdt,solusdt,xrpusdt"}]}))
            threading.Thread(target=self._pinger,daemon=True).start()
        def on_message(ws,raw):
            try:
                msg=json.loads(raw); pl=msg.get('payload',{})
                if msg.get('topic')=='crypto_prices':
                    sym=pl.get('symbol','').lower().replace('usdt','').upper()
                    price=pl.get('price')
                    if sym in COINS and price: self.bot.update_crypto_price(sym,float(price),volume=None)
            except Exception: pass
        def on_error(ws,err): log.error(f"[RTDS] Error: {err}"); self._fail_count+=1; self.bot.kill_switch.record_api_error()
        def on_close(ws,code,msg):
            self.connected=False
            if self._binance_active: log.info("[RTDS] Binance active — not reconnecting"); return
            if self._fail_count>=self._MAX_FAILS:
                self._binance_active=True; _send_alert('WARNING','RTDS failed — switching to Binance')
                self.bot._start_binance_ws(); return
            log.warning(f"[RTDS] Closed, retry {self._reconnect_delay}s")
            time.sleep(self._reconnect_delay); self._reconnect_delay=min(self._reconnect_delay*2,60)
            if not self.bot.emergency_stop.is_active(): self._connect_event.clear(); self.connect()
        self.ws=websocket.WebSocketApp(RTDS_WS,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
        threading.Thread(target=self.ws.run_forever,daemon=True).start()
    def _pinger(self):
        while self.connected and self.ws:
            try: self.ws.send("PING")
            except Exception: break
            time.sleep(5)

# ══════════════════════════════════════════════════════════════════════════════
# MASTER BOT V6 + MEAN REVERSION
# ══════════════════════════════════════════════════════════════════════════════

class MasterBotV6:
    def __init__(self):
        self._price_feed_active = PriceFeed.NONE
        self._state_lock = threading.Lock()
        self._prices: Dict[str,float] = {}
        self._velocities_ema: Dict[str,float] = {}
        self._volume_emas: Dict[str,float] = {c:0.0 for c in COINS}
        self._active_positions: Dict[str,Position] = {}
        self._virtual_free = VIRTUAL_BANKROLL
        self._trade_count = 0
        self._bot_state = BotState.RUNNING
        self._last_trade_ts = 0.0
        self._last_exit_ts = 0.0
        self._last_health_ts = 0.0
        self._last_market_data = {}
        self._meanrev_positions: Dict[str, Position] = {}  # [MEAN REV] Track mean rev positions separately

        self._regime_detectors = {c: RegimeDetector() for c in COINS}
        self._current_regimes = {c: Regime.CHOPPY for c in COINS}

        # Safety
        self.emergency_stop = EmergencyStop()
        self.circuit_breaker = CircuitBreaker()
        self.kill_switch = KillSwitch(VIRTUAL_BANKROLL)
        self.rate_limiter = RateLimiter(CLOB_MAX_RPS)

        # Proxy
        if _PROXY_AVAILABLE:
            self.proxy_mgr = ProxyManager()
            self.sell_queue = ManualSellQueue()
            log.info(f"[Proxy] Loaded: {self.proxy_mgr.status()['proxy_count']} proxies")
        else:
            self.proxy_mgr = None
            self.sell_queue = None

        # Live trading
        self.live = None
        if _LIVE_OK and _LIVE_INT and load_live_config and V4BotLiveIntegration:
            try:
                cfg, pk, addr = load_live_config()
                self.live = V4BotLiveIntegration(config=cfg, private_key=pk, address=addr)
                status = self.live.get_status()
                log.info(f"[Live] Integration: {status}")
            except Exception as e:
                log.warning(f"[Live] Init failed ({e}) — paper mode")

        # Risk manager
        self.rm = None
        if _RISK_OK and RiskManager:
            try: self.rm = RiskManager.load(starting_bankroll=VIRTUAL_BANKROLL)
            except Exception as e: log.warning(f"[Risk] Manager failed: {e}")

        # Resolution engine
        self.resolution_engine = None
        if _RES_OK and ResolutionFallbackEngine and ResolutionConfig:
            try:
                cfg = ResolutionConfig()
                cfg.FALLBACK1_TRIGGER_HOURS = 2.0
                cfg.FALLBACK2_TRIGGER_HOURS = 48.0
                cfg.LIVE_FALLBACK_AUTO_FINALIZE = True
                self.resolution_engine = ResolutionFallbackEngine(config=cfg, is_paper=IS_PAPER_TRADING)
            except Exception as e: log.warning(f"[Resolution] Engine failed: {e}")

        # Auto-redeem
        self.auto_redeem = None
        if _REDEEM_AVAILABLE and AutoRedeemEngine:
            try:
                wallet_mgr = getattr(self.live, 'wallet_manager', None) if self.live else None
                contract_mgr = getattr(self.live, 'contract_manager', None) if self.live else None
                self.auto_redeem = AutoRedeemEngine(
                    wallet_manager=wallet_mgr,
                    contract_manager=contract_mgr,
                    alert_fn=_send_alert,
                    emergency_stop_fn=self.emergency_stop.is_active,
                )
                log.info("[AutoRedeem] Engine loaded")
            except Exception as e:
                log.warning(f"[AutoRedeem] Engine failed: {e}")

        # Arb engine
        self.arb_engine = None
        if _ARB_AVAILABLE and CrossMarketArbitrage:
            try:
                self.arb_engine = CrossMarketArbitrage(bot=self)
                log.info("[Arb] Cross-market arbitrage engine initialized")
            except Exception as e:
                log.warning(f"[Arb] Engine init failed: {e}")

        # Dual strategy
        self.dual_engine = None
        if _DUAL_AVAILABLE and DualStrategyEngine:
            try:
                self.dual_engine = DualStrategyEngine(self)
                log.info("[Dual] Dual strategy engine initialized")
            except Exception as e:
                log.warning(f"[Dual] Engine init failed: {e}")

        # News feed
        self.news_feed = None
        if _NEWS_AVAILABLE and NewsFeed:
            try:
                self.news_feed = NewsFeed()
                log.info("[News] News feed initialized")
            except Exception as e:
                log.warning(f"[News] Feed init failed: {e}")

        # PnL Tracker
        self.pnl_tracker = None
        if _PNL_AVAILABLE and PnLTracker:
            try:
                self.pnl_tracker = PnLTracker()
                log.info("[PnL] Tracker initialized")
            except Exception as e:
                log.warning(f"[PnL] Tracker init failed: {e}")

        # ═════════════════════════════════════════════════════════════════════
        # [MEAN REVERSION] Initialize Mean Reversion Integration
        # ═════════════════════════════════════════════════════════════════════
        self.meanrev_integration = None
        if _MEANREV_AVAILABLE and MeanReversionIntegration and MEANREV_ENABLED:
            try:
                meanrev_bankroll = VIRTUAL_BANKROLL * MEANREV_BANKROLL_PCT
                self.meanrev_integration = MeanReversionIntegration(self, bankroll=meanrev_bankroll)
                log.info(f"[MeanRev] ✅ Integration initialized with ${meanrev_bankroll:.2f} allocation ({MEANREV_BANKROLL_PCT:.0%})")
                log.info(f"[MeanRev] Paper mode: {MEANREV_PAPER_MODE}")
            except Exception as e:
                log.error(f"[MeanRev] ❌ Integration failed: {e}")
        elif not MEANREV_ENABLED:
            log.info("[MeanRev] ⏸️  Disabled via MEANREV_ENABLED env var")
        else:
            log.warning("[MeanRev] ⚠️  Module not available")

        # WebSocket managers
        self.clob_ws = CLOBWebSocketManager(self)
        self.rtds_ws = RTDSWebSocketManager(self)

        self._bootstrap_kelly()
        self._load_state()
        
        # [MEAN REV] Performance tracking
        self._meanrev_trade_count = 0
        self._meanrev_wins = 0
        self._meanrev_losses = 0
        self._meanrev_total_pnl = 0.0

    def start(self):
        log.info("="*70)
        log.info("MASTER BOT V6 + MEAN REVERSION — Strategy Testing Build")
        log.info(f"  Paper mode      : {IS_PAPER_TRADING}")
        log.info(f"  Mean Rev enabled: {MEANREV_ENABLED and self.meanrev_integration is not None}")
        if self.meanrev_integration:
            log.info(f"  Mean Rev alloc  : ${self.meanrev_integration.bankroll:.2f} ({MEANREV_BANKROLL_PCT:.0%})")
            log.info(f"  Mean Rev paper  : {MEANREV_PAPER_MODE}")
        log.info(f"  Balance         : ${self._virtual_free:.2f}")
        log.info(f"  Positions       : {len(self._active_positions)}")
        log.info("="*70)

        _send_alert('INFO', f'🚀 Bot V6 + Mean Reversion started | Paper: {IS_PAPER_TRADING} | MeanRev: {MEANREV_ENABLED}')

        # Start WebSockets
        self.clob_ws.connect()
        self.rtds_ws.connect()

        log.info(f"Waiting up to {WS_CONNECT_TIMEOUT}s for RTDS...")
        if not self.rtds_ws._connect_event.wait(timeout=WS_CONNECT_TIMEOUT):
            _send_alert('WARNING', "RTDS timeout — starting Binance fallback")
            self._start_binance_ws()
        else:
            self._price_feed_active = PriceFeed.RTDS

        if not self.clob_ws._connect_event.wait(timeout=10):
            log.warning("CLOB WS not connected — price-based exits may lag")

        self._verify_balance()

        if self.auto_redeem:
            self.auto_redeem.start()

        if not hasattr(self, '_stop_event'):
            self._stop_event = threading.Event()
        if not hasattr(self, '_monitor_thread') or not self._monitor_thread.is_alive():
            self._monitor_thread = threading.Thread(target=self._monitor_positions, daemon=True, name='pos-monitor')
            self._monitor_thread.start()
            log.info("[Monitor] Position monitor thread launched")

        # [MEAN REV] Start mean reversion monitor thread
        if self.meanrev_integration:
            self._meanrev_monitor_thread = threading.Thread(target=self._monitor_meanrev_positions, daemon=True, name='meanrev-monitor')
            self._meanrev_monitor_thread.start()
            log.info("[MeanRev] Monitor thread launched")

        if self.rm:
            self.rm.print_status()
        log.info("Bot ready — entering main loop")

        loop_counter = 0
        start_time = time.time()

        while not self.emergency_stop.is_active():
            loop_counter += 1
            try:
                # Log every 12 iterations (~1 minute)
                if loop_counter % 12 == 0:
                    elapsed = time.time() - start_time
                    log.info(f"[STATUS] Loop #{loop_counter} | Elapsed: {elapsed/60:.1f}min | Trades: {self._trade_count} | MeanRev: {self._meanrev_trade_count}")
                    self._write_health()
                
                # Evaluate all markets for all strategies
                for coin in COINS:
                    for tf in TIMEFRAMES:
                        try:
                            self._evaluate_market(coin, tf)
                        except Exception as e:
                            log.debug(f"[Main] Error evaluating {coin}/{tf}m: {e}")
                
                # Check external arb
                if self.arb_engine:
                    try:
                        market_cache = {}
                        for coin in COINS:
                            for tf in TIMEFRAMES:
                                mk = f"{coin.upper()}-{tf}m"
                                if mk in self._last_market_data:
                                    market_cache[mk] = self._last_market_data[mk]
                        
                        arb_opps = self.arb_engine.check_all(markets=market_cache, bankroll=self._virtual_free, paper=IS_PAPER_TRADING)
                        for opp in arb_opps:
                            log.info(f"[Arb] External signal: {opp}")
                    except Exception as e:
                        log.debug(f"[Arb] check_all error: {e}")

                self._check_exits()
                self._retry_sell_queue()
                time.sleep(5)
                
            except Exception as e:
                log.error(f"Main loop: {e}", exc_info=True)
                self.kill_switch.record_api_error()
                time.sleep(5)

        log.critical("BOT HALTED")
        if self.auto_redeem: self.auto_redeem.stop()
        self._write_health(force=True)
        self._generate_meanrev_report()  # [MEAN REV] Final report

    # ═════════════════════════════════════════════════════════════════════════
    # [MEAN REVERSION] Position monitoring
    # ═════════════════════════════════════════════════════════════════════════
    def _monitor_meanrev_positions(self):
        """Monitor mean reversion positions for exits"""
        import time as _time
        log.info("[MeanRev] Position monitor started")
        while not self._stop_event.is_set():
            try:
                if self.meanrev_integration and self.meanrev_integration.enabled:
                    # Check each active mean reversion position
                    for market_id in list(self.meanrev_integration.engine.positions.keys()):
                        try:
                            # Extract coin and timeframe from market_id
                            parts = market_id.split('-')
                            if len(parts) != 2:
                                continue
                            coin = parts[0]
                            tf_str = parts[1].replace('m', '')
                            timeframe = int(tf_str)
                            
                            # Get current prices from our cache
                            mk = f"{coin}-{timeframe}m"
                            if mk not in self._last_market_data:
                                continue
                            
                            pm_data = self._last_market_data[mk].get('pm_data', {})
                            prices = pm_data.get('outcomePrices', [0.5, 0.5])
                            yes_price = float(prices[0]) if isinstance(prices[0], (int, float, str)) else 0.5
                            no_price = float(prices[1]) if isinstance(prices[1], (int, float, str)) else 0.5
                            
                            # Check for exit
                            exit_info = self.meanrev_integration.check_exits(market_id, yes_price, no_price, MEANREV_PAPER_MODE)
                            if exit_info:
                                trade_record = exit_info
                                self._record_meanrev_exit(trade_record)
                                
                        except Exception as e:
                            log.debug(f"[MeanRev] Error checking {market_id}: {e}")
                
                _time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                log.error(f"[MeanRev] Monitor loop error: {e}")
                _time.sleep(10)
        log.info("[MeanRev] Position monitor stopped")

    def _record_meanrev_exit(self, trade_record: Dict):
        """Record a mean reversion trade exit"""
        if not trade_record:
            return
        
        pnl = trade_record.get('pnl', 0)
        won = pnl > 0
        
        self._meanrev_trade_count += 1
        if won:
            self._meanrev_wins += 1
        else:
            self._meanrev_losses += 1
        self._meanrev_total_pnl += pnl
        
        # Log to separate file
        with _FILE_LOCK:
            data = safe_load_json(MEANREV_LOG, default={})
            if not isinstance(data, dict):
                data = {}
            trades = data.get('trades', [])
            if not isinstance(trades, list):
                trades = []
            trades.append(trade_record)
            data['trades'] = trades
            data['summary'] = {
                'total_trades': self._meanrev_trade_count,
                'wins': self._meanrev_wins,
                'losses': self._meanrev_losses,
                'win_rate': self._meanrev_wins / self._meanrev_trade_count if self._meanrev_trade_count > 0 else 0,
                'total_pnl': self._meanrev_total_pnl,
                'last_update': datetime.now(tz=timezone.utc).isoformat()
            }
            atomic_write_json(data, MEANREV_LOG)
        
        emoji = "✅" if won else "❌"
        log.info(f"{emoji} [MeanRev] EXIT recorded: {trade_record.get('market_id')} | "
                f"P&L: ${pnl:+.2f} | Reason: {trade_record.get('exit_reason')}")
        
        # Alert on significant trades
        if abs(pnl) > 0.5:
            _send_alert('INFO' if won else 'WARNING', 
                       f"Mean Rev {'WIN' if won else 'LOSS'}: ${abs(pnl):.2f} | "
                       f"{trade_record.get('market_id')} | {trade_record.get('exit_reason')}")

    def _generate_meanrev_report(self):
        """Generate final mean reversion performance report"""
        if self._meanrev_trade_count == 0:
            log.info("[MeanRev] No trades executed — no report to generate")
            return
        
        win_rate = self._meanrev_wins / self._meanrev_trade_count if self._meanrev_trade_count > 0 else 0
        
        report = {
            'generated_at': datetime.now(tz=timezone.utc).isoformat(),
            'strategy': 'mean_reversion',
            'paper_mode': MEANREV_PAPER_MODE,
            'summary': {
                'total_trades': self._meanrev_trade_count,
                'wins': self._meanrev_wins,
                'losses': self._meanrev_losses,
                'win_rate': f"{win_rate:.1%}",
                'total_pnl_usd': round(self._meanrev_total_pnl, 4),
                'avg_pnl_per_trade': round(self._meanrev_total_pnl / self._meanrev_trade_count, 4) if self._meanrev_trade_count > 0 else 0
            },
            'status': 'ACTIVE' if self.meanrev_integration and self.meanrev_integration.enabled else 'DISABLED'
        }
        
        # Also include engine stats if available
        if self.meanrev_integration and self.meanrev_integration.engine:
            engine_stats = self.meanrev_integration.get_stats()
            report['engine_stats'] = engine_stats
        
        # Save report
        report_file = f'{WORKSPACE}/mean_reversion_report_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        log.info("="*70)
        log.info("MEAN REVERSION STRATEGY — FINAL REPORT")
        log.info("="*70)
        log.info(f"Total Trades:    {self._meanrev_trade_count}")
        log.info(f"Wins:            {self._meanrev_wins}")
        log.info(f"Losses:          {self._meanrev_losses}")
        log.info(f"Win Rate:        {win_rate:.1%}")
        log.info(f"Total P&L:       ${self._meanrev_total_pnl:+.2f}")
        log.info(f"Avg P&L/Trade:   ${self._meanrev_total_pnl / self._meanrev_trade_count:.2f}" if self._meanrev_trade_count > 0 else "N/A")
        log.info(f"Report saved:    {report_file}")
        log.info("="*70)
        
        _send_alert('INFO', f"📊 Mean Reversion Report: {self._meanrev_trade_count} trades, {win_rate:.1%} WR, ${self._meanrev_total_pnl:+.2f} P&L")

    # ═════════════════════════════════════════════════════════════════════════
    # EVALUATE MARKET (Modified to include Mean Reversion)
    # ═════════════════════════════════════════════════════════════════════════
    def _evaluate_market(self, coin: str, tf: int):
        """Evaluate market for ALL strategies: Momentum, Arb, and Mean Reversion"""
        with self._state_lock:
            vf = self._virtual_free
            n = len(self._active_positions)
            regime = self._current_regimes.get(coin, Regime.CHOPPY)
            lt = self._last_trade_ts
        
        if vf < 20:
            return
        if n >= MAX_POSITIONS:
            return
        
        self.kill_switch.reset_if_stale(quiet_window_secs=900)
        if self.kill_switch.is_active():
            return
        if self.circuit_breaker.is_tripped():
            return
        
        min_i = 10 if tf == 5 else 20
        time_since_last = time.time() - lt
        if time_since_last < min_i:
            return
        
        rp = self._regime_detectors[coin].get_params(regime)
        if rp.get('timeframe') != tf and regime in [Regime.TREND_UP, Regime.TREND_DOWN, Regime.LOW_VOL]:
            return
        
        if not self.rate_limiter.acquire(wait=2.0):
            return
        
        try:
            self._evaluate_http_with_meanrev(coin, tf, rp, regime)
        except Exception as e:
            log.error(f"evaluate {coin}/{tf}: {e}", exc_info=True)
            self.kill_switch.record_api_error()

    def _evaluate_http_with_meanrev(self, coin: str, tf: int, rp: dict, regime: Regime):
        """HTTP evaluation including Mean Reversion signals"""
        slot = int(time.time()//(tf*60))*(tf*60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"

        # Fetch market data
        if self.proxy_mgr:
            resp, ok = self.proxy_mgr.request_with_retry(
                'GET', f"{GAMMA_API}/events/slug/{slug}", call_name=f"Gamma/{coin}/{tf}m",
                headers={'User-Agent':'MasterBotV6/1.0','Accept':'application/json'})
        else:
            try:
                resp = requests.get(f"{GAMMA_API}/events/slug/{slug}",
                                    headers={'User-Agent':'MasterBotV6/1.0'}, timeout=2)
                ok = resp.status_code == 200
            except Exception as e:
                self.kill_switch.record_api_error()
                return

        if not ok or resp is None or resp.status_code != 200:
            return

        event = resp.json()
        if event.get('closed') or event.get('resolved'):
            return
        markets = event.get('markets', [])
        if not markets:
            return

        mkt = markets[0]
        prices_p = json.loads(mkt.get('outcomePrices', '[]'))
        if len(prices_p) != 2:
            return
        yes_p, no_p = float(prices_p[0]), float(prices_p[1])
        
        # Cache market data
        tokens = mkt.get('clobTokenIds') or mkt.get('tokens', [])
        yes_asset_id = str(tokens[0]) if len(tokens) > 0 and tokens[0] else ''
        no_asset_id = str(tokens[1]) if len(tokens) > 1 and tokens[1] else ''
        
        mk = f"{coin.upper()}-{tf}m"
        with self._state_lock:
            self._last_market_data[mk] = {
                'pm_data': {
                    'market_id': mk,
                    'conditionId': mkt.get('conditionId'),
                    'outcomePrices': [yes_p, no_p],
                    'clobTokenIds': tokens,
                    'slug': slug
                }
            }

        # ═════════════════════════════════════════════════════════════════════
        # [MEAN REVERSION] Evaluate and trade
        # ═════════════════════════════════════════════════════════════════════
        if self.meanrev_integration and self.meanrev_integration.enabled:
            try:
                market_data = {
                    'yes_asset_id': yes_asset_id,
                    'no_asset_id': no_asset_id,
                    'slug': slug,
                    'conditionId': mkt.get('conditionId')
                }
                
                result = self.meanrev_integration.evaluate_and_trade(
                    coin=coin,
                    yes_price=yes_p,
                    no_price=no_p,
                    timeframe=tf,
                    market_data=market_data,
                    paper_mode=MEANREV_PAPER_MODE
                )
                
                if result and result.success:
                    self._record_meanrev_entry(result, coin, tf, yes_p, no_p, yes_asset_id, no_asset_id, slug)
                    
            except Exception as e:
                log.debug(f"[MeanRev] Evaluation error: {e}")

        # Continue with existing momentum/arb evaluation
        self._evaluate_momentum_arb(coin, tf, yes_p, no_p, rp, regime, slug, yes_asset_id, no_asset_id, tokens)

    def _record_meanrev_entry(self, result: 'MeanRevTradeResult', coin: str, tf: int, 
                              yes_p: float, no_p: float, yes_id: str, no_id: str, slug: str):
        """Record mean reversion entry in our position tracking"""
        mk = f"{coin.upper()}-{tf}m"
        
        # Create a position entry for tracking
        pos = Position(
            market_id=mk,
            side=result.side,
            entry_price=result.fill_price,
            shares=result.shares,
            yes_asset_id=yes_id,
            no_asset_id=no_id,
            slug=slug,
            coin=coin.upper(),
            timeframe=tf,
            pos_id=f"meanrev_{int(time.time())}",
            token_id=yes_id if result.side == 'YES' else no_id,
            strategy='mean_reversion'
        )
        
        # Track in active positions
        with self._state_lock:
            self._active_positions[mk] = pos
            self._meanrev_positions[mk] = pos
        
        # Subscribe to CLOB
        aid = pos.active_asset_id
        if aid:
            self.clob_ws.subscribe([aid])
        
        # Log trade
        self._log_trade({
            'type': 'MEAN_REVERSION',
            'market': mk,
            'side': result.side,
            'amount': result.amount,
            'entry_price': result.fill_price,
            'shares': result.shares,
            'strategy': 'mean_reversion',
            'live_virtual': MEANREV_PAPER_MODE
        })
        
        log.info(f"🔄 [MeanRev] ENTRY: {mk} {result.side} @ {result.fill_price:.3f} | ${result.amount:.2f}")

    def _evaluate_momentum_arb(self, coin: str, tf: int, yes_p: float, no_p: float, 
                                rp: dict, regime: Regime, slug: str, yes_id: str, no_id: str, tokens: list):
        """Original momentum and arb evaluation"""
        mk = f"{coin.upper()}-{tf}m"
        
        # Skip if mean reversion already has a position here
        if self.meanrev_integration and mk in self.meanrev_integration.engine.positions:
            return
        
        # Skip if we already have any position
        with self._state_lock:
            if mk in self._active_positions:
                return
        
        # [ARBITRAGE] Check for sum < 1.0
        if yes_p + no_p < 1.001:
            edge = (1.0 - (yes_p + no_p)) * 100
            if edge > 0:
                log.info(f"🎯 ARB SIGNAL {coin}/{tf}m: SUM={yes_p+no_p:.4f} EDGE={edge:.3f}%")
                self._enter_arb(coin, tf, yes_p, no_p, rp, slug, yes_id, no_id)
                return

        # [MOMENTUM] Edge-based entry
        with self._state_lock:
            velocity = self._velocities_ema.get(coin, 0.0)
            vf = self._virtual_free

        if velocity == 0.0:
            return

        threshold = VELOCITY_THRESHOLDS[coin]['raw'] * rp.get('velocity_mult', 1.0)
        side = None
        if velocity > threshold and yes_p < rp.get('max_price', 0.75):
            side = 'YES'
        elif velocity < -threshold and no_p < rp.get('max_price', 0.75):
            side = 'NO'
        if not side:
            return

        entry_price = yes_p if side == 'YES' else no_p
        
        # Validate with kill switch
        exposure = sum(p.shares * p.entry_price for p in self._active_positions.values())
        ok_k, rk = self.kill_switch.validate_trade(50, exposure, vf)  # Placeholder size
        if not ok_k:
            return

        # Execute momentum trade
        self._enter_momentum(coin, tf, side, entry_price, yes_p, no_p, rp, slug, yes_id, no_id, tokens, regime)

    def _enter_arb(self, coin, tf, yes_p, no_p, rp, slug, yes_id, no_id):
        """Execute arbitrage trade"""
        mk = f"{coin.upper()}-{tf}m"
        with self._state_lock:
            vf = self._virtual_free
            exp = sum(p.shares * p.entry_price for p in self._active_positions.values())
        
        LIVE_MAX_BET = float(os.getenv('MAX_SINGLE_TRADE_USD', '5.0'))
        LIVE_MIN_BET = float(os.getenv('MIN_SINGLE_TRADE_USD', '1.0'))
        LIVE_MAX_PCT = float(os.getenv('MAX_POSITION_PCT', '0.08'))
        
        edge = rp.get('edge', 0.0)
        entry_p = yes_p if rp.get('side', 'YES') == 'YES' else no_p
        kelly_f = edge / (1.0 - entry_p) if entry_p < 1.0 else 0.0
        kelly_f = max(0.0, min(kelly_f, 0.25))
        
        kelly_amt = vf * kelly_f * rp.get('size_mult', 1.0)
        cap_amt = vf * LIVE_MAX_PCT
        amount = min(kelly_amt, cap_amt, LIVE_MAX_BET)
        amount = round(amount, 2)
        
        if amount < LIVE_MIN_BET:
            return
        
        arb_side = 'YES' if yes_p <= no_p else 'NO'
        arb_price = yes_p if arb_side == 'YES' else no_p
        
        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count
        
        log.info(f"🎯 #{tc} ARB {coin} {tf}m | {arb_side} @ {arb_price:.3f} | ${amount:.2f}")
        
        # Paper trade execution
        if not IS_PAPER_TRADING:
            log.info(f"[LIVE] Would execute ARB: {mk} {arb_side} ${amount:.2f}")
        
        self._log_trade({
            'type': 'ARBITRAGE',
            'market': mk,
            'side': arb_side,
            'amount': amount,
            'entry_price': arb_price,
            'live_virtual': IS_PAPER_TRADING
        })

    def _enter_momentum(self, coin, tf, side, entry_price, yes_p, no_p, rp, slug, yes_id, no_id, tokens, regime):
        """Execute momentum trade"""
        mk = f"{coin.upper()}-{tf}m"
        with self._state_lock:
            self._trade_count += 1
            tc = self._trade_count
        
        log.info(f"📈 #{tc} MOMENTUM {coin} {tf}m | {side} @ {entry_price:.3f}")
        
        self._log_trade({
            'type': 'MOMENTUM',
            'market': mk,
            'side': side,
            'entry_price': entry_price,
            'regime': regime.value,
            'live_virtual': IS_PAPER_TRADING
        })

    # ═════════════════════════════════════════════════════════════════════════
    # POSITION MONITORING & EXITS
    # ═════════════════════════════════════════════════════════════════════════
    def _monitor_positions(self):
        """Monitor positions for resolution"""
        import time as _time
        log.info("[Monitor] Position monitor started")
        while not self._stop_event.is_set():
            try:
                with self._state_lock:
                    open_ids = list(self._active_positions.keys())
                
                for mid in open_ids:
                    try:
                        with self._state_lock:
                            pos = self._active_positions.get(mid)
                        if pos is None:
                            continue
                        
                        # Skip mean reversion positions - they have their own monitor
                        if pos.strategy == 'mean_reversion':
                            continue
                        
                        slug = getattr(pos, 'slug', None) or mid
                        resolved, winner = self._check_market_resolved(slug)
                        
                        if resolved:
                            our_side = getattr(pos, 'side', 'YES')
                            exit_price = 1.0 if (winner or '').upper() == our_side.upper() else 0.0
                            log.info(f"[Monitor] {mid} RESOLVED — winner={winner} our={our_side}")
                            self._execute_exit(pos, ExitReason.RESOLVED, exit_price)
                        else:
                            # Time fallback
                            age = _time.time() - getattr(pos, 'entry_time', _time.time())
                            tf = int(getattr(pos, 'timeframe', 5))
                            if age > (tf * 60) + 120:
                                log.warning(f"[Monitor] {mid} timeout — forcing exit at 0.5")
                                with self._state_lock:
                                    live_pos = self._active_positions.get(mid)
                                if live_pos is not None:
                                    self._execute_exit(live_pos, ExitReason.TIME_STOP, 0.5)
                    except Exception as e:
                        log.warning(f"[Monitor] Error checking {mid}: {e}")
                
                _time.sleep(15)
            except Exception as e:
                log.error(f"[Monitor] Loop error: {e}")
                _time.sleep(15)
        log.info("[Monitor] Position monitor stopped")

    def _check_market_resolved(self, slug: str):
        """Query Gamma API for resolution status"""
        try:
            for url in [
                f"https://gamma-api.polymarket.com/events/slug/{slug}",
                f"https://gamma-api.polymarket.com/markets/{slug}",
            ]:
                try:
                    r = requests.get(url, timeout=5)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    event = data[0] if isinstance(data, list) and data else data
                    if not event:
                        continue
                    
                    markets = event.get('markets', [event])
                    for m in markets:
                        if not (m.get('closed') or m.get('resolved') or m.get('resolutionTime')):
                            continue
                        outcomes = m.get('outcomes', [])
                        prices = m.get('outcomePrices', [])
                        if isinstance(prices, str):
                            try:
                                prices = json.loads(prices)
                            except Exception:
                                prices = []
                        for o, p in zip(outcomes, prices):
                            try:
                                if float(p) >= 0.99:
                                    return True, str(o).upper()
                            except (ValueError, TypeError):
                                pass
                        result = m.get('result') or m.get('winner')
                        if result:
                            return True, str(result).upper()
                    return False, None
                except Exception:
                    continue
            return False, None
        except Exception as e:
            log.debug(f"[Monitor] _check_market_resolved({slug}): {e}")
            return False, None

    def _check_exits(self):
        """Check for price-based exits"""
        now = time.time()
        if now - self._last_exit_ts < 15:
            return
        self._last_exit_ts = now
        
        with self._state_lock:
            snap = dict(self._active_positions)
        
        for mid, pos in snap.items():
            # Skip mean reversion positions
            if pos.strategy == 'mean_reversion':
                continue
            
            cp = self._get_current_price(pos)
            if cp:
                reason = evaluate_exits(pos, cp)
                if reason:
                    self._execute_exit(pos, reason, cp)

    def _get_current_price(self, pos: Position) -> Optional[float]:
        aid = pos.active_asset_id
        if aid:
            return self.clob_ws.get_mid_price(aid)
        return None

    def _execute_exit(self, pos: Position, reason: ExitReason, cur_price: float, extra: dict = None):
        """Execute position exit"""
        pnl = (cur_price - pos.entry_price) / pos.entry_price * 100
        pnl_amt = pos.shares * (cur_price - pos.entry_price)
        
        log.info(f"🚪 EXIT {pos.market_id} | {reason.value} | PnL: {pnl:+.1f}%")
        
        won = pnl > 0
        self.circuit_breaker.record(won)
        self.kill_switch.record_trade(pnl_amt, won)
        
        if self.rm:
            try:
                self.rm.on_trade_closed(position_id=pos.market_id, won=won, pnl=pnl_amt,
                                       coin=pos.coin or pos.market_id.split('-')[0])
            except Exception as e:
                log.error(f"rm.on_trade_closed: {e}")
        
        with self._state_lock:
            self._virtual_free += pos.shares * cur_price
            self._active_positions.pop(pos.market_id, None)
            if pos.market_id in self._meanrev_positions:
                del self._meanrev_positions[pos.market_id]
        
        self._log_trade({
            'type': 'EXIT',
            'market': pos.market_id,
            'side': pos.side,
            'exit_reason': reason.value,
            'exit_price': cur_price,
            'entry_price': pos.entry_price,
            'shares': pos.shares,
            'pnl_pct': round(pnl, 4),
            'strategy': pos.strategy,
            **(extra or {})
        })
        self._save_state()

    def _retry_sell_queue(self):
        """Retry queued sells"""
        pass  # Simplified for testing

    # ═════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════════════
    def _verify_balance(self):
        if IS_PAPER_TRADING or not self.live:
            return
        real = _get_usdc_balance_safe(self.live)
        if real is None:
            log.warning("[Balance] Cannot fetch on-chain balance")
            return
        with self._state_lock:
            virt = self._virtual_free
        drift = abs(real - virt) / max(virt, 1.0)
        if drift > BALANCE_DRIFT_THRESHOLD:
            _send_alert('CRITICAL', f"Balance drift {drift:.1%}: on-chain=${real:.2f} virtual=${virt:.2f}")
            with self._state_lock:
                self._virtual_free = real

    def _start_binance_ws(self):
        log.info("Starting Binance fallback WS")
        self._price_feed_active = PriceFeed.BINANCE
        _d = [5]
        def on_open(ws): log.info("[Binance] Connected"); _d[0] = 5
        def on_message(ws, raw):
            try:
                d = json.loads(raw)
                sym = d.get('s', '').replace('USDT', '')
                price = float(d.get('p', 0))
                vol = float(d.get('q', 0))
                if sym in COINS and price > 0:
                    self.update_crypto_price(sym, price, volume=vol)
            except Exception:
                pass
        def on_error(ws, err):
            self.kill_switch.record_api_error()
            log.error(f"[Binance] {err}")
        def on_close(ws, c, m):
            log.warning(f"[Binance] Closed, retry {_d[0]}s")
            time.sleep(_d[0])
            _d[0] = min(_d[0] * 2, 60)
            if not self.emergency_stop.is_active():
                self._start_binance_ws()
        ws = websocket.WebSocketApp(BINANCE_WS, on_open=on_open, on_message=on_message,
                                     on_error=on_error, on_close=on_close)
        threading.Thread(target=ws.run_forever, daemon=True).start()

    def update_crypto_price(self, coin: str, price: float, volume: Optional[float]):
        if self.emergency_stop.is_active():
            return
        with self._state_lock:
            if volume is not None:
                alpha = 2/21
                prev = self._volume_emas.get(coin, 0.0)
                self._volume_emas[coin] = volume if prev == 0.0 else alpha * volume + (1-alpha) * prev
            if coin in self._prices:
                raw = price - self._prices[coin]
                ef = VELOCITY_THRESHOLDS[coin]['ema_factor']
                prev_v = self._velocities_ema.get(coin, 0.0)
                self._velocities_ema[coin] = raw if prev_v == 0.0 else ef * raw + (1-ef) * prev_v
            self._prices[coin] = price
        self._regime_detectors[coin].add_price(price)
        with self._state_lock:
            self._current_regimes[coin] = self._regime_detectors[coin].compute_regime()

    def handle_market_resolved(self, payload: dict):
        log.info(f"[CLOB resolved] {payload.get('slug')} winner={payload.get('winning_outcome')}")

    def _get_all_asset_ids(self) -> List[str]:
        with self._state_lock:
            ids = []
            for p in self._active_positions.values():
                if p.yes_asset_id:
                    ids.append(p.yes_asset_id)
                if p.no_asset_id:
                    ids.append(p.no_asset_id)
            return ids

    def _log_trade(self, trade: dict):
        trade['timestamp_utc'] = datetime.now(tz=timezone.utc).isoformat()
        with self._state_lock:
            trade['virtual_balance'] = round(self._virtual_free, 4)
        with _FILE_LOCK:
            raw = safe_load_json(TRADE_LOG, default={})
            if isinstance(raw, list):
                raw = {"trades": raw, "meta": {"migrated": True}}
            if not isinstance(raw, dict):
                raw = {}
            trades_list = raw.get("trades", [])
            if not isinstance(trades_list, list):
                trades_list = []
            trades_list.append(trade)
            if len(trades_list) > 2000:
                trades_list = trades_list[-1000:]
            raw["trades"] = trades_list
            raw["meta"] = {
                "count": len(trades_list),
                "last_trade": trade['timestamp_utc'],
                "version": "v6_meanrev",
            }
            atomic_write_json(raw, TRADE_LOG)

    def _save_state(self):
        with self._state_lock:
            state = {
                'balance': self._virtual_free,
                'trade_count': self._trade_count,
                'bot_state': self._bot_state.value,
                'active_positions': {k: v.to_dict() for k, v in self._active_positions.items()},
                'kill_switch': self.kill_switch.status(),
                'circuit_breaker': self.circuit_breaker.status(),
                'last_update': datetime.now(tz=timezone.utc).isoformat(),
                # [MEAN REV] Save mean reversion stats
                'meanrev_stats': {
                    'trade_count': self._meanrev_trade_count,
                    'wins': self._meanrev_wins,
                    'losses': self._meanrev_losses,
                    'total_pnl': self._meanrev_total_pnl
                }
            }
        with _FILE_LOCK:
            atomic_write_json(state, STATE_FILE)

    def _load_state(self):
        with _FILE_LOCK:
            state = safe_load_json(STATE_FILE, default={})
        if not state:
            log.info("No saved state — fresh start")
            return
        with self._state_lock:
            self._virtual_free = state.get('balance', VIRTUAL_BANKROLL)
            self._trade_count = state.get('trade_count', 0)
            # [MEAN REV] Load stats
            mr_stats = state.get('meanrev_stats', {})
            self._meanrev_trade_count = mr_stats.get('trade_count', 0)
            self._meanrev_wins = mr_stats.get('wins', 0)
            self._meanrev_losses = mr_stats.get('losses', 0)
            self._meanrev_total_pnl = mr_stats.get('total_pnl', 0.0)
            
            for mid, pd in state.get('active_positions', {}).items():
                try:
                    pos = Position.from_dict(pd)
                    self._active_positions[mid] = pos
                    if pos.strategy == 'mean_reversion':
                        self._meanrev_positions[mid] = pos
                    log.info(f"Resumed: {mid} @ {pos.entry_price:.3f} ({pos.strategy})")
                except Exception as e:
                    log.error(f"Resume {mid}: {e}")
        log.info(f"State loaded: ${self._virtual_free:.2f}, {len(self._active_positions)} positions")

    def _write_health(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_health_ts < 30:
            return
        self._last_health_ts = now
        with self._state_lock:
            health = {
                'timestamp_utc': datetime.now(tz=timezone.utc).isoformat(),
                'bot_state': self._bot_state.value,
                'balance': round(self._virtual_free, 2),
                'trade_count': self._trade_count,
                'open_positions': len(self._active_positions),
                'clob_connected': self.clob_ws.connected,
                'rtds_connected': self.rtds_ws.connected,
                'price_feed': self._price_feed_active.value,
                'emergency_stop': self.emergency_stop.is_active(),
                'kill_switch': self.kill_switch.status(),
                'circuit_breaker': self.circuit_breaker.status(),
                'paper_mode': IS_PAPER_TRADING,
                # [MEAN REV] Add mean reversion health
                'mean_reversion': {
                    'enabled': self.meanrev_integration is not None and self.meanrev_integration.enabled,
                    'trades': self._meanrev_trade_count,
                    'wins': self._meanrev_wins,
                    'losses': self._meanrev_losses,
                    'win_rate': self._meanrev_wins / self._meanrev_trade_count if self._meanrev_trade_count > 0 else 0,
                    'total_pnl': round(self._meanrev_total_pnl, 4)
                } if self.meanrev_integration else {'enabled': False}
            }
        with _FILE_LOCK:
            atomic_write_json(health, HEALTH_FILE)

    def _bootstrap_kelly(self):
        cal = Path(f"{WORKSPACE}/kelly_calibration.json")
        if cal.exists():
            return
        try:
            n = import_trade_history(TRADE_LOG, field_map={"id":"market","market_id":"market","coin":"market",
                "entry_price":"entry_price","outcome":"outcome","pnl_pct":"pnl_pct","timestamp":"timestamp_utc"})
            log.info(f"[Kelly] Imported {n} trades")
        except Exception as e:
            log.debug(f"[Kelly] Bootstrap: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    bot = MasterBotV6()
    bot.start()
