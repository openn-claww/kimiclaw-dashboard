#!/usr/bin/env python3
"""
Fixed Dashboard Sync - Prevents getting stuck
"""

import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# Config
DB_PATH = "/root/.openclaw/skills/polytrader/trades.db"
LOG_FILE = "/root/.openclaw/workspace/logs/sync.log"

def log_sync(message):
    """Log sync activity"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    print(message)

def sync_dashboard():
    """Sync dashboard with latest data"""
    log_sync("Starting dashboard sync...")
    
    try:
        # Get trade data
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC")
        trades = [dict(row) for row in cursor.fetchall()]
        
        # Get stats
        cursor.execute("SELECT COUNT(*) as total, SUM(size_usd) as invested FROM trades")
        stats = cursor.fetchone()
        
        conn.close()
        
        # Log success
        log_sync(f"Sync complete - {len(trades)} trades, ${stats['invested'] or 0:.2f} invested")
        
        return {
            'success': True,
            'trades': len(trades),
            'invested': stats['invested'] or 0,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        log_sync(f"Sync error: {e}")
        return {'success': False, 'error': str(e)}

if __name__ == "__main__":
    result = sync_dashboard()
    print(json.dumps(result, indent=2))
