#!/usr/bin/env python3
"""
Polymarket Trading Dashboard - FastAPI Backend
Real-time trading dashboard with WebSocket support
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import subprocess

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Configuration ───────────────────────────────────────────────────────────
WORKSPACE = Path(os.getenv('BOT_WORKSPACE', '/root/.openclaw/workspace'))
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8888'))

# File paths
STATE_FILE = WORKSPACE / 'master_v6_state.json'
HEALTH_FILE = WORKSPACE / 'master_v6_health.json'
TRADES_FILE = WORKSPACE / 'master_v6_trades.json'
LOG_FILE = WORKSPACE / 'master_v6_run.log'
ALERT_FILE = WORKSPACE / 'master_v6_alerts.json'
PNL_FILE = WORKSPACE / 'pnl_trades.json'
BOT_PID_FILE = WORKSPACE / 'v6_bot.pid'

# ── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(WORKSPACE / 'dashboard.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('dashboard')

# ── Data Models ──────────────────────────────────────────────────────────────
@dataclass
class BotStatus:
    running: bool
    mode: str  # 'paper' or 'live'
    strategy: str  # Current active strategy
    strategies: List[str]  # Available strategies
    balance: float
    paper_balance: float  # Separate paper trading balance
    real_balance: float   # Separate real trading balance
    trade_count: int
    paper_trades: int     # Separate paper trade count
    real_trades: int      # Separate real trade count
    open_positions: int
    paper_positions: int  # Separate paper positions
    real_positions: int   # Separate real positions
    uptime: Optional[str] = None
    last_update: Optional[str] = None

@dataclass
class Position:
    market: str
    side: str
    size: float
    entry_price: float
    current_price: Optional[float] = None
    pnl: Optional[float] = None
    timestamp: Optional[str] = None

@dataclass
class Trade:
    type: str
    market: str
    timestamp: str
    side: Optional[str] = None
    amount: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None

@dataclass
class PnLMetrics:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    gross_pnl: float
    fees_paid: float
    best_trade: Dict
    worst_trade: Dict
    by_coin: Dict
    by_strategy: Dict

# ── State Management ─────────────────────────────────────────────────────────
class DashboardState:
    def __init__(self):
        self.clients: List[WebSocket] = []
        self.bot_process = None
        self._cached_state = {}
        self._last_refresh = 0
        
    async def broadcast(self, message: Dict):
        """Broadcast message to all connected WebSocket clients"""
        disconnected = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)
        
        # Clean up disconnected clients
        for client in disconnected:
            if client in self.clients:
                self.clients.remove(client)

    def safe_load_json(self, filepath: Path, default=None) -> Any:
        """Safely load JSON file"""
        try:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
        return default if default is not None else {}

    def get_bot_status(self) -> BotStatus:
        """Get current bot status from state files with separate paper/real tracking"""
        state = self.safe_load_json(STATE_FILE, {})
        health = self.safe_load_json(HEALTH_FILE, {})
        
        # Check if bot is running
        running = False
        if BOT_PID_FILE.exists():
            try:
                pid = int(BOT_PID_FILE.read_text().strip())
                os.kill(pid, 0)  # Check if process exists
                running = True
            except (ValueError, ProcessLookupError, PermissionError):
                running = False
        
        # Get strategy information
        strategies = ['Mean Reversion', 'Bond Buyer', 'Dual Strategy', 'Momentum']
        current_strategy = health.get('active_strategy', 'Mean Reversion')
        
        # Separate paper and real trading data
        paper_data = state.get('paper_trading', {})
        real_data = state.get('live_trading', {})
        
        # Get active positions split by mode
        active_positions = state.get('active_positions', {})
        paper_positions = sum(1 for p in active_positions.values() if p.get('paper', True))
        real_positions = sum(1 for p in active_positions.values() if not p.get('paper', True))
        
        return BotStatus(
            running=running,
            mode='paper' if health.get('paper_mode', True) else 'live',
            strategy=current_strategy,
            strategies=strategies,
            balance=state.get('balance', 0.0),
            paper_balance=paper_data.get('balance', state.get('balance', 0.0)),
            real_balance=real_data.get('balance', 0.0),
            trade_count=state.get('trade_count', 0),
            paper_trades=paper_data.get('trade_count', 0),
            real_trades=real_data.get('trade_count', 0),
            open_positions=len(active_positions),
            paper_positions=paper_positions,
            real_positions=real_positions,
            last_update=state.get('last_update')
        )

    def get_pnl_metrics(self) -> Optional[PnLMetrics]:
        """Get P&L metrics from health file"""
        health = self.safe_load_json(HEALTH_FILE, {})
        pnl = health.get('pnl_tracker', {})
        
        if not pnl:
            return None
            
        return PnLMetrics(
            total_trades=pnl.get('total_trades', 0),
            wins=pnl.get('wins', 0),
            losses=pnl.get('losses', 0),
            win_rate=pnl.get('win_rate', 0.0),
            net_pnl=pnl.get('net_pnl', 0.0),
            gross_pnl=pnl.get('gross_pnl', 0.0),
            fees_paid=pnl.get('fees_paid', 0.0),
            best_trade=pnl.get('best_trade', {}),
            worst_trade=pnl.get('worst_trade', {}),
            by_coin=pnl.get('by_coin', {}),
            by_strategy=pnl.get('by_strategy', {})
        )

    def get_recent_trades(self, limit: int = 50) -> List[Trade]:
        """Get recent trades from trades file"""
        data = self.safe_load_json(TRADES_FILE, {})
        trades = data.get('trades', [])
        
        recent = []
        for t in trades[-limit:]:
            recent.append(Trade(
                type=t.get('type', 'UNKNOWN'),
                market=t.get('market', 'Unknown'),
                timestamp=t.get('timestamp_utc', ''),
                side=t.get('side'),
                amount=t.get('amount') or t.get('size'),
                entry_price=t.get('entry_price'),
                exit_price=t.get('exit_price'),
                pnl_pct=t.get('pnl_pct'),
                exit_reason=t.get('exit_reason')
            ))
        return recent

    def get_logs(self, lines: int = 100) -> List[str]:
        """Get recent log lines"""
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, 'r') as f:
                    all_lines = f.readlines()
                    return all_lines[-lines:]
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
        return []

    def get_alerts(self, limit: int = 20) -> List[Dict]:
        """Get recent alerts"""
        try:
            if ALERT_FILE.exists():
                with open(ALERT_FILE, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        alerts = data
                    else:
                        alerts = data.get('alerts', [])
                    return alerts[-limit:]
        except Exception as e:
            logger.error(f"Error reading alerts: {e}")
        return []

    async def start_bot(self, mode: str = 'paper') -> bool:
        """Start the trading bot"""
        try:
            if mode == 'live':
                cmd = ['python3', str(WORKSPACE / 'master_bot_v6_polyclaw_integration.py'), '--live']
            else:
                cmd = ['python3', str(WORKSPACE / 'master_bot_v6_polyclaw_integration.py')]
            
            subprocess.Popen(cmd, cwd=WORKSPACE)
            await asyncio.sleep(2)  # Give it time to start
            return True
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False

    async def stop_bot(self) -> bool:
        """Stop the trading bot"""
        try:
            if BOT_PID_FILE.exists():
                pid = int(BOT_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(1)
                return True
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
            return False

# ── Global State ─────────────────────────────────────────────────────────────
dashboard_state = DashboardState()

# ── WebSocket Manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        dashboard_state.clients.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in dashboard_state.clients:
            dashboard_state.clients.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# ── Background Tasks ─────────────────────────────────────────────────────────
async def data_refresh_loop():
    """Continuously refresh data and broadcast to clients with paper/real split"""
    while True:
        try:
            if manager.active_connections:
                status = dashboard_state.get_bot_status()
                pnl = dashboard_state.get_pnl_metrics()
                
                await manager.broadcast({
                    'type': 'status_update',
                    'data': {
                        'status': {
                            'running': status.running,
                            'mode': status.mode,
                            'strategy': status.strategy,
                            'strategies': status.strategies,
                            'balance': status.balance,
                            'paper_balance': status.paper_balance,
                            'real_balance': status.real_balance,
                            'trade_count': status.trade_count,
                            'paper_trades': status.paper_trades,
                            'real_trades': status.real_trades,
                            'open_positions': status.open_positions,
                            'paper_positions': status.paper_positions,
                            'real_positions': status.real_positions
                        },
                        'pnl': asdict(pnl) if pnl else None,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                })
            await asyncio.sleep(5)  # Update every 5 seconds
        except Exception as e:
            logger.error(f"Error in refresh loop: {e}")
            await asyncio.sleep(5)

# ── FastAPI App ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(data_refresh_loop())
    logger.info("Dashboard server starting...")
    yield
    # Shutdown
    logger.info("Dashboard server shutting down...")

app = FastAPI(
    title="Polymarket Trading Dashboard",
    description="Real-time trading dashboard for Polymarket bot",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(WORKSPACE / 'trading-dashboard/static')), name="static")

# ── API Routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main dashboard page"""
    return FileResponse(WORKSPACE / 'trading-dashboard/templates/index.html')

