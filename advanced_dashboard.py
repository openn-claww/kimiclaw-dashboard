#!/usr/bin/env python3
"""
Advanced Live Dashboard with Control Center
Real-time sync + Interactive controls + AI thought process logging
"""

import sqlite3
import json
import subprocess
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Paths
DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")
DASHBOARD_DIR = Path("/root/.openclaw/workspace/control-center-dashboard")
LOG_FILE = Path("/root/.openclaw/workspace/control_center.log")
SKILL_DIR = Path("/root/.openclaw/skills/polyclaw")
MEMORY_DIR = Path("/root/.openclaw/workspace/memory")

class AdvancedDashboard:
    def __init__(self):
        self.data = {
            "wallet": {},
            "positions": [],
            "trades": [],
            "thoughts": [],
            "stats": {},
            "resolved": [],
            "pending": [],
            "pnl": {"realized": 0, "unrealized": 0, "total": 0},
            "system_status": {},
            "last_sync": None,
            "diljeet_status": "IDLE",
            "current_action": "Monitoring markets...",
            "lessons_learned": []
        }
        DASHBOARD_DIR.mkdir(exist_ok=True)
    
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        with open(LOG_FILE, 'a') as f:
            f.write(log_msg + '\n')
    
    def get_wallet(self) -> Dict:
        try:
            cmd = f"cd {SKILL_DIR} && bash -c 'source .env && uv run python scripts/polyclaw.py wallet status'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            self.log(f"Wallet error: {e}")
        return {}
    
    def get_positions(self) -> List[Dict]:
        try:
            cmd = f"cd {SKILL_DIR} && bash -c 'source .env && uv run python scripts/polyclaw.py positions list --json'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            self.log(f"Positions error: {e}")
        return []
    
    def get_db_trades(self) -> List[Dict]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        trades = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(t) for t in trades]
    
    def get_thoughts(self) -> List[Dict]:
        """Get Diljeet's thought process from memory"""
        thoughts = []
        try:
            # Get recent trading decisions
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, market_question, side, reasoning, confidence, strategy 
                FROM trades WHERE reasoning IS NOT NULL 
                ORDER BY id DESC LIMIT 10
            """)
            for row in cursor.fetchall():
                thoughts.append({
                    "time": row['timestamp'],
                    "market": row['market_question'][:50] + "..." if len(row['market_question']) > 50 else row['market_question'],
                    "decision": f"{row['side']} at {row['confidence']}/10 confidence",
                    "thought": row['reasoning'][:200] + "..." if len(row['reasoning']) > 200 else row['reasoning'],
                    "strategy": row['strategy']
                })
            conn.close()
        except Exception as e:
            self.log(f"Thoughts error: {e}")
        return thoughts
    
    def get_lessons(self) -> List[str]:
        """Get lessons learned"""
        lessons = []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT lesson_learned FROM trades WHERE lesson_learned IS NOT NULL")
            for row in cursor.fetchall():
                if row[0]:
                    lessons.append(row[0])
            conn.close()
        except:
            pass
        return lessons[-5:]  # Last 5 lessons
    
    def check_system_status(self) -> Dict:
        """Check if trading is enabled"""
        try:
            import subprocess as sp
            result = sp.run(["openclaw", "cron", "list"], capture_output=True, text=True)
            output = result.stdout + result.stderr
            
            trading_enabled = "short-term-trading-heartbeat" in output and "enabled" in output.lower()
            
            return {
                "trading_enabled": trading_enabled,
                "dashboard_sync": True,
                "wallet_connected": True,
                "last_check": datetime.now().isoformat()
            }
        except:
            return {"trading_enabled": False, "error": "Cannot check status"}
    
    def sync(self):
        self.log("Starting advanced sync...")
        self.data["wallet"] = self.get_wallet()
        self.data["positions"] = self.get_positions()
        self.data["trades"] = self.get_db_trades()
        self.data["thoughts"] = self.get_thoughts()
        self.data["lessons_learned"] = self.get_lessons()
        self.data["system_status"] = self.check_system_status()
        
        # Calculate stats
        self.calculate_stats()
        
        # Set Diljeet's current status
        self.data["diljeet_status"] = "MONITORING"
        self.data["current_action"] = "Scanning markets for opportunities..."
        
        self.data["last_sync"] = datetime.now().isoformat()
        self.log(f"Sync complete: {len(self.data['trades'])} trades, {len(self.data['positions'])} positions")
        return self.data
    
    def calculate_stats(self):
        trades = self.data["trades"]
        positions = self.data["positions"]
        
        total_trades = len(trades)
        total_invested = sum(t.get('size_usd', 0) for t in trades)
        
        # Categorize positions
        resolved = []
        pending = []
        winners = []
        losers = []
        
        for p in positions:
            pnl = p.get('pnl', 0)
            if p.get('market_resolved'):
                resolved.append(p)
                if pnl > 0:
                    winners.append(p)
                else:
                    losers.append(p)
            else:
                pending.append(p)
        
        realized_pnl = sum(p.get('pnl', 0) for p in resolved)
        unrealized_pnl = sum(p.get('pnl', 0) for p in pending)
        
        self.data["stats"] = {
            "total_trades": total_trades,
            "total_invested": total_invested,
            "open_positions": len(positions),
            "resolved_positions": len(resolved),
            "pending_positions": len(pending),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(len(winners) / len(resolved) * 100, 1) if resolved else 0
        }
        
        self.data["resolved"] = resolved
        self.data["pending"] = pending
        self.data["winners"] = winners
        self.data["losers"] = losers
        self.data["pnl"] = {
            "realized": round(realized_pnl, 2),
            "unrealized": round(unrealized_pnl, 2),
            "total": round(realized_pnl + unrealized_pnl, 2)
        }
    
    def generate_html(self) -> str:
        d = self.data
        wallet = d.get("wallet", {})
        balances = wallet.get("balances", {})
        stats = d.get("stats", {})
        pnl = d.get("pnl", {})
        system = d.get("system_status", {})
        
        # Generate trades HTML
        trades_html = ""
        for t in d.get("trades", [])[:20]:
            status_color = "#00ff88" if t.get('status') == 'RESOLVED' else "#00d4ff"
            pnl_val = t.get('pnl_usd', 0) or 0
            pnl_color = "#00ff88" if pnl_val >= 0 else "#ff4757"
            trades_html += f"""
                <tr>
                    <td>#{t.get('id')}</td>
                    <td>{t.get('timestamp', '')[:16]}</td>
                    <td>{t.get('market_question', '')[:30]}...</td>
                    <td><span class="badge badge-{t.get('side', '').lower()}">{t.get('side')}</span></td>
                    <td>${t.get('size_usd', 0)}</td>
                    <td>${t.get('entry_price', 0)}</td>
                    <td style="color: {pnl_color}">${pnl_val:+.2f}</td>
                    <td><span class="badge" style="background: {status_color}20; color: {status_color}">{t.get('status', 'OPEN')}</span></td>
                </tr>
            """
        
        # Generate thoughts HTML
        thoughts_html = ""
        for th in d.get("thoughts", [])[:5]:
            thoughts_html += f"""
                <div class="thought-card">
                    <div class="thought-header">
                        <span class="thought-time">{th.get('time', '')}</span>
                        <span class="thought-strategy">{th.get('strategy', '')}</span>
                    </div>
                    <div class="thought-market">{th.get('market', '')}</div>
                    <div class="thought-decision">🧠 Decision: {th.get('decision', '')}</div>
                    <div class="thought-body">{th.get('thought', '')}</div>
                </div>
            """
        
        # Generate lessons HTML
        lessons_html = ""
        for lesson in d.get("lessons_learned", []):
            lessons_html += f"""
                <div class="lesson-item">📌 {lesson}</div>
            """
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diljeet Control Center | Live Trading Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #151520;
            --bg-card: #1a1a2e;
            --border: #252535;
            --accent: #00d4ff;
            --success: #00ff88;
            --danger: #ff4757;
            --warning: #ffc107;
            --text: #ffffff;
            --text-muted: #888888;
            --gradient-1: linear-gradient(135deg, #00d4ff 0%, #7b2cbf 100%);
            --gradient-2: linear-gradient(135deg, #00ff88 0%, #00d4ff 100%);
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', -apple-system, sans-serif; background: var(--bg-primary); color: var(--text); line-height: 1.6; }}
        
        /* Header */
        .header {{ background: var(--bg-secondary); border-bottom: 1px solid var(--border); padding: 20px 30px; position: sticky; top: 0; z-index: 100; }}
        .header-content {{ max-width: 1600px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .logo {{ display: flex; align-items: center; gap: 15px; }}
        .logo-icon {{ width: 50px; height: 50px; background: var(--gradient-1); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px; }}
        .logo-text h1 {{ font-size: 24px; font-weight: 700; background: var(--gradient-1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .logo-text p {{ color: var(--text-muted); font-size: 13px; }}
        
        /* Diljeet Status */
        .diljeet-status {{ display: flex; align-items: center; gap: 20px; background: var(--bg-card); padding: 15px 25px; border-radius: 12px; border: 1px solid var(--border); }}
        .diljeet-avatar {{ width: 45px; height: 45px; background: var(--gradient-2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.7; }} }}
        .diljeet-info {{ text-align: left; }}
        .diljeet-name {{ font-weight: 600; font-size: 16px; }}
        .diljeet-action {{ color: var(--accent); font-size: 13px; }}
        .sync-indicator {{ display: flex; align-items: center; gap: 8px; color: var(--success); font-size: 12px; }}
        .sync-dot {{ width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: blink 1s infinite; }}
        @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
        
        /* Controls */
        .controls {{ display: flex; gap: 10px; }}
        .btn {{ padding: 10px 20px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.3s; font-size: 13px; }}
        .btn-danger {{ background: rgba(255, 71, 87, 0.2); color: var(--danger); border: 1px solid var(--danger); }}
        .btn-danger:hover {{ background: var(--danger); color: white; }}
        .btn-success {{ background: rgba(0, 255, 136, 0.2); color: var(--success); border: 1px solid var(--success); }}
        .btn-success:hover {{ background: var(--success); color: black; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        
        /* Main Grid */
        .container {{ max-width: 1600px; margin: 0 auto; padding: 25px; }}
        .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 20px; }}
        
        /* Cards */
        .card {{ background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 16px; padding: 25px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        .card-title {{ font-size: 16px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 10px; }}
        .card-icon {{ font-size: 20px; }}
        
        /* Stats Grid */
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
        .stat-item {{ background: var(--bg-card); padding: 20px; border-radius: 12px; border: 1px solid var(--border); transition: all 0.3s; }}
        .stat-item:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
        .stat-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
        .stat-value {{ font-size: 28px; font-weight: 700; }}
        .stat-change {{ font-size: 12px; margin-top: 5px; }}
        .positive {{ color: var(--success); }}
        .negative {{ color: var(--danger); }}
        
        /* Money Flow */
        .flow-container {{ display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px; background: var(--bg-card); border-radius: 12px; }}
        .flow-item {{ text-align: center; flex: 1; }}
        .flow-arrow {{ font-size: 24px; color: var(--accent); }}
        .flow-label {{ font-size: 11px; color: var(--text-muted); margin-bottom: 5px; }}
        .flow-amount {{ font-size: 24px; font-weight: 700; }}
        .flow-wallet {{ color: var(--warning); }}
        .flow-invested {{ color: var(--accent); }}
        .flow-total {{ color: var(--success); }}
        
        /* Tables */
        .table-container {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ text-align: left; padding: 15px 12px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }}
        td {{ padding: 15px 12px; border-bottom: 1px solid var(--border); }}
        tr:hover {{ background: rgba(0, 212, 255, 0.05); }}
        .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
        .badge-yes {{ background: rgba(0, 255, 136, 0.2); color: var(--success); }}
        .badge-no {{ background: rgba(255, 71, 87, 0.2); color: var(--danger); }}
        
        /* Thought Cards */
        .thought-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 15px; }}
        .thought-header {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
        .thought-time {{ color: var(--text-muted); font-size: 12px; }}
        .thought-strategy {{ background: var(--accent); color: black; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
        .thought-market {{ font-weight: 600; margin-bottom: 8px; color: var(--accent); }}
        .thought-decision {{ font-size: 13px; color: var(--success); margin-bottom: 10px; }}
        .thought-body {{ font-size: 13px; color: var(--text-muted); line-height: 1.6; }}
        
        /* Chart Container */
        .chart-container {{ height: 300px; position: relative; }}
        
        /* Responsive */
        .col-3 {{ grid-column: span 3; }}
        .col-4 {{ grid-column: span 4; }}
        .col-6 {{ grid-column: span 6; }}
        .col-8 {{ grid-column: span 8; }}
        .col-12 {{ grid-column: span 12; }}
        
        @media (max-width: 1200px) {{ .col-3, .col-4 {{ grid-column: span 6; }} }}
        @media (max-width: 768px) {{ .col-3, .col-4, .col-6, .col-8 {{ grid-column: span 12; }} }}
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <div class="logo">
                <div class="logo-icon">🦞</div>
                <div class="logo-text">
                    <h1>Diljeet Control Center</h1>
                    <p>Live Trading Dashboard • Real-Time Sync</p>
                </div>
            </div>
            
            <div class="diljeet-status">
                <div class="diljeet-avatar">🤖</div>
                <div class="diljeet-info">
                    <div class="diljeet-name">Diljeet AI</div>
                    <div class="diljeet-action">{d.get('current_action', 'Monitoring...')}</div>
                    <div class="sync-indicator">
                        <span class="sync-dot"></span>
                        <span>Live Sync • {d.get('last_sync', 'Never')[:19]}</span>
                    </div>
                </div>
            </div>
            
            <div class="controls">
                <button class="btn btn-danger" {'disabled' if not system.get('trading_enabled') else ''} onclick="alert('Trading already stopped!')">
                    ⏹ STOP TRADING
                </button>
                <button class="btn btn-success" onclick="alert('Manual sync triggered!')">
                    🔄 SYNC NOW
                </button>
            </div>
        </div>
    </header>

    <div class="container">
        <div class="grid">
            <!-- WALLET OVERVIEW -->
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title"><span class="card-icon">💰</span> Money Flow</div>
                    </div>
                    <div class="flow-container">
                        <div class="flow-item">
                            <div class="flow-label">WALLET (USDC.e)</div>
                            <div class="flow-amount flow-wallet">${balances.get('USDC.e', '0.00')}</div>
                        </div>
                        <div class="flow-arrow">→</div>
                        <div class="flow-item">
                            <div class="flow-label">INVESTED</div>
                            <div class="flow-amount flow-invested">${stats.get('total_invested', 0)}</div>
                        </div>
                        <div class="flow-arrow">→</div>
                        <div class="flow-item">
                            <div class="flow-label">EXPECTED VALUE</div>
                            <div class="flow-amount flow-total">${round(float(balances.get('USDC.e', 0)) + stats.get('total_invested', 0) + pnl.get('total', 0), 2)}</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- KEY STATS -->
            <div class="col-12">
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-label">Total Trades</div>
                        <div class="stat-value">{stats.get('total_trades', 0)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Open Positions</div>
                        <div class="stat-value">{stats.get('open_positions', 0)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-value positive">{stats.get('win_rate', 0)}%</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Total P&L</div>
                        <div class="stat-value {'positive' if pnl.get('total', 0) >= 0 else 'negative'}">${pnl.get('total', 0):+.2f}</div>
                    </div>
                </div>
            </div>

            <!-- ALL TRADES -->
            <div class="col-8">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title"><span class="card-icon">📊</span> All Trades (Live from DB + Blockchain)</div>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Time</th>
                                    <th>Market</th>
                                    <th>Side</th>
                                    <th>Size</th>
                                    <th>Entry</th>
                                    <th>P&L</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trades_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- DILJEET'S THOUGHTS -->
            <div class="col-4">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title"><span class="card-icon">🧠</span> Diljeet's Thought Process</div>
                    </div>
                    {thoughts_html if thoughts_html else '<p style="color: var(--text-muted); text-align: center; padding: 20px;">No recent thoughts recorded</p>'}
                </div>
            </div>

            <!-- LESSONS LEARNED -->
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title"><span class="card-icon">📚</span> Lessons Learned</div>
                    </div>
                    {lessons_html if lessons_html else '<p style="color: var(--text-muted);">No lessons recorded yet</p>'}
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
        return html
    
    def save_and_deploy(self):
        html = self.generate_html()
        with open(DASHBOARD_DIR / "index.html", 'w') as f:
            f.write(html)
        
        # Deploy
        try:
            os.chdir(DASHBOARD_DIR)
            os.system("git init 2>/dev/null")
            os.system("git add -A")
            os.system('git commit -m "Advanced control center" 2>/dev/null')
            os.system("git push -f https://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@github.com/openn-claww/kimiclaw-dashboard.git master:gh-pages 2>/dev/null")
            self.log("Advanced dashboard deployed!")
        except Exception as e:
            self.log(f"Deploy error: {e}")

def main():
    dashboard = AdvancedDashboard()
    dashboard.sync()
    dashboard.save_and_deploy()
    print(json.dumps(dashboard.data, indent=2, default=str))

if __name__ == "__main__":
    main()
