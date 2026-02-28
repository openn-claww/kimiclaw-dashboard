#!/usr/bin/env python3
"""
OpenClaw Memory Interface
Usage:
  python3 memory/memory.py recall "topic"
  python3 memory/memory.py log "topic" "content" [--tags tag1,tag2]
  python3 memory/memory.py search "keyword"
  python3 memory/memory.py recent [N]
  python3 memory/memory.py stats
"""

import sqlite3
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "memory.db"


# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    topic     TEXT NOT NULL,
    content   TEXT NOT NULL,
    tags      TEXT DEFAULT '',          -- comma-separated
    source    TEXT DEFAULT 'manual',    -- 'conversation'|'manual'|'heartbeat'
    created   TEXT NOT NULL,
    updated   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    role      TEXT NOT NULL,            -- 'user'|'assistant'|'system'
    content   TEXT NOT NULL,
    topic     TEXT DEFAULT '',
    created   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_topic   ON memories(topic);
CREATE INDEX IF NOT EXISTS idx_memories_tags    ON memories(tags);
CREATE INDEX IF NOT EXISTS idx_conversations_ts ON conversations(created);
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ─── Core API ─────────────────────────────────────────────────────────────────

def recall(topic: str, limit: int = 5) -> list[dict]:
    """Retrieve memories by topic (fuzzy match)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM memories
               WHERE topic LIKE ? OR tags LIKE ? OR content LIKE ?
               ORDER BY updated DESC LIMIT ?""",
            (f"%{topic}%", f"%{topic}%", f"%{topic}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def log_memory(topic: str, content: str, tags: str = "", source: str = "manual") -> int:
    """Insert or update a memory entry."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM memories WHERE topic = ?", (topic,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memories SET content=?, tags=?, source=?, updated=? WHERE id=?",
                (content, tags, source, now, existing["id"]),
            )
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO memories (topic, content, tags, source, created, updated) VALUES (?,?,?,?,?,?)",
                (topic, content, tags, source, now, now),
            )
            return cur.lastrowid


def log_conversation(role: str, content: str, topic: str = "") -> int:
    """Append a conversation turn to the log."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (role, content, topic, created) VALUES (?,?,?,?)",
            (role, content, topic, now),
        )
        return cur.lastrowid


def search(keyword: str, limit: int = 10) -> list[dict]:
    """Full-text search across memories."""
    return recall(keyword, limit)


def recent_conversations(n: int = 20) -> list[dict]:
    """Return the N most recent conversation turns."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY created DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def stats() -> dict:
    with get_db() as conn:
        mem_count  = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        oldest     = conn.execute("SELECT MIN(created) FROM memories").fetchone()[0]
        newest     = conn.execute("SELECT MAX(updated) FROM memories").fetchone()[0]
    return {
        "memories": mem_count,
        "conversation_turns": conv_count,
        "oldest_memory": oldest,
        "newest_update": newest,
        "db_path": str(DB_PATH),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OpenClaw Memory CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_recall = sub.add_parser("recall", help="Recall memories by topic")
    p_recall.add_argument("topic")
    p_recall.add_argument("--limit", type=int, default=5)

    p_log = sub.add_parser("log", help="Log a memory")
    p_log.add_argument("topic")
    p_log.add_argument("content")
    p_log.add_argument("--tags", default="")
    p_log.add_argument("--source", default="manual")

    p_conv = sub.add_parser("log_conv", help="Log a conversation turn")
    p_conv.add_argument("role", choices=["user", "assistant", "system"])
    p_conv.add_argument("content")
    p_conv.add_argument("--topic", default="")

    p_search = sub.add_parser("search", help="Search memories")
    p_search.add_argument("keyword")
    p_search.add_argument("--limit", type=int, default=10)

    p_recent = sub.add_parser("recent", help="Recent conversation turns")
    p_recent.add_argument("n", type=int, nargs="?", default=20)

    sub.add_parser("stats", help="Memory statistics")

    args = parser.parse_args()

    if args.cmd == "recall":
        results = recall(args.topic, args.limit)
        if results:
            for r in results:
                print(f"\n[{r['updated']}] ({r['topic']})")
                print(f"  {r['content']}")
                if r["tags"]:
                    print(f"  tags: {r['tags']}")
        else:
            print(f"No memories found for topic: '{args.topic}'")

    elif args.cmd == "log":
        row_id = log_memory(args.topic, args.content, args.tags, args.source)
        print(f"Memory saved (id={row_id}): {args.topic}")

    elif args.cmd == "log_conv":
        row_id = log_conversation(args.role, args.content, args.topic)
        print(f"Conversation turn logged (id={row_id})")

    elif args.cmd == "search":
        results = search(args.keyword, args.limit)
        print(json.dumps(results, indent=2))

    elif args.cmd == "recent":
        turns = recent_conversations(args.n)
        for t in turns:
            print(f"[{t['created']}] {t['role'].upper()}: {t['content'][:120]}")

    elif args.cmd == "stats":
        print(json.dumps(stats(), indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
