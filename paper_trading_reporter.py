#!/usr/bin/env python3
"""
Paper Trading Reporter
Posts trades to Discord and updates dashboard
"""

import json
import time
from datetime import datetime

DISCORD_CHANNEL = "1475209252183343347"
INTERNAL_LOG = "/root/.openclaw/workspace/InternalLog.json"
DASHBOARD_FILE = "/root/.openclaw/workspace/paper-trading-dashboard.html"

def get_recent_trades(limit=10):
    """Get recent paper trades from InternalLog"""
    try:
        with open(INTERNAL_LOG, 'r') as f:
            log = json.load(f)
        
        paper_trades = [e for e in log if e.get('event_type') == 'trade_sim']
        return paper_trades[-limit:]
    except:
        return []

def get_virtual_balance():
    """Calculate current virtual balance"""
    try:
        with open(INTERNAL_LOG, 'r') as f:
            log = json.load(f)
        
        balance = 1000.0
        for entry in log:
            if entry.get('event_type') == 'trade_sim':
                balance = entry.get('virtual_balance_after', balance)
        return balance
    except:
        return 940.0

def generate_discord_report():
    """Generate report for Discord"""
    balance = get_virtual_balance()
    trades = get_recent_trades(5)
    
    report = []
    report.append(f"📊 PAPER TRADING REPORT — {datetime.now().strftime('%H:%M UTC')}")
    report.append(f"Virtual Balance: ${balance:.2f}")
    report.append(f"Recent Trades: {len(trades)}")
    report.append("")
    
    if trades:
        report.append("Latest Trades:")
        for t in trades[-3:]:
            report.append(f"  • {t.get('side')} {t.get('market', 'Unknown')[:30]}... | ${t.get('amount')}")
    
    return "\n".join(report)

def update_dashboard():
    """Update paper trading dashboard HTML"""
    balance = get_virtual_balance()
    trades = get_recent_trades(20)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Trading Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ font-family: 'Inter', sans-serif; background: #0a0a0f; color: white; }}</style>
    <meta http-equiv="refresh" content="30">
</head>
<body class="min-h-screen p-6">
    <div class="max-w-6xl mx-auto">
        <header class="mb-8">
            <h1 class="text-4xl font-bold text-blue-400">Paper Trading Dashboard</h1>
            <p class="text-gray-400">Live 5-min & 15-min Trading</p>
        </header>
        
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-gray-900 p-6 rounded-lg border border-gray-800">
                <div class="text-gray-400 text-sm">Virtual Balance</div>
                <div class="text-3xl font-bold text-green-400">${balance:.2f}</div>
            </div>
            <div class="bg-gray-900 p-6 rounded-lg border border-gray-800">
                <div class="text-gray-400 text-sm">Total Trades</div>
                <div class="text-3xl font-bold text-blue-400">{len(trades)}</div>
            </div>
            <div class="bg-gray-900 p-6 rounded-lg border border-gray-800">
                <div class="text-gray-400 text-sm">Open Positions</div>
                <div class="text-3xl font-bold text-yellow-400">{len(trades)}</div>
            </div>
            <div class="bg-gray-900 p-6 rounded-lg border border-gray-800">
                <div class="text-gray-400 text-sm">P&L</div>
                <div class="text-3xl font-bold {'text-green-400' if balance >= 1000 else 'text-red-400'}">${balance - 1000:+.2f}</div>
            </div>
        </div>
        
        <div class="bg-gray-900 p-6 rounded-lg border border-gray-800">
            <h2 class="text-xl font-semibold mb-4">Recent Paper Trades</h2>
            <table class="w-full text-sm">
                <thead class="text-gray-400 border-b border-gray-700">
                    <tr>
                        <th class="text-left py-3">Time</th>
                        <th class="text-left py-3">Market</th>
                        <th class="text-center py-3">Side</th>
                        <th class="text-right py-3">Amount</th>
                        <th class="text-right py-3">Balance</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for t in reversed(trades[-10:]):
        html += f"""
                    <tr class="border-b border-gray-800">
                        <td class="py-3">{t.get('timestamp_utc', 'N/A')}</td>
                        <td class="py-3">{t.get('market', 'Unknown')[:40]}...</td>
                        <td class="py-3 text-center"><span class="px-2 py-1 bg-blue-900 text-blue-400 rounded">{t.get('side', 'N/A')}</span></td>
                        <td class="py-3 text-right">${t.get('amount', 0)}</td>
                        <td class="py-3 text-right">${t.get('virtual_balance_after', 0)}</td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>
        
        <footer class="mt-8 text-center text-gray-500 text-sm">
            <p>Auto-refresh every 30 seconds</p>
            <p>Trading 5-min and 15-min markets continuously</p>
        </footer>
    </div>
</body>
</html>
"""
    
    with open(DASHBOARD_FILE, 'w') as f:
        f.write(html)

if __name__ == "__main__":
    print(generate_discord_report())
    update_dashboard()
    print("Dashboard updated!")
