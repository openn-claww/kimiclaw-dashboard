/**
 * PolyClaw Trading Dashboard - Main Application
 * Agency Agent Pattern: Frontend Developer
 * 
 * Architecture:
 * - Component-based design with clear separation
 * - WebSocket for real-time updates
 * - TypeScript for type safety
 * - Performance optimized with requestAnimationFrame
 */

import type {
  BotStatus,
  PnLMetrics,
  Trade,
  Alert,
  Strategy,
  WebSocketMessage,
  StatCardProps,
  TableColumn
} from './types/index.js';

// ── Configuration ─────────────────────────────────────────────────────────────
const CONFIG = {
  WS_URL: `wss://${window.location.host}/ws`,
  API_BASE: '',
  REFRESH_INTERVAL: 10000,
  WS_RECONNECT_DELAY: 3000,
  MAX_RECONNECT_ATTEMPTS: 10
} as const;

// ── State Management ──────────────────────────────────────────────────────────
interface AppState {
  botStatus: BotStatus | null;
  pnlMetrics: PnLMetrics | null;
  currentPage: string;
  wsConnected: boolean;
  reconnectAttempts: number;
}

const state: AppState = {
  botStatus: null,
  pnlMetrics: null,
  currentPage: 'dashboard',
  wsConnected: false,
  reconnectAttempts: 0
};

// ── WebSocket Manager ─────────────────────────────────────────────────────────
class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private listeners: Map<string, Set<(data: unknown) => void>> = new Map();

  connect(): void {
    try {
      this.ws = new WebSocket(CONFIG.WS_URL);
      
      this.ws.onopen = () => {
        console.log('[WebSocket] Connected');
        state.wsConnected = true;
        state.reconnectAttempts = 0;
        this.updateConnectionStatus(true);
        this.emit('connection', { connected: true });
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('[WebSocket] Parse error:', error);
        }
      };

      this.ws.onclose = () => {
        console.log('[WebSocket] Disconnected');
        state.wsConnected = false;
        this.updateConnectionStatus(false);
        this.emit('connection', { connected: false });
        this.scheduleReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };
    } catch (error) {
      console.error('[WebSocket] Connection error:', error);
      this.scheduleReconnect();
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    switch (message.type) {
      case 'status_update':
      case 'initial':
        if (message.data?.status) {
          state.botStatus = message.data.status;
          this.emit('status', message.data.status);
        }
        if (message.data?.pnl) {
          state.pnlMetrics = message.data.pnl;
          this.emit('pnl', message.data.pnl);
        }
        break;
      case 'ping':
        // Keep-alive, no action needed
        break;
      case 'error':
        console.error('[WebSocket] Server error:', message);
        break;
    }
  }

  private scheduleReconnect(): void {
    if (state.reconnectAttempts >= CONFIG.MAX_RECONNECT_ATTEMPTS) {
      console.warn('[WebSocket] Max reconnection attempts reached');
      return;
    }

    state.reconnectAttempts++;
    const delay = Math.min(CONFIG.WS_RECONNECT_DELAY * Math.pow(2, state.reconnectAttempts), 30000);
    
    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${state.reconnectAttempts})`);
    
    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  private updateConnectionStatus(connected: boolean): void {
    const dot = document.getElementById('ws-status');
    const text = document.getElementById('ws-text');
    
    if (dot && text) {
      if (connected) {
        dot.classList.remove('connection-status__dot--disconnected');
        text.textContent = 'Connected';
      } else {
        dot.classList.add('connection-status__dot--disconnected');
        text.textContent = 'Disconnected';
      }
    }
  }

  on(event: string, callback: (data: unknown) => void): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
    
    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }

  private emit(event: string, data: unknown): void {
    this.listeners.get(event)?.forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`[WebSocket] Error in ${event} listener:`, error);
      }
    });
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.ws?.close();
  }
}

const wsManager = new WebSocketManager();

// ── API Client ────────────────────────────────────────────────────────────────
class ApiClient {
  private async fetch<T>(endpoint: string): Promise<T | null> {
    try {
      const response = await fetch(`${CONFIG.API_BASE}${endpoint}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json() as T;
    } catch (error) {
      console.error(`[API] Error fetching ${endpoint}:`, error);
      return null;
    }
  }

  async getStatus(): Promise<BotStatus | null> {
    return this.fetch<BotStatus>('/api/status');
  }

  async getPnL(): Promise<PnLMetrics | null> {
    return this.fetch<PnLMetrics>('/api/pnl');
  }

  async getTrades(limit = 50): Promise<Trade[]> {
    const result = await this.fetch<{ trades: Trade[] }>(`/api/trades?limit=${limit}`);
    return result?.trades || [];
  }

  async getAlerts(limit = 20): Promise<Alert[]> {
    const result = await this.fetch<{ alerts: Alert[] }>(`/api/alerts?limit=${limit}`);
    return result?.alerts || [];
  }

  async getLogs(lines = 100): Promise<string[]> {
    const result = await this.fetch<{ logs: string[] }>(`/api/logs?lines=${lines}`);
    return result?.logs || [];
  }

  async startBot(mode: 'paper' | 'live' = 'paper'): Promise<boolean> {
    try {
      const response = await fetch(`/api/bot/start?mode=${mode}`, { method: 'POST' });
      return response.ok;
    } catch (error) {
      console.error('[API] Error starting bot:', error);
      return false;
    }
  }

  async stopBot(): Promise<boolean> {
    try {
      const response = await fetch('/api/bot/stop', { method: 'POST' });
      return response.ok;
    } catch (error) {
      console.error('[API] Error stopping bot:', error);
      return false;
    }
  }
}

