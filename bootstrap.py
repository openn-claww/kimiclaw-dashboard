#!/usr/bin/env python3
"""
bootstrap.py — Writes all dashboard files to disk, then runs install
Paste this entire file into your KimiClaw terminal:
  python3 /root/.openclaw/workspace/bootstrap.py
"""
import os, base64, subprocess, sys
from pathlib import Path

DEST = Path('/opt/bot-dashboard')
print(f"Writing dashboard files to {DEST}...")

files = {}

# ── backend/main.py ──────────────────────────────────────────────
files['backend/main.py'] = r'''
import os, json, time, asyncio, secrets
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from typing import Optional

os.nice(19)

import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

WORKSPACE   = Path(os.getenv('BOT_WORKSPACE', '/root/.openclaw/workspace'))
PASSWORD    = os.getenv('DASHBOARD_PASSWORD', 'changeme')
LOG_FILE    = WORKSPACE / 'master_v6_run.log'
TRADE_LOG   = WORKSPACE / 'master_v6_trades.json'
STATE_FILE  = WORKSPACE / 'master_v6_state.json'
HEALTH_FILE = WORKSPACE / 'master_v6_health.json'
MAX_CLIENTS = 20
CACHE_TTL   = 1.0

_file_cache:  dict = {}
_cache_times: dict = {}
_connected:   int  = 0
_session_tokens: set = set()

def verify_token(t): return t in _session_tokens
def create_token(pw):
    if secrets.compare_digest(pw, PASSWORD):
        tok = secrets.token_hex(32); _session_tokens.add(tok); return tok
    return None

async def read_json_cached(path: Path) -> dict:
    key = str(path); now = time.monotonic()
    if key in _file_cache and (now - _cache_times.get(key,0)) < CACHE_TTL:
        return _file_cache[key]
    try:
        loop = asyncio.get_event_loop()
        raw  = await loop.run_in_executor(None, path.read_text)
        data = json.loads(raw)
    except Exception: data = {}
    _file_cache[key] = data; _cache_times[key] = now
    return data

def invalidate_cache(path: Path): _cache_times.pop(str(path), None)

async def tail_log(n=100):
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, LOG_FILE.read_text)
        return text.splitlines()[-n:]
    except FileNotFoundError: return ["Log file not found"]

async def build_payload():
    trades_raw = await read_json_cached(TRADE_LOG)
    state      = await read_json_cached(STATE_FILE)
    health     = await read_json_cached(HEALTH_FILE)
    trades = trades_raw.get('trades', [])
    meta   = trades_raw.get('meta', {})
    closed = [t for t in trades if t.get('type') == 'EXIT']
    wins   = [t for t in closed if float(t.get('pnl_pct',0)) > 0]
    net_pnl = 0.0
    for t in closed:
        ep = float(t.get('entry_price',0.5)); sh = float(t.get('shares',0))
        xp = float(t.get('exit_price',0))
        if ep > 0 and sh > 0:
            gross = (1.0-ep)*sh if xp>=0.99 else -ep*sh
            net_pnl += gross - max(0,gross)*0.02
    now = time.time()
    positions = []
    for mid, pos in state.get('active_positions',{}).items():
        age = (now - float(pos.get('entry_time',now)))/60
        positions.append({**pos,'market_id':mid,'age_min':round(age,1)})
    return {
        'ts': datetime.now(timezone.utc).isoformat(),
        'balance': float(state.get('balance', health.get('balance',0))),
        'net_pnl': round(net_pnl,4),
        'trade_count': int(meta.get('count', len(trades))),
        'win_rate': round(len(wins)/max(len(closed),1)*100,1),
        'bot_state': state.get('bot_state', health.get('bot_state','unknown')),
        'paper_mode': health.get('paper_mode', True),
        'clob_connected': health.get('clob_connected', False),
        'rtds_connected': health.get('rtds_connected', False),
        'kill_switch': health.get('kill_switch', state.get('kill_switch',{})),
        'active_positions': positions,
        'recent_trades': list(reversed(closed[-20:])),
        'maintenance': (WORKSPACE/'MAINTENANCE').exists(),
        'emergency_stop': (WORKSPACE/'EMERGENCY_STOP').exists(),
    }

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*',
                           ping_timeout=20, ping_interval=10)

@sio.event
async def connect(sid, environ, auth):
    global _connected
    if not verify_token((auth or {}).get('token','')): raise ConnectionRefusedError('Unauthorized')
    if _connected >= MAX_CLIENTS: raise ConnectionRefusedError('Max clients')
    _connected += 1
    payload = await build_payload()
    await sio.emit('update', payload, to=sid)
    await sio.emit('log_lines', {'lines': await tail_log(50)}, to=sid)

@sio.event
async def disconnect(sid):
    global _connected; _connected = max(0, _connected-1)

@sio.event
async def control(sid, data):
    if not verify_token(data.get('token','')): return
    action = data.get('action',''); flag = None
    if   action == 'emergency_stop':   flag = WORKSPACE/'EMERGENCY_STOP'
    elif action == 'maintenance_on':   flag = WORKSPACE/'MAINTENANCE'
    elif action == 'reset_killswitch': flag = WORKSPACE/'RESET_KILLSWITCH'
    elif action in ('maintenance_off','cancel_emergency'):
        p = WORKSPACE/('MAINTENANCE' if 'maint' in action else 'EMERGENCY_STOP')
        if p.exists(): p.unlink()
        await sio.emit('control_ack',{'action':action,'ok':True},to=sid); return
    if flag: flag.touch(); await sio.emit('control_ack',{'action':action,'ok':True},to=sid)

app = FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

@app.post("/auth/login")
async def login(body: dict):
    tok = create_token(body.get('password',''))
    if tok: return {"token": tok}
    raise HTTPException(status_code=401)

@app.get("/api/snapshot")
async def snapshot(token: str=''):
    if not verify_token(token): raise HTTPException(status_code=401)
    return await build_payload()

@app.get("/api/logs")
async def logs(token: str='', n: int=100):
    if not verify_token(token): raise HTTPException(status_code=401)
    return {"lines": await tail_log(min(n,500))}

@app.get("/health")
async def health_ep(): return {"ok":True,"clients":_connected}

FRONTEND = Path(__file__).parent.parent/'frontend'/'dist'
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND/'assets')), name="assets")
    @app.get("/{full_path:path}")
    async def spa(full_path: str): return FileResponse(str(FRONTEND/'index.html'))

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

@app.on_event("startup")
async def startup():
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    loop = asyncio.get_event_loop()

    class FH(FileSystemEventHandler):
        def __init__(self): self._t=0
        def on_modified(self, e):
            if Path(e.src_path).suffix in ('.json','.log'):
                invalidate_cache(Path(e.src_path))
                now=time.monotonic()
                if now-self._t>0.5:
                    self._t=now
                    asyncio.run_coroutine_threadsafe(self._push(),loop)
        async def _push(self):
            if _connected:
                try: await sio.emit('update', await build_payload())
                except: pass

    class LW(FileSystemEventHandler):
        def __init__(self): self._pos=0
        def on_modified(self, e):
            if Path(e.src_path)==LOG_FILE:
                asyncio.run_coroutine_threadsafe(self._push(),loop)
        async def _push(self):
            try:
                text=(await loop.run_in_executor(None,LOG_FILE.read_text)).splitlines()
                new=text[self._pos:]; self._pos=len(text)
                if new and _connected: await sio.emit('log_append',{'lines':new[-20:]})
            except: pass

    obs=Observer()
    obs.schedule(FH(), str(WORKSPACE), recursive=False)
    obs.schedule(LW(), str(WORKSPACE), recursive=False)
    obs.start()

    async def poll():
        while True:
            await asyncio.sleep(2)
            if _connected:
                try: await sio.emit('update', await build_payload())
                except: pass
    asyncio.create_task(poll())

if __name__=='__main__':
    import uvicorn
    uvicorn.run("main:socket_app",host="0.0.0.0",port=8080,reload=False,log_level="warning")
'''

