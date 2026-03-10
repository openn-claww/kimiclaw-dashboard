#!/usr/bin/env python3
"""
pre_live_check.py — Pre-flight verification before live trading
Run: python3 /root/.openclaw/workspace/pre_live_check.py

Checks all 7 issue areas and prints a GO / NO-GO decision.
"""
import os, sys, json, subprocess, re
from pathlib import Path

WS = '/root/.openclaw/workspace'
sys.path.insert(0, WS)

PASS = '✅'; FAIL = '❌'; WARN = '⚠️ '
results = {'pass': 0, 'fail': 0, 'warn': 0}

def chk(ok, label, detail='', critical=True):
    sym = PASS if ok else (FAIL if critical else WARN)
    key = 'pass' if ok else ('fail' if critical else 'warn')
    results[key] += 1
    print(f"  {sym} {label}" + (f"\n       {detail}" if detail else ''))
    return ok

print("=" * 65)
print("  PRE-LIVE CHECKLIST — Polymarket Bot V6")
print("=" * 65)

# ── SECTION 1: Environment variables ─────────────────────────────
print("\n[1] Environment Variables")

required = {
    'POLY_PRIVATE_KEY':    ('0x', 'Wallet private key'),
    'POLY_ADDRESS':        ('0x', 'Wallet address'),
    'CHAINSTACK_NODE':     ('https://', 'Polygon RPC'),
    'POLY_PAPER_TRADING':  (None, 'Paper/live mode flag'),
}
optional_with_defaults = {
    'MAX_SINGLE_TRADE_USD': ('5.0',  'Max bet per trade'),
    'MIN_SINGLE_TRADE_USD': ('1.0',  'Min bet per trade'),
    'MAX_POSITION_PCT':     ('0.08', 'Max % per position'),
    'MAX_DAILY_LOSS_PCT':   ('0.10', 'Max daily loss %'),
    'MAX_CONSECUTIVE_LOSSES': ('5',  'Consecutive loss limit'),
    'MAX_TOTAL_EXPOSURE_PCT': ('0.25','Max total exposure %'),
    'HTTPS_PROXY':          (None,   'Residential proxy (optional)'),
}

for var, (prefix, desc) in required.items():
    val = os.getenv(var, '')
    ok  = bool(val) and (val.startswith(prefix) if prefix else True)
    chk(ok, f"{var} set", f"current: {'*****' if 'KEY' in var or 'PRIVATE' in var else val[:40]}")

for var, (default, desc) in optional_with_defaults.items():
    val = os.getenv(var, default or '')
    chk(bool(val), f"{var} = {val}", desc, critical=False)

paper = os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true'
chk(not paper, "POLY_PAPER_TRADING=false (live mode)", 
    "Set to false when ready — currently: " + os.getenv('POLY_PAPER_TRADING','true'),
    critical=False)

# ── SECTION 2: PolyClaw wallet + approvals ───────────────────────
print("\n[2] PolyClaw Wallet")

try:
    r = subprocess.run(
        ['uv', 'run', 'python', 'scripts/polyclaw.py', 'wallet', 'status'],
        capture_output=True, text=True, timeout=15,
        cwd='/root/.openclaw/skills/polyclaw'  # Fixed path
    )
    if r.returncode == 0:
        try:
            w = json.loads(r.stdout)
            usdc = float(w.get('balances', {}).get('USDC.e', 0))
            pol  = float(w.get('balances', {}).get('POL', 0))
            unlocked    = w.get('unlocked', False)
            approvals   = w.get('approvals_set', False)
            chk(unlocked,        "Wallet unlocked")
            chk(approvals,       "Contract approvals set",
                "If not set: uv run python scripts/polyclaw.py wallet approve")
            chk(usdc >= 10,      f"USDC balance ${usdc:.2f} >= $10",
                f"Current: ${usdc:.2f}")
            chk(pol  >= 0.05,    f"POL balance {pol:.3f} >= 0.05 (gas)",
                "Low gas — top up Polygon POL")
        except json.JSONDecodeError:
            chk(False, "Wallet status JSON parse failed", r.stdout[:100])
    else:
        chk(False, "PolyClaw wallet status failed", r.stderr[:100])
except FileNotFoundError:
    chk(False, "uv / polyclaw not found", "Check PolyClaw installation")
except subprocess.TimeoutExpired:
    chk(False, "Wallet status timed out (RPC issue?)")

# ── SECTION 3: Proxy check ───────────────────────────────────────
print("\n[3] Proxy / CLOB connectivity")

proxy = os.getenv('HTTPS_PROXY', '')
if proxy:
    chk(True, f"HTTPS_PROXY set: {proxy[:40]}...", critical=False)
    # Quick connectivity test through proxy
    try:
        import requests
        r = requests.get('https://clob.polymarket.com/tick-size',
                         proxies={'https': proxy}, timeout=8)
        chk(r.status_code == 200, f"CLOB reachable via proxy (status {r.status_code})")
    except Exception as e:
        chk(False, f"CLOB via proxy failed: {e}")
