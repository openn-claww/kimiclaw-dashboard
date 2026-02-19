import React, { useState, useEffect } from 'react';
import { 
  Wallet, TrendingUp, Activity, Calendar, Settings,
  Plus, Trash2, CheckCircle, XCircle, Clock, BarChart3,
  Bell, ArrowUpRight, ArrowDownRight
} from 'lucide-react';
import { format } from 'date-fns';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const trades = [
  { id: 1, market: 'Jesus return 2027', side: 'NO', size: 2.0, pnl: -0.07, status: 'OPEN' },
  { id: 2, market: 'Iran strike Feb 20', side: 'NO', size: 1.0, pnl: 0, status: 'OPEN' }
];

const tasks = [
  { id: 1, name: 'Trading Heartbeat', schedule: 'Every 10 min', status: 'active', priority: 'high' },
  { id: 2, name: 'Analysis Report', schedule: 'Every 2 days', status: 'active', priority: 'medium' },
  { id: 3, name: 'Social Monitor', schedule: 'Every 6 hours', status: 'active', priority: 'low' }
];

const chartData = [
  { time: '10:00', value: 16.71 },
  { time: '12:00', value: 16.64 },
  { time: '14:00', value: 16.64 },
  { time: '16:00', value: 16.64 },
  { time: '18:00', value: 16.64 },
  { time: '20:00', value: 16.64 },
  { time: '22:00', value: 16.64 },
];