# ── backend/requirements.txt ─────────────────────────────────────
files['backend/requirements.txt'] = '''fastapi==0.110.0
uvicorn[standard]==0.29.0
python-socketio==5.11.1
websockets==12.0
watchdog==4.0.0
python-multipart==0.0.9
aiofiles==23.2.1
'''

# ── frontend/package.json ────────────────────────────────────────
files['frontend/package.json'] = '''{
  "name": "polymarket-dashboard",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "socket.io-client": "^4.7.5"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.2"
  }
}
'''

# ── frontend/vite.config.js ──────────────────────────────────────
files['frontend/vite.config.js'] = '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', minify: 'esbuild' },
  server: {
    proxy: {
      '/auth': 'http://localhost:8080',
      '/api':  'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/socket.io': { target: 'http://localhost:8080', ws: true },
    }
  }
})
'''

# ── frontend/index.html ──────────────────────────────────────────
files['frontend/index.html'] = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>[POLYARB] Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
'''

# ── frontend/src/main.jsx ────────────────────────────────────────
files['frontend/src/main.jsx'] = '''import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
'''

# ── frontend/src/App.jsx ─────────────────────────────────────────
files['frontend/src/App.jsx'] = r'''import { useState, useEffect, useRef, useCallback } from "react";
import { io } from "socket.io-client";
import BalanceCard from "./components/BalanceCard";
import PositionsTable from "./components/PositionsTable";
import TradesList from "./components/TradesList";
import BotHealth from "./components/BotHealth";
import ControlPanel from "./components/ControlPanel";
import LogStream from "./components/LogStream";

const API = import.meta.env.VITE_API_URL || "";

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("dash_token") || "");
  const [password, setPassword] = useState("");
  const [loginErr, setLoginErr] = useState("");
  const [data, setData] = useState(null);
  const [logs, setLogs] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const socketRef = useRef(null);

  const login = async (e) => {
    e.preventDefault();
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!r.ok) { setLoginErr("Invalid password"); return; }
      const { token: tok } = await r.json();
      sessionStorage.setItem("dash_token", tok);
      setToken(tok); setLoginErr("");
    } catch { setLoginErr("Connection failed"); }
  };

  const sendControl = useCallback((action) => {
    if (socketRef.current) socketRef.current.emit("control", { action, token });
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const socket = io(API, { auth: { token }, transports: ["websocket"], reconnectionDelay: 2000 });
    socketRef.current = socket;
    socket.on("connect",    () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));
    socket.on("update",     (p) => { setData(p); setLastUpdate(new Date()); });
    socket.on("log_lines",  ({ lines }) => setLogs(lines.slice(-200)));
    socket.on("log_append", ({ lines }) => setLogs(p => [...p, ...lines].slice(-200)));
    socket.on("connect_error", (e) => {
      if (e.message === "Unauthorized") { sessionStorage.removeItem("dash_token"); setToken(""); }
    });
    return () => socket.disconnect();
  }, [token]);

  if (!token) return (
    <div className="login-screen">
      <div className="login-box">
        <div className="login-logo">
          <span className="logo-bracket">[</span><span className="logo-text">POLY</span>
          <span className="logo-accent">ARB</span><span className="logo-bracket">]</span>
        </div>
        <p className="login-sub">TRADING SYSTEM v6</p>
        <form onSubmit={login} className="login-form">
          <input type="password" placeholder="ACCESS CODE" value={password}
            onChange={e => setPassword(e.target.value)} className="login-input" autoFocus />
          <button type="submit" className="login-btn">AUTHENTICATE</button>
        </form>
        {loginErr && <p className="login-error">{loginErr}</p>}
      </div>
    </div>
  );

  return (
    <div className="dashboard">
      <header className="dash-header">
        <div className="header-left">
          <span className="header-logo">
            <span className="logo-bracket">[</span><span className="logo-text">POLY</span>
            <span className="logo-accent">ARB</span><span className="logo-bracket">]</span>
          </span>
          {data?.paper_mode
            ? <span className="badge badge-paper">PAPER</span>
            : <span className="badge badge-live">⚡ LIVE</span>}
        </div>
        <div className="header-center">
          {data?.emergency_stop && <span className="badge badge-emergency blinking">⛔ EMERGENCY STOP</span>}
          {data?.maintenance    && <span className="badge badge-maintenance">⏸ MAINTENANCE</span>}
        </div>
        <div className="header-right">
          <span className={`conn-indicator ${connected ? "conn-on" : "conn-off"}`}>
            {connected ? "● LIVE" : "○ RECONNECTING"}
          </span>
          {lastUpdate && <span className="last-update">{lastUpdate.toLocaleTimeString()}</span>}
          <button className="logout-btn" onClick={() => { sessionStorage.removeItem("dash_token"); setToken(""); }}>LOGOUT</button>
        </div>
      </header>
      <main className="dash-grid">
        <div className="grid-row row-top">
          <BalanceCard data={data} />
          <BotHealth data={data} />
          <ControlPanel data={data} onControl={sendControl} />
        </div>
        <div className="grid-row row-mid">
          <PositionsTable positions={data?.active_positions || []} />
          <TradesList trades={data?.recent_trades || []} />
        </div>
        <div className="grid-row row-bot">
          <LogStream lines={logs} />
        </div>
      </main>
    </div>
  );
}
'''