@app.get("/api/status")
async def api_status():
    """Get current bot status"""
    status = dashboard_state.get_bot_status()
    return asdict(status)

@app.get("/api/pnl")
async def api_pnl():
    """Get P&L metrics"""
    pnl = dashboard_state.get_pnl_metrics()
    if pnl:
        return asdict(pnl)
    raise HTTPException(status_code=404, detail="P&L data not available")

@app.get("/api/trades")
async def api_trades(limit: int = 50):
    """Get recent trades"""
    trades = dashboard_state.get_recent_trades(limit)
    return {'trades': [asdict(t) for t in trades]}

@app.get("/api/positions")
async def api_positions():
    """Get active positions"""
    state = dashboard_state.safe_load_json(STATE_FILE, {})
    return {'positions': state.get('active_positions', {})}

@app.get("/api/logs")
async def api_logs(lines: int = 100):
    """Get recent log lines"""
    logs = dashboard_state.get_logs(lines)
    return {'logs': logs}

@app.get("/api/alerts")
async def api_alerts(limit: int = 20):
    """Get recent alerts"""
    alerts = dashboard_state.get_alerts(limit)
    return {'alerts': alerts}

@app.get("/api/health")
async def api_health():
    """Get detailed health metrics"""
    health = dashboard_state.safe_load_json(HEALTH_FILE, {})
    return health

