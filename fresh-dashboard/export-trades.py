#!/usr/bin/env python3
"""
Export trades from SQLite to JSON for dashboard
Run this after every trade to update dashboard
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = '/root/.openclaw/skills/polytrader/trades.db'
OUTPUT_PATH = '/root/.openclaw/workspace/fresh-dashboard/public/trades-live.json'

def export_trades():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get all trades
    trades = conn.execute('SELECT * FROM trades ORDER BY timestamp DESC').fetchall()
    
    # Get stats
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_positions,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
            COALESCE(SUM(pnl_usd), 0) as total_pnl,
            COALESCE(SUM(size_usd), 0) as total_invested
        FROM trades
    ''').fetchone()
    
    # Get wallet info
    wallet = {
        'usdc': 11.26,
        'pol': 8.56,
        'total_value': 19.82 + (stats['total_pnl'] or 0)
    }
    
    data = {
        'updated': datetime.now().isoformat(),
        'trades': [dict(t) for t in trades],
        'stats': dict(stats),
        'wallet': wallet
    }
    
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f'✅ Exported {len(trades)} trades to {OUTPUT_PATH}')
    conn.close()

if __name__ == '__main__':
    export_trades()
