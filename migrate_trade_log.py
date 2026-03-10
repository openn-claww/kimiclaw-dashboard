#!/usr/bin/env python3
"""migrate_trade_log.py — Convert list-format trade log to dict format"""
import json
from pathlib import Path
TRADE_LOG = '/root/.openclaw/workspace/master_v6_trades.json'
p = Path(TRADE_LOG)
if not p.exists():
    print("No trade log found"); exit()
raw = json.loads(p.read_text())
if isinstance(raw, list):
    new = {"trades": raw, "meta": {"count": len(raw), "migrated": True, "version": "v6"}}
    bak = TRADE_LOG + '.pre_migration'
    p.rename(bak)
    p.write_text(json.dumps(new, indent=2))
    print(f"Migrated {len(raw)} trades. Backup: {bak}")
elif isinstance(raw, dict) and "trades" in raw:
    print(f"Already migrated: {len(raw['trades'])} trades")
else:
    print(f"Unknown format: {type(raw)}")