# ── Control Endpoints ────────────────────────────────────────────────────────

@app.post("/api/bot/start")
async def bot_start(mode: str = 'paper'):
    """Start the trading bot"""
    success = await dashboard_state.start_bot(mode)
    return {'success': success, 'mode': mode}

@app.post("/api/bot/stop")
async def bot_stop():
    """Stop the trading bot"""
    success = await dashboard_state.stop_bot()
    return {'success': success}

@app.post("/api/bot/mode")
async def bot_mode_switch(mode: str):
    """Switch bot mode between paper and live"""
    if mode not in ['paper', 'live']:
        raise HTTPException(status_code=400, detail="Mode must be 'paper' or 'live'")
    
    try:
        # Update health file with new mode
        health = dashboard_state.safe_load_json(HEALTH_FILE, {})
        health['paper_mode'] = (mode == 'paper')
        health['mode_switched_at'] = datetime.now(timezone.utc).isoformat()
        
        with open(HEALTH_FILE, 'w') as f:
            json.dump(health, f, indent=2)
        
        # Broadcast mode change to all clients
        await manager.broadcast({
            'type': 'mode_changed',
            'data': {'mode': mode, 'timestamp': health['mode_switched_at']}
        })
        
        return {
            'success': True, 
            'mode': mode,
            'message': f'Switched to {mode.upper()} trading mode',
            'requires_restart': False
        }
    except Exception as e:
        logger.error(f"Error switching mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bot/strategy")
async def bot_strategy_switch(strategy: str):
    """Switch active trading strategy"""
    available_strategies = ['Mean Reversion', 'Bond Buyer', 'Dual Strategy', 'Momentum']
    
    if strategy not in available_strategies:
        raise HTTPException(
            status_code=400, 
            detail=f"Strategy must be one of: {', '.join(available_strategies)}"
        )
    
    try:
        # Update health file with new strategy
        health = dashboard_state.safe_load_json(HEALTH_FILE, {})
        previous_strategy = health.get('active_strategy', 'Mean Reversion')
        health['active_strategy'] = strategy
        health['strategy_switched_at'] = datetime.now(timezone.utc).isoformat()
        health['previous_strategy'] = previous_strategy
        
        with open(HEALTH_FILE, 'w') as f:
            json.dump(health, f, indent=2)
        
        # Broadcast strategy change to all clients
        await manager.broadcast({
            'type': 'strategy_changed',
            'data': {
                'strategy': strategy,
                'previous': previous_strategy,
                'timestamp': health['strategy_switched_at']
            }
        })
        
        return {
            'success': True,
            'strategy': strategy,
            'previous': previous_strategy,
            'message': f'Switched to {strategy} strategy'
        }
    except Exception as e:
        logger.error(f"Error switching strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/strategies")
async def api_strategies():
    """Get available strategies and their performance"""
    strategies = [
        {
            'id': 'mean_reversion',
            'name': 'Mean Reversion',
            'win_rate': 81.9,
            'sharpe': 3.79,
            'status': 'active',
            'description': 'RSI + Bollinger Bands based signals'
        },
        {
            'id': 'bond_buyer',
            'name': 'Bond Buyer',
            'win_rate': 84.6,
            'sharpe': 2.5,
            'status': 'ready',
            'description': 'High probability (90%+) position buying'
        },
        {
            'id': 'dual',
            'name': 'Dual Strategy',
            'win_rate': None,
            'sharpe': None,
            'status': 'active',
            'description': 'External Arb + Momentum combined'
        },
        {
            'id': 'momentum',
            'name': 'Momentum',
            'win_rate': 50.0,
            'sharpe': 0.8,
            'status': 'baseline',
            'description': 'Velocity-based trend following'
        }
    ]
    return {'strategies': strategies}

# ── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial data
        status = dashboard_state.get_bot_status()
        pnl = dashboard_state.get_pnl_metrics()
        await websocket.send_json({
            'type': 'initial',
            'data': {
                'status': asdict(status),
                'pnl': asdict(pnl) if pnl else None
            }
        })
        
        # Keep connection alive and handle client messages
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(message)
                
                # Handle commands from client
                if data.get('action') == 'refresh':
                    status = dashboard_state.get_bot_status()
                    await websocket.send_json({
                        'type': 'status_update',
                        'data': asdict(status)
                    })
                    
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({'type': 'ping'})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# ── Main Entry Point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🚀 Starting Polymarket Trading Dashboard on port {DASHBOARD_PORT}")
    print(f"📊 Dashboard URL: http://localhost:{DASHBOARD_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="info")