# ── Components ────────────────────────────────────────────────────
files['frontend/src/components/BalanceCard.jsx'] = '''export default function BalanceCard({ data }) {
  const balance = data?.balance ?? 0, pnl = data?.net_pnl ?? 0;
  const wr = data?.win_rate ?? 0, count = data?.trade_count ?? 0;
  return (
    <div className="card card-balance">
      <div className="card-label">ACCOUNT</div>
      <div className="balance-main">
        <span className="balance-currency">USDC</span>
        <span className="balance-amount">{balance.toFixed(2)}</span>
      </div>
      <div className="balance-pnl">
        <span className={`pnl-value ${pnl>=0?"pnl-pos":"pnl-neg"}`}>{pnl>=0?"+":""}{pnl.toFixed(4)}</span>
        <span className="pnl-label">NET P&L</span>
      </div>
      <div className="balance-stats">
        <div className="stat"><span className="stat-val">{count}</span><span className="stat-lbl">TRADES</span></div>
        <div className="stat-divider"/>
        <div className="stat"><span className="stat-val">{wr.toFixed(1)}%</span><span className="stat-lbl">WIN RATE</span></div>
      </div>
    </div>
  );
}
'''

files['frontend/src/components/BotHealth.jsx'] = '''function Dot({ on, label }) {
  return (
    <div className="health-row">
      <span className={`health-dot ${on?"dot-on":"dot-off"}`}>●</span>
      <span className="health-label">{label}</span>
      <span className={`health-status ${on?"status-ok":"status-err"}`}>{on?"OK":"DOWN"}</span>
    </div>
  );
}
export default function BotHealth({ data }) {
  const ks = data?.kill_switch || {};
  return (
    <div className="card card-health">
      <div className="card-label">SYSTEM STATUS</div>
      <div className="health-state">
        <span className="state-indicator">{data?.bot_state==="running"?"▶":"■"}</span>
        <span className="state-text">{(data?.bot_state||"unknown").toUpperCase()}</span>
      </div>
      <div className="health-checks">
        <Dot on={data?.clob_connected} label="CLOB WS"/>
        <Dot on={data?.rtds_connected} label="RTDS WS"/>
        <Dot on={!ks.active}           label="KILL SWITCH"/>
      </div>
      {ks.active && <div className="ks-alert">⚠ KILL SWITCH ACTIVE</div>}
      <div className="health-metrics">
        <div className="hm-row"><span className="hm-lbl">DAILY LOSS</span><span className="hm-val">${(ks.daily_loss_usd||0).toFixed(2)}</span></div>
        <div className="hm-row"><span className="hm-lbl">CONSEC LOSSES</span><span className={`hm-val ${(ks.consec||0)>=3?"hm-warn":""}`}>{ks.consec||0}</span></div>
      </div>
    </div>
  );
}
'''

