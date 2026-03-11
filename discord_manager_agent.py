#!/usr/bin/env python3
"""
Discord Manager Agent - Centralized Discord Communication Manager

ROLE: Sole Discord communication manager for all agents.
All Discord tasks must go through this agent.

Usage:
    python3 discord_manager_agent.py init
    python3 discord_manager_agent.py send <channel_id> <message>
    python3 discord_manager_agent.py queue <channel_id> <message> [priority]
    python3 discord_manager_agent.py status [message_id]
    python3 discord_manager_agent.py retry <message_id>
    python3 discord_manager_agent.py channels
    python3 discord_manager_agent.py log <action> <details>
"""

import sqlite3
import sys
import json
from datetime import datetime
from pathlib import Path

# Configuration
DB_PATH = "/root/.openclaw/workspace/discord_manager.db"
SCHEMA_PATH = "/root/.openclaw/workspace/discord_manager_schema.sql"

# Default channels to track
DEFAULT_CHANNELS = {
    "1481044580957946087": {"name": "Main Updates", "type": "text", "description": "Original main updates channel"},
    "1471630920451621086": {"name": "User DM", "type": "dm", "description": "Personal DM channel"},
    "1481229012889243702": {"name": "Dashboard Updates", "type": "text", "description": "Dashboard updates channel"},
    "webchat": {"name": "Web Interface", "type": "web", "description": "Default web interface"},
}


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database with schema."""
    print("[DiscordManager] Initializing database...")
    
    # Ensure directory exists
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    # Read and execute schema
    with open(SCHEMA_PATH, 'r') as f:
        schema = f.read()
    
    conn = get_db()
    conn.executescript(schema)
    conn.commit()
    conn.close()
    
    print(f"[DiscordManager] Database initialized at {DB_PATH}")
    
    # Register default channels
    register_default_channels()
    
    log_activity("SYSTEM", "INIT", "Database initialized successfully")
    return True


def register_default_channels():
    """Register all known channels."""
    print("[DiscordManager] Registering default channels...")
    
    conn = get_db()
    cursor = conn.cursor()
    
    for channel_id, info in DEFAULT_CHANNELS.items():
        cursor.execute('''
            INSERT OR REPLACE INTO channels (id, name, channel_type, description, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (channel_id, info["name"], info["type"], info["description"], datetime.now()))
        print(f"  ✓ Registered: {channel_id} ({info['name']})")
    
    conn.commit()
    conn.close()
    
    log_activity("SYSTEM", "REGISTER_CHANNELS", f"Registered {len(DEFAULT_CHANNELS)} channels")
    return True


def register_channel(channel_id, name, channel_type="text", description=""):
    """Register a new channel."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO channels (id, name, channel_type, description, updated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (channel_id, name, channel_type, description, datetime.now()))
    
    conn.commit()
    conn.close()
    
    log_activity("SYSTEM", "REGISTER_CHANNEL", f"Registered channel {channel_id}: {name}")
    print(f"[DiscordManager] Registered channel: {channel_id} ({name})")
    return True


def send_message(channel_id, content, requester="unknown", priority=5):
    """Queue a message for sending."""
    # Validate channel
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM channels WHERE id = ? AND is_active = 1", (channel_id,))
    channel = cursor.fetchone()
    
    if not channel:
        print(f"[DiscordManager] ERROR: Channel {channel_id} not found or inactive")
        conn.close()
        return False
    
    # Insert message
    cursor.execute('''
        INSERT INTO messages (channel_id, content, status, priority, requester_agent, created_at)
        VALUES (?, ?, 'queued', ?, ?, ?)
    ''', (channel_id, content, priority, requester, datetime.now()))
    
    message_id = cursor.lastrowid
    
    # Add to queue
    cursor.execute('''
        INSERT INTO message_queue (message_id, status, created_at)
        VALUES (?, 'queued', ?)
    ''', (message_id, datetime.now()))
    
    conn.commit()
    conn.close()
    
    log_activity(requester, "QUEUE_MESSAGE", f"Message {message_id} queued for {channel_id}")
    print(f"[DiscordManager] Message queued (ID: {message_id}) -> {channel['name']}")
    print(f"  Content: {content[:80]}{'...' if len(content) > 80 else ''}")
    
    return message_id


