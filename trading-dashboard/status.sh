#!/bin/bash
# Check dashboard status

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PolyClaw Trading Dashboard Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if dashboard server is running
DASHBOARD_PID=$(pgrep -f "dashboard_server.py")
if [ -n "$DASHBOARD_PID" ]; then
    echo "✅ Dashboard Server: RUNNING (PID: $DASHBOARD_PID)"
else
    echo "❌ Dashboard Server: STOPPED"
fi

# Check if tunnel is running
TUNNEL_PID=$(pgrep -f "cloudflared")
if [ -n "$TUNNEL_PID" ]; then
    echo "✅ Cloudflare Tunnel: RUNNING (PID: $TUNNEL_PID)"
else
    echo "❌ Cloudflare Tunnel: STOPPED"
fi

echo ""
echo "📊 Dashboard URL:"
echo "   Local:  http://localhost:8888"
echo "   Public: https://bolt-checklist-almost-identifying.trycloudflare.com"
echo ""

# Test API
if curl -s http://localhost:8888/api/status > /dev/null 2>&1; then
    echo "✅ API Status: OK"
    curl -s http://localhost:8888/api/status | python3 -m json.tool 2>/dev/null | head -10
else
    echo "❌ API Status: UNREACHABLE"
fi

echo ""
echo "📁 Log Files:"
echo "   Server: /root/.openclaw/workspace/trading-dashboard/server.log"
echo "   Bot:    /root/.openclaw/workspace/master_v6_run.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"