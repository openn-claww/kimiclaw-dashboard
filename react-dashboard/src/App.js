import React, { useState, useEffect } from 'react';
import { 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  Target, 
  Calendar,
  Plus,
  Activity,
  DollarSign,
  Percent,
  BarChart3,
  Settings,
  Bell
} from 'lucide-react';
import { format } from 'date-fns';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

// Sample data - will be replaced with real data from your trades
const sampleTrades = [
  {
    id: 1,
    timestamp: '2026-02-19T10:04:41',
    market: 'Will Jesus Christ return before 2027?',
    market_id: '703258',
    side: 'NO',
    size: 2.0,
    entry: 0.97,
    current: 0.97,
    pnl: -0.06,
    status: 'OPEN',
    tx_hash: '7f55f8a140da6033fc46d86aca0bfdff7a7326bc9401151baf0ecc78e7b41a2c',
    strategy: 'Conservative NO on low-probability event',
    confidence: 9
  },
  {
    id: 2,
    timestamp: '2026-02-19T12:18:27',
    market: 'US strikes Iran by February 20, 2026?',
    market_id: '1320793',
    side: 'NO',
    size: 1.0,
    entry: 0.93,
    current: 0.93,
    pnl: 0,
    status: 'OPEN',
    tx_hash: '077b29241c9236cb313111303d85dd213a4df0650ddfa761fedd22bbd7fb4f34',
    strategy: 'Short-term high confidence NO',
    confidence: 8
  }
];

const sampleTasks = [
  {
    id: 1,
    name: 'Scan 15-min BTC markets',
    schedule: 'Every 10 minutes',
    lastRun: '2026-02-19T20:20:00',
    nextRun: '2026-02-19T20:30:00',
    status: 'active'
  },
  {
    id: 2,
    name: 'Social media strategy scan',
    schedule: 'Every 6 hours',
    lastRun: '2026-02-19T18:00:00',
    nextRun: '2026-02-19T20:00:00',
    status: 'active'
  },
  {
    id: 3,
    name: 'Performance report',
    schedule: 'Every 2 days',
    lastRun: '2026-02-19T12:00:00',
    nextRun: '2026-02-21T12:00:00',
    status: 'active'
  }
];

const pnlData = [
  { time: '10:00', pnl: 0 },
  { time: '11:00', pnl: -0.03 },
  { time: '12:00', pnl: -0.06 },
  { time: '13:00', pnl: -0.06 },
  { time: '14:00', pnl: -0.06 },
  { time: '15:00', pnl: -0.06 },
  { time: '16:00', pnl: -0.06 },
  { time: '17:00', pnl: -0.06 },
  { time: '18:00', pnl: -0.06 },
  { time: '19:00', pnl: -0.06 },
  { time: '20:00', pnl: -0.06 },
];

const positionData = [
  { name: 'Long-term', value: 2, color: '#00d4ff' },
  { name: 'Short-term', value: 1, color: '#00ff88' },
];

function StatCard({ title, value, subtitle, icon: Icon, trend }) {
  return (
    <div className="bg-trader-card border border-trader-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider">{title}</h3>
        <Icon className="w-5 h-5 text-trader-accent" />
      </div>
      <div className="text-3xl font-bold text-white mb-2">{value}</div>
      {trend && (
        <div className={`text-sm flex items-center gap-1 ${trend >= 0 ? 'text-trader-success' : 'text-trader-danger'}`}>
          {trend >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          {trend > 0 ? '+' : ''}{trend}%
        </div>
      )}
      {subtitle && <div className="text-gray-500 text-sm mt-1">{subtitle}</div>}
    </div>
  );
}

function TradeRow({ trade }) {
  return (
    <tr className="border-b border-trader-border hover:bg-trader-card/50 transition-colors">
      <td className="py-4 px-4">
        <div className="text-white font-medium">{trade.market}</div>
        <div className="text-gray-500 text-sm">ID: {trade.market_id}</div>
      </td>
      <td className="py-4 px-4">
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          trade.side === 'YES' ? 'bg-trader-success/20 text-trader-success' : 'bg-trader-danger/20 text-trader-danger'
        }`}>
          {trade.side}
        </span>
      </td>
      <td className="py-4 px-4 text-white">${trade.size.toFixed(2)}</td>
      <td className="py-4 px-4 text-white">${trade.entry.toFixed(2)}</td>
      <td className="py-4 px-4">
        <span className={`font-medium ${trade.pnl >= 0 ? 'text-trader-success' : 'text-trader-danger'}`}>
          {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
        </span>
      </td>
      <td className="py-4 px-4">
        <span className="px-3 py-1 rounded-full text-sm bg-trader-success/20 text-trader-success">
          ● {trade.status}
        </span>
      </td>
      <td className="py-4 px-4">
        <a 
          href={`https://polygonscan.com/tx/${trade.tx_hash}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-trader-accent hover:underline text-sm"
        >
          View TX
        </a>
      </td>
    </tr>
  );
}

