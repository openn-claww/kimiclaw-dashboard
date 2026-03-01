#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('memory/memory.db')
cursor = conn.cursor()

# Report for Feb 25, 2026 (London GMT midnight = 00:00)
report_date = '2026-02-25'

print('=' * 60)
print(f'DAILY EOD REPORT - {report_date}')
print('=' * 60)

# 1. Total bets placed today (Feb 25)
cursor.execute('''
    SELECT COUNT(*) FROM trades 
    WHERE timestamp LIKE ?
''', (f'{report_date}%',))
bets_today = cursor.fetchone()[0]
print(f'\n1) TOTAL BETS PLACED TODAY: {bets_today}')

# 2. Total invested today
cursor.execute('''
    SELECT COALESCE(SUM(size_usd), 0) FROM trades 
    WHERE timestamp LIKE ?
''', (f'{report_date}%',))
invested_today = cursor.fetchone()[0]
print(f'2) TOTAL INVESTED TODAY: ${invested_today:.2f} USDC')

# 3. Total P&L today (realized from trades closing today)
cursor.execute('''
    SELECT COALESCE(SUM(pnl_usd), 0) FROM trades 
    WHERE timestamp LIKE ? AND status = 'CLOSED'
''', (f'{report_date}%',))
pnl_today = cursor.fetchone()[0]
print(f'3) TOTAL P&L TODAY: ${pnl_today:.2f} USDC')

# 4. Gas fees spent
print(f'4) GAS FEES SPENT: $0.00 (not tracked in current system)')

# 5. Net profit/loss after fees
net_pnl = pnl_today - 0
print(f'5) NET PROFIT/LOSS AFTER FEES: ${net_pnl:.2f} USDC')

# 6. Resolved bets + redeemed amounts today
cursor.execute('''
    SELECT COUNT(*), COALESCE(SUM(size_usd), 0), COALESCE(SUM(pnl_usd), 0) 
    FROM trades 
    WHERE timestamp LIKE ? AND status = 'CLOSED'
''', (f'{report_date}%',))
resolved = cursor.fetchone()
print(f'6) RESOLVED BETS TODAY: {resolved[0]}')
print(f'   Redeemed Amounts: ${resolved[1] + resolved[2]:.2f} USDC (principal + profit)')

# 7. Pending bets summary (all open positions)
cursor.execute('''
    SELECT COUNT(*), COALESCE(SUM(size_usd), 0) FROM trades 
    WHERE status = 'OPEN'
''')
pending = cursor.fetchone()
print(f'\n7) PENDING BETS SUMMARY:')
print(f'   Total Open Positions: {pending[0]}')
print(f'   Total Value at Risk: ${pending[1]:.2f} USDC')

# List open positions
cursor.execute('''
    SELECT market_question, side, size_usd, entry_price 
    FROM trades 
    WHERE status = 'OPEN'
    ORDER BY timestamp DESC
''')
open_positions = cursor.fetchall()
print(f'\n   OPEN POSITIONS:')
for pos in open_positions:
    print(f'   - {pos[0][:40]}... | {pos[1]} | ${pos[2]} @ ${pos[3]}')

# Account summary
cursor.execute('SELECT COALESCE(SUM(pnl_usd), 0) FROM trades WHERE pnl_usd IS NOT NULL')
total_realized_pnl = cursor.fetchone()[0]
print(f'\nLIFETIME REALIZED P&L: ${total_realized_pnl:.2f} USDC')

conn.close()
print('\n' + '=' * 60)
print('Report generated: 2026-02-26 03:27 AM Asia/Shanghai')
print('Reporting period: 2026-02-25 00:00 - 23:59 GMT')
print('=' * 60)