files['frontend/src/components/ControlPanel.jsx'] = '''import { useState } from "react";
export default function ControlPanel({ data, onControl }) {
  const [confirm, setConfirm] = useState(null);
  const ask = (action, label, danger=false) => setConfirm({action, label, danger});
  const execute = () => { if(confirm) onControl(confirm.action); setConfirm(null); };
  return (
    <div className="card card-control">
      <div className="card-label">CONTROLS</div>
      <div className="ctrl-buttons">
        {!data?.emergency_stop
          ? <button className="ctrl-btn btn-danger" onClick={()=>ask("emergency_stop","EMERGENCY STOP",true)}>⛔ EMERGENCY STOP</button>
          : <button className="ctrl-btn btn-cancel" onClick={()=>ask("cancel_emergency","CANCEL EMERGENCY STOP",true)}>✓ CANCEL STOP</button>}
        {!data?.maintenance
          ? <button className="ctrl-btn btn-warn" onClick={()=>ask("maintenance_on","PAUSE TRADING")}>⏸ PAUSE TRADING</button>
          : <button className="ctrl-btn btn-ok"   onClick={()=>ask("maintenance_off","RESUME TRADING")}>▶ RESUME TRADING</button>}
        <button className="ctrl-btn btn-neutral" onClick={()=>ask("reset_killswitch","RESET KILL SWITCH")}
          disabled={!data?.kill_switch?.active}>↺ RESET KILL SWITCH</button>
      </div>
      {confirm && (
        <div className="confirm-overlay">
          <div className="confirm-box">
            <p className={`confirm-msg ${confirm.danger?"confirm-danger":""}`}>Confirm: {confirm.label}?</p>
            <div className="confirm-btns">
              <button className="cbtn cbtn-yes" onClick={execute}>YES</button>
              <button className="cbtn cbtn-no"  onClick={()=>setConfirm(null)}>NO</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
'''

files['frontend/src/components/PositionsTable.jsx'] = '''export default function PositionsTable({ positions }) {
  return (
    <div className="card card-positions">
      <div className="card-label">OPEN POSITIONS <span className="count-badge">{positions.length}</span></div>
      {!positions.length ? <div className="empty-state">NO OPEN POSITIONS</div> : (
        <table className="data-table"><thead><tr>
          <th>MARKET</th><th>SIDE</th><th>ENTRY</th><th>SHARES</th><th>COST</th><th>AGE</th>
        </tr></thead><tbody>
          {positions.map((pos,i) => {
            const age = pos.age_min<60?`${pos.age_min.toFixed(0)}m`:`${(pos.age_min/60).toFixed(1)}h`;
            const old = pos.age_min>7;
            return (
              <tr key={i} className={old?"row-stale":""}>
                <td className="td-market">{pos.market_id}</td>
                <td className={`td-side ${pos.side==="YES"?"side-yes":"side-no"}`}>{pos.side}</td>
                <td className="td-mono">${pos.entry_price?.toFixed(3)}</td>
                <td className="td-mono">{pos.shares?.toFixed(2)}</td>
                <td className="td-mono">${(pos.entry_price*pos.shares).toFixed(2)}</td>
                <td className={`td-mono ${old?"age-warn":""}`}>{age}</td>
              </tr>
            );
          })}
        </tbody></table>
      )}
    </div>
  );
}
'''

