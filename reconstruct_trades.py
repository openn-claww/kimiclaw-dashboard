#!/usr/bin/env python3
"""
Reconstruct missing trades from cron logs
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")

# Missing trades from cron logs
MISSING_TRADES = [
    {
        "timestamp": "2026-02-19 23:23:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.42,
        "tx_hash": "fbaab0da184ef7e7c82100424f24f0649e8a4c80e39f256f0a58301dcd8065c5",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "BTC trading above $66K threshold, market mispriced at 42%",
        "confidence": 9
    },
    {
        "timestamp": "2026-02-19 23:33:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.715,
        "tx_hash": "995847c81b3a358eaf85fbbb4f7336559f78d0ded6866aa38f0a293f73d0041f",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "High confidence YES - BTC above threshold",
        "confidence": 8
    },
    {
        "timestamp": "2026-02-19 23:43:00",
        "market_id": "1345690",
        "market_question": "Will Bitcoin dip to $55,000 in February?",
        "side": "NO",
        "size_usd": 1.0,
        "entry_price": 0.89,
        "tx_hash": "ca411e904c9b53a5c74f588e79b077e1314daa5edec5ba73091c01740eca830a",
        "strategy": "Auto-trade BTC no dip",
        "reasoning": "BTC at ~$95K, 42% drop to $55K extremely unlikely in 10 days",
        "confidence": 9
    },
    {
        "timestamp": "2026-02-19 23:53:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.76,
        "tx_hash": "cc3a448628e4b6e154c33ac00750b2b82237eceaff21065cf4f8f0ee2d4588ff",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "Market expires in hours, BTC above threshold",
        "confidence": 8
    },
    {
        "timestamp": "2026-02-20 00:03:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.62,
        "tx_hash": "74d253d831b4a580c7baf10a43ca044c2978bfaa30c945956ea2608b9bf457b6",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "BTC at ~$66,500, above $66K threshold, ~38% edge",
        "confidence": 8
    },
    {
        "timestamp": "2026-02-20 00:13:00",
        "market_id": "1345641",
        "market_question": "Will Bitcoin reach $75,000 in February?",
        "side": "NO",
        "size_usd": 1.0,
        "entry_price": 0.845,
        "tx_hash": "1649fcfd1bf9c8b2cc18241b6e9476508f3beb5e9e752ab548104fac20a92e19",
        "strategy": "Auto-trade BTC no $75K",
        "reasoning": "BTC at ~$96K, already achieved $75K, NO pays 84.5%",
        "confidence": 9
    },
    {
        "timestamp": "2026-02-20 00:23:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.68,
        "tx_hash": "7cb1d8b8da4cc72ac0f1566954707a271f3f4618c0393d44144edfbd0c59144d",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "Quick resolution play, BTC holding above threshold",
        "confidence": 8
    },
    {
        "timestamp": "2026-02-20 00:33:00",
        "market_id": "1369917",
        "market_question": "Will the price of Bitcoin be above $66,000 on February 19?",
        "side": "YES",
        "size_usd": 1.0,
        "entry_price": 0.92,
        "tx_hash": "a98ec40e346f2f67b34e663d8cbb8bbb91bb32ac744dd91ab0406b53dedb6fee",
        "strategy": "Auto-trade BTC above $66K",
        "reasoning": "High confidence, market expires today, BTC above $66K",
        "confidence": 9
    }
]

def insert_missing_trades():
    """Insert missing trades into database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted = 0
    skipped = 0
    
    for trade in MISSING_TRADES:
        # Check if already exists
        cursor.execute("SELECT id FROM trades WHERE tx_hash = ?", (trade["tx_hash"],))
        if cursor.fetchone():
            print(f"⏭️  Skipping (exists): {trade['tx_hash'][:16]}...")
            skipped += 1
            continue
        
        # Insert trade
        cursor.execute("""
            INSERT INTO trades (
                timestamp, market_id, market_question, side, size_usd,
                entry_price, status, strategy, reasoning, confidence, tx_hash, github_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade["timestamp"], trade["market_id"], trade["market_question"],
            trade["side"], trade["size_usd"], trade["entry_price"], "OPEN",
            trade["strategy"], trade["reasoning"], trade["confidence"],
            trade["tx_hash"], 0
        ))
        
        inserted += 1
        print(f"✅ Inserted: {trade['market_question'][:40]}... | {trade['side']} ${trade['size_usd']}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: Inserted {inserted}, Skipped {skipped}")
    print(f"{'='*60}")
    
    return inserted

if __name__ == "__main__":
    print("="*60)
    print("RECONSTRUCTING MISSING TRADES")
    print("="*60)
    insert_missing_trades()
