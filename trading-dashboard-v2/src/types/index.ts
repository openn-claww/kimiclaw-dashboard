/**
 * Trading Dashboard - TypeScript Types
 * Agency Agent Pattern: Frontend Developer
 */

// ── Bot Status Types ─────────────────────────────────────────────────────────

export interface BotStatus {
  running: boolean;
  mode: 'paper' | 'live';
  balance: number;
  trade_count: number;
  open_positions: number;
  uptime: string | null;
  last_update: string | null;
}

export interface KillSwitch {
  active: boolean;
  daily_loss_usd: number;
  daily_loss_pct: number;
  consec: number;
}

export interface CircuitBreaker {
  tripped: boolean;
  win_rate: number | null;
  sample: number;
  total: number;
  warmup: boolean;
}

// ── P&L Types ────────────────────────────────────────────────────────────────

export interface TradeStats {
  trades: number;
  wins: number;
  net_pnl: number;
  win_rate: number;
}

export interface CoinPerformance {
  trades: number;
  wins: number;
  net_pnl: number;
  win_rate: number;
}

export interface StrategyPerformance {
  trades: number;
  wins: number;
  net_pnl: number;
}

export interface PnLMetrics {
  total_trades: number;
  open_trades: number;
  open_exposure: number;
  wins: number;
  losses: number;
  win_rate: number;
  win_rate_last50: number;
  net_pnl: number;
  gross_pnl: number;
  fees_paid: number;
  avg_hold_secs: number;
  best_trade: { id: string; net_pnl: number };
  worst_trade: { id: string; net_pnl: number };
  by_coin: Record<string, CoinPerformance>;
  by_strategy: Record<string, StrategyPerformance>;
  last_updated: string;
}

// ── Trade Types ──────────────────────────────────────────────────────────────

export type TradeType = 'ARB_CROSS_MARKET' | 'EXIT' | 'ENTRY' | 'MANUAL';
export type TradeSide = 'YES' | 'NO' | null;
export type ExitReason = 'resolved' | 'stop_loss' | 'take_profit' | 'manual' | null;

export interface Trade {
  type: TradeType;
  market: string;
  timestamp: string;
  side: TradeSide;
  amount: number | null;
  size: number | null;
  entry_price: number | null;
  exit_price: number | null;
  pnl_pct: number | null;
  exit_reason: ExitReason;
  virtual_balance?: number;
}

// ── Position Types ───────────────────────────────────────────────────────────

export interface Position {
  market: string;
  side: TradeSide;
  size: number;
  entry_price: number;
  current_price?: number;
  pnl?: number;
  timestamp?: string;
}

// ── Alert Types ───────────────────────────────────────────────────────────────

export type AlertLevel = 'info' | 'warning' | 'error' | 'critical' | 'success';

export interface Alert {
  ts: string;
  level: AlertLevel;
  message: string;
  title?: string;
}

// ── Health Types ──────────────────────────────────────────────────────────────

export interface HealthMetrics {
  timestamp_utc: string;
  bot_state: string;
  balance: number;
  trade_count: number;
  open_positions: number;
  clob_connected: boolean;
  rtds_connected: boolean;
  price_feed: string;
  emergency_stop: boolean;
  kill_switch: KillSwitch;
  circuit_breaker: CircuitBreaker;
  paper_mode: boolean;
  zone_filter: boolean;
  proxy: string | null;
  sell_queue: string | null;
  auto_redeem: {
    total: number;
    by_status: Record<string, number>;
    poll_interval: number;
    running: boolean;
  };
  arb_engine: {
    open_positions: number;
    closed_trades: number;
    circuit_breaker: CircuitBreaker;
  };
  news_feed: {
    sentiment: string;
    confidence: number;
    source: string;
    keywords: string[];
    headlines: string[];
  };
  pnl_tracker: PnLMetrics;
}

// ── Strategy Types ───────────────────────────────────────────────────────────

export interface Strategy {
  id: string;
  name: string;
  description: string;
  active: boolean;
  trades: number;
  winRate: number;
  pnl: number;
  color: string;
}

// ── Chart Types ───────────────────────────────────────────────────────────────

export interface ChartDataset {
  label: string;
  data: number[];
  borderColor: string;
  backgroundColor: string;
  fill?: boolean;
  tension?: number;
}

export interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

// ── Component Props Types ─────────────────────────────────────────────────────

export interface StatCardProps {
  label: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: string;
  iconColor: string;
  ariaLabel: string;
}

export interface ButtonProps {
  variant: 'primary' | 'secondary' | 'success' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  children: HTMLElement | string;
  ariaLabel: string;
}

export interface TableColumn<T> {
  key: keyof T | string;
  header: string;
  width?: string;
  render?: (row: T) => HTMLElement | string;
}

// ── WebSocket Types ───────────────────────────────────────────────────────────

export interface WebSocketMessage {
  type: 'status_update' | 'initial' | 'ping' | 'error';
  data?: {
    status?: BotStatus;
    pnl?: PnLMetrics;
  };
  timestamp?: string;
}

// ── API Response Types ────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export type StatusResponse = BotStatus;
export type PnLResponse = PnLMetrics;
export type TradesResponse = { trades: Trade[] };
export type PositionsResponse = { positions: Record<string, Position> };
export type AlertsResponse = { alerts: Alert[] };
export type LogsResponse = { logs: string[] };
export type HealthResponse = HealthMetrics;
