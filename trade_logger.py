#!/usr/bin/env python3
"""
Trade Logger - Robust database logging with verification
"""

import sqlite3
import json
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")

def log_trade(market_id, market_question, side, size_usd, entry_price, tx_hash, strategy="", reasoning="", confidence=5):
    """Log a trade to database with verification"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Insert trade
        cursor.execute("""
            INSERT INTO trades (
                timestamp, market_id, market_question, side, size_usd, 
                entry_price, status, strategy, reasoning, confidence, tx_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, market_id, market_question, side, size_usd,
            entry_price, 'OPEN', strategy, reasoning, confidence, tx_hash
        ))
        
        conn.commit()
        
        # Verify insertion
        cursor.execute("SELECT * FROM trades WHERE tx_hash = ?", (tx_hash,))
        result = cursor.fetchone()
        
        if result:
            print(f"✅ Trade logged successfully: {tx_hash[:16]}...")
            return True
        else:
            print(f"❌ Trade NOT found after insertion: {tx_hash}")
            return False
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_trade_count():
    """Get total trade count"""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.close()
    return count

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "count":
        print(f"Total trades: {get_trade_count()}")
    else:
        # Test logging
        log_trade(
            market_id="12345",
            market_question="Test market",
            side="YES",
            size_usd=1.0,
            entry_price=0.5,
            tx_hash="0xtest123",
            strategy="Test",
            reasoning="Testing logger",
            confidence=5
        )