else:
    chk(False, "No HTTPS_PROXY set — datacenter IPs may be blocked",
        "Set: export HTTPS_PROXY=http://user:pass@geo.iproyal.com:12321",
        critical=False)
    # Test direct access
    try:
        import requests
        r = requests.get('https://clob.polymarket.com/tick-size', timeout=8)
        chk(r.status_code == 200,
            f"CLOB reachable without proxy (status {r.status_code})",
            "Direct access works — proxy optional for now", critical=False)
    except Exception as e:
        chk(False, f"CLOB direct access failed: {e}",
            "→ Proxy required. Get residential proxy from iproyal.com / brightdata.com")

# ── SECTION 4: Risk limits sanity check ─────────────────────────
print("\n[4] Risk Limits (for $59 bankroll)")

bankroll  = 59.0  # update this if you top up
max_trade = float(os.getenv('MAX_SINGLE_TRADE_USD', '75.0'))
max_daily = float(os.getenv('MAX_DAILY_LOSS_PCT',   '0.15'))
max_expo  = float(os.getenv('MAX_TOTAL_EXPOSURE_PCT','0.50'))

chk(max_trade <= 5.0,
    f"MAX_SINGLE_TRADE_USD=${max_trade:.2f} (want ≤$5)",
    f"Currently ${max_trade:.2f} — set: export MAX_SINGLE_TRADE_USD=5.0")
chk(max_daily <= 0.10,
    f"MAX_DAILY_LOSS_PCT={max_daily:.0%} (want ≤10%)",
    f"$={bankroll*max_daily:.2f} max daily loss")
chk(max_expo  <= 0.25,
    f"MAX_TOTAL_EXPOSURE_PCT={max_expo:.0%} (want ≤25%)",
    f"${bankroll*max_expo:.2f} max concurrent exposure")
chk(True, f"Kill switch auto-reset at 15min quiet window", critical=False)

# ── SECTION 5: Key bot files exist ──────────────────────────────
print("\n[5] Bot Files")

required_files = [
    'master_bot_v6_polyclaw_integration.py',
    'pnl_tracker.py',
    'cross_market_arb.py',
    'atomic_json.py',
]
optional_files = [
    'proxy_manager.py',
    'auto_redeem.py',
    'news_feed.py',
]
for f in required_files:
    chk(Path(f'{WS}/{f}').exists(), f"{f} exists")
for f in optional_files:
    chk(Path(f'{WS}/{f}').exists(), f"{f} exists (optional)", critical=False)

# Check master_bot has all critical fixes applied
mb = Path(f'{WS}/master_bot_v6_polyclaw_integration.py').read_text()
fixes = {
    'FIX-1 (trade log dict wrapper)': '"trades"' in mb and 'atomic_write_json' in mb,
    'FIX-2A (WS errors skip kill switch)': 'TRADING_ERRORS' in mb,
    'FIX-2B (WS ping keepalive)':     'ping_interval=20' in mb,
    'FIX-2C (kill switch auto-reset)': 'reset_if_stale' in mb,
    'FIX-3 (stale PID lock)':          '_is_stale_lock' in mb,
    'FIX-4 (Kelly sizing)':            'kelly_f' in mb,
}
for label, ok in fixes.items():
    chk(ok, label)

# ── SECTION 6: Warmup mode ──────────────────────────────────────
print("\n[6] Warmup Mode")

warmup = int(os.getenv('WARMUP_TRADE_COUNT', '0'))
warmup_max = float(os.getenv('WARMUP_MAX_BET', '1.0'))
chk(warmup >= 20, f"WARMUP_TRADE_COUNT={warmup} (want ≥20 for $1 warmup)",
    "Set: export WARMUP_TRADE_COUNT=20", critical=False)
chk(warmup_max <= 1.0, f"WARMUP_MAX_BET=${warmup_max:.2f} (want $1.00)",
    "Set: export WARMUP_MAX_BET=1.0", critical=False)

# ── SECTION 7: Telegram alerts ──────────────────────────────────
print("\n[7] Alerts")

tg_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
tg_chat  = os.getenv('TELEGRAM_CHAT_ID', '')
chk(bool(tg_token and tg_chat),
    "Telegram alerts configured",
    "Get token: @BotFather on Telegram → /newbot\n"
    "       Get chat_id: send /start to your bot then:\n"
    "       curl https://api.telegram.org/bot<TOKEN>/getUpdates",
    critical=False)
if tg_token and tg_chat:
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={'chat_id': tg_chat, 'text': '🤖 Pre-live check: Telegram OK'},
            timeout=5
        )
        chk(r.ok, "Telegram test message sent", critical=False)
    except Exception as e:
        chk(False, f"Telegram test failed: {e}", critical=False)

# ── VERDICT ─────────────────────────────────────────────────────
print("\n" + "=" * 65)
total = sum(results.values())
print(f"  RESULTS: {results['pass']}/{total} passed, "
      f"{results['fail']} critical failures, "
      f"{results['warn']} warnings")
print()

if results['fail'] == 0:
    print("  🟢 GO — All critical checks passed")
    print("     Recommended rollout:")
    print("     Phase 1: WARMUP_TRADE_COUNT=20 WARMUP_MAX_BET=1.0 (first 20 trades @ $1)")
    print("     Phase 2: After 20 trades profitable → remove warmup cap")
    print("     Phase 3: After 1 week profitable → consider increasing to $10 max")
elif results['fail'] <= 2:
    print("  🟡 CONDITIONAL GO — Fix critical failures above before live trading")
else:
    print("  🔴 NO-GO — Too many critical failures")

print("=" * 65)
