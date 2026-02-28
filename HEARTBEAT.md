# HEARTBEAT.md — OpenClaw Periodic Check Tasks
> These tasks run on a schedule. Each check logs its result to memory.db.

---

## ⏱️ Schedule Overview
| Interval | Task |
|----------|------|
| Every 1 min  | Price feed alive check |
| Every 5 min  | Open positions review |
| Every 15 min | RSI + indicator snapshot |
| Every 1 hr   | P&L summary → memory |
| Every 6 hr   | Strategy drift check |
| Daily 00:00  | Session rollup + MEMORY.md update |

---

## 🫀 Heartbeat Tasks

### HB-01 · Price Feed Alive (1 min)
```bash
python3 memory/memory.py recall "price_feed_error"
# If errors found → alert; else log "OK"
python3 memory/memory.py log "heartbeat_price_feed" "Feed alive @ $(date -u +%Y-%m-%dT%H:%M:%SZ)" --tags "heartbeat,price_feed" --source "heartbeat"
```

### HB-02 · Open Positions Review (5 min)
```bash
# Replace with your exchange CLI / API call
POSITIONS=$(your_bot positions --json)
python3 memory/memory.py log "open_positions" "$POSITIONS" --tags "heartbeat,positions" --source "heartbeat"
```

### HB-03 · RSI Snapshot (15 min)
```bash
RSI=$(your_bot indicator --name RSI --pair BTC/USDT)
python3 memory/memory.py log "BTC_RSI" "RSI=$RSI at $(date -u +%H:%M)" --tags "BTC,RSI,indicator" --source "heartbeat"

# Threshold alert
if (( $(echo "$RSI > 70" | bc -l) )); then
  python3 memory/memory.py log "BTC_RSI_alert" "OVERBOUGHT RSI=$RSI at $(date -u)" --tags "alert,BTC,RSI"
fi
```

### HB-04 · Hourly P&L Summary (1 hr)
```bash
PNL=$(your_bot pnl --period 1h)
python3 memory/memory.py log "pnl_1h" "$PNL" --tags "heartbeat,pnl" --source "heartbeat"
```

### HB-05 · Strategy Drift Check (6 hr)
```bash
# Compare current win-rate vs baseline
WIN_RATE=$(your_bot stats --metric win_rate)
python3 memory/memory.py log "strategy_drift" "Win rate: $WIN_RATE (checked $(date -u +%Y-%m-%d))" --tags "strategy,drift,audit" --source "heartbeat"
```

### HB-06 · Daily Session Rollup (cron: 0 0 * * *)
```bash
# Dump last 24h conversation summary into memory
python3 -c "
from memory_integration import summarize_and_store
from memory.memory import recent_conversations
turns = recent_conversations(100)
content = '\n'.join(f\"{t['role']}: {t['content'][:200]}\" for t in turns)
summarize_and_store('daily_rollup_$(date +%Y-%m-%d)', summary=content[:1000])
"
```

---

## 🔔 Alert Routing
Edit to match your notification stack:
```bash
send_alert() {
  local msg="$1"
  # Slack:   curl -X POST -d "{\"text\":\"$msg\"}" $SLACK_WEBHOOK
  # Telegram: curl "https://api.telegram.org/bot$TG_TOKEN/sendMessage?chat_id=$TG_CHAT&text=$msg"
  # Email:   echo "$msg" | mail -s "OpenClaw Alert" you@example.com
  echo "[ALERT] $msg"
}
```

---

## 🧪 Test a Heartbeat Manually
```bash
cd /root/.openclaw/workspace
python3 memory/memory.py log "heartbeat_test" "Manual heartbeat OK" --tags "test,heartbeat"
python3 memory/memory.py recall "heartbeat_test"
python3 memory/memory.py stats
```

---

## 📌 Crontab Example
```cron
* * * * *   cd /root/.openclaw/workspace && bash heartbeats/hb01_price_feed.sh
*/5 * * * * cd /root/.openclaw/workspace && bash heartbeats/hb02_positions.sh
0 * * * *   cd /root/.openclaw/workspace && bash heartbeats/hb04_pnl.sh
0 0 * * *   cd /root/.openclaw/workspace && bash heartbeats/hb06_daily_rollup.sh
```
