-- Memory Database Schema
-- SQLite3 - scalable, queryable, fast

-- Conversations: Every message exchange
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    user_message TEXT,
    assistant_message TEXT,
    tags TEXT, -- comma-separated for quick filtering
    importance INTEGER DEFAULT 5 -- 1-10, for pruning decisions
);

-- Trades: Every trade with full context
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    market_id TEXT NOT NULL,
    market_question TEXT,
    side TEXT CHECK(side IN ('YES', 'NO')),
    size_usd REAL,
    entry_price REAL,
    exit_price REAL,
    pnl_usd REAL,
    pnl_percent REAL,
    status TEXT CHECK(status IN ('OPEN', 'CLOSED', 'CANCELLED')),
    tx_hash TEXT,
    strategy TEXT, -- why we took this trade
    reflection TEXT, -- what we learned
    tags TEXT
);

-- Topics: Key subjects for quick lookup
CREATE TABLE topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT, -- trading, technical, user_preference, etc.
    summary TEXT,
    first_mentioned DATETIME,
    last_updated DATETIME,
    related_topics TEXT, -- comma-separated topic names
    source_conversation_id INTEGER,
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id)
);

-- Memories: Distilled lessons and patterns
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    type TEXT CHECK(type IN ('lesson', 'pattern', 'preference', 'rule', 'goal')),
    content TEXT NOT NULL,
    source_trade_id INTEGER,
    source_conversation_id INTEGER,
    confidence INTEGER DEFAULT 7, -- 1-10, how sure we are
    verified BOOLEAN DEFAULT FALSE, -- did this prove true?
    FOREIGN KEY (source_trade_id) REFERENCES trades(id),
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id)
);

-- Market Snapshots: Cache market data for analysis
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    market_id TEXT NOT NULL,
    question TEXT,
    yes_price REAL,
    no_price REAL,
    volume_24h REAL,
    tags TEXT
);

-- Indices for fast queries
CREATE INDEX idx_conversations_timestamp ON conversations(timestamp);
CREATE INDEX idx_conversations_tags ON conversations(tags);
CREATE INDEX idx_trades_market_id ON trades(market_id);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_topics_name ON topics(name);
CREATE INDEX idx_memories_type ON memories(type);
CREATE INDEX idx_market_snapshots_market_id ON market_snapshots(market_id);
