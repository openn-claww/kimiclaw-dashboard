# Memory System v2 — SQLite Database

## Architecture

**Database:** `/root/.openclaw/workspace/memory/memory.db`
**Schema:** `/root/.openclaw/workspace/memory/schema.sql`
**CLI:** `/root/.openclaw/workspace/memory/memory.sh`

## Tables

| Table | Purpose |
|-------|---------|
| `conversations` | Every message exchange with tags |
| `trades` | Complete trade history with P&L |
| `topics` | Indexed subjects for quick lookup |
| `memories` | Distilled lessons, patterns, rules |
| `market_snapshots` | Cached market data |

## Usage

```bash
# Log a conversation
./memory.sh log "user message" "assistant reply" "trading,polymarket"

# Log a trade
./memory.sh trade "703258" "NO" 5.0 0.97 "High confidence, low probability event"

# Query a topic
./memory.sh query "jesus"

# Search memories
./memory.sh search "strategy"

# Get active trades
./memory.sh active

# Reflection report
./memory.sh reflect
```

## Query Examples

```sql
-- All trades with positive P&L
SELECT * FROM trades WHERE pnl_usd > 0;

-- Topics mentioned this week
SELECT * FROM topics WHERE last_updated > datetime('now', '-7 days');

-- High-confidence memories
SELECT * FROM memories WHERE confidence >= 8 ORDER BY timestamp DESC;
```

## Scalability

- SQLite handles millions of rows
- Indexed columns for fast queries
- Can migrate to PostgreSQL later if needed
- Backup: Just copy the .db file
