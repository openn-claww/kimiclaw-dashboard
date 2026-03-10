# MEMORY.md — OpenClaw Agent Long-Term Memory
> Curated, human-reviewed facts. Update manually or via `memory_integration.summarize_and_store()`.
> Last updated: 2025-02-28

---

## 🤖 Agent Identity
- **Name:** OpenClaw
- **Role:** Autonomous trading bot monitor and assistant
- **Primary workspace:** `/root/.openclaw/workspace/`
- **Memory DB:** `memory/memory.db`

---

## 📈 Trading Bot Configuration
| Parameter | Value |
|-----------|-------|
| Exchange | _e.g. Binance / Coinbase_ |
| Default pairs | _e.g. BTC/USDT, ETH/USDT_ |
| Strategy | _e.g. RSI mean-reversion_ |
| Risk per trade | _e.g. 1% account balance_ |
| Max open trades | _e.g. 5_ |

---

## 🔑 Key Facts (auto-updateable)
<!-- Add entries like: `python3 memory/memory.py log "fact_name" "fact content"` -->

- **Bot status:** Configured with News Feed (2026-03-08)
- **News API Keys:** 3x NewsAPI + 1x GNews configured
- **Last profitable session:** Unknown
- **Last loss:** Unknown
- **Known API quirks:** NewsAPI has 12hr delay on free tier; GNews is real-time

## 📊 Financial History (2026-02-19 to 2026-03-08)

### Trading Performance
| Metric | Value |
|--------|-------|
| **Starting Capital (Est.)** | $27.65 |
| **Current Balance** | $11.03 liquid + $1.99 open = **$13.02** |
| **NET LOSS** | **-$15.60 (-56.4%)** |
| **Total Trades** | 20 |
| **Win Rate** | 68.4% (13 wins, 6 losses, 1 open) |
| **Fees Paid** | $0.97 |

### Trade Breakdown
| Category | Trades | Net P&L |
|----------|--------|---------|
| BTC/Crypto | 13 | **-$12.28** |
| Sports | 3 | **-$3.56** |
| Geopolitical | 3 | **+$0.29** |
| Other | 1 | **-$0.05** |

### Biggest Mistakes
1. Warriors game: -$8.16 (position too large)
2. BTC range NO: -$5.10 (wrong direction)
3. BTC directional: -$13.16 total (multiple wrong bets)

### What Worked
1. Small BTC scalps: +$4.42 (high probability, small size)
2. NO on extreme targets: +$1.96 (tails rarely hit)
3. Iran geopolitical: +$0.29 (news analysis correct)

## 📰 News Feed Configuration (2026-03-08)
| Source | Keys | Daily Limit | Type |
|--------|------|-------------|------|
| GNews | 1 | 100 | Real-time |
| NewsAPI | 3 | 300 total | 12hr delay |
| Currents | 1 | ~20 | Emergency backup |

### Integration Status
- `news_feed_compact.py` - ✅ Active
- V6 Integration - ✅ 4 changes applied
- API Keys - ✅ Configured in .env
- Test Results - ✅ Working (BTC: BULLISH, ETH: NEUTRAL, SOL: BEARISH)

## 🔧 Arb Strategy Fixes (2026-03-08)
| Parameter | Old | New | Reason |
|-----------|-----|-----|--------|
| Min Spread | 3.5% | 5% | Cover fees + profit margin |
| Position Sizing | Fixed $5 | Kelly Criterion | Scale with edge confidence |
| Min Position | - | $1 | Reduce risk on weak signals |
| News Filter | ❌ | ✅ | Skip conflicting trades |

### Backtest Results (30-day sim)
| Metric | Baseline | News-Enhanced | Improvement |
|--------|----------|---------------|-------------|
| Win Rate | 54% | 58% | +4% |
| Drawdown | 61.5% | 27.9% | **-54%** |
| Losses | High | -50% | **Cut in half** |

---

## ⚠️ Alerts & Thresholds
- RSI overbought threshold: **70**
- RSI oversold threshold: **30**
- Max drawdown alert: **5%**
- Daily loss limit: **2%**

---

## 📚 Session Summaries
<!-- Auto-populated by summarize_and_store() — newest first -->

### [DATE] - Session title
_Paste or auto-generate summary here._

---

## 🛠️ Operational Notes
- Memory DB is queried before every response via `recall_before_answer(topic)`
- Every conversation turn is logged via `log_turn(role, content, topic)`
- Heartbeat checks run every _N minutes_ and log results to DB
- To wipe session logs only: `sqlite3 memory/memory.db "DELETE FROM conversations;"`

---

## 🔗 Related Files
- `memory/memory.py` — core DB interface (CRUD + CLI)
- `memory_integration.py` — agent loop wrappers
- `HEARTBEAT.md` — periodic check tasks