files['frontend/src/components/TradesList.jsx'] = '''export default function TradesList({ trades }) {
  return (
    <div className="card card-trades">
      <div className="card-label">RECENT TRADES</div>
      {!trades.length ? <div className="empty-state">NO COMPLETED TRADES</div> : (
        <div className="trades-list">
          {[...trades].reverse().slice(0,20).map((t,i) => {
            const win = parseFloat(t.pnl_pct??0)>0;
            const ep=parseFloat(t.entry_price??0.5), sh=parseFloat(t.shares??0), xp=parseFloat(t.exit_price??0);
            const net = win ? ((1-ep)*sh*0.98).toFixed(4) : (-(ep*sh)).toFixed(4);
            const ts = t.timestamp_utc ? new Date(t.timestamp_utc).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}) : "--:--";
            return (
              <div key={i} className={`trade-row ${win?"trade-win":"trade-loss"}`}>
                <span className="trade-indicator">{win?"▲":"▼"}</span>
                <span className="trade-market">{t.market}</span>
                <span className={`trade-side ${t.side==="YES"?"side-yes":"side-no"}`}>{t.side}</span>
                <span className="trade-price">{ep.toFixed(3)}→{xp.toFixed(2)}</span>
                <span className={`trade-pnl ${win?"pnl-pos":"pnl-neg"}`}>{win?"+":""}{net}</span>
                <span className="trade-time">{ts}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
'''

files['frontend/src/components/LogStream.jsx'] = '''import { useEffect, useRef, useState } from "react";
function colorLine(l) {
  if (/CRITICAL|ERROR|FATAL|❌/.test(l)) return "log-error";
  if (/WARNING|WARN|⚠/.test(l))         return "log-warn";
  if (/✅|ARB EXECUTED|ENTRY|EXIT/.test(l)) return "log-success";
  if (/\[CLOB\]|\[RTDS\]|\[WS\]/.test(l)) return "log-system";
  if (/\[PnL\]|\[Monitor\]/.test(l))       return "log-pnl";
  return "log-default";
}
export default function LogStream({ lines }) {
  const bottomRef = useRef(null);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("");
  useEffect(() => { if (!paused && bottomRef.current) bottomRef.current.scrollIntoView({behavior:"smooth"}); }, [lines, paused]);
  const filtered = filter ? lines.filter(l=>l.toLowerCase().includes(filter.toLowerCase())) : lines;
  return (
    <div className="card card-log">
      <div className="log-header">
        <span className="card-label">LOG STREAM</span>
        <div className="log-controls">
          <input className="log-filter" placeholder="filter..." value={filter} onChange={e=>setFilter(e.target.value)}/>
          <button className={`log-pause-btn ${paused?"paused":""}`} onClick={()=>setPaused(p=>!p)}>
            {paused?"▶ RESUME":"⏸ PAUSE"}
          </button>
          <span className="log-count">{lines.length} lines</span>
        </div>
      </div>
      <div className="log-body">
        {filtered.map((l,i) => <div key={i} className={`log-line ${colorLine(l)}`}>{l}</div>)}
        <div ref={bottomRef}/>
      </div>
    </div>
  );
}
'''