def get_message_status(message_id=None):
    """Get status of message(s)."""
    conn = get_db()
    cursor = conn.cursor()
    
    if message_id:
        cursor.execute('''
            SELECT m.id, m.channel_id, c.name as channel_name, m.content, m.status, 
                   m.priority, m.retry_count, m.created_at, m.sent_at, m.requester_agent
            FROM messages m
            JOIN channels c ON m.channel_id = c.id
            WHERE m.id = ?
        ''', (message_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            print(f"\n[DiscordManager] Message {message_id} Status:")
            print(f"  Channel: {row['channel_name']} ({row['channel_id']})")
            print(f"  Status: {row['status']}")
            print(f"  Priority: {row['priority']}")
            print(f"  Retries: {row['retry_count']}")
            print(f"  Requester: {row['requester_agent']}")
            print(f"  Created: {row['created_at']}")
            if row['sent_at']:
                print(f"  Sent: {row['sent_at']}")
            print(f"  Content: {row['content'][:100]}{'...' if len(row['content']) > 100 else ''}")
            return dict(row)
        else:
            print(f"[DiscordManager] Message {message_id} not found")
            return None
    else:
        # Show recent messages summary
        cursor.execute('''
            SELECT m.id, c.name as channel_name, m.status, m.created_at
            FROM messages m
            JOIN channels c ON m.channel_id = c.id
            ORDER BY m.created_at DESC
            LIMIT 10
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        print("\n[DiscordManager] Recent Messages:")
        print(f"{'ID':<6} {'Channel':<20} {'Status':<12} {'Created'}")
        print("-" * 60)
        for row in rows:
            print(f"{row['id']:<6} {row['channel_name']:<20} {row['status']:<12} {row['created_at']}")
        return [dict(r) for r in rows]


def list_channels():
    """List all registered channels."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, channel_type, description, is_active, created_at
        FROM channels
        ORDER BY created_at
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    print("\n[DiscordManager] Registered Channels:")
    print(f"{'ID':<22} {'Name':<20} {'Type':<8} {'Active'}")
    print("-" * 60)
    for row in rows:
        active = "✓" if row['is_active'] else "✗"
        print(f"{row['id']:<22} {row['name']:<20} {row['channel_type']:<8} {active}")
    
    return [dict(r) for r in rows]


def retry_message(message_id):
    """Retry a failed message."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, retry_count FROM messages WHERE id = ?", (message_id,))
    row = cursor.fetchone()
    
    if not row:
        print(f"[DiscordManager] Message {message_id} not found")
        conn.close()
        return False
    
    if row['status'] not in ['failed', 'sent']:
        print(f"[DiscordManager] Message {message_id} status is '{row['status']}', not retryable")
        conn.close()
        return False
    
    # Reset for retry
    cursor.execute('''
        UPDATE messages 
        SET status = 'queued', retry_count = 0, error_message = NULL
        WHERE id = ?
    ''', (message_id,))
    
    cursor.execute('''
        INSERT INTO message_queue (message_id, status, created_at)
        VALUES (?, 'queued', ?)
    ''', (message_id, datetime.now()))
    
    conn.commit()
    conn.close()
    
    log_activity("SYSTEM", "RETRY_MESSAGE", f"Message {message_id} queued for retry")
    print(f"[DiscordManager] Message {message_id} queued for retry")
    return True


def log_activity(agent_name, action, details):
    """Log agent activity."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO agent_log (agent_name, action, details, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (agent_name, action, details, datetime.now()))
    
    conn.commit()
    conn.close()


def get_stats():
    """Get database statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) as count FROM channels")
    stats['channels'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages")
    stats['total_messages'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status = 'queued'")
    stats['queued'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status = 'sent'")
    stats['sent'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status = 'failed'")
    stats['failed'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM agent_log")
    stats['log_entries'] = cursor.fetchone()['count']
    
    conn.close()
    
    print("\n[DiscordManager] Statistics:")
    print(f"  Channels: {stats['channels']}")
    print(f"  Total Messages: {stats['total_messages']}")
    print(f"  Queued: {stats['queued']}")
    print(f"  Sent: {stats['sent']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Log Entries: {stats['log_entries']}")
    
    return stats


def process_queue(limit=10):
    """Process queued messages (simulation - no actual Discord API)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.channel_id, m.content, m.priority, m.retry_count
        FROM messages m
        JOIN message_queue q ON m.id = q.message_id
        WHERE q.status = 'queued'
        ORDER BY m.priority ASC, q.created_at ASC
        LIMIT ?
    ''', (limit,))
    
    messages = cursor.fetchall()
    
    processed = 0
    for msg in messages:
        # Mark as processing
        cursor.execute("UPDATE message_queue SET status = 'processing' WHERE message_id = ?", (msg['id'],))
        cursor.execute("UPDATE messages SET status = 'sending' WHERE id = ?", (msg['id'],))
        conn.commit()
        
        # Simulate sending (in real implementation, this would use Discord API)
        print(f"[DiscordManager] Processing message {msg['id']} -> {msg['channel_id']}")
        
        # Mark as sent (simulation)
        cursor.execute('''
            UPDATE messages 
            SET status = 'sent', sent_at = ?
            WHERE id = ?
        ''', (datetime.now(), msg['id']))
        
        cursor.execute('''
            UPDATE message_queue 
            SET status = 'completed', processed_at = ?
            WHERE message_id = ?
        ''', (datetime.now(), msg['id']))
        
        conn.commit()
        processed += 1
    
    conn.close()
    
    if processed > 0:
        print(f"[DiscordManager] Processed {processed} message(s)")
    
    return processed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "init":
        init_db()
        print("\n[DiscordManager] Initialization complete!")
        
    elif command == "send":
        if len(sys.argv) < 4:
            print("Usage: python3 discord_manager_agent.py send <channel_id> <message>")
            sys.exit(1)
        channel_id = sys.argv[2]
        content = sys.argv[3]
        priority = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        send_message(channel_id, content, priority=priority)
        
    elif command == "queue":
        if len(sys.argv) < 4:
            print("Usage: python3 discord_manager_agent.py queue <channel_id> <message> [priority]")
            sys.exit(1)
        channel_id = sys.argv[2]
        content = sys.argv[3]
        priority = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        send_message(channel_id, content, priority=priority)
        
    elif command == "status":
        message_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        get_message_status(message_id)
        
    elif command == "retry":
        if len(sys.argv) < 3:
            print("Usage: python3 discord_manager_agent.py retry <message_id>")
            sys.exit(1)
        retry_message(int(sys.argv[2]))
        
    elif command == "channels":
        list_channels()
        
    elif command == "stats":
        get_stats()
        
    elif command == "process":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        process_queue(limit)
        
    elif command == "log":
        if len(sys.argv) < 4:
            print("Usage: python3 discord_manager_agent.py log <action> <details>")
            sys.exit(1)
        log_activity("CLI", sys.argv[2], sys.argv[3])
        print("[DiscordManager] Activity logged")
        
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
