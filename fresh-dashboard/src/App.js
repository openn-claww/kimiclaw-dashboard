import React, { useState, useEffect } from 'react';
import { Wallet, TrendingUp, Activity, Calendar, Plus, CheckCircle, XCircle, Clock, BarChart3, Bell } from 'lucide-react';
import { format } from 'date-fns';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function App() {
  const [tab, setTab] = useState('overview');
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState({});
  const [wallet, setWallet] = useState({});
  const [loading, setLoading] = useState(true);
  const [taskList, setTaskList] = useState([
    { id: 1, name: 'Trading Heartbeat', schedule: 'Every 10 min', status: 'active', priority: 'high' },
    { id: 2, name: 'Analysis Report', schedule: 'Every 2 days', status: 'active', priority: 'medium' },
    { id: 3, name: 'Social Monitor', schedule: 'Every 6 hours', status: 'active', priority: 'low' }
  ]);
  const [showAdd, setShowAdd] = useState(false);
  const [newTask, setNewTask] = useState({ name: '', schedule: '', priority: 'medium' });

  // Fetch live data
  useEffect(() => {
    fetch('/trades-live.json')
      .then(res => res.json())
      .then(data => {
        setTrades(data.trades || []);
        setStats(data.stats || {});
        setWallet(data.wallet || {});
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load trades:', err);
        setLoading(false);
      });
  }, []);

  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl_usd || 0), 0);
  const totalValue = (wallet.total_value || 19.82) + totalPnl;

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

  if (loading) return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">Loading...</div>;

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold">KimiClaw Dashboard</h1>
                <p className="text-gray-400 text-sm">LIVE Trading Data</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-gray-400">{format(new Date(), 'PPp')}</span>
              <Bell className="w-5 h-5 text-gray-400" />
            </div>
          </div>
        </div>
      </header>

      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {['overview', 'trades', 'tasks', 'wallet'].map((t) => (
              <button key={t} onClick={() => setTab(t)} className={`px-6 py-4 text-sm font-medium capitalize transition-colors border-b-2 ${tab === t ? 'text-blue-400 border-blue-400' : 'text-gray-400 border-transparent hover:text-white'}`}>
                {t}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {tab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total Value</span>
                  <Wallet className="w-5 h-5 text-blue-400" />
                </div>
                <div className="text-3xl font-bold">${totalValue.toFixed(2)}</div>
                <div className="text-gray-500 text-sm mt-2">{trades.length} positions</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Total P&L</span>
                  <TrendingUp className="w-5 h-5 text-green-400" />
                </div>
                <div className={`text-3xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>${totalPnl.toFixed(2)}</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Open Positions</span>
                  <Activity className="w-5 h-5 text-yellow-400" />
                </div>
                <div className="text-3xl font-bold">{stats.open_positions || trades.length}</div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-gray-400 text-sm">Active Tasks</span>
                  <Calendar className="w-5 h-5 text-purple-400" />
                </div>
                <div className="text-3xl font-bold">{taskList.length}</div>
              </div>
            </div>

            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <h3 className="text-lg font-semibold mb-6">Recent Trades (LIVE)</h3>
              <table className="w-full">
                <thead>
                  <tr className="text-left border-b border-gray-700">
                    <th className="pb-3 text-gray-400">Market</th>
                    <th className="pb-3 text-gray-400">Side</th>
                    <th className="pb-3 text-gray-400">Size</th>
                    <th className="pb-3 text-gray-400">Entry</th>
                    <th className="pb-3 text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-gray-700/50">
                      <td className="py-4">
                        <div className="font-medium">{trade.market_question?.substring(0, 50)}...</div>
                        <div className="text-gray-500 text-sm">ID: {trade.market_id}</div>
                      </td>
                      <td className="py-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{trade.side}</span>
                      </td>
                      <td className="py-4">${trade.size_usd?.toFixed(2)}</td>
                      <td className="py-4">${trade.entry_price?.toFixed(2)}</td>
                      <td className="py-4">
                        <span className="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">● {trade.status}</span>
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
            <h2 className="text-2xl font-bold">All Trades ({trades.length})</h2>
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-300">Market</th>
                    <th className="text-left py-3 px-4 text-gray-300">Side</th>
                    <th className="text-left py-3 px-4 text-gray-300">Size</th>
                    <th className="text-left py-3 px-4 text-gray-300">Entry</th>
                    <th className="text-left py-3 px-4 text-gray-300">TX</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.id} className="border-b border-gray-700">
                      <td className="py-4 px-4">
                        <div className="font-medium">{trade.market_question}</div>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs ${trade.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{trade.side}</span>
                      </td>
                      <td className="py-4 px-4">${trade.size_usd?.toFixed(2)}</td>
                      <td className="py-4 px-4">${trade.entry_price?.toFixed(2)}</td>
                      <td className="py-4 px-4">
                        <a href={`https://polygonscan.com/tx/${trade.tx_hash}`} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline text-sm">View</a>
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
              <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                <Plus className="w-4 h-4" /> Add Task
              </button>
            </div>
            {showAdd && (
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <input type="text" placeholder="Task name" value={newTask.name} onChange={(e) => setNewTask({...newTask, name: e.target.value})} className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white" />
                  <input type="text" placeholder="Schedule" value={newTask.schedule} onChange={(e) => setNewTask({...newTask, schedule: e.target.value})} className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white" />
                  <select value={newTask.priority} onChange={(e) => setNewTask({...newTask, priority: e.target.value})} className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div className="flex gap-2 mt-4">
                  <button onClick={addTask} className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600"><CheckCircle className="w-4 h-4 inline mr-2" />Save</button>
                  <button onClick={() => setShowAdd(false)} className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"><XCircle className="w-4 h-4 inline mr-2" />Cancel</button>
                </div>
              </div>
            )}
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="text-left py-3 px-4 text-gray-300">Task</th>
                    <th className="text-left py-3 px-4 text-gray-300">Schedule</th>
                    <th className="text-left py-3 px-4 text-gray-300">Status</th>
                    <th className="text-left py-3 px-4 text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {taskList.map(task => (
                    <tr key={task.id} className="border-b border-gray-700">
                      <td className="py-4 px-4"><div className="font-medium">{task.name}</div></td>
                      <td className="py-4 px-4 text-gray-400">{task.schedule}</td>
                      <td className="py-4 px-4"><span className={`px-2 py-1 rounded-full text-xs ${task.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>{task.status === 'active' ? '● Running' : '○ Paused'}</span></td>
                      <td className="py-4 px-4">
                        <div className="flex gap-2">
                          <button onClick={() => toggleTask(task.id)} className="p-2 bg-gray-700 rounded hover:bg-gray-600">{task.status === 'active' ? <Clock className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}</button>
                          <button onClick={() => deleteTask(task.id)} className="p-2 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30"><XCircle className="w-4 h-4" /></button>
                        </div>
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
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <h3 className="text-lg font-semibold mb-4">Balances (LIVE)</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                    <span>USDC.e</span>
                    <span className="text-xl font-bold">${wallet.usdc?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                    <span>POL</span>
                    <span className="text-xl font-bold">{wallet.pol?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="flex justify-between items-center p-4 bg-blue-500/20 rounded-lg border border-blue-500">
                    <span>Total Value</span>
                    <span className="text-xl font-bold text-blue-400">${wallet.total_value?.toFixed(2) || '0.00'}</span>
                  </div>
                </div>
              </div>
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                <h3 className="text-lg font-semibold mb-4">Wallet Address</h3>
                <div className="p-4 bg-gray-700 rounded-lg font-mono text-sm break-all">0x557A656C110a9eFdbFa28773DE4aCc2c3924a274</div>
                <a href="https://polygonscan.com/address/0x557A656C110a9eFdbFa28773DE4aCc2c3924a274" target="_blank" rel="noopener noreferrer" className="mt-4 inline-block px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">View on PolygonScan</a>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
