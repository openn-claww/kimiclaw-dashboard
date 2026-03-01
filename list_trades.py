#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('memory/memory.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('''
    SELECT id, timestamp, market_id, market_question, side, size_usd, entry_price, exit_price, pnl_usd, status, tx_hash, strategy, tags
    FROM trades
    ORDER BY timestamp DESC
''')

trades = cursor.fetchall()

print(f"Total trades: {len(trades)}")
print("=" * 80)

for t in trades:
    print(f"ID: {t['id']}")
    print(f"Time: {t['timestamp']}")
    print(f"Market: {t['market_question']} (ID: {t['market_id']})")
    print(f"Side: {t['side']} | Amount: ${t['size_usd']}")
    print(f"Entry: {t['entry_price']} | Exit: {t['exit_price']}")
    print(f"PnL: {t['pnl_usd']} | Status: {t['status']}")
    print(f"Tx: {t['tx_hash']}")
    print(f"Tags: {t['tags']}")
    print("-" * 80)

conn.close()
