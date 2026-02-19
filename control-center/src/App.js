import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Wallet, TrendingUp, Calendar, Plus, CheckCircle, XCircle, Clock, BarChart3, Activity, Settings, Bell } from 'lucide-react';
import { format } from 'date-fns';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

// Sample data
const trades = [
  { id: 1, market: 'Jesus return 2027', side: 'NO', size: 2.0, entry: 0.97, pnl: -0.06, status: 'OPEN' },
  { id: 2, market: 'Iran strike Feb 20', side: 'NO', size: 1.0, entry: 0.93, pnl: 0, status: 'OPEN' }
];

const tasks = [
  { id: 1, name: 'Trading Heartbeat', schedule: 'Every 10 min', status: 'active', priority: 'high' },
  { id: 2, name: 'Analysis Report', schedule: 'Every 2 days', status: 'active', priority: 'medium' },
  { id: 3, name: 'Social Monitor', schedule: 'Every 6 hours', status: 'active', priority: 'low' }
];

const pnlData = [
  { time: '10:00', value: 16.71 },
  { time: '12:00', value: 16.65 },
  { time: '14:00', value: 16.65 },
  { time: '16:00', value: 16.65 },
  { time: '18:00', value: 16.65 },
  { time: '20:00', value: 16.65 },
];

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [taskList, setTaskList] = useState(tasks);
  const [newTask, setNewTask] = useState({ name: '', schedule: '', priority: 'medium' });
  const [showAddTask, setShowAddTask] = useState(false);

  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const totalInvested = trades.reduce((sum, t) => sum + t.size, 0);

  const addTask = () => {
    if (newTask.name && newTask.schedule) {
      setTaskList([...taskList, { ...newTask, id: Date.now(), status: 'active' }]);
      setNewTask({ name: '', schedule: '', priority: 'medium' });
      setShowAddTask(false);
    }
  };

  const deleteTask = (id) => {
    setTaskList(taskList.filter(t => t.id !== id));
  };

  const toggleTask = (id) => {
    setTaskList(taskList.map(t => t.id === id ? { ...t, status: t.status === 'active' ? 'paused' : 'active' } : t));
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center">
                <LayoutDashboard className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold">KimiClaw Control Center</h1>
                <p className="text-gray-400 text-sm">Manage everything in one place</p>
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
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {['overview', 'trades', 'tasks', 'wallet', 'settings'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-6 py-4 text-sm font-medium capitalize transition-colors border-b-2 ${
                  activeTab === tab ? 'text-blue-400 border-blue-400' : 'text-gray-400 border-transparent hover:text-white'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total Value</span>
                  <Wallet className="w-5 h-5 text-blue-400" />
                </div>
                <div className="text-3xl font-bold">$16.65</div>
                <div className="text-red-400 text-sm mt-2">-2.12%</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total P&L</span>
                  <TrendingUp className="w-5 h-5 text-green-400" />
                </div>
                <div className={`text-3xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${totalPnl.toFixed(2)}
                </div>
                <div className="text-gray-500 text-sm mt-2">Across {trades.length} trades</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Open Positions</span>
                  <Activity className="w-5 h-5 text-yellow-400" />
                </div>
                <div className="text-3xl font-bold">{trades.length}</div>
                <div className="text-gray-500 text-sm mt-2">${totalInvested.toFixed(2)} invested</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Active Tasks</span>
                  <Calendar className="w-5 h-5 text-purple-400" />
                </div>
                <div className="text-3xl font-bold">{taskList.length}</div>
                <div className="text-gray-500 text-sm mt-2">Running smoothly</div>
              </div>
            </div>

            {/* Chart */}
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <h3 className="text-lg font-semibold mb-6">Portfolio Value</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={pnlData}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="time" stroke="#6b7280" />
                    <YAxis stroke="#6b7280" domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                    <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                    <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Recent Trades */}
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <h3 className="text-lg font-semibold mb-6">Recent Trades</h3>
              <table className="w-full">
                <thead>
                  <tr className="text-left border-b border-gray-700">
                    <th className="pb-3 text-gray-400">Market</th>
                    <th className="pb-3 text-gray-400">Side</th>
                    <th className="pb-3 text-gray-400">Size</th>
                    <th className="pb-3 text-gray-400">P&L</th>
                    <th className="pb-3 text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-gray-700/50">
                      <td className="py-4">
                        <div className="font-medium">{trade.market}</div>
                      </td>
                      <td className="py-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-4">${trade.size.toFixed(2)}</td>
                      <td className={`py-4 ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </td>
                      <td className="py-4">
                        <span className="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
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

        {activeTab === 'tasks' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold">Scheduled Tasks</h2>
              <button 
                onClick={() => setShowAddTask(true)}
                className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                <Plus className="w-4 h-4" />
                Add Task
              </button>
            </div>

            {showAddTask && (
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <h3 className="text-lg font-semibold mb-4">Add New Task</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <input
                    type="text"
                    placeholder="Task name"
                    value={newTask.name}
                    onChange={(e) => setNewTask({...newTask, name: e.target.value})}
                    className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  />
                  <input
                    type="text"
                    placeholder="Schedule (e.g., Every 10 min)"
                    value={newTask.schedule}
                    onChange={(e) => setNewTask({...newTask, schedule: e.target.value})}
                    className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  />
                  <select
                    value={newTask.priority}
                    onChange={(e) => setNewTask({...newTask, priority: e.target.value})}
                    className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  >
                    <option value="low">Low Priority</option>
                    <option value="medium">Medium Priority</option>
                    <option value="high">High Priority</option>
                  </select>
                </div>
                <div className="flex gap-2 mt-4">
                  <button onClick={addTask} className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">
                    <CheckCircle className="w-4 h-4 inline mr-2" />
                    Save
                  </button>
                  <button onClick={() => setShowAddTask(false)} className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700">
                    <XCircle className="w-4 h-4 inline mr-2" />
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
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
                    <tr key={task.id} className="border-b border-gray-700">
                      <td className="py-4 px-4">
                        <div className="font-medium">{task.name}</div>
                      </td>
                      <td className="py-4 px-4 text-gray-400">{task.schedule}</td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${
                          task.priority === 'high' ? 'bg-red-500/20 text-red-400' :
                          task.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-blue-500/20 text-blue-400'
                        }`}>
                          {task.priority}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${
                          task.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          {task.status === 'active' ? '● Running' : '○ Paused'}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <div className="flex gap-2">
                          <button onClick={() => toggleTask(task.id)} className="p-2 bg-gray-700 rounded hover:bg-gray-600">
                            {task.status === 'active' ? <Clock className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                          </button>
                          <button onClick={() => deleteTask(task.id)} className="p-2 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30">
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

        {activeTab === 'trades' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold">All Trades</h2>
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-300">Market</th>
                    <th className="text-left py-3 px-4 text-gray-300">Side</th>
                    <th className="text-left py-3 px-4 text-gray-300">Entry</th>
                    <th className="text-left py-3 px-4 text-gray-300">Size</th>
                    <th className="text-left py-3 px-4 text-gray-300">P&L</th>
                    <th className="text-left py-3 px-4 text-gray-300">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-gray-700">
                      <td className="py-4 px-4">
                        <div className="font-medium">{trade.market}</div>
                        <div className="text-gray-500 text-sm">ID: {trade.marketId || trade.id}</div>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-4 px-4">${trade.entry?.toFixed(2) || '-'}</td>
                      <td className="py-4 px-4">${trade.size.toFixed(2)}</td>
                      <td className={`py-4 px-4 ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </td>
                      <td className="py-4 px-4">
                        <span className="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
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

        {activeTab === 'wallet' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold">Wallet</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <h3 className="text-lg font-semibold mb-4">Balances</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                    <span>USDC.e</span>
                    <span className="text-xl font-bold">$7.93</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                    <span>POL</span>
                    <span className="text-xl font-bold">8.72</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-blue-500/20 rounded-lg border border-blue-500">
                    <span>Total Value</span>
                    <span className="text-xl font-bold text-blue-400">$16.65</span>
                  </div>
                </div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <h3 className="text-lg font-semibold mb-4">Wallet Address</h3>
                <div className="p-4 bg-gray-700 rounded-lg font-mono text-sm break-all">
                  0x557A656C110a9eFdbFa28773DE4aCc2c3924a274
                </div>
                <div className="mt-4 flex gap-2">
                  <a 
                    href="https://polygonscan.com/address/0x557A656C110a9eFdbFa28773DE4aCc2c3924a274"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                  >
                    View on PolygonScan
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold">Settings</h2>
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 max-w-2xl">
              <h3 className="text-lg font-semibold mb-6">Trading Configuration</h3>
              <div className="space-y-4">
                <div className="flex justify-between items-center py-4 border-b border-gray-700">
                  <div>
                    <div className="font-medium">Max Risk Per Trade</div>
                    <div className="text-gray-400 text-sm">Percentage of wallet per trade</div>
                  </div>
                  <input type="number" defaultValue={5} className="w-20 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white" />
                </div>
                <div className="flex justify-between items-center py-4 border-b border-gray-700">
                  <div>
                    <div className="font-medium">Default Bet Size</div>
                    <div className="text-gray-400 text-sm">Default amount per trade</div>
                  </div>
                  <input type="number" defaultValue={1} className="w-20 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white" />
                </div>
                <div className="flex justify-between items-center py-4 border-b border-gray-700">
                  <div>
                    <div className="font-medium">Dry Run Mode</div>
                    <div className="text-gray-400 text-sm">Simulate trades without execution</div>
                  </div>
                  <button className="w-12 h-6 bg-green-500 rounded-full relative">
                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                  </button>
                </div>
                <div className="flex justify-between items-center py-4">
                  <div>
                    <div className="font-medium">Discord Notifications</div>
                    <div className="text-gray-400 text-sm">Send alerts to Discord</div>
                  </div>
                  <button className="w-12 h-6 bg-green-500 rounded-full relative">
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