const api = new ApiClient();

// ── UI Components ─────────────────────────────────────────────────────────────

class StatCardComponent {
  static render(props: StatCardProps): string {
    const changeClass = props.changeType ? `stat-card__change--${props.changeType}` : 'stat-card__change--neutral';
    
    return `
      <div class="stat-card" role="region" aria-label="${props.ariaLabel}">
        <div class="stat-card__header">
          <span class="stat-card__label">${props.label}</span>
          <div class="stat-card__icon stat-card__icon--${props.iconColor}" aria-hidden="true">
            <i class="fas ${props.icon}"></i>
          </div>
        </div>
        <div class="stat-card__value">${props.value}</div>
        <div class="stat-card__change ${changeClass}">
          <i class="fas fa-${props.changeType === 'positive' ? 'arrow-up' : props.changeType === 'negative' ? 'arrow-down' : 'minus'}"></i>
          <span>${props.change || 'No change'}</span>
        </div>
      </div>
    `;
  }
}

class TableComponent<T extends Record<string, unknown>> {
  static render<T extends Record<string, unknown>>(
    columns: TableColumn<T>[],
    data: T[],
    emptyMessage = 'No data available'
  ): string {
    if (data.length === 0) {
      return `
        <div class="empty-state" role="status">
          <div class="empty-state__icon" aria-hidden="true">
            <i class="fas fa-inbox"></i>
          </div>
          <h3 class="empty-state__title">${emptyMessage}</h3>
        </div>
      `;
    }

    const headers = columns.map(col => 
      `<th class="table__th" scope="col">${col.header}</th>`
    ).join('');

    const rows = data.map(row => {
      const cells = columns.map(col => {
        const value = col.render 
          ? col.render(row)
          : String(row[col.key as keyof T] ?? '-');
        return `<td class="table__td">${value}</td>`;
      }).join('');
      return `<tr class="table__row">${cells}</tr>`;
    }).join('');

    return `
      <div class="table-container" role="region" aria-label="Data table">
        <table class="table">
          <thead class="table__head">
            <tr>${headers}</tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }
}

// ── Chart Manager ─────────────────────────────────────────────────────────────
class ChartManager {
  private charts: Map<string, Chart> = new Map();

  initPnLChart(canvasId: string): void {
    const canvas = document.getElementById(canvasId) as HTMLCanvasElement;
    if (!canvas) return;

    // Using Chart.js from CDN
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // @ts-expect-error Chart is loaded from CDN
    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        datasets: [{
          label: 'P&L',
          data: [0, -5, -10, -20, -25, -30, -32.64],
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          intersect: false,
          mode: 'index'
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#16161f',
            titleColor: '#ffffff',
            bodyColor: '#a1a1aa',
            borderColor: '#2a2a3a',
            borderWidth: 1,
            padding: 12,
            displayColors: false
          }
        },
        scales: {
          y: {
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { 
              color: '#71717a',
              callback: (value: number) => `$${value}`
            }
          },
          x: {
            grid: { display: false },
            ticks: { color: '#71717a' }
          }
        }
      }
    });

    this.charts.set(canvasId, chart);
  }

  initStrategyChart(canvasId: string, strategies: Strategy[]): void {
    const canvas = document.getElementById(canvasId) as HTMLCanvasElement;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // @ts-expect-error Chart is loaded from CDN
    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: strategies.map(s => s.name),
        datasets: [{
          label: 'P&L (USDC)',
          data: strategies.map(s => s.pnl),
          backgroundColor: strategies.map(s => s.pnl >= 0 ? '#10b981' : '#ef4444'),
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { 
              color: '#71717a',
              callback: (value: number) => `$${value}`
            }
          },
          x: {
            grid: { display: false },
            ticks: { color: '#a1a1aa' }
          }
        }
      }
    });

    this.charts.set(canvasId, chart);
  }

  destroy(canvasId: string): void {
    const chart = this.charts.get(canvasId);
    if (chart) {
      chart.destroy();
      this.charts.delete(canvasId);
    }
  }
}

const chartManager = new ChartManager();

// ── Page Controllers ──────────────────────────────────────────────────────────

class DashboardPage {
  static async render(): Promise<void> {
    const container = document.getElementById('page-dashboard');
    if (!container) return;

    // Update stat cards
    this.updateStatCards();

    // Initialize charts
    requestAnimationFrame(() => {
      chartManager.initPnLChart('pnl-chart');
    });

    // Load recent trades
    await this.loadRecentTrades();

    // Load alerts
    await this.loadAlerts();
  }

  static updateStatCards(): void {
    const statsGrid = document.getElementById('stats-grid');
    if (!statsGrid) return;

    const status = state.botStatus;
    const pnl = state.pnlMetrics;

    const pnlValue = pnl?.net_pnl ?? 0;
    const pnlFormatted = pnlValue >= 0 
      ? `+$${pnlValue.toFixed(2)}` 
      : `-$${Math.abs(pnlValue).toFixed(2)}`;

    const cards: StatCardProps[] = [
      {
        label: 'Total Balance',
        value: `$${(status?.balance ?? 0).toFixed(2)}`,
        change: 'Available USDC',
        changeType: 'neutral',
        icon: 'fa-wallet',
        iconColor: 'primary',
        ariaLabel: 'Account balance statistics'
      },
      {
        label: 'Net P&L',
        value: pnlFormatted,
        change: 'All time',
        changeType: pnlValue >= 0 ? 'positive' : 'negative',
        icon: 'fa-chart-line',
        iconColor: pnlValue >= 0 ? 'success' : 'danger',
        ariaLabel: 'Profit and loss statistics'
      },
      {
        label: 'Win Rate',
        value: `${((pnl?.win_rate ?? 0) * 100).toFixed(1)}%`,
        change: `${pnl?.total_trades ?? 0} trades`,
        changeType: 'neutral',
        icon: 'fa-trophy',
        iconColor: 'warning',
        ariaLabel: 'Win rate statistics'
      },
      {
        label: 'Open Positions',
        value: String(status?.open_positions ?? 0),
        change: 'Active trades',
        changeType: 'neutral',
        icon: 'fa-folder-open',
        iconColor: 'purple',
        ariaLabel: 'Open positions count'
      }
    ];

    statsGrid.innerHTML = cards.map(card => StatCardComponent.render(card)).join('');
  }

  static async loadRecentTrades(): Promise<void> {
    const tbody = document.getElementById('recent-trades');
    if (!tbody) return;

    const trades = await api.getTrades(10);
    
    if (trades.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="empty-state">
            <i class="fas fa-inbox empty-state__icon"></i>
            <h3 class="empty-state__title">No trades yet</h3>
            <p class="empty-state__message">Trades will appear here when the bot starts</p>
          </td>
        </tr>
      `;
      return;
    }

