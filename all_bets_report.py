#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('memory/memory.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM trades ORDER BY id DESC')
trades = cursor.fetchall()
conn.close()

print('=== ALL BETS TRACKER ===\n')
print(f'Total Bets: {len(trades)}')
print(f'Open Bets: {sum(1 for t in trades if t[10] == "OPEN")}')
print(f'Closed Bets: {sum(1 for t in trades if t[10] == "CLOSED")}')
print()

for trade in trades:
    id_, timestamp, market_id, market_question, side, size_usd, entry_price, exit_price, pnl_usd, pnl_percent, status, tx_hash, strategy, reflection, tags = trade
    
    # Calculate expected return
    if status == 'OPEN':
        if side == 'YES':
            expected_return = size_usd * (1 / entry_price) if entry_price > 0 else 0
        else:  # NO
            expected_return = size_usd * (1 / (1 - entry_price)) if entry_price < 1 else 0
    else:  # CLOSED
        if pnl_usd is not None:
            expected_return = size_usd + pnl_usd
        else:
            expected_return = size_usd
    
    tx_link = f'https://polygonscan.com/tx/{tx_hash}' if tx_hash else 'N/A'
    
    print(f'📊 BET #{id_}')
    print(f'   Market: {market_question}')
    print(f'   Side: {side}')
    print(f'   Amount: ${size_usd:.2f}')
    print(f'   Status: {status}')
    print(f'   Expected Return: ${expected_return:.2f}')
    print(f'   Tx: {tx_link}')
    if pnl_usd is not None:
        pnl_str = f'{pnl_percent*100:.1f}%' if pnl_percent is not None else 'N/A'
        print(f'   PnL: ${pnl_usd:.2f} ({pnl_str})')
    print()