function TaskRow({ task }) {
  return (
    <tr className="border-b border-trader-border hover:bg-trader-card/50 transition-colors">
      <td className="py-4 px-4">
        <div className="text-white font-medium">{task.name}</div>
      </td>
      <td className="py-4 px-4 text-gray-400">{task.schedule}</td>
      <td className="py-4 px-4 text-gray-400">{format(new Date(task.lastRun), 'HH:mm')}</td>
      <td className="py-4 px-4 text-gray-400">{format(new Date(task.nextRun), 'HH:mm')}</td>
      <td className="py-4 px-4">
        <span className="px-3 py-1 rounded-full text-sm bg-trader-success/20 text-trader-success">
          ● Active
        </span>
      </td>
      <td className="py-4 px-4">
        <button className="text-trader-accent hover:text-white transition-colors">
          <Settings className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const totalPnl = sampleTrades.reduce((sum, t) => sum + t.pnl, 0);
  const totalInvested = sampleTrades.reduce((sum, t) => sum + t.size, 0);

  return (
    <div className="min-h-screen bg-trader-dark">
      {/* Header */}
      <header className="bg-trader-card border-b border-trader-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-trader-accent rounded-lg flex items-center justify-center">
                <Target className="w-6 h-6 text-black" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">PolyTrader</h1>
                <p className="text-gray-500 text-sm">Professional Trading Dashboard</p>
              </div>
            </div>
            <div className="flex items-center gap-6">
              <div className="text-right">
                <div className="text-gray-400 text-sm">{format(currentTime, 'EEEE, MMMM do, yyyy')}</div>
                <div className="text-white font-mono">{format(currentTime, 'HH:mm:ss')}</div>
              </div>
              <button className="p-2 rounded-lg bg-trader-card border border-trader-border hover:border-trader-accent transition-colors">
                <Bell className="w-5 h-5 text-gray-400" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-trader-card border-b border-trader-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {[
              { id: 'overview', label: 'Overview', icon: Activity },
              { id: 'trades', label: 'Trades', icon: BarChart3 },
              { id: 'tasks', label: 'Scheduled Tasks', icon: Calendar },
              { id: 'settings', label: 'Settings', icon: Settings },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-6 py-4 text-sm font-medium transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'text-trader-accent border-trader-accent'
                    : 'text-gray-400 border-transparent hover:text-white'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'overview' && (
          <div className="space-y-8">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <StatCard
                title="Total P&L"
                value={`$${totalPnl.toFixed(2)}`}
                subtitle="Since Feb 19, 2026"
                icon={DollarSign}
                trend={-3}
              />
              <StatCard
                title="Active Positions"
                value={sampleTrades.length}
                subtitle="2 open trades"
                icon={Target}
              />
              <StatCard
                title="Total Invested"
                value={`$${totalInvested.toFixed(2)}`}
                subtitle="Across all positions"
                icon={Wallet}
              />
              <StatCard
                title="Win Rate"
                value="0%"
                subtitle="No closed trades yet"
                icon={Percent}
              />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-trader-card border border-trader-border rounded-xl p-6">
                <h3 className="text-white font-medium mb-6 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-trader-accent" />
                  P&L Over Time
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={pnlData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#252535" />
                      <XAxis dataKey="time" stroke="#666" />
                      <YAxis stroke="#666" />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#151520', border: '1px solid #252535' }}
                        labelStyle={{ color: '#fff' }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="pnl" 
                        stroke="#00d4ff" 
                        strokeWidth={2}
                        dot={{ fill: '#00d4ff' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="bg-trader-card border border-trader-border rounded-xl p-6">
                <h3 className="text-white font-medium mb-6 flex items-center gap-2">
                  <PieChart className="w-5 h-5 text-trader-accent" />
                  Position Distribution
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={positionData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {positionData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#151520', border: '1px solid #252535' }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-6 mt-4">
                  {positionData.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <div 
                        className="w-3 h-3 rounded-full" 
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-gray-400 text-sm">{item.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recent Trades Preview */}
            <div className="bg-trader-card border border-trader-border rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-trader-border flex items-center justify-between">
                <h3 className="text-white font-medium">Recent Trades</h3>
                <button 
                  onClick={() => setActiveTab('trades')}
                  className="text-trader-accent text-sm hover:underline"
                >
                  View All →
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-trader-dark">
                    <tr>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Market</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Side</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Size</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">P&L</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sampleTrades.slice(0, 3).map((trade) => (
                      <TradeRow key={trade.id} trade={trade} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'trades' && (
          <div className="bg-trader-card border border-trader-border rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-trader-border flex items-center justify-between">
              <h3 className="text-white font-medium">All Trades</h3>
              <button className="flex items-center gap-2 px-4 py-2 bg-trader-accent text-black rounded-lg font-medium hover:bg-trader-accent/90 transition-colors">
                <Plus className="w-4 h-4" />
                New Trade
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-trader-dark">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Market</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Side</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Size</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Entry</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">P&L</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Status</th>
                    <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {sampleTrades.map((trade) => (
                    <TradeRow key={trade.id} trade={trade} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'tasks' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Scheduled Tasks</h2>
              <button className="flex items-center gap-2 px-4 py-2 bg-trader-accent text-black rounded-lg font-medium hover:bg-trader-accent/90 transition-colors">
                <Plus className="w-4 h-4" />
                Create Task
              </button>
            </div>
            
            <div className="bg-trader-card border border-trader-border rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-trader-dark">
                    <tr>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Task Name</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Schedule</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Last Run</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Next Run</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Status</th>
                      <th className="text-left py-3 px-4 text-gray-400 text-sm font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sampleTasks.map((task) => (
                      <TaskRow key={task.id} task={task} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="max-w-2xl space-y-6">
            <div className="bg-trader-card border border-trader-border rounded-xl p-6">
              <h3 className="text-white font-medium mb-6">Trading Settings</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-gray-400 text-sm mb-2">Max Risk Per Trade (%)</label>
                  <input 
                    type="number" 
                    defaultValue={5}
                    className="w-full bg-trader-dark border border-trader-border rounded-lg px-4 py-2 text-white focus:border-trader-accent focus:outline-none"
                  />
                </div>
                
                <div>
                  <label className="block text-gray-400 text-sm mb-2">Default Bet Size ($)</label>
                  <input 
                    type="number" 
                    defaultValue={1}
                    className="w-full bg-trader-dark border border-trader-border rounded-lg px-4 py-2 text-white focus:border-trader-accent focus:outline-none"
                  />
                </div>
                
                <div className="flex items-center justify-between py-4 border-t border-trader-border">
                  <div>
                    <div className="text-white">Dry Run Mode</div>
                    <div className="text-gray-500 text-sm">Simulate trades without real execution</div>
                  </div>
                  <button className="w-12 h-6 bg-trader-success rounded-full relative">
                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                  </button>
                </div>
                
                <div className="flex items-center justify-between py-4 border-t border-trader-border">
                  <div>
                    <div className="text-white">Discord Notifications</div>
                    <div className="text-gray-500 text-sm">Send alerts to Discord channel</div>
                  </div>
                  <button className="w-12 h-6 bg-trader-success rounded-full relative">
                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
