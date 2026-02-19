#!/bin/bash
# Memory Database CLI
# Usage: ./memory.sh [query|log|trade|topic|reflect] [args]

DB="/root/.openclaw/workspace/memory/memory.db"

init() {
    if [ ! -f "$DB" ]; then
        sqlite3 "$DB" < /root/.openclaw/workspace/memory/schema.sql
        echo "✓ Database initialized at $DB"
    fi
}

log_conversation() {
    local user_msg="$1"
    local assistant_msg="$2"
    local tags="$3"
    sqlite3 "$DB" "INSERT INTO conversations (user_message, assistant_message, tags) VALUES ('$(echo "$user_msg" | sed "s/'/''/g")', '$(echo "$assistant_msg" | sed "s/'/''/g")', '$tags');"
}

log_trade() {
    local market_id="$1"
    local side="$2"
    local size="$3"
    local entry="$4"
    local strategy="$5"
    sqlite3 "$DB" "INSERT INTO trades (market_id, side, size_usd, entry_price, status, strategy) VALUES ('$market_id', '$side', $size, $entry, 'OPEN', '$(echo "$strategy" | sed "s/'/''/g")');"
}

query_topic() {
    local topic="$1"
    sqlite3 "$DB" "SELECT summary, last_updated FROM topics WHERE name LIKE '%$topic%' ORDER BY last_updated DESC LIMIT 5;"
}

search_memories() {
    local query="$1"
    sqlite3 "$DB" "SELECT type, content, timestamp FROM memories WHERE content LIKE '%$query%' ORDER BY confidence DESC, timestamp DESC LIMIT 10;"
}

get_active_trades() {
    sqlite3 "$DB" "SELECT market_id, side, size_usd, entry_price, timestamp FROM trades WHERE status='OPEN';"
}

reflect() {
    echo "=== Recent Trades ==="
    sqlite3 "$DB" "SELECT market_id, side, pnl_usd, reflection FROM trades WHERE reflection IS NOT NULL ORDER BY timestamp DESC LIMIT 5;"
    echo ""
    echo "=== Key Memories ==="
    sqlite3 "$DB" "SELECT type, content FROM memories WHERE confidence >= 8 ORDER BY timestamp DESC LIMIT 10;"
}

case "$1" in
    init) init ;;
    log) log_conversation "$2" "$3" "$4" ;;
    trade) log_trade "$2" "$3" "$4" "$5" "$6" ;;
    query) query_topic "$2" ;;
    search) search_memories "$2" ;;
    active) get_active_trades ;;
    reflect) reflect ;;
    *) echo "Usage: $0 {init|log|trade|query|search|active|reflect}"; exit 1 ;;
esac
