#!/bin/bash
# v6-service-control.sh - Control V6 Bot and Health Monitor as Systemd Services

cd /root/.openclaw/workspace

show_help() {
    echo "V6 Bot Service Control"
    echo ""
    echo "Usage: bash v6-service-control.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       - Start V6 Bot and Health Monitor"
    echo "  stop        - Stop V6 Bot and Health Monitor"
    echo "  restart     - Restart both services"
    echo "  status      - Check service status"
    echo "  logs        - View bot logs"
    echo "  monitor     - View health monitor logs"
    echo "  stats       - Show statistics"
    echo "  enable      - Enable auto-start on boot"
    echo "  disable     - Disable auto-start on boot"
    echo ""
}

case "${1:-}" in
    start)
        echo "🚀 Starting V6 Bot and Health Monitor..."
        sudo systemctl daemon-reload
        sudo systemctl start v6-bot.service
        sudo systemctl start v6-health-monitor.service
        echo ""
        echo "Services started. Check status with: bash v6-service-control.sh status"
        ;;
        
    stop)
        echo "🛑 Stopping V6 Bot and Health Monitor..."
        sudo systemctl stop v6-health-monitor.service
        sudo systemctl stop v6-bot.service
        echo "✅ Services stopped"
        ;;
        
    restart)
        echo "🔄 Restarting V6 Bot and Health Monitor..."
        sudo systemctl daemon-reload
        sudo systemctl restart v6-bot.service
        sudo systemctl restart v6-health-monitor.service
        echo "✅ Services restarted"
        ;;
        
    status)
        echo "============================================================"
        echo "                 V6 SERVICE STATUS"
        echo "============================================================"
        echo ""
        echo "V6 Bot Service:"
        sudo systemctl status v6-bot.service --no-pager -l | head -15
        echo ""
        echo "Health Monitor Service:"
        sudo systemctl status v6-health-monitor.service --no-pager -l | head -15
        echo ""
        echo "============================================================"
        ;;
        
    logs)
        echo "📄 V6 Bot Logs (last 50 lines):"
        echo "============================================================"
        sudo journalctl -u v6-bot.service -n 50 --no-pager
        echo ""
        echo "📄 Output Log:"
        tail -30 /root/.openclaw/workspace/v6_bot_output.log 2>/dev/null || echo "(No output log yet)"
        ;;
        
    monitor)
        echo "📄 Health Monitor Logs (last 50 lines):"
        echo "============================================================"
        sudo journalctl -u v6-health-monitor.service -n 50 --no-pager
        ;;
        
    stats)
        python3 /root/.openclaw/workspace/v6_stats.py
        ;;
        
    enable)
        echo "🔧 Enabling auto-start on boot..."
        sudo systemctl daemon-reload
        sudo systemctl enable v6-bot.service
        sudo systemctl enable v6-health-monitor.service
        echo "✅ Auto-start enabled"
        ;;
        
    disable)
        echo "🔧 Disabling auto-start on boot..."
        sudo systemctl disable v6-bot.service
        sudo systemctl disable v6-health-monitor.service
        echo "✅ Auto-start disabled"
        ;;
        
    *)
        show_help
        ;;
esac