    const columns: TableColumn<Trade>[] = [
      { key: 'timestamp', header: 'Time', render: (row) => {
        const date = new Date(row.timestamp);
        return date.toLocaleTimeString();
      }},
      { key: 'market', header: 'Market' },
      { key: 'type', header: 'Type', render: (row) => 
        `<span class="tag tag--info">${row.type}</span>`
      },
      { key: 'side', header: 'Side' },
      { key: 'amount', header: 'Amount', render: (row) => 
        row.amount ? `$${row.amount.toFixed(2)}` : '-'
      },
      { key: 'entry_price', header: 'Price', render: (row) => 
        row.entry_price ? row.entry_price.toFixed(3) : '-'
      },
      { key: 'pnl_pct', header: 'P&L', render: (row) => {
        if (row.pnl_pct == null) return '-';
        const icon = row.pnl_pct > 0 ? 'fa-arrow-up' : row.pnl_pct < 0 ? 'fa-arrow-down' : 'fa-minus';
        const colorClass = row.pnl_pct > 0 ? 'text--success' : row.pnl_pct < 0 ? 'text--danger' : 'text--secondary';
        return `<span class="${colorClass}"><i class="fas ${icon}"></i> ${row.pnl_pct.toFixed(2)}%</span>`;
      }},
      { key: 'exit_reason', header: 'Status', render: (row) => 
        `<span class="tag ${row.exit_reason ? 'tag--success' : 'tag--warning'}">${row.exit_reason || 'Open'}</span>`
      }
    ];

