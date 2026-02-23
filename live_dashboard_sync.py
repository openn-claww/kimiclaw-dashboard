#!/usr/bin/env python3
"""
Live Dashboard Sync System
Real-time sync between blockchain, database, and dashboard
"""

import sqlite3
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Paths
DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")
DASHBOARD_DIR = Path("/root/.openclaw/workspace/live-dashboard")
LOG_FILE = Path("/root/.openclaw/workspace/sync.log")
SKILL_DIR = Path("/root/.openclaw/skills/polyclaw")

class LiveDashboardSync:
    def __init__(self):
        self.data = {
            "wallet": {},
            "positions": [],
            "trades": [],
            "stats": {},
            "resolved": [],
            "pending": [],
            "pnl": {"realized": 0, "unrealized": 0, "total": 0},
            "last_sync": None
        }
    
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        with open(LOG_FILE, 'a') as f:
            f.write(log_msg + '\n')
    
    def get_wallet_status(self) -> Dict:
        """Get live wallet status from blockchain"""
        try:
            cmd = f"cd {SKILL_DIR} && bash -c 'source .env && uv run python scripts/polyclaw.py wallet status'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            self.log(f"Wallet error: {e}")
        return {}
    
    def get_positions(self) -> List[Dict]:
        """Get live positions from blockchain"""
        try:
            cmd = f"cd {SKILL_DIR} && bash -c 'source .env && uv run python scripts/polyclaw.py positions list --json'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            self.log(f"Positions error: {e}")
        return []
    
    def get_db_trades(self) -> List[Dict]:
        """Get trades from database"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        trades = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(t) for t in trades]
    
    def sync_data(self):
        """Sync all data sources"""
        self.log("Starting full sync...")
        
        # 1. Get wallet
        self.data["wallet"] = self.get_wallet_status()
        
        # 2. Get blockchain positions
        self.data["positions"] = self.get_positions()
        
        # 3. Get database trades
        self.data["trades"] = self.get_db_trades()
        
        # 4. Calculate stats
        self.calculate_stats()
        
        # 5. Update timestamp
        self.data["last_sync"] = datetime.now().isoformat()
        
        self.log(f"Sync complete: {len(self.data['positions'])} positions, {len(self.data['trades'])} trades")
        
        return self.data
    
    def calculate_stats(self):
        """Calculate comprehensive stats"""
        trades = self.data["trades"]
        positions = self.data["positions"]
        
        # Basic stats
        total_trades = len(trades)
        total_invested = sum(t.get('size_usd', 0) for t in trades)
        
        # Resolved vs pending
        resolved = [p for p in positions if p.get('market_resolved', False)]
        pending = [p for p in positions if not p.get('market_resolved', False)]
        
        # P&L calculation
        realized_pnl = sum(p.get('pnl', 0) for p in resolved)
        unrealized_pnl = sum(p.get('pnl', 0) for p in pending)
        
        self.data["stats"] = {
            "total_trades": total_trades,
            "total_invested": total_invested,
            "open_positions": len(positions),
            "resolved_positions": len(resolved),
            "pending_positions": len(pending)
        }
        
        self.data["resolved"] = resolved
        self.data["pending"] = pending
        self.data["pnl"] = {
            "realized": round(realized_pnl, 2),
            "unrealized": round(unrealized_pnl, 2),
            "total": round(realized_pnl + unrealized_pnl, 2)
        }
    
    def generate_dashboard_html(self) -> str:
        """Generate live dashboard HTML"""
        data = self.data
        
        wallet = data.get("wallet", {})
        balances = wallet.get("balances", {})
        
        stats = data.get("stats", {})
        pnl = data.get("pnl", {})
        
        trades_html = ""
        for t in data.get("trades", []):
            status_color = "#00ff88" if t.get('status') == 'RESOLVED' else "#00d4ff"
            trades_html += f"""
                <tr>
                    <td>{t.get('id')}</td>
                    <td>{t.get('timestamp', '')[:16]}</td>
                    <td>{t.get('market_question', '')[:35]}...</td>
                    <td><span class="badge badge-{t.get('side', '').lower()}">{t.get('side')}</span></td>
                    <td>${t.get('size_usd', 0)}</td>
                    <td>${t.get('entry_price', 0)}</td>
                    <td><span class="badge" style="background: {status_color}20; color: {status_color}">● {t.get('status', 'OPEN')}</span></td>
                </tr>
            """
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KimiClaw LIVE Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0f; color: #fff; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #151520 0%, #1a1a2e 100%); border: 1px solid #252535; padding: 25px; margin-bottom: 25px; border-radius: 16px; }}
        .header h1 {{ color: #00d4ff; font-size: 32px; margin-bottom: 5px; }}
        .header p {{ color: #888; font-size: 14px; }}
        .sync-status {{ float: right; text-align: right; }}
        .sync-indicator {{ display: inline-block; width: 10px; height: 10px; background: #00ff88; border-radius: 50%; animation: pulse 2s infinite; margin-right: 5px; }}
        @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
        .alert {{ background: rgba(255, 71, 87, 0.1); border: 1px solid #ff4757; color: #ff4757; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .alert-success {{ background: rgba(0, 255, 136, 0.1); border-color: #00ff88; color: #00ff88; }}
        .alert-warning {{ background: rgba(255, 193, 7, 0.1); border-color: #ffc107; color: #ffc107; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 25px; }}
        .stat-card {{ background: #151520; border: 1px solid #252535; border-radius: 12px; padding: 20px; transition: transform 0.2s; }}
        .stat-card:hover {{ transform: translateY(-2px); border-color: #00d4ff; }}
        .stat-card h3 {{ color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px; }}
        .stat-card .value {{ font-size: 28px; font-weight: bold; color: #fff; }}
        .stat-card .positive {{ color: #00ff88; }}
        .stat-card .negative {{ color: #ff4757; }}
        .section {{ background: #151520; border: 1px solid #252535; border-radius: 12px; padding: 25px; margin-bottom: 20px; }}
        .section h2 {{ color: #00d4ff; margin-bottom: 20px; font-size: 18px; display: flex; align-items: center; gap: 10px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #252535; }}
        th {{ color: #00d4ff; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
        tr:hover {{ background: rgba(0, 212, 255, 0.05); }}
        .badge {{ padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
        .badge-yes {{ background: rgba(0, 255, 136, 0.2); color: #00ff88; }}
        .badge-no {{ background: rgba(255, 71, 87, 0.2); color: #ff4757; }}
        .badge-open {{ background: rgba(0, 212, 255, 0.2); color: #00d4ff; }}
        .badge-resolved {{ background: rgba(0, 255, 136, 0.2); color: #00ff88; }}
        .money-flow {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .flow-card {{ background: #0f0f1a; border: 1px solid #252535; border-radius: 8px; padding: 15px; text-align: center; }}
        .flow-card h4 {{ color: #888; font-size: 11px; margin-bottom: 8px; }}
        .flow-card .amount {{ font-size: 24px; font-weight: bold; }}
        .updated {{ text-align: right; color: #666; font-size: 11px; margin-top: 15px; }}
        .tx-link {{ color: #00d4ff; text-decoration: none; font-size: 11px; }}
        .tx-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="sync-status">
                <span class="sync-indicator"></span>
                <span style="color: #00ff88; font-size: 12px;">LIVE SYNC</span>
                <div style="color: #666; font-size: 11px; margin-top: 5px;">Last: {data.get('last_sync', 'Never')[:19]}</div>
            </div>
            <h1>🦞 KimiClaw LIVE Dashboard</h1>
            <p>Real-Time Trading Data | Auto-Sync Every 30s</p>
        </div>

        <div class="alert-success">
            ✅ SYSTEM ACTIVE — Tracking {stats.get('total_trades', 0)} trades across {stats.get('open_positions', 0)} positions
        </div>

        <!-- MONEY FLOW -->
        <div class="section">
            <h2>💰 Money Flow</h2>
            <div class="money-flow">
                <div class="flow-card">
                    <h4>WALLET (USDC.e)</h4>
                    <div class="amount" style="color: #ffc107;">${balances.get('USDC.e', '0.00')}</div>
                </div>
                <div class="flow-card">
                    <h4>INVESTED</h4>
                    <div class="amount" style="color: #00d4ff;">${stats.get('total_invested', 0)}</div>
                </div>
                <div class="flow-card">
                    <h4>TOTAL VALUE</h4>
                    <div class="amount" style="color: {('#00ff88' if pnl.get('total', 0) >= 0 else '#ff4757')};">${round(float(balances.get('USDC.e', 0)) + stats.get('total_invested', 0) + pnl.get('total', 0), 2)}</div>
                </div>
            </div>
        </div>

        <!-- STATS -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Trades</h3>
                <div class="value">{stats.get('total_trades', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Open Positions</h3>
                <div class="value">{stats.get('open_positions', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Resolved</h3>
                <div class="value" style="color: #00ff88;">{stats.get('resolved_positions', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Pending</h3>
                <div class="value" style="color: #ffc107;">{stats.get('pending_positions', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Realized P&L</h3>
                <div class="value {'positive' if pnl.get('realized', 0) >= 0 else 'negative'}">${pnl.get('realized', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Unrealized P&L</h3>
                <div class="value {'positive' if pnl.get('unrealized', 0) >= 0 else 'negative'}">${pnl.get('unrealized', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Total P&L</h3>
                <div class="value {'positive' if pnl.get('total', 0) >= 0 else 'negative'}">${pnl.get('total', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>POL Balance</h3>
                <div class="value">{balances.get('POL', '0')}</div>
            </div>
        </div>

        <!-- ALL TRADES -->
        <div class="section">
            <h2>📊 All Trades (Live from DB)</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Time</th>
                        <th>Market</th>
                        <th>Side</th>
                        <th>Size</th>
                        <th>Entry</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {trades_html}
                </tbody>
            </table>
            <div class="updated">Auto-refreshes every 30 seconds</div>
        </div>

        <!-- WALLET INFO -->
        <div class="section">
            <h2>👛 Wallet Details</h2>
            <p><strong>Address:</strong> 0x557A656C110a9eFdbFa28773DE4aCc2c3924a274</p>
            <p><strong>USDC.e:</strong> ${balances.get('USDC.e', '0.00')}</p>
            <p><strong>POL:</strong> {balances.get('POL', '0')}</p>
            <p><a href="https://polygonscan.com/address/0x557A656C110a9eFdbFa28773DE4aCc2c3924a274" target="_blank" class="tx-link">View on PolygonScan →</a></p>
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def save_dashboard(self):
        """Save dashboard to file"""
        html = self.generate_dashboard_html()
        with open(DASHBOARD_DIR / "index.html", 'w') as f:
            f.write(html)
        self.log("Dashboard saved")
    
    def deploy(self):
        """Deploy to GitHub Pages"""
        try:
            os.chdir(DASHBOARD_DIR)
            os.system("git add -A")
            os.system('git commit -m "Live sync update"')
            os.system("git push -f origin master:gh-pages")
            self.log("Dashboard deployed")
        except Exception as e:
            self.log(f"Deploy error: {e}")

def main():
    sync = LiveDashboardSync()
    sync.sync_data()
    sync.save_dashboard()
    sync.deploy()
    print(json.dumps(sync.data, indent=2, default=str))

if __name__ == "__main__":
    main()