function App() {
  const [tab, setTab] = useState('overview');
  const [taskList, setTaskList] = useState(tasks);
  const [showAdd, setShowAdd] = useState(false);
  const [newTask, setNewTask] = useState({ name: '', schedule: '', priority: 'medium' });

  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const totalValue = 16.64;

  const addTask = () => {
    if (newTask.name && newTask.schedule) {
      setTaskList([...taskList, { ...newTask, id: Date.now(), status: 'active' }]);
      setNewTask({ name: '', schedule: '', priority: 'medium' });
      setShowAdd(false);
    }
  };

  const deleteTask = (id) => setTaskList(taskList.filter(t => t.id !== id));
  
  const toggleTask = (id) => {
    setTaskList(taskList.map(t => t.id === id ? { ...t, status: t.status === 'active' ? 'paused' : 'active' } : t));
  };

  return (
    <div className="min-h-screen bg-dark text-white">
      {/* Header */}
      <header className="bg-card border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-accent rounded-lg flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-dark" />
              </div>
              <div>
                <h1 className="text-xl font-bold">KimiClaw Dashboard</h1>
                <p className="text-gray-400 text-sm">Trading Control Center</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-gray-400">{format(new Date(), 'PPp')}</span>
              <Bell className="w-5 h-5 text-gray-400" />
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-card border-b border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {['overview', 'trades', 'tasks', 'wallet'].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-6 py-4 text-sm font-medium capitalize transition-colors border-b-2 ${
                  tab === t ? 'text-accent border-accent' : 'text-gray-400 border-transparent hover:text-white'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {tab === 'overview' && (
          <div className="space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-card rounded-xl p-6 border border-border">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total Value</span>
                  <Wallet className="w-5 h-5 text-accent" />
                </div>
                <div className="text-3xl font-bold">${totalValue.toFixed(2)}</div>
                <div className="text-danger text-sm mt-2">-0.42%</div>
              </div>

              <div className="bg-card rounded-xl p-6 border border-border">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total P&L</span>
                  <TrendingUp className="w-5 h-5 text-success" />
                </div>
                <div className={`text-3xl font-bold ${totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                  ${totalPnl.toFixed(2)}
                </div>
                <div className="text-gray-500 text-sm mt-2">Across {trades.length} trades</div>
              </div>

              <div className="bg-card rounded-xl p-6 border border-border">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Open Positions</span>
                  <Activity className="w-5 h-5 text-warning" />
                </div>
                <div className="text-3xl font-bold">{trades.length}</div>
                <div className="text-gray-500 text-sm mt-2">$3.00 invested</div>
              </div>

              <div className="bg-card rounded-xl p-6 border border-border">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Active Tasks</span>
                  <Calendar className="w-5 h-5 text-purple-400" />
                </div>
                <div className="text-3xl font-bold">{taskList.length}</div>
                <div className="text-gray-500 text-sm mt-2">Running smoothly</div>
              </div>
            </div>

            {/* Chart */}
            <div className="bg-card rounded-xl p-6 border border-border">
              <h3 className="text-lg font-semibold mb-6">Portfolio Value</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#252535" />
                    <XAxis dataKey="time" stroke="#666" />
                    <YAxis stroke="#666" />
                    <Tooltip contentStyle={{ backgroundColor: '#151520', border: '1px solid #252535' }} />
                    <Area type="monotone" dataKey="value" stroke="#00d4ff" fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Recent Trades */}
            <div className="bg-card rounded-xl p-6 border border-border">
              <h3 className="text-lg font-semibold mb-6">Recent Trades</h3>
              <table className="w-full">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="pb-3 text-gray-400">Market</th>
                    <th className="pb-3 text-gray-400">Side</th>
                    <th className="pb-3 text-gray-400">Size</th>
                    <th className="pb-3 text-gray-400">P&L</th>
                    <th className="pb-3 text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-border/50">
                      <td className="py-4">
                        <div className="font-medium">{trade.market}</div>
                      </td>
                      <td className="py-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-4">${trade.size.toFixed(2)}</td>
                      <td className={`py-4 ${trade.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </td>
                      <td className="py-4">
                        <span className="px-2 py-1 rounded-full text-xs bg-success/20 text-success">
                          ● {trade.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'tasks' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold">Scheduled Tasks</h2>
              <button 
                onClick={() => setShowAdd(true)}
                className="flex items-center gap-2 px-4 py-2 bg-accent text-dark rounded-lg hover:bg-accent/80"
              >
                <Plus className="w-4 h-4" />
                Add Task
              </button>
            </div>

            {showAdd && (
              <div className="bg-card rounded-xl p-6 border border-border">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <input
                    type="text"
                    placeholder="Task name"
                    value={newTask.name}
                    onChange={(e) => setNewTask({...newTask, name: e.target.value})}
                    className="bg-dark border border-border rounded-lg px-4 py-2 text-white"
                  />
                  <input
                    type="text"
                    placeholder="Schedule"
                    value={newTask.schedule}
                    onChange={(e) => setNewTask({...newTask, schedule: e.target.value})}
                    className="bg-dark border border-border rounded-lg px-4 py-2 text-white"
                  />
                  <select
                    value={newTask.priority}
                    onChange={(e) => setNewTask({...newTask, priority: e.target.value})}
                    className="bg-dark border border-border rounded-lg px-4 py-2 text-white"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div className="flex gap-2 mt-4">
                  <button onClick={addTask} className="px-4 py-2 bg-success text-dark rounded-lg hover:bg-success/80">
                    <CheckCircle className="w-4 h-4 inline mr-2" />Save
                  </button>
                  <button onClick={() => setShowAdd(false)} className="px-4 py-2 bg-border text-white rounded-lg hover:bg-card">
                    <XCircle className="w-4 h-4 inline mr-2" />Cancel
                  </button>
                </div>
              </div>
            )}

            <div className="bg-card rounded-xl border border-border overflow-hidden">
              <table className="w-full">
                <thead className="bg-dark">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-300">Task</th>
                    <th className="text-left py-3 px-4 text-gray-300">Schedule</th>
                    <th className="text-left py-3 px-4 text-gray-300">Priority</th>
                    <th className="text-left py-3 px-4 text-gray-300">Status</th>
                    <th className="text-left py-3 px-4 text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {taskList.map(task => (
                    <tr key={task.id} className="border-b border-border">
                      <td className="py-4 px-4">
                        <div className="font-medium">{task.name}</div>
                      </td>
                      <td className="py-4 px-4 text-gray-400">{task.schedule}</td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${
                          task.priority === 'high' ? 'bg-danger/20 text-danger' :
                          task.priority === 'medium' ? 'bg-warning/20 text-warning' :
                          'bg-accent/20 text-accent'
                        }`}>
                          {task.priority}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${task.status === 'active' ? 'bg-success/20 text-success' : 'bg-gray-500/20 text-gray-400'}`}>
                          {task.status === 'active' ? '● Running' : '○ Paused'}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <div className="flex gap-2">
                          <button onClick={() => toggleTask(task.id)} className="p-2 bg-border rounded hover:bg-card">
                            {task.status === 'active' ? <Clock className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                          </button>
                          <button onClick={() => deleteTask(task.id)} className="p-2 bg-danger/20 text-danger rounded hover:bg-danger/30">
                            <XCircle className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'trades' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold">All Trades</h2>
            <div className="bg-card rounded-xl border border-border overflow-hidden">
              <table className="w-full">
                <thead className="bg-dark">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-300">Market</th>
                    <th className="text-left py-3 px-4 text-gray-300">Side</th>
                    <th className="text-left py-3 px-4 text-gray-300">Size</th>
                    <th className="text-left py-3 px-4 text-gray-300">P&L</th>
                    <th className="text-left py-3 px-4 text-gray-300">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-border">
                      <td className="py-4 px-4">
                        <div className="font-medium">{trade.market}</div>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-4 px-4">${trade.size.toFixed(2)}</td>
                      <td className={`py-4 px-4 ${trade.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </td>
                      <td className="py-4 px-4">
                        <span className="px-2 py-1 rounded-full text-xs bg-success/20 text-success">● {trade.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'wallet' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold">Wallet</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-card rounded-xl p-6 border border-border">
                <h3 className="text-lg font-semibold mb-4">Balances</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-4 bg-dark rounded-lg">
                    <span>USDC.e</span>
                    <span className="text-xl font-bold">$11.26</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-dark rounded-lg">
                    <span>POL</span>
                    <span className="text-xl font-bold">8.56</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-accent/20 rounded-lg border border-accent">
                    <span>Total Value</span>
                    <span className="text-xl font-bold text-accent">$19.82</span>
                  </div>
                </div>
              </div>
              <div className="bg-card rounded-xl p-6 border border-border">
                <h3 className="text-lg font-semibold mb-4">Wallet Address</h3>
                <div className="p-4 bg-dark rounded-lg font-mono text-sm break-all">
                  0x557A656C110a9eFdbFa28773DE4aCc2c3924a274
                </div>
                <a 
                  href="https://polygonscan.com/address/0x557A656C110a9eFdbFa28773DE4aCc2c3924a274"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-block px-4 py-2 bg-accent text-dark rounded-lg hover:bg-accent/80"
                >
                  View on PolygonScan
                </a>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
