# PolyClaw Trading Dashboard v2.0

A comprehensive, professional trading dashboard for the Polymarket bot with real-time updates, WebSocket support, and full bot control capabilities.

## 🌐 Public Access URL

**Dashboard URL:** https://warrant-shown-email-postage.trycloudflare.com

## 📊 Features

### 1. Dashboard/Home
- Real-time balance tracking
- P&L overview with win/loss metrics
- Win rate visualization
- Open positions counter
- Recent trades table
- Live alerts feed
- Interactive P&L chart

### 2. Trading Control
- Start/Stop bot with one click
- Paper/Live mode toggle
- Kill switch status
- Circuit breaker monitoring
- Daily loss tracking
- Connection status indicators
- Activity log

### 3. Strategy Management
- View all strategies with performance metrics
- Enable/disable strategies
- P&L by strategy
- Win rate by strategy
- Trade count per strategy
- Performance comparison chart

### 4. Market Analysis
- Live BTC/ETH price charts
- Active opportunities scanner
- Market sentiment indicators
- Real-time market data

### 5. Logs
- Real-time bot log streaming
- Adjustable line count (100/500/1000)
- Log level color coding
- Auto-refresh capability

### 6. Settings
- API key configuration
- Risk parameter adjustment
- Position size limits
- Daily loss limits
- Circuit breaker thresholds
- Data reset options

## 🚀 Technology Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla HTML5, CSS3, JavaScript
- **Charts:** Chart.js
- **Real-time:** WebSocket
- **Icons:** Font Awesome
- **Fonts:** Inter (Google Fonts)

## 📁 Project Structure

```
trading-dashboard/
├── dashboard_server.py    # FastAPI backend
├── requirements.txt       # Python dependencies
├── start.sh              # Startup script
├── server.log            # Server logs
├── static/               # Static assets
└── templates/
    └── index.html        # Main dashboard UI
```

## 🔧 Installation

### Prerequisites
- Python 3.8+
- pip

### Install Dependencies
```bash
cd trading-dashboard
pip install -r requirements.txt
```

### Start the Dashboard
```bash
./start.sh
```

Or manually:
```bash
python3 dashboard_server.py
```

The dashboard will be available at:
- Local: http://localhost:8888
- Public: https://bolt-checklist-almost-identifying.trycloudflare.com

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard page |
| `/api/status` | GET | Bot status (running, mode, balance, etc.) |
| `/api/pnl` | GET | P&L metrics |
| `/api/trades` | GET | Recent trades |
| `/api/positions` | GET | Active positions |
| `/api/logs` | GET | Bot logs |
| `/api/alerts` | GET | Recent alerts |
| `/api/health` | GET | Detailed health metrics |
| `/api/bot/start` | POST | Start bot |
| `/api/bot/stop` | POST | Stop bot |
| `/ws` | WebSocket | Real-time updates |

## 🎨 UI/UX Features

- **Dark Theme:** Professional dark mode with accent colors
- **Responsive Design:** Mobile-friendly layout
- **Real-time Updates:** WebSocket connection for live data
- **Interactive Charts:** Chart.js for data visualization
- **Smooth Animations:** CSS transitions and hover effects
- **Sidebar Navigation:** Easy page switching
- **Status Indicators:** Visual bot status badges
- **Connection Status:** Live WebSocket connection indicator

## 📱 Mobile Responsive

The dashboard is fully responsive with:
- Collapsible sidebar
- Stacked layouts on small screens
- Touch-friendly buttons
- Optimized font sizes
- Horizontal scrolling for tables

## 🔒 Security Notes

- API keys are stored locally (not sent to server)
- WebSocket connections are encrypted (WSS)
- Paper trading mode is default
- Live mode requires explicit toggle

## 🔄 Bot Integration

The dashboard reads from the bot's state files:
- `master_v6_state.json` - Bot state
- `master_v6_health.json` - Health metrics
- `master_v6_trades.json` - Trade history
- `master_v6_run.log` - Bot logs
- `master_v6_alerts.json` - Alerts

## 📝 Control Capabilities

Users can control the bot from the dashboard:
1. **Start/Stop Bot:** Toggle bot operation
2. **Mode Switch:** Paper or Live trading
3. **Strategy Toggle:** Enable/disable strategies
4. **Risk Settings:** Adjust parameters
5. **Log Viewing:** Monitor bot activity

## 🐛 Troubleshooting

### Dashboard won't start
```bash
# Check if port 8888 is in use
lsof -i :8888

# Kill existing process
pkill -f dashboard_server

# Restart
./start.sh
```

### No data showing
- Verify bot state files exist
- Check file permissions
- Ensure bot has written initial state

### WebSocket disconnected
- Check network connection
- Refresh the page
- Check server logs: `tail -f server.log`

## 📊 Data Refresh

- Dashboard auto-refreshes every 10 seconds
- WebSocket provides real-time updates
- Manual refresh available via header button

## 🎯 Future Enhancements

- [ ] User authentication
- [ ] Trade execution from dashboard
- [ ] Backtest visualization
- [ ] Portfolio allocation charts
- [ ] News feed integration
- [ ] Telegram bot integration
- [ ] Email alerts
- [ ] Multi-wallet support

## 📄 License

Private - For PolyClaw trading bot use only.

## 👤 Author

PolyClaw Trading System

---

**Status:** ✅ Fully Operational
**Last Updated:** 2026-03-11
**Version:** 2.0.0
