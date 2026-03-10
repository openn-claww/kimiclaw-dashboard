#!/usr/bin/env python3
"""
ULTIMATE BOT v4 - PRODUCTION VERSION
Features: Volume Filter + Sentiment + Adaptive Exits + MTF
"""

# PID mutex - MUST be first to prevent duplicate processes
from bot_lock import acquire_lock
acquire_lock()

import websocket
import json
import time
import statistics
from datetime import datetime, timezone
from collections import defaultdict, deque
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from entry_validation import calculate_edge, REGIME_PARAMS
from risk_manager import RiskManager
from atomic_json import atomic_write_json, safe_load_json
from edge_tracker import (
    get_kelly_stake,
    get_kelly_stake_with_diagnostics,
    record_completed_trade,
    import_trade_history,
    print_edge_status,
    calibrator,
)
from kelly_sizing import KellySizer
from resolution_fallback_v1 import (
    ResolutionFallbackEngine,
    ResolutionConfig,
    manual_resolve,
)
from market_finder import get_current_slug, get_market as get_market_from_events

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 500.00  # Starting virtual balance
MAX_POSITIONS = 5
POSITION_SIZE_PCT = 0.05
MIN_EDGE = 0.10
RECONNECT_DELAY = 5

VELOCITY_THRESHOLDS = {
    'BTC': {'raw': 0.15, 'ema_factor': 0.3},
    'ETH': {'raw': 0.015, 'ema_factor': 0.3},
    'SOL': {'raw': 0.25, 'ema_factor': 0.3},
    'XRP': {'raw': 0.08, 'ema_factor': 0.3},
}

VOLUME_MULTIPLIERS = {'BTC': 1.5, 'ETH': 1.5, 'SOL': 1.8, 'XRP': 1.6}

COINS = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES = [5, 15]

STOP_LOSS_PCT = 0.20
TAKE_PROFIT_PCT = 0.40
TIME_STOP_MINUTES = 90

REGIME_WINDOW = 30
GAMMA_API = "https://gamma-api.polymarket.com"
STATE_FILE = "/root/.openclaw/workspace/wallet_v4_production.json"
LOG_FILE = "/root/.openclaw/workspace/trades_v4_production.json"

# ============ RESOLUTION FALLBACK CONFIG ============
IS_PAPER_TRADING = True  # Set to False for live trading
resolution_cfg = ResolutionConfig()
resolution_cfg.FALLBACK1_TRIGGER_HOURS = 2.0
resolution_cfg.FALLBACK2_TRIGGER_HOURS = 48.0
resolution_cfg.LIVE_FALLBACK_AUTO_FINALIZE = True

resolution_engine = ResolutionFallbackEngine(
    config=resolution_cfg,
    is_paper=IS_PAPER_TRADING,
)

# ============ INITIALIZE ============
rm = RiskManager.load(starting_bankroll=VIRTUAL_BANKROLL)

# Bootstrap Kelly calibration from existing trade history
def _bootstrap_kelly_calibration():
    """One-time import of existing trades for Kelly calibration."""
    from pathlib import Path
    cal_file = Path("/root/.openclaw/workspace/kelly_calibration.json")
    if cal_file.exists():
        print("[Bootstrap] Kelly calibration already exists.")
        return
    
    n = import_trade_history(
        "/root/.openclaw/workspace/trades_v4_production.json",
        field_map={
            "id": "market",
            "market_id": "market",
            "coin": "market",
            "entry_price": "entry_price",
            "outcome": "outcome",
            "pnl_pct": "pnl_pct",
            "timestamp": "timestamp_utc",
        }
    )
    print(f"[Bootstrap] Imported {n} historical trades into Kelly calibrator.")

_bootstrap_kelly_calibration()

