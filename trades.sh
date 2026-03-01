#!/bin/bash
# trades.sh — Show all trades with PnL
python3 /root/.openclaw/workspace/../trade_manager.py list 2>/dev/null || \
python3 -c "
import json
from pathlib import Path

f = Path('/root/.openclaw/workspace/trades_v4.json')
if not f.exists():
    print('No trades file found.')
    exit(0)

trades = json.loads(f.read_text())
if not trades:
    print('No trades recorded.')
    exit(0)

print(f\"\n{'─'*80}\")
print(f\"{'ID':<22} {'Coin':<6} {'Side':<5} {'TF':<5} {'Entry':<8} {'Status':<8} {'PnL':>8}\")
print(f\"{'─'*80}\")
for t in sorted(trades.values(), key=lambda x: x.get('entry_time', 0)):
    pnl = t.get('net_pnl', 0)
    pnl_str = f'+{pnl:.4f}' if pnl >= 0 else f'{pnl:.4f}'
    status = t.get('status', '?')
    icon = '✅' if status == 'won' else ('❌' if status == 'lost' else '⏳')
    print(f\"{t.get('trade_id','?')[:22]:<22} {t.get('coin',''):<6} {t.get('side',''):<5} {t.get('timeframe',''):<5} {t.get('entry_price',0):<8.3f} {icon+status:<8} {pnl_str:>8}\")
print(f\"{'─'*80}\n\")
"
