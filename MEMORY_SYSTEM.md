# 🧠 Memory System Architecture

## Core Principle
Every conversation, trade, decision, and lesson gets written to disk. I query this before answering anything that might have prior context.

## Memory Files

### 1. Daily Logs (`memory/YYYY-MM-DD.md`)
- Raw transcript of what happened
- Conversations, trades, decisions
- Links to specific market IDs, trade hashes

### 2. Long-Term Memory (`MEMORY.md`)
- Distilled lessons from daily logs
- Patterns that worked/failed
- User preferences, boundaries, trust level
- Updated weekly via reflection

### 3. Trading Journal (`TRADING_JOURNAL.md`)
- Every trade with entry/exit, P&L, reasoning
- Active positions tracking
- Strategy performance over time

### 4. User Model (`USER.md`)
- What you care about
- How you think, decide, react
- Communication preferences

### 5. Topic Index (`memory/TOPICS.md`)
- Quick lookup: "what did we say about X?"
- Cross-references to daily logs

## Query Protocol

Before answering questions about:
- Past trades → Check TRADING_JOURNAL.md
- Prior discussions → Search memory/*.md + grep TOPICS.md
- User preferences → Read USER.md
- Lessons learned → Read MEMORY.md

## Reflection Schedule
- After every trade → Update TRADING_JOURNAL
- End of day → Update daily log
- Weekly → Distill MEMORY.md from daily logs
- On demand → When you ask "what about X?"

## Implementation

All files are plain text, grep-able, human-readable.
No database needed — filesystem is the database.