# ── CSS (full) ───────────────────────────────────────────────────
files['frontend/src/index.css'] = """@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Syne:wght@400;600;800&display=swap');
:root{--bg:#080c0f;--bg-card:#0d1318;--bg-card2:#111820;--border:#1e2d3a;--border-hl:#2a4055;--text:#c8d8e4;--text-dim:#4a6070;--text-faint:#2a3a48;--green:#00e676;--green-dim:#005c2e;--red:#ff3d57;--red-dim:#5c0010;--amber:#ffab00;--amber-dim:#4a3000;--blue:#00b0ff;--blue-dim:#003040;--cyan:#00e5ff;--font-mono:'JetBrains Mono',monospace;--font-ui:'Syne',sans-serif}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}html{font-size:13px}
body{background:var(--bg);color:var(--text);font-family:var(--font-mono);-webkit-font-smoothing:antialiased;overflow-x:hidden;min-height:100vh}
body::before{content:'';position:fixed;inset:0;z-index:9999;pointer-events:none;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 4px)}
.login-screen{display:flex;align-items:center;justify-content:center;min-height:100vh;background:radial-gradient(ellipse at 50% 0%,rgba(0,230,118,.06) 0%,transparent 60%),var(--bg)}
.login-box{width:340px;padding:48px 40px;border:1px solid var(--border);background:var(--bg-card);text-align:center}
.login-logo{font-family:var(--font-ui);font-size:2rem;font-weight:800;letter-spacing:.1em;margin-bottom:4px}
.logo-bracket{color:var(--text-dim)}.logo-text{color:var(--text)}.logo-accent{color:var(--green)}
.login-sub{color:var(--text-dim);font-size:.75rem;letter-spacing:.3em;margin-bottom:36px}
.login-form{display:flex;flex-direction:column;gap:12px}
.login-input{background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:var(--font-mono);font-size:.9rem;padding:12px 16px;letter-spacing:.2em;outline:none;transition:border-color .2s}
.login-input:focus{border-color:var(--green)}
.login-btn{background:transparent;border:1px solid var(--green);color:var(--green);font-family:var(--font-mono);font-size:.8rem;font-weight:700;letter-spacing:.25em;padding:12px;cursor:pointer;transition:all .2s}
.login-btn:hover{background:var(--green);color:var(--bg)}.login-error{color:var(--red);font-size:.75rem;margin-top:12px}
.dashboard{display:flex;flex-direction:column;min-height:100vh}
.dash-header{display:flex;align-items:center;justify-content:space-between;padding:0 20px;height:48px;border-bottom:1px solid var(--border);background:var(--bg-card);flex-shrink:0}
.header-left,.header-center,.header-right{display:flex;align-items:center;gap:16px}
.header-right{font-size:.75rem}
.header-logo{font-family:var(--font-ui);font-size:1rem;font-weight:800;letter-spacing:.08em}
.badge{font-size:.65rem;font-weight:700;letter-spacing:.2em;padding:2px 8px;border:1px solid}
.badge-paper{border-color:var(--blue);color:var(--blue);background:var(--blue-dim)}
.badge-live{border-color:var(--green);color:var(--green);background:var(--green-dim)}
.badge-emergency{border-color:var(--red);color:var(--red);background:var(--red-dim)}
.badge-maintenance{border-color:var(--amber);color:var(--amber);background:var(--amber-dim)}
.blinking{animation:blink 1s step-end infinite}
@keyframes blink{50%{opacity:.3}}
.conn-indicator{font-size:.75rem;letter-spacing:.1em}.conn-on{color:var(--green)}.conn-off{color:var(--red)}
.last-update{color:var(--text-dim);font-size:.7rem}
.logout-btn{background:none;border:1px solid var(--border);color:var(--text-dim);font-family:var(--font-mono);font-size:.65rem;letter-spacing:.15em;padding:4px 10px;cursor:pointer}
.logout-btn:hover{border-color:var(--text-dim);color:var(--text)}
.dash-grid{flex:1;display:flex;flex-direction:column;padding:16px;gap:12px;overflow:auto}
.grid-row{display:flex;gap:12px}.row-top{flex-shrink:0}.row-mid{flex:1;min-height:0}.row-bot{height:240px;flex-shrink:0}
.card{background:var(--bg-card);border:1px solid var(--border);padding:16px;position:relative;overflow:hidden}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--border-hl),transparent)}
.card-label{font-size:.65rem;font-weight:700;letter-spacing:.3em;color:var(--text-dim);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.count-badge{background:var(--bg);border:1px solid var(--border);color:var(--text);font-size:.6rem;padding:1px 6px}
.card-balance{width:240px;flex-shrink:0}
.balance-main{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.balance-currency{color:var(--text-dim);font-size:.8rem}
.balance-amount{font-family:var(--font-ui);font-size:2.2rem;font-weight:800;color:var(--text);letter-spacing:-.02em}
.balance-pnl{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.pnl-value{font-size:1rem;font-weight:700}.pnl-label{font-size:.65rem;color:var(--text-dim);letter-spacing:.2em}
.pnl-pos{color:var(--green)}.pnl-neg{color:var(--red)}
.balance-stats{display:flex;align-items:center;border-top:1px solid var(--border);padding-top:12px}
.stat{flex:1;text-align:center}.stat-val{display:block;font-size:1.1rem;font-weight:600;color:var(--text)}
.stat-lbl{font-size:.6rem;color:var(--text-dim);letter-spacing:.2em}
.stat-divider{width:1px;height:32px;background:var(--border)}
.card-health{flex:1}
.health-state{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.state-indicator{font-size:1.2rem;color:var(--green)}.state-text{font-family:var(--font-ui);font-size:1rem;font-weight:600;letter-spacing:.1em}
.health-checks{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.health-row{display:flex;align-items:center;gap:8px;font-size:.75rem}
.health-dot{font-size:.6rem}.dot-on{color:var(--green)}.dot-off{color:var(--red)}
.health-label{flex:1;color:var(--text-dim);letter-spacing:.1em}
.health-status{font-size:.65rem;font-weight:700;letter-spacing:.1em}
.status-ok{color:var(--green)}.status-err{color:var(--red)}
.ks-alert{background:var(--red-dim);border:1px solid var(--red);color:var(--red);font-size:.7rem;font-weight:700;letter-spacing:.2em;padding:6px 10px;margin-bottom:10px;animation:blink 1.5s step-end infinite}
.health-metrics{display:flex;flex-direction:column;gap:4px;border-top:1px solid var(--border);padding-top:10px}
.hm-row{display:flex;justify-content:space-between;font-size:.72rem}
.hm-lbl{color:var(--text-dim)}.hm-val{color:var(--text)}.hm-warn{color:var(--amber)}
.card-control{width:220px;flex-shrink:0}
.ctrl-buttons{display:flex;flex-direction:column;gap:8px}
.ctrl-btn{width:100%;background:transparent;font-family:var(--font-mono);font-size:.68rem;font-weight:700;letter-spacing:.15em;padding:9px 12px;cursor:pointer;border:1px solid;text-align:left;transition:all .15s}
.ctrl-btn:disabled{opacity:.3;cursor:not-allowed}
.btn-danger{border-color:var(--red);color:var(--red)}.btn-danger:hover:not(:disabled){background:var(--red);color:var(--bg)}
.btn-cancel{border-color:var(--green);color:var(--green)}.btn-cancel:hover{background:var(--green);color:var(--bg)}
.btn-warn{border-color:var(--amber);color:var(--amber)}.btn-warn:hover{background:var(--amber);color:var(--bg)}
.btn-ok{border-color:var(--green);color:var(--green)}.btn-ok:hover{background:var(--green);color:var(--bg)}
.btn-neutral{border-color:var(--border-hl);color:var(--text-dim)}.btn-neutral:hover:not(:disabled){border-color:var(--text);color:var(--text)}
.confirm-overlay{position:absolute;inset:0;z-index:10;background:rgba(8,12,15,.92);display:flex;align-items:center;justify-content:center}
.confirm-box{background:var(--bg-card2);border:1px solid var(--border-hl);padding:20px;text-align:center;min-width:160px}
.confirm-msg{font-size:.75rem;margin-bottom:16px;color:var(--text)}.confirm-danger{color:var(--red)}
.confirm-btns{display:flex;gap:8px;justify-content:center}
.cbtn{font-family:var(--font-mono);font-size:.72rem;font-weight:700;letter-spacing:.15em;padding:6px 20px;cursor:pointer;border:1px solid;background:transparent;transition:all .15s}
.cbtn-yes{border-color:var(--red);color:var(--red)}.cbtn-yes:hover{background:var(--red);color:var(--bg)}
.cbtn-no{border-color:var(--border-hl);color:var(--text-dim)}.cbtn-no:hover{border-color:var(--text);color:var(--text)}
.card-positions{flex:1;overflow:auto;min-width:0}.card-trades{flex:1;overflow:auto;min-width:0}
.empty-state{color:var(--text-faint);font-size:.75rem;letter-spacing:.2em;padding:24px;text-align:center}
.data-table{width:100%;border-collapse:collapse;font-size:.75rem}
.data-table th{text-align:left;font-size:.6rem;letter-spacing:.2em;color:var(--text-dim);padding:4px 8px;border-bottom:1px solid var(--border);font-weight:500}
.data-table td{padding:6px 8px;border-bottom:1px solid var(--text-faint)}
.data-table tr:last-child td{border-bottom:none}
.data-table tr:hover td{background:rgba(255,255,255,.02)}
.td-market{font-weight:600;color:var(--text)}.td-side{font-weight:700;letter-spacing:.1em}.td-mono{font-family:var(--font-mono);color:var(--text)}
.side-yes{color:var(--green)}.side-no{color:var(--red)}.row-stale td{opacity:.6}.age-warn{color:var(--amber)}
.trades-list{display:flex;flex-direction:column;gap:3px}
.trade-row{display:flex;align-items:center;gap:8px;font-size:.72rem;padding:5px 8px;border-left:2px solid transparent;transition:background .1s}
.trade-win{border-left-color:var(--green)}.trade-loss{border-left-color:var(--red)}
.trade-row:hover{background:rgba(255,255,255,.02)}
.trade-indicator{font-size:.6rem;width:12px;flex-shrink:0}
.trade-win .trade-indicator{color:var(--green)}.trade-loss .trade-indicator{color:var(--red)}
.trade-market{font-weight:600;min-width:60px}.trade-side{font-weight:700;min-width:30px}
.trade-price{color:var(--text-dim);flex:1;font-size:.68rem}
.trade-pnl{font-weight:700;min-width:72px;text-align:right}
.trade-time{color:var(--text-dim);font-size:.65rem;min-width:50px;text-align:right}
.card-log{display:flex;flex-direction:column;overflow:hidden}
.log-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-shrink:0}
.log-controls{display:flex;align-items:center;gap:8px}
.log-filter{background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:var(--font-mono);font-size:.68rem;padding:3px 8px;width:140px;outline:none}
.log-filter:focus{border-color:var(--blue)}
.log-pause-btn{background:none;border:1px solid var(--border);color:var(--text-dim);font-family:var(--font-mono);font-size:.62rem;letter-spacing:.1em;padding:3px 8px;cursor:pointer}
.log-pause-btn.paused{border-color:var(--amber);color:var(--amber)}.log-count{color:var(--text-faint);font-size:.65rem}
.log-body{flex:1;overflow-y:auto;overflow-x:hidden;font-size:.68rem;line-height:1.6;padding:4px 0}
.log-body::-webkit-scrollbar{width:4px}.log-body::-webkit-scrollbar-track{background:var(--bg)}.log-body::-webkit-scrollbar-thumb{background:var(--border-hl)}
.log-line{padding:0 4px;white-space:pre-wrap;word-break:break-all}
.log-error{color:var(--red)}.log-warn{color:var(--amber)}.log-success{color:var(--green)}
.log-system{color:var(--blue)}.log-pnl{color:var(--cyan)}.log-default{color:var(--text-dim)}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border-hl)}
@media(max-width:900px){.row-top,.row-mid{flex-direction:column}.card-balance,.card-control{width:100%}}
"""