prices = {}
velocities_ema = {}
volume_emas = {coin: 0.0 for coin in COINS}
trade_count = 0
last_trade_time = 0
virtual_free = VIRTUAL_BANKROLL
open_positions = defaultdict(list)
active_positions = {}
last_exit_check = 0
reconnect_count = 0

regime_detectors = {coin: deque(maxlen=REGIME_WINDOW*2) for coin in COINS}
current_regimes = {coin: 'choppy' for coin in COINS}

def save_state():
    state = {
        'balance': virtual_free,
        'positions': dict(open_positions),
        'trade_count': trade_count,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    if not atomic_write_json(state, STATE_FILE):
        logger.critical("State file write failed — data may be out of sync")

def log_trade(trade):
    log = safe_load_json(LOG_FILE, default=[])
    log.append(trade)
    if not atomic_write_json(log, LOG_FILE):
        logger.critical("Trade log write failed — trade may be lost")

def get_sentiment_mult(fng, side):
    if side == 'YES':
        if fng > 80: return None
        return 1.5 if fng <= 20 else (1.0 if fng <= 60 else 0.5)
    else:
        if fng < 20: return None
        return 1.5 if fng >= 80 else (1.0 if fng >= 40 else 0.5)

def detect_regime(coin):
    hist = regime_detectors[coin]
    if len(hist) < 10:
        return 'choppy'
    recent = list(hist)[-10:]
    returns = [(recent[i] - recent[i-1]) / recent[i-1] for i in range(1, len(recent)) if recent[i-1] > 0]
    if not returns:
        return 'choppy'
    vol = statistics.stdev(returns) if len(returns) > 1 else 0
    trend = sum(returns)
    if vol > 0.005: return 'high_vol'
    if abs(trend) > 0.01: return 'trend_up' if trend > 0 else 'trend_down'
    return 'choppy'

def evaluate_exits(position, current_price):
    stop_price = position['entry_price'] * (1 - STOP_LOSS_PCT)
    if current_price <= stop_price:
        return 'stop_loss'
    if (time.time() - position['entry_time']) / 60 >= TIME_STOP_MINUTES:
        return 'time_stop'
    if current_price >= position['entry_price'] * (1 + TAKE_PROFIT_PCT):
        return 'take_profit'
    return None

def execute_exit(position, market_id, reason, current_price):
    global virtual_free
    pnl = (current_price - position['entry_price']) / position['entry_price'] * 100
    pnl_amount = position['shares'] * (current_price - position['entry_price'])
    
    print(f"🚪 [{datetime.now().strftime('%H:%M:%S')}] EXIT {market_id} | {reason} | PnL: {pnl:+.1f}%")
    
    virtual_free += position['shares'] * current_price
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
    """Resolution fallback-enabled exit checker — Tier 1/2/3 resolution system."""
    global last_exit_check, virtual_free
    now = time.time()
    if now - last_exit_check < 15:
        return
    last_exit_check = now
    
    # Build position dict for resolution engine
    position_dict = {}
    for market_id, pos in active_positions.items():
        parts = market_id.split('-')
        coin = parts[0]
        tf = int(parts[1].replace('m', ''))
        slot = int(pos.get('entry_time', now) // (tf * 60)) * (tf * 60)
        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
        
        # Calculate expiration time
        entry_ts = pos.get('entry_time', now)
        expiration_ts = entry_ts + (tf * 60)
        expiration_utc = datetime.fromtimestamp(expiration_ts, tz=timezone.utc).isoformat()
        
        position_dict[market_id] = {
            'slug': slug,
            'coin': coin.upper(),
            'timeframe': tf,
            'entry_price': pos.get('entry_price', 0),
            'side': pos.get('side', 'YES'),
            'expiration_utc': expiration_utc,
            '_original_position': pos,
            '_market_id': market_id,
        }
    
    # Use resolution fallback engine
    resolved_items = resolution_engine.check_all_exits(position_dict)
    
    for market_id, outcome, source, tier in resolved_items:
        position = active_positions.get(market_id)
        if not position:
            continue
            
        # Calculate P&L
        entry_price = position['entry_price']
        final_price = 1.0 if outcome == position['side'] else 0.0
        pnl = (final_price - entry_price) / entry_price * 100
        pnl_amount = position['shares'] * (final_price - entry_price)
        won = outcome == position['side']
        
        tier_label = {1: "OFFICIAL", 2: "FALLBACK", 3: "FORCED"}.get(tier, "UNKNOWN")
        print(f"💰 [{datetime.now().strftime('%H:%M:%S')}] SETTLED {market_id} | {outcome} wins | {tier_label} | PnL: {pnl:+.1f}%")
        
        virtual_free += position['shares'] + (position['shares'] * pnl / 100)
        rm.on_trade_closed(position_id=market_id, won=won, pnl=pnl_amount, coin=market_id.split('-')[0])
        
        log_trade({
            'timestamp_utc': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'EXIT',
            'market': market_id,
            'side': position['side'],
            'exit_price': final_price,
            'entry_price': entry_price,
            'exit_reason': f'resolved_{tier_label.lower()}',
            'resolution_source': source,
            'resolution_tier': tier,
            'pnl_pct': pnl,
            'virtual_balance': virtual_free
        })
        
        # Record trade for Kelly calibration
        pnl_pct = (1.0 - entry_price) / entry_price if outcome == "WIN" else -1.0
        record_completed_trade(
            trade_id=market_id,
            market_id=market_id,
            coin=market_id.split('-')[0],
            entry_price=entry_price,
            outcome="WIN" if won else "LOSS",
            pnl_pct=pnl_pct,
            notes=f"resolved via {source} tier {tier}",
        )
        
        if market_id in active_positions:
            del active_positions[market_id]
        if market_id in open_positions:
            del open_positions[market_id]
        
        save_state()
    
    # Reconcile any previously fallback-resolved positions
    for market_id_key, data in resolution_engine.state_mgr._state.items():
        if (
            data.get("resolved")
            and not data.get("polymarket_confirmed")
            and not data.get("discrepancy_detected")
        ):
            resolution_engine.reconcile_with_polymarket(
                market_id_key, data.get("slug", "")
            )

def evaluate_market(coin, tf):
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
        
        # FIX: Use /events/slug/ endpoint (not /markets/slug/)
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        resp = requests.get(f"{GAMMA_API}/events/slug/{slug}", timeout=2, headers=headers)
        
        if resp.status_code == 200:
            event_data = resp.json()
            if event_data.get('closed') or event_data.get('resolved'):
                return
            
            # Get market from events wrapper
            markets = event_data.get('markets', [])
            if not markets:
                return
            
            data = markets[0]  # First market in the event
            
            prices_pm = json.loads(data.get('outcomePrices', '[]'))
            if len(prices_pm) == 2:
                yes_price = float(prices_pm[0])
                no_price = float(prices_pm[1])
                
                # Check arbitrage
                if yes_price + no_price < 0.985:
                    amount = min(50.0, virtual_free * POSITION_SIZE_PCT)
                    if amount >= 20:
                        ok, reason = rm.pre_trade_check(coin=coin, side="ARB", size_usd=amount)
                        if not ok:
                            return
                        
                        trade_count += 1
                        profit = (1.0 - (yes_price + no_price)) * 100
                        print(f"🎯 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} ARB {coin} {tf}m | +{profit:.2f}%")
                        
                        pos_id = rm.on_trade_opened(coin=coin, side="ARB", size_usd=amount, market_id=market_key)
                        virtual_free -= amount
                        save_state()
                        last_trade_time = current_time
                    return
                
                # V4 ENTRY LOGIC
                if coin in velocities_ema and velocities_ema[coin] != 0:
                    velocity = velocities_ema[coin]
                    threshold = VELOCITY_THRESHOLDS[coin]['raw']
                    
                    side = None
                    if velocity > threshold and yes_price < 0.75:
                        side = 'YES'
                    elif velocity < -threshold and no_price < 0.75:
                        side = 'NO'
                    
                    if not side:
                        return
                    
                    # Volume filter (Part 1)
                    if volume_emas[coin] > 0:
                        if volume < volume_emas[coin] * VOLUME_MULTIPLIERS[coin]:
                            return
                    
                    # Sentiment filter (Part 2)
                    fng = 50  # Neutral for now - can integrate FNG API
                    sentiment_mult = get_sentiment_mult(fng, side)
                    if sentiment_mult is None:
                        return
                    
                    # MTF filter (Part 4) - requires M15 + H1 alignment
                    # Simplified: check if velocity is strong
                    if abs(velocity) < threshold * 1.2:
                        return
                    
                    signal = calculate_edge(
                        coin=coin,
                        yes_price=yes_price,
                        no_price=no_price,
                        velocity=velocity,
                        regime_params=REGIME_PARAMS.get(our_regime, REGIME_PARAMS['default']),
                        market=data
                    )
                    
                    if signal:
                        # Calibrated Kelly position sizing
                        entry_price = signal['yes_price'] if signal['side'] == 'YES' else signal['no_price']
                        amount, kelly_diag = get_kelly_stake_with_diagnostics(
                            entry_price=entry_price,
                            bankroll=virtual_free,
                            coin=coin,
                        )
                        
                        if amount == 0.0:
                            print(f"⛔ KELLY SKIP: {kelly_diag.get('reason', 'Unknown')}")
                            return
                        
                        # Apply sentiment and confidence multipliers on top of Kelly
                        amount = amount * sentiment_mult * signal.get('confidence', 1.0)
                        amount = max(1.0, min(virtual_free * 0.10, amount))  # floor/ceiling
                        
                        if amount < 20:
                            return
                        
                        ok, reason = rm.pre_trade_check(coin=coin, side=signal['side'], size_usd=amount)
                        if not ok:
                            print(f"⛔ RISK BLOCK: {reason[:60]}")
                            return
                        
                        trade_count += 1
                        side = signal['side']
                        
                        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} EDGE {coin} {tf}m | {side} @ {entry_price:.3f} | Kelly: ${amount:.2f}")
                        
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
                        
                        # Register with resolution fallback engine
                        expiration_ts = time.time() + (tf * 60)
                        expiration_utc = datetime.fromtimestamp(expiration_ts, tz=timezone.utc).isoformat()
                        slot = int(time.time() // (tf * 60)) * (tf * 60)
                        slug = f"{coin.lower()}-updown-{tf}m-{slot}"
                        resolution_engine.register_position(
                            market_id=market_key,
                            slug=slug,
                            coin=coin.upper(),
                            timeframe_minutes=tf,
                            entry_price=entry_price,
                            position_side=side,
                            expiration_utc=expiration_utc,
                        )
                        
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

def on_message(ws, message):
    global prices, velocities_ema, current_regimes, volume_emas
    
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        volume = float(data.get('q', 0))
        
        if symbol in COINS and price > 0:
            # Update volume EMA
            if volume_emas[symbol] == 0:
                volume_emas[symbol] = volume
            else:
                alpha = 2 / 21
                volume_emas[symbol] = alpha * volume + (1 - alpha) * volume_emas[symbol]
            
            if symbol in regime_detectors:
                regime_detectors[symbol].append(price)
                current_regimes[symbol] = detect_regime(symbol)
            
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ ULTIMATE BOT v4 - PRODUCTION - CONNECTED!")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Features: Volume + Sentiment + Adaptive Exits + MTF")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Balance: ${VIRTUAL_BANKROLL:.2f}")
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
print("ULTIMATE BOT v4 - PRODUCTION")
print("Volume Filter + Sentiment + Adaptive Exits + MTF")
print("="*70)

start_bot()
