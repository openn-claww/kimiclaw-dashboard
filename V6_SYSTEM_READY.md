# V6 BOT SYSTEM - SETUP COMPLETE ✅
**Date:** March 8, 2026 04:15 AM  
**Virtual Balance:** $250  
**Mode:** Paper Trading

---

## 🟢 WHAT'S BEEN SET UP

### 1. V6 Bot Files
| File | Purpose | Status |
|------|---------|--------|
| `master_bot_v6_polyclaw_integration.py` | Main V6 bot | ✅ Ready |
| `cross_market_arb.py` | Arbitrage module | ✅ Ready |
| `news_feed_compact.py` | News feed module | ✅ Ready |

### 2. Health Monitoring System
| File | Purpose |
|------|---------|
| `v6_health_monitor.py` | Auto-restart + health tracking |
| `start_v6_with_monitor.sh` | Launcher script |
| `stop_v6.sh` | Stop script |
| `status_v6.sh` | Status checker |
| `v6_stats.py` | Detailed stats viewer |

### 3. Control Scripts Created
```bash
start_v6_with_monitor.sh    # Start bot + monitor
stop_v6.sh                  # Stop everything
status_v6.sh                # Check status
manual_start_v6.sh          # Manual start
v6_stats.py                 # Show statistics
```

---

## 🚀 TO START V6 BOT

### Option 1: With Health Monitor (Recommended)
```bash
cd /root/.openclaw/workspace
bash start_v6_with_monitor.sh
```

This starts:
- V6 Bot (paper trading, $250 virtual)
- Health Monitor (restarts bot if it crashes)

### Option 2: Manual Start
```bash
cd /root/.openclaw/workspace
bash manual_start_v6.sh
```

---

## 📊 TO CHECK STATUS

```bash
# Quick status
bash status_v6.sh

# Detailed statistics
python3 v6_stats.py

# Live log view
tail -f v6_bot_output.log

# Health monitor logs
tail -f v6_health_monitor.log
```

---

## 🛑 TO STOP

```bash
bash stop_v6.sh
```

---

## 📁 TRACKING FILES

| File | Purpose |
|------|---------|
| `v6_bot.pid` | Bot process ID |
| `v6_health_monitor.pid` | Monitor process ID |
| `v6_bot_output.log` | Bot logs |
| `v6_health_monitor.log` | Monitor logs |
| `v6_health_monitor.json` | Health history |
| `master_v6_health.json` | Bot health status |

---

## ⚡ WHAT THE SYSTEM DOES

### Health Monitor Features:
1. ✅ Checks bot every 60 seconds
2. ✅ Auto-restarts if bot crashes
3. ✅ Tracks: trades, wins, P&L, win rate
4. ✅ Logs all activity to JSON
5. ✅ Backs off if too many restarts

### V6 Bot Features:
1. ✅ Cross-market arbitrage detection
2. ✅ News feed (GNews + 3x NewsAPI)
3. ✅ Kelly Criterion position sizing ($1-5)
4. ✅ 5% minimum spread threshold
5. ✅ Signal combination (arb + news)

---

## 🎯 EXPECTED BEHAVIOR

After starting:
- Bot logs in and connects to APIs
- Starts checking for arb opportunities
- 2-3 trades per day expected
- Position sizes: $1-5 based on edge
- News filter skips ~15% of signals

**Watch for these log messages:**
```
✅ [CrossArb] ARB SIGNAL: BTC/5m YES @ 0.450 | spread=5.2% edge=5.2% size=$2.50
✅ [CrossArb+News] BTC news=BULLISH conf=0.75 size_mult=0.94
⚠️ [CrossArb+News] BTC skipped: news_skip:strong_conflict_skip
```

---

## 📈 MONITORING SCHEDULE

Check every 6 hours:
```bash
bash status_v6.sh
python3 v6_stats.py
```

After 48 hours, evaluate:
- Win rate >55%?
- Drawdown <20%?
- Avg spread >5%?
- Position sizes $1-5?

If all good → Go live with $10-20

---

## 🆘 TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| Bot won't start | Check `v6_bot_output.log` |
| Health monitor fails | Check `v6_health_monitor.log` |
| No trades | Check API keys in `.env` |
| Crashes repeatedly | Check logs for errors |

---

## 📝 SUMMARY

**System Status:** ✅ Ready to Start  
**Next Step:** Run `bash start_v6_with_monitor.sh`  
**Duration:** Monitor for 48 hours  
**Decision:** Go live if metrics look good

The V6 bot system is fully configured with health monitoring. Just run the start command and let it paper trade for 48 hours!