# ── install.sh ───────────────────────────────────────────────────
files['install.sh'] = r'''#!/bin/bash
set -e
DEST="/opt/bot-dashboard"
BOT_WORKSPACE="${BOT_WORKSPACE:-/root/.openclaw/workspace}"
echo "=== PolyARB Dashboard Install ==="
[ "$EUID" -ne 0 ] && echo "Run as root" && exit 1
apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv curl wget 2>/dev/null
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null
  apt-get install -y -qq nodejs
fi
echo "Node $(node -v)"
[ -z "$DASHBOARD_PASSWORD" ] && DASHBOARD_PASSWORD=$(openssl rand -hex 12) && echo "Password: $DASHBOARD_PASSWORD"
cd "$DEST/backend"
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
echo "Python deps OK"
cd "$DEST/frontend" && npm install --silent && npm run build
echo "Frontend built"
cat > /etc/systemd/system/bot-dashboard.service << EOF
[Unit]
Description=PolyARB Dashboard
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=$DEST/backend
Environment=DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD
Environment=BOT_WORKSPACE=$BOT_WORKSPACE
Environment=PYTHONUNBUFFERED=1
ExecStart=$DEST/backend/.venv/bin/python main.py
Restart=always
RestartSec=5
Nice=19
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable bot-dashboard && systemctl restart bot-dashboard
sleep 2 && systemctl is-active --quiet bot-dashboard && echo "Service running on :8080" || echo "Check: journalctl -u bot-dashboard -n 20"
if ! command -v cloudflared &>/dev/null; then
  ARCH=$(dpkg --print-architecture)
  wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
  dpkg -i "cloudflared-linux-${ARCH}.deb" 2>/dev/null && rm -f "cloudflared-linux-${ARCH}.deb"
fi
nohup cloudflared tunnel --url http://localhost:8080 > /tmp/cloudflared.log 2>&1 &
sleep 4
URL=$(grep -o 'https://[^ ]*trycloudflare.com' /tmp/cloudflared.log 2>/dev/null | head -1)
echo ""
echo "Local:    http://localhost:8080"
echo "Password: $DASHBOARD_PASSWORD"
[ -n "$URL" ] && echo "Public:   $URL"
'''

# ── Write all files ───────────────────────────────────────────────
for rel, content in files.items():
    path = DEST / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip('\n'))
    print(f"  wrote {rel}")

# Make install.sh executable
(DEST / 'install.sh').chmod(0o755)

print(f"\n✅ All files written to {DEST}")
print("\nNext steps:")
print(f"  cd {DEST}")
print(f"  bash install.sh")
print()
print("Or to set a custom password first:")
print(f"  export DASHBOARD_PASSWORD=yourpassword && bash {DEST}/install.sh")
