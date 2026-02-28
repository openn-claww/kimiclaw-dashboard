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

- **Bot status:** Unknown (update after first heartbeat)
- **Last profitable session:** Unknown
- **Last loss:** Unknown
- **Known API quirks:** None yet

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
