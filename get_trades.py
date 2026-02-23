import sqlite3
import json

conn = sqlite3.connect('memory/memory.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT * FROM trades ORDER BY timestamp DESC')
trades = cursor.fetchall()

print('=== ALL TRADES ===')
for trade in trades:
    t = dict(trade)
    print(f"ID: {t['id']}")
    print(f"  Market ID: {t['market_id']}")
    print(f"  Question: {t['market_question']}")
    print(f"  Side: {t['side']}")
    print(f"  Size: ${t['size_usd']}")
    print(f"  Entry: {t['entry_price']}")
    print(f"  Status: {t['status']}")
    print(f"  Tx: {t['tx_hash']}")
    print(f"  PnL: {t['pnl_usd']}")
    print()

conn.close()
