#!/usr/bin/env python3
"""
ULTIMATE BOT v4 - FIXED with proper headers
"""

import websocket
import json
import time
import urllib.request
from datetime import datetime
from collections import defaultdict
import threading
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from risk_manager import RiskManager

# ============ CONFIGURATION ============
VIRTUAL_BANKROLL = 500.00
POSITION_SIZE_PCT = 0.05
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
COINS = ['BTC', 'ETH', 'SOL', 'XRP']
STATE_FILE = "/root/.openclaw/workspace/wallet_v4_fixed.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# ============ INITIALIZE ============
rm = RiskManager(starting_balance=VIRTUAL_BANKROLL)
prices = {}
velocities_ema = {}
trade_count = 0
virtual_free = VIRTUAL_BANKROLL
active_positions = {}
refresher_running = True

def find_markets(timeframe):
    results = []
    for asset in ["btc", "eth"]:
        slug = f"{asset}-updown-{timeframe}"
        url = f"{GAMMA_API}/events?slug={slug}&closed=false&limit=5&order=id&ascending=false"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=5) as resp:
                events = json.loads(resp.read())
            for event in events:
                markets = event.get("markets", [])
                if markets:
                    outcome_prices = json.loads(markets[0].get("outcomePrices", '["0.5","0.5"]'))
                    results.append({
                        "asset": asset.upper(),
                        "timeframe": timeframe,
                        "slug": event.get("slug"),
                        "yes_price": float(outcome_prices[0]),
                        "no_price": float(outcome_prices[1]),
                    })
                    break
        except Exception as e:
            pass
    return results

def market_refresh_loop():
    global active_positions
    while refresher_running:
        for tf in ['5m', '15m']:
            markets = find_markets(tf)
            for m in markets:
                key = f"{m['asset']}_{tf}"
                if key not in active_positions or active_positions[key].get('slug') != m['slug']:
                    print(f"[MARKET] {key}: {m['slug'][:50]}... | YES:{m['yes_price']:.3f} NO:{m['no_price']:.3f}")
                active_positions[key] = m
        time.sleep(240)  # Refresh every 4 min

def on_message(ws, message):
    global prices, velocities_ema, trade_count, virtual_free
    try:
        data = json.loads(message)
        symbol = data.get('s', '').replace('USDT', '')
        price = float(data.get('p', 0))
        
        if symbol in COINS and price > 0:
            if symbol in prices:
                velocity = price - prices[symbol]
                if symbol not in velocities_ema:
                    velocities_ema[symbol] = velocity
                else:
                    velocities_ema[symbol] = 0.3 * velocity + 0.7 * velocities_ema[symbol]
                
                # Check for trades
                threshold = {'BTC': 0.15, 'ETH': 0.015, 'SOL': 0.25, 'XRP': 0.08}.get(symbol, 0.1)
                for tf in ['5m', '15m']:
                    key = f"{symbol}_{tf}"
                    if key in active_positions:
                        market = active_positions[key]
                        vel = velocities_ema[symbol]
                        yes_p = market['yes_price']
                        no_p = market['no_price']
                        
                        side = None
                        if vel > threshold and yes_p < 0.75:
                            side = 'YES'
                        elif vel < -threshold and no_p < 0.75:
                            side = 'NO'
                        
                        if side and virtual_free >= 20:
                            trade_count += 1
                            amount = min(50.0, virtual_free * POSITION_SIZE_PCT)
                            print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] #{trade_count} {symbol} {tf} | {side} | ${amount:.2f}")
                            virtual_free -= amount
            
            prices[symbol] = price
    except:
        pass

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ BOT CONNECTED - Balance: ${virtual_free:.2f}")
    threading.Thread(target=market_refresh_loop, daemon=True).start()

def on_error(ws, error):
    print(f"⚠️  Error: {error}")

def on_close(ws, *args):
    print("🔌 Reconnecting...")
    time.sleep(5)
    start_bot()

def start_bot():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade",
        on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close
    )
    ws.run_forever()

print("="*60)
print("ULTIMATE BOT v4 - FIXED")
print("="*60)
start_bot()
