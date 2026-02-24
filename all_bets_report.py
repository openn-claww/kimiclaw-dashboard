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

output = []
output.append("📊 ALL BETS TRACKER REPORT")
output.append(f"📅 Generated: Tuesday, February 24th, 2026 — 8:32 PM (Asia/Shanghai)")
output.append(f"📈 Total Bets: {len(trades)}")
output.append("")

# Separate open and closed
open_trades = [t for t in trades if t['status'] == 'OPEN']
closed_trades = [t for t in trades if t['status'] == 'CLOSED']

output.append(f"🔵 OPEN BETS: {len(open_trades)}")
output.append("=" * 60)

for t in open_trades:
    # Calculate expected return for open trades
    entry = t['entry_price'] or 0
    size = t['size_usd'] or 0
    if entry > 0:
        expected_return = size / entry  # If you bet at 0.97, you get ~1.03
    else:
        expected_return = size
    
    tx_link = f"[Tx](https://polygonscan.com/tx/{t['tx_hash']})" if t['tx_hash'] else "N/A"
    
    output.append(f"📊 BET #{t['id']} | Market: {t['market_question']} | Side: {t['side']} | Amount: ${size:.2f} | Status: {t['status']} | Expected: ${expected_return:.2f} | Tx: {tx_link}")

output.append("")
output.append(f"✅ CLOSED BETS: {len(closed_trades)}")
output.append("=" * 60)

for t in closed_trades:
    size = t['size_usd'] or 0
    pnl = t['pnl_usd'] or 0
    exit_price = t['exit_price'] or 0
    
    # For closed trades, expected return is the payout
    expected_return = size + pnl
    
    tx_link = f"[Tx](https://polygonscan.com/tx/{t['tx_hash']})" if t['tx_hash'] else "N/A"
    
    output.append(f"📊 BET #{t['id']} | Market: {t['market_question']} | Side: {t['side']} | Amount: ${size:.2f} | Status: {t['status']} | Expected: ${expected_return:.2f} | Tx: {tx_link}")

output.append("")
output.append("📋 SUMMARY")
output.append("-" * 40)

# Calculate totals
total_wagered = sum(t['size_usd'] or 0 for t in trades)
total_open = sum(t['size_usd'] or 0 for t in open_trades)
total_closed_pnl = sum(t['pnl_usd'] or 0 for t in closed_trades)

output.append(f"💰 Total Wagered: ${total_wagered:.2f}")
output.append(f"🔵 Open Exposure: ${total_open:.2f}")
output.append(f"✅ Closed P&L: +${total_closed_pnl:.2f}")

print("\n".join(output))

conn.close()
