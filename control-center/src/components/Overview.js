import React, { useState, useEffect, createContext, useContext } from 'react';
import { 
  LayoutDashboard, 
  Wallet, 
  TrendingUp, 
  Calendar,
  Plus,
  Trash2,
  Edit3,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  BarChart3,
  PieChart,
  Activity,
  Settings,
  Bell,
  Search,
  Filter,
  ArrowUpRight,
  ArrowDownRight,
  MoreVertical,
  Play,
  Pause,
  RefreshCw,
  Terminal,
  Bot,
  Zap,
  Shield,
  Globe,
  Database,
  GitBranch,
  MessageSquare,
  Server,
  Cpu
} from 'lucide-react';
import { format, parseISO, isAfter, isBefore } from 'date-fns';
import { 
  LineChart, Line, AreaChart, Area, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
  BarChart, Bar, Legend
} from 'recharts';
import { v4 as uuidv4 } from 'uuid';

// Context for global state
const AppContext = createContext();

// Mock data - will be replaced with real data
const initialTrades = [
  {
    id: '1',
    timestamp: '2026-02-19T10:04:41',
    market: 'Will Jesus Christ return before 2027?',
    marketId: '703258',
    side: 'NO',
    size: 2.0,
    entry: 0.97,
    current: 0.97,
    pnl: -0.06,
    status: 'OPEN',
    txHash: '7f55f8a140da6033fc46d86aca0bfdff7a7326bc9401151baf0ecc78e7b41a2c',
    strategy: 'Conservative NO',
    confidence: 9,
    type: 'long-term'
  },
  {
    id: '2',
    timestamp: '2026-02-19T12:18:27',
    market: 'US strikes Iran by February 20, 2026?',
    marketId: '1320793',
    side: 'NO',
    size: 1.0,
    entry: 0.93,
    current: 0.93,
    pnl: 0,
    status: 'OPEN',
    txHash: '077b29241c9236cb313111303d85dd213a4df0650ddfa761fedd22bbd7fb4f34',
    strategy: 'Short-term NO',
    confidence: 8,
    type: 'short-term'
  }
];

const initialTasks = [
  {
    id: '1',
    name: 'Short-term Trading Heartbeat',
    description: 'Scan for 15-min BTC/ETH markets',
    schedule: 'Every 10 minutes',
    cronExpression: '*/10 * * * *',
    lastRun: '2026-02-19T21:30:00',
    nextRun: '2026-02-19T21:40:00',
    status: 'active',
    priority: 'high',
    category: 'trading',
    enabled: true
  },
  {
    id: '2',
    name: 'Trading Analysis Report',
    description: 'Generate 2-day performance report',
    schedule: 'Every 2 days',
    cronExpression: '0 0 */2 * *',
    lastRun: '2026-02-19T12:00:00',
    nextRun: '2026-02-21T12:00:00',
    status: 'active',
    priority: 'medium',
    category: 'reporting',
    enabled: true
  },
  {
    id: '3',
    name: 'Social Media Monitor',
    description: 'Scan Twitter/Reddit for strategies',
    schedule: 'Every 6 hours',
    cronExpression: '0 */6 * * *',
    lastRun: '2026-02-19T18:00:00',
    nextRun: '2026-02-20T00:00:00',
    status: 'active',
    priority: 'low',
    category: 'research',
    enabled: true
  }
];

const initialWallet = {
  address: '0x557A...a274',
  usdc: 7.93,
  pol: 8.72,
  totalValue: 16.65,
  change24h: -0.36,
  changePercent: -2.12
};

const pnlHistory = [
  { time: '10:00', pnl: 0, value: 16.71 },
  { time: '11:00', pnl: -0.03, value: 16.68 },
  { time: '12:00', pnl: -0.06, value: 16.65 },
  { time: '13:00', pnl: -0.06, value: 16.65 },
  { time: '14:00', pnl: -0.06, value: 16.65 },
  { time: '15:00', pnl: -0.06, value: 16.65 },
  { time: '16:00', pnl: -0.06, value: 16.65 },
  { time: '17:00', pnl: -0.06, value: 16.65 },
  { time: '18:00', pnl: -0.06, value: 16.65 },
  { time: '19:00', pnl: -0.06, value: 16.65 },
  { time: '20:00', pnl: -0.06, value: 16.65 },
  { time: '21:00', pnl: -0.06, value: 16.65 },
];

// Components
const Card = ({ children, className = '' }) => (
  <div className={`bg-card border border-border rounded-xl ${className}`}>
    {children}
  </div>
);

