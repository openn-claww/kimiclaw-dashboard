# V6 BOT SYSTEMD SERVICES
**Date:** March 8, 2026  
**Services:** v6-bot.service + v6-health-monitor.service

---

## 🚀 QUICK START

### Start Both Services
```bash
bash v6-service-control.sh start
```

Or manually:
```bash
sudo systemctl start v6-bot.service
sudo systemctl start v6-health-monitor.service
```

---

## 📋 SERVICE DETAILS

### v6-bot.service
- **Type:** Systemd service
- **Purpose:** Main V6 trading bot
- **Mode:** Paper trading ($250 virtual)
- **Restart:** Always (10s delay, 3 tries/minute)
- **Logs:** journald + file

### v6-health-monitor.service
- **Type:** Systemd service  
- **Purpose:** Monitor and auto-restart V6 bot
- **Depends:** v6-bot.service
- **Restart:** Always (30s delay, 5 tries/2min)
- **Logs:** journald + file

---

## 🎮 CONTROL COMMANDS

### Using Helper Script
```bash
bash v6-service-control.sh [command]

Commands:
  start       - Start both services
  stop        - Stop both services
  restart     - Restart both services
  status      - Check status
  logs        - View bot logs
  monitor     - View health monitor logs
  stats       - Show statistics
  enable      - Auto-start on boot
  disable     - Disable auto-start
```

### Using systemctl Directly
```bash
# Start/Stop
sudo systemctl start v6-bot.service
sudo systemctl stop v6-bot.service
sudo systemctl restart v6-bot.service

# Check status
sudo systemctl status v6-bot.service
sudo systemctl status v6-health-monitor.service

# View logs
sudo journalctl -u v6-bot.service -f          # Follow
sudo journalctl -u v6-bot.service -n 100      # Last 100 lines
sudo journalctl -u v6-bot.service --since "1 hour ago"

# Enable auto-start on boot
sudo systemctl enable v6-bot.service
sudo systemctl enable v6-health-monitor.service
```

---

## 📊 MONITORING

### Real-time Status
```bash
# Quick status
bash v6-service-control.sh status

# Detailed stats
bash v6-service-control.sh stats

# Live logs
sudo journalctl -u v6-bot.service -f
```

### Log Files
- Bot output: `/root/.openclaw/workspace/v6_bot_output.log`
- Health monitor: `/root/.openclaw/workspace/v6_health_monitor.log`
- Health JSON: `/root/.openclaw/workspace/v6_health_monitor.json`

---

## 🔧 SERVICE CONFIGURATION

### Environment Variables (in service file)
```
POLY_PAPER_TRADING=true
POLY_VIRTUAL_BALANCE=250
NEWSAPI_KEY_1=06dc3ef927d3416aba1b6ece3fb57716
NEWSAPI_KEY_2=9bd8097226574cd3932fa65081029738
NEWSAPI_KEY_3=a7dce4fae15c486c811af014a1094728
GNEWS_KEY=01f1ea1cc4375f5a24c0afb3d953e4d4
CURRENTS_KEY=06dc3ef927d3416aba1b6ece3fb57716
```

### Service Files Location
- `/etc/systemd/system/v6-bot.service`
- `/etc/systemd/system/v6-health-monitor.service`

---

## 🔄 AUTO-RESTART BEHAVIOR

### V6 Bot
- **Restarts:** On crash or exit
- **Delay:** 10 seconds
- **Limit:** 3 restarts per minute
- **Action:** If limit exceeded, stays stopped until manual restart

### Health Monitor
- **Restarts:** On crash or exit
- **Delay:** 30 seconds  
- **Limit:** 5 restarts per 2 minutes
- **Action:** Monitors bot and restarts it if needed

---

## 📈 EXPECTED OUTPUT

### When Running
```
$ bash v6-service-control.sh status

V6 Bot Service:
   Active: active (running) since Sun 2026-03-08 04:20:00 CST
   Main PID: 12345 (python3)
   CGroup: /system.slice/v6-bot.service
           └─12345 /usr/bin/python3 ...master_bot_v6_polyclaw...

Health Monitor Service:
   Active: active (running) since Sun 2026-03-08 04:20:05 CST
   Main PID: 12346 (python3)
```

### Logs
```
[CrossArb] ✅ ARB SIGNAL: BTC/5m YES @ 0.450 | spread=5.2% edge=5.2% size=$2.50
[CrossArb+News] BTC news=BULLISH conf=0.75 size_mult=0.94
```

---

## 🛠️ TROUBLESHOOTING

### Bot Won't Start
```bash
# Check for errors
sudo journalctl -u v6-bot.service -n 50

# Check syntax
python3 -m py_compile master_bot_v6_polyclaw_integration.py

# Manual test
sudo systemctl stop v6-bot.service
export POLY_PAPER_TRADING=true
python3 master_bot_v6_polyclaw_integration.py
```

### Service Failed
```bash
# Reset failed state
sudo systemctl reset-failed v6-bot.service
sudo systemctl start v6-bot.service
```

### Too Many Restarts
```bash
# Check restart count
sudo systemctl status v6-bot.service | grep -i restart

# If failing repeatedly, check logs
sudo journalctl -u v6-bot.service --since "10 minutes ago"
```

---

## 📝 SERVICE FILE LOCATIONS

| File | Path |
|------|------|
| V6 Bot Service | `/etc/systemd/system/v6-bot.service` |
| Health Monitor Service | `/etc/systemd/system/v6-health-monitor.service` |
| Control Script | `/root/.openclaw/workspace/v6-service-control.sh` |

---

## ⏱️ 48-HOUR TEST CHECKLIST

- [ ] Services start successfully
- [ ] Bot logs show API connections
- [ ] Health monitor logs show checks
- [ ] Trades are being logged
- [ ] Win rate >55%
- [ ] No excessive restarts
- [ ] Position sizes $1-5
- [ ] Spreads >5%

---

## 🎯 GO LIVE DECISION

After 48 hours:
- ✅ Win rate >55% + Drawdown <20% → Go live
- ❌ Issues found → Fix first

To switch to live trading:
```bash
# Edit service file
sudo nano /etc/systemd/system/v6-bot.service

# Change: Environment="POLY_PAPER_TRADING=true"
# To:     # Environment="POLY_PAPER_TRADING=true"

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart v6-bot.service
```

---

**Status:** ✅ Services configured and ready  
**Next:** Run `bash v6-service-control.sh start`
