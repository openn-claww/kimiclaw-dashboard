const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// Database path
const DB_PATH = '/root/.openclaw/skills/polytrader/trades.db';

// API endpoint to get all trades
app.get('/api/trades', (req, res) => {
  const db = new sqlite3.Database(DB_PATH);
  db.all('SELECT * FROM trades ORDER BY timestamp DESC', [], (err, rows) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({ trades: rows });
  });
  db.close();
});

// API endpoint to get stats
app.get('/api/stats', (req, res) => {
  const db = new sqlite3.Database(DB_PATH);
  db.get(`
    SELECT 
      COUNT(*) as total_trades,
      SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_positions,
      SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
      SUM(pnl_usd) as total_pnl,
      SUM(size_usd) as total_invested
    FROM trades
  `, [], (err, row) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json(row);
  });
  db.close();
});

// Serve static files
app.use(express.static(path.join(__dirname, 'build')));

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`API server running on port ${PORT}`);
});