const Badge = ({ children, type = 'default' }) => {
  const styles = {
    default: 'bg-border text-gray-300',
    success: 'bg-success-dim text-success',
    danger: 'bg-danger-dim text-danger',
    warning: 'bg-warning-dim text-warning',
    accent: 'bg-accent/10 text-accent',
    info: 'bg-info/10 text-info'
  };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[type]}`}>
      {children}
    </span>
  );
};

const Button = ({ children, onClick, variant = 'primary', size = 'md', icon: Icon }) => {
  const variants = {
    primary: 'bg-accent text-dark hover:bg-accent-hover',
    secondary: 'bg-border text-white hover:bg-card-hover',
    danger: 'bg-danger text-white hover:bg-danger/80',
    ghost: 'text-gray-400 hover:text-white'
  };
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2',
    lg: 'px-6 py-3 text-lg'
  };
  return (
    <button 
      onClick={onClick}
      className={`flex items-center gap-2 rounded-lg font-medium transition-all ${variants[variant]} ${sizes[size]}`}
    >
      {Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
};

// Dashboard Views
const Overview = ({ trades, tasks, wallet }) => {
  const totalInvested = trades.reduce((sum, t) => sum + t.size, 0);
  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const openTrades = trades.filter(t => t.status === 'OPEN');
  const activeTasks = tasks.filter(t => t.enabled);

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-400 text-sm">Total Value</span>
            <Wallet className="w-5 h-5 text-accent" />
          </div>
          <div className="text-3xl font-bold text-white">${wallet.totalValue.toFixed(2)}</div>
          <div className={`flex items-center gap-1 mt-2 ${wallet.change24h >= 0 ? 'text-success' : 'text-danger'}`}>
            {wallet.change24h >= 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
            <span>{wallet.changePercent.toFixed(2)}%</span>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-400 text-sm">Total P&L</span>
            <TrendingUp className="w-5 h-5 text-success" />
          </div>
          <div className={`text-3xl font-bold ${totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
          </div>
          <div className="text-gray-500 text-sm mt-2">Across {trades.length} trades</div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-400 text-sm">Open Positions</span>
            <Activity className="w-5 h-5 text-warning" />
          </div>
          <div className="text-3xl font-bold text-white">{openTrades.length}</div>
          <div className="text-gray-500 text-sm mt-2">${totalInvested.toFixed(2)} invested</div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-400 text-sm">Active Tasks</span>
            <Calendar className="w-5 h-5 text-purple" />
          </div>
          <div className="text-3xl font-bold text-white">{activeTasks.length}</div>
          <div className="text-gray-500 text-sm mt-2">{tasks.length - activeTasks.length} paused</div>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Portfolio Value</h3>
            <Badge type="info">Live</Badge>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={pnlHistory}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#252535" />
                <XAxis dataKey="time" stroke="#666" />
                <YAxis stroke="#666" domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#151520', border: '1px solid #252535' }}
                  labelStyle={{ color: '#fff' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="value" 
                  stroke="#00d4ff" 
                  fillOpacity={1} 
                  fill="url(#colorValue)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Task Status</h3>
            <Button variant="ghost" size="sm" icon={RefreshCw}>Refresh</Button>
          </div>
          <div className="space-y-4">
            {tasks.slice(0, 3).map(task => (
              <div key={task.id} className="flex items-center justify-between p-4 bg-darker rounded-lg">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${task.enabled ? 'bg-success animate-pulse' : 'bg-gray-500'}`} />
                  <div>
                    <div className="text-white font-medium">{task.name}</div>
                    <div className="text-gray-500 text-sm">{task.schedule}</div>
                  </div>
                </div>
                <Badge type={task.enabled ? 'success' : 'default'}>
                  {task.enabled ? 'Running' : 'Paused'}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">Recent Trades</h3>
          <Button variant="secondary" size="sm">View All</Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left border-b border-border">
                <th className="pb-3 text-gray-400 font-medium">Market</th>
                <th className="pb-3 text-gray-400 font-medium">Side</th>
                <th className="pb-3 text-gray-400 font-medium">Size</th>
                <th className="pb-3 text-gray-400 font-medium">P&L</th>
                <th className="pb-3 text-gray-400 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(trade => (
                <tr key={trade.id} className="border-b border-border/50">
                  <td className="py-4">
                    <div className="text-white font-medium">{trade.market}</div>
                    <div className="text-gray-500 text-sm">ID: {trade.marketId}</div>
                  </td>
                  <td className="py-4">
                    <Badge type={trade.side === 'YES' ? 'success' : 'danger'}>
                      {trade.side}
                    </Badge>
                  </td>
                  <td className="py-4 text-white">${trade.size.toFixed(2)}</td>
                  <td className="py-4">
                    <span className={trade.pnl >= 0 ? 'text-success' : 'text-danger'}>
                      {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-4">
                    <Badge type={trade.status === 'OPEN' ? 'success' : 'default'}>
                      ● {trade.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export default Overview;
