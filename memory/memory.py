#!/usr/bin/env python3
"""
Memory System v2 - Python Interface
Queryable, scalable, persistent memory for OpenClaw.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path("/root/.openclaw/workspace/memory/memory.db")

class Memory:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """Ensure tables exist"""
        # Tables already created by memory.sh init, skip if exists
        pass
    
    def log_conversation(self, user_msg: str, assistant_msg: str, 
                         tags: str = "", importance: int = 5) -> int:
        """Log a conversation exchange"""
        cursor = self.conn.execute(
            """INSERT INTO conversations (user_message, assistant_message, tags, importance)
               VALUES (?, ?, ?, ?)""",
            (user_msg, assistant_msg, tags, importance)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def log_trade(self, market_id: str, market_question: str, side: str,
                  size_usd: float, entry_price: float, strategy: str,
                  tags: str = "") -> int:
        """Log a new trade"""
        cursor = self.conn.execute(
            """INSERT INTO trades (market_id, market_question, side, size_usd, 
                                  entry_price, status, strategy, tags)
               VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
            (market_id, market_question, side, size_usd, entry_price, strategy, tags)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def close_trade(self, trade_id: int, exit_price: float, 
                    pnl_usd: float, reflection: str = ""):
        """Close a trade and record P&L"""
        pnl_percent = (pnl_usd / (exit_price * 100)) * 100 if exit_price else 0
        self.conn.execute(
            """UPDATE trades SET exit_price = ?, pnl_usd = ?, pnl_percent = ?,
                               status = 'CLOSED', reflection = ?
               WHERE id = ?""",
            (exit_price, pnl_usd, pnl_percent, reflection, trade_id)
        )
        self.conn.commit()
    
    def add_memory(self, content: str, mem_type: str = "lesson",
                   source_trade_id: Optional[int] = None,
                   confidence: int = 7) -> int:
        """Add a distilled memory/lesson"""
        cursor = self.conn.execute(
            """INSERT INTO memories (type, content, source_trade_id, confidence)
               VALUES (?, ?, ?, ?)""",
            (mem_type, content, source_trade_id, confidence)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def update_topic(self, name: str, summary: str, category: str = ""):
        """Update or create a topic"""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO topics (name, category, summary, first_mentioned, last_updated)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   summary = excluded.summary,
                   last_updated = excluded.last_updated""",
            (name, category, summary, now, now)
        )
        self.conn.commit()
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search across all memory types"""
        results = []
        
        # Search conversations
        convs = self.conn.execute(
            """SELECT 'conversation' as source, timestamp, user_message as content, tags
               FROM conversations 
               WHERE user_message LIKE ? OR assistant_message LIKE ?
               ORDER BY timestamp DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        ).fetchall()
        results.extend([dict(r) for r in convs])
        
        # Search memories
        mems = self.conn.execute(
            """SELECT 'memory' as source, timestamp, content, type as tags
               FROM memories WHERE content LIKE ?
               ORDER BY confidence DESC, timestamp DESC LIMIT ?""",
            (f"%{query}%", limit)
        ).fetchall()
        results.extend([dict(r) for r in mems])
        
        # Search topics
        topics = self.conn.execute(
            """SELECT 'topic' as source, last_updated as timestamp, 
                      summary as content, category as tags
               FROM topics WHERE name LIKE ? OR summary LIKE ?
               ORDER BY last_updated DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        ).fetchall()
        results.extend([dict(r) for r in topics])
        
        return results
    
    def get_active_trades(self) -> List[Dict]:
        """Get all open positions"""
        rows = self.conn.execute(
            """SELECT * FROM trades WHERE status = 'OPEN' ORDER BY timestamp DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get trade history with P&L"""
        rows = self.conn.execute(
            """SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    
    def get_lessons(self, min_confidence: int = 7) -> List[Dict]:
        """Get high-confidence lessons"""
        rows = self.conn.execute(
            """SELECT * FROM memories 
               WHERE confidence >= ? AND type = 'lesson'
               ORDER BY timestamp DESC""",
            (min_confidence,)
        ).fetchall()
        return [dict(r) for r in rows]
    
    def recall(self, topic: str) -> str:
        """Generate a recall summary for a topic"""
        # Get topic info
        t = self.conn.execute(
            "SELECT * FROM topics WHERE name LIKE ?",
            (f"%{topic}%",)
        ).fetchone()
        
        if t:
            summary = f"**{t['name']}** ({t['category']})\n{t['summary']}\n\n"
        else:
            summary = f"No exact topic match for '{topic}'. Searching...\n\n"
        
        # Search related content
        results = self.search(topic, limit=5)
        if results:
            summary += "**Related memories:**\n"
            for r in results[:5]:
                summary += f"- [{r['source']}] {r['content'][:100]}...\n"
        
        return summary
    
    def stats(self) -> Dict:
        """Get memory system stats"""
        stats = {}
        for table in ['conversations', 'trades', 'memories', 'topics']:
            count = self.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            stats[table] = count
        
        # Trading stats
        trade_stats = self.conn.execute(
            """SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_trades,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(pnl_usd) as total_pnl
            FROM trades"""
        ).fetchone()
        stats['trading'] = dict(trade_stats)
        
        return stats
    
    def close(self):
        self.conn.close()

# Singleton instance
_memory = None

def get_memory() -> Memory:
    """Get or create memory instance"""
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory

if __name__ == "__main__":
    import sys
    m = get_memory()
    
    if len(sys.argv) < 2:
        print("Usage: python memory.py {stats|search|recall|active|history}")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "stats":
        print(json.dumps(m.stats(), indent=2))
    elif cmd == "search" and len(sys.argv) > 2:
        results = m.search(sys.argv[2])
        for r in results:
            print(f"[{r['source']}] {r['timestamp']}: {r['content'][:80]}...")
    elif cmd == "recall" and len(sys.argv) > 2:
        print(m.recall(sys.argv[2]))
    elif cmd == "active":
        trades = m.get_active_trades()
        print(json.dumps(trades, indent=2, default=str))
    elif cmd == "history":
        trades = m.get_trade_history()
        print(json.dumps(trades, indent=2, default=str))
    else:
        print(f"Unknown command: {cmd}")
