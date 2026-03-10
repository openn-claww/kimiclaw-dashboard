#!/bin/bash
# Daily Bot Status Report
# Run: ./daily_status.sh

echo "═══════════════════════════════════════════════════════════════"
echo "  V4 BOT DAILY STATUS - $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "🤖 BOT PROCESS"
echo "─────────────────────────────────────────────────────────────"
ps aux | grep ultimate_bot_v4_production | grep -v grep | grep -v bash || echo "  Bot NOT running!"

echo ""
echo "💰 WALLET STATUS"
echo "─────────────────────────────────────────────────────────────"
python3 -c "
import json
try:
    with open('/root/.openclaw/workspace/wallet_v4_production.json') as f:
        w = json.load(f)
    print(f\"  Balance:       \${w.get('bankroll_current', 0):,.2f}\")
    print(f\"  Started:       {w.get('started_at', 'N/A')}\")
    print(f\"  Total Trades:  {w.get('total_trades', 0)}\")
    print(f\"  Win Rate:      {w.get('winning_trades', 0)}/{w.get('total_trades', 0)}\")
    print(f\"  Total P&L:     \${w.get('total_pnl', 0):+.2f}\")
    print(f\"  Today's P&L:   \${w.get('daily_pnl', 0):+.2f}\")
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "📊 RECENT TRADES"
echo "─────────────────────────────────────────────────────────────"
python3 -c "
import json
try:
    with open('/root/.openclaw/workspace/wallet_v4_production.json') as f:
        w = json.load(f)
    trades = w.get('trades', [])
    if trades:
        for t in trades[-5:]:
            status = t.get('resolution_status', 'OPEN')
            pnl = t.get('pnl', 0)
            print(f\"  {t.get('market', 'N/A'):<12} {t.get('side', 'N/A'):>4} @ {t.get('entry_price', 0):.3f} | {status:<12} | \${pnl:>+7.2f}\")
    else:
        print('  No trades yet')
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "🔍 RESOLUTION FALLBACK"
echo "─────────────────────────────────────────────────────────────"
python3 -c "
import json
try:
    with open('/root/.openclaw/workspace/resolution_state.json') as f:
        r = json.load(f)
    unresolved = [v for v in r.values() if not v.get('resolved')]
    resolved = [v for v in r.values() if v.get('resolved')]
    print(f\"  Tracked:   {len(r)}\")
    print(f\"  Unresolved: {len(unresolved)}\")
    print(f\"  Resolved:   {len(resolved)}\")
    if resolved:
        print()
        print('  Recent resolutions:')
        for pos in list(resolved)[-3:]:
            tier = pos.get('resolution_tier', 1)
            tier_label = {1: 'OFFICIAL', 2: 'FALLBACK', 3: 'FORCED'}.get(tier, '?')
            print(f\"    {pos['market_id']} → {pos.get('resolution_outcome')} [{tier_label}]\")
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "🎯 KELLY CALIBRATION"
echo "─────────────────────────────────────────────────────────────"
python3 -c "
import json
try:
    with open('/root/.openclaw/workspace/kelly_calibration.json') as f:
        k = json.load(f)
    trades = k.get('trades', [])
    print(f\"  Trades recorded: {len(trades)}\")
    if trades:
        buckets = {}
        for t in trades:
            b = t.get('bucket', 'unknown')
            buckets[b] = buckets.get(b, 0) + 1
        print()
        print('  Per-bucket samples:')
        for b, n in sorted(buckets.items()):
            status = '✓' if n >= 30 else ('~' if n >= 10 else '○')
            print(f\"    {status} {b:<12}: {n:>3} trades\")
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "⚠️  RISK STATUS"
echo "─────────────────────────────────────────────────────────────"
python3 -c "
import json
try:
    with open('/root/.openclaw/workspace/wallet_v4_production.json') as f:
        w = json.load(f)
    if w.get('kill_switch_triggered'):
        print('  🚨 KILL SWITCH TRIGGERED')
    else:
        print('  ✅ Kill switch: OK')
    print(f\"  Drawdown halt: {w.get('halted', False)}\")
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Next: Check again tomorrow morning for 24h results"
echo "═══════════════════════════════════════════════════════════════"