    tbody.innerHTML = TableComponent.render(columns, trades.reverse());
  }

  static async loadAlerts(): Promise<void> {
    const container = document.getElementById('alert-list');
    if (!container) return;

    const alerts = await api.getAlerts(5);
    
    if (alerts.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-bell-slash empty-state__icon"></i>
          <h3 class="empty-state__title">No alerts</h3>
          <p class="empty-state__message">Alerts will appear here when the bot is running</p>
        </div>
      `;
      return;
    }

    container.innerHTML = alerts.map(alert => {
      const level = alert.level === 'CRITICAL' ? 'error' : 
                    alert.level === 'WARNING' ? 'warning' : 'info';
      const icon = level === 'error' ? 'fa-exclamation-circle' : 
                   level === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
      
      return `
        <div class="alert alert--${level}" role="alert">
          <div class="alert__icon" style="background: rgba(var(--color-${level}-500), 0.1); color: var(--color-${level}-500);">
            <i class="fas ${icon}"></i>
          </div>
          <div class="alert__content">
            <div class="alert__title">${alert.level}</div>
            <div class="alert__message">${alert.message}</div>
            <div class="alert__time">${new Date(alert.ts).toLocaleTimeString()}</div>
          </div>
        </div>
      `;
    }).join('');
  }
}

// ── Navigation Controller ─────────────────────────────────────────────────────
class NavigationController {
  private static readonly pageTitles: Record<string, string> = {
    dashboard: 'Dashboard',
    trading: 'Trading Control',
    strategies: 'Strategies',
    markets: 'Market Analysis',
    logs: 'Logs',
    settings: 'Settings'
  };

  static init(): void {
    // Nav item click handlers
    document.querySelectorAll('.nav__item').forEach(item => {
      item.addEventListener('click', (e) => {
        const page = (e.currentTarget as HTMLElement).dataset.page;
        if (page) this.navigateTo(page);
      });
    });

    // Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    mobileMenuBtn?.addEventListener('click', () => {
      sidebar?.classList.toggle('sidebar--open');
      overlay?.classList.toggle('overlay--visible');
    });

    overlay?.addEventListener('click', () => {
      sidebar?.classList.remove('sidebar--open');
      overlay?.classList.remove('overlay--visible');
    });
  }

  static navigateTo(page: string): void {
    // Update nav items
    document.querySelectorAll('.nav__item').forEach(item => {
      item.classList.remove('nav__item--active');
      if ((item as HTMLElement).dataset.page === page) {
        item.classList.add('nav__item--active');
      }
    });

    // Update page visibility
    document.querySelectorAll('.page').forEach(p => p.classList.remove('page--active'));
    document.getElementById(`page-${page}`)?.classList.add('page--active');

    // Update page title
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = this.pageTitles[page] || 'Dashboard';

    // Page-specific initialization
    if (page === 'dashboard') {
      DashboardPage.render();
    }

    state.currentPage = page;

    // Close mobile menu
    document.getElementById('sidebar')?.classList.remove('sidebar--open');
    document.getElementById('overlay')?.classList.remove('overlay--visible');
  }
}

// ── Bot Control Controller ────────────────────────────────────────────────────
class BotControlController {
  static init(): void {
    const startBtn = document.getElementById('btn-start');
    const stopBtn = document.getElementById('btn-stop');
    const modeToggle = document.getElementById('mode-toggle') as HTMLInputElement;

    startBtn?.addEventListener('click', async () => {
      const mode = modeToggle?.checked ? 'live' : 'paper';
      startBtn.setAttribute('disabled', 'true');
      startBtn.classList.add('btn--loading');
      
      const success = await api.startBot(mode);
      
      startBtn.removeAttribute('disabled');
      startBtn.classList.remove('btn--loading');
      
      if (success) {
        this.logActivity(`Bot started in ${mode} mode`);
      } else {
        alert('Failed to start bot');
      }
    });

    stopBtn?.addEventListener('click', async () => {
      stopBtn.setAttribute('disabled', 'true');
      
      const success = await api.stopBot();
      
      stopBtn.removeAttribute('disabled');
      
      if (success) {
        this.logActivity('Bot stopped');
      } else {
        alert('Failed to stop bot');
      }
    });

    modeToggle?.addEventListener('change', () => {
      const label = document.getElementById('mode-label');
      if (label) {
        if (modeToggle.checked) {
          label.textContent = 'Live Trading';
          label.classList.add('text--danger');
        } else {
          label.textContent = 'Paper Trading';
          label.classList.remove('text--danger');
        }
      }
    });
  }

  private static logActivity(message: string): void {
    const log = document.getElementById('activity-log');
    if (!log) return;

    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.innerHTML = `<span class="text--muted">[${time}]</span> ${message}`;
    log.insertBefore(entry, log.firstChild);
  }
}

// ── UI Update Controller ──────────────────────────────────────────────────────
class UIUpdateController {
  static init(): void {
    // Listen for WebSocket updates
    wsManager.on('status', () => this.updateBotStatus());
    wsManager.on('pnl', () => DashboardPage.updateStatCards());

    // Initial update
    this.updateBotStatus();

    // Periodic refresh fallback
    setInterval(() => {
      this.refreshData();
    }, CONFIG.REFRESH_INTERVAL);
  }

  static updateBotStatus(): void {
    const status = state.botStatus;
    if (!status) return;

    // Update badge
    const badge = document.getElementById('bot-status-badge');
    const badgeText = document.getElementById('bot-status-text');
    
    if (badge && badgeText) {
      badge.classList.remove('status-badge--running', 'status-badge--stopped');
      badge.classList.add(status.running ? 'status-badge--running' : 'status-badge--stopped');
      badgeText.textContent = status.running ? 'Running' : 'Stopped';
    }

    // Update mode badge
    const modeBadge = document.getElementById('mode-badge');
    if (modeBadge) {
      modeBadge.classList.remove('mode-badge--paper', 'mode-badge--live');
      modeBadge.classList.add(status.mode === 'live' ? 'mode-badge--live' : 'mode-badge--paper');
      modeBadge.textContent = status.mode === 'live' ? 'Live Trading' : 'Paper Trading';
    }

    // Update buttons
    const startBtn = document.getElementById('btn-start') as HTMLButtonElement;
    const stopBtn = document.getElementById('btn-stop') as HTMLButtonElement;
    
    if (startBtn) startBtn.disabled = status.running;
    if (stopBtn) stopBtn.disabled = !status.running;
  }

  static async refreshData(): Promise<void> {
    const status = await api.getStatus();
    const pnl = await api.getPnL();
    
    if (status) state.botStatus = status;
    if (pnl) state.pnlMetrics = pnl;

    if (state.currentPage === 'dashboard') {
      DashboardPage.updateStatCards();
    }
  }
}

// ── Application Initialization ────────────────────────────────────────────────
function initApp(): void {
  console.log('[App] Initializing PolyClaw Trading Dashboard v2.0');

  // Initialize navigation
  NavigationController.init();

  // Initialize bot controls
  BotControlController.init();

  // Initialize UI updates
  UIUpdateController.init();

  // Connect WebSocket
  wsManager.connect();

  // Load initial page
  NavigationController.navigateTo('dashboard');

  console.log('[App] Initialization complete');
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  wsManager.disconnect();
});
