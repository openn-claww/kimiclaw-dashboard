#!/usr/bin/env python3
"""
strategy_performance_tracker.py - Track and compare strategy performance
Database for storing and analyzing all strategy trades.
"""

import sqlite3
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict

DB_PATH = Path('/root/.openclaw/workspace/strategy_performance.db')

@dataclass
class TradeRecord:
    trade_id: str
    strategy: str  # 'mean_reversion', 'momentum', 'arbitrage', 'external_arb'
    market_id: str
    coin: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    pnl: Optional[float]
    pnl_pct: Optional[float]
    entry_time: str
    exit_time: Optional[str]
    exit_reason: Optional[str]
    timeframe: int
    paper_mode: bool
    
    def to_dict(self) -> Dict:
        return {
            'trade_id': self.trade_id,
            'strategy': self.strategy,
            'market_id': self.market_id,
            'coin': self.coin,
            'side': self.side,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'amount': self.amount,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'exit_reason': self.exit_reason,
            'timeframe': self.timeframe,
            'paper_mode': self.paper_mode
        }


class StrategyPerformanceTracker:
    """SQLite-based performance tracker for all strategies"""
    
    STRATEGIES = ['mean_reversion', 'momentum', 'arbitrage', 'external_arb']
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Main trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    coin TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    amount REAL NOT NULL,
                    pnl REAL,
                    pnl_pct REAL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    exit_reason TEXT,
                    timeframe INTEGER NOT NULL,
                    paper_mode BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Strategy performance summary table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_summary (
                    strategy TEXT PRIMARY KEY,
                    total_trades INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0.0,
                    avg_pnl REAL DEFAULT 0.0,
                    win_rate REAL DEFAULT 0.0,
                    profit_factor REAL DEFAULT 0.0,
                    sharpe_ratio REAL DEFAULT 0.0,
                    max_drawdown REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Hourly snapshots
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hourly_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hour TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    trades INTEGER DEFAULT 0,
                    pnl REAL DEFAULT 0.0,
                    UNIQUE(hour, strategy)
                )
            ''')
            
            conn.commit()
    
    def record_entry(self, trade: TradeRecord) -> bool:
        """Record a new trade entry"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO trades 
                    (trade_id, strategy, market_id, coin, side, entry_price, amount, 
                     entry_time, timeframe, paper_mode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade.trade_id, trade.strategy, trade.market_id, trade.coin,
                    trade.side, trade.entry_price, trade.amount, trade.entry_time,
                    trade.timeframe, trade.paper_mode
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"[Tracker] Error recording entry: {e}")
            return False
    
    def record_exit(self, trade_id: str, exit_price: float, pnl: float, 
                    pnl_pct: float, exit_time: str, exit_reason: str) -> bool:
        """Record a trade exit"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE trades 
                    SET exit_price = ?, pnl = ?, pnl_pct = ?, exit_time = ?, exit_reason = ?
                    WHERE trade_id = ?
                ''', (exit_price, pnl, pnl_pct, exit_time, exit_reason, trade_id))
                conn.commit()
                
                # Update strategy summary
                self._update_strategy_summary(conn)
                return True
        except Exception as e:
            print(f"[Tracker] Error recording exit: {e}")
            return False
    
    def _update_strategy_summary(self, conn):
        """Update strategy performance summaries"""
        cursor = conn.cursor()
        
        for strategy in self.STRATEGIES:
            # Get completed trades for this strategy
            cursor.execute('''
                SELECT pnl, pnl_pct FROM trades 
                WHERE strategy = ? AND exit_price IS NOT NULL
            ''', (strategy,))
            
            trades = cursor.fetchall()
            
            if not trades:
                continue
            
            pnls = [t[0] for t in trades if t[0] is not None]
            pnl_pcts = [t[1] for t in trades if t[1] is not None]
            
            if not pnls:
                continue
            
            wins = sum(1 for p in pnls if p > 0)
            losses = len(pnls) - wins
            total_pnl = sum(pnls)
            avg_pnl = total_pnl / len(pnls)
            win_rate = wins / len(pnls) if pnls else 0
            
            # Profit factor
            gross_profit = sum(p for p in pnls if p > 0)
            gross_loss = abs(sum(p for p in pnls if p < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            # Sharpe-like ratio
            if len(pnl_pcts) >= 2:
                avg_pct = sum(pnl_pcts) / len(pnl_pcts)
                variance = sum((p - avg_pct) ** 2 for p in pnl_pcts) / len(pnl_pcts)
                std_pct = variance ** 0.5 if variance > 0 else 0.0001
                sharpe = avg_pct / std_pct * (len(pnl_pcts) ** 0.5) if std_pct > 0 else 0
            else:
                sharpe = 0
            
            # Max drawdown
            cumulative = 0
            peak = 0
            max_dd = 0
            for p in pnls:
                cumulative += p
                peak = max(peak, cumulative)
                dd = peak - cumulative
                max_dd = max(max_dd, dd)
            
            cursor.execute('''
                INSERT OR REPLACE INTO strategy_summary 
                (strategy, total_trades, wins, losses, total_pnl, avg_pnl, 
                 win_rate, profit_factor, sharpe_ratio, max_drawdown, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (strategy, len(pnls), wins, losses, total_pnl, avg_pnl,
                  win_rate, profit_factor, sharpe, max_dd, datetime.now().isoformat()))
        
        conn.commit()
    
    def get_strategy_summary(self, strategy: str = None) -> Dict:
        """Get performance summary for a strategy or all strategies"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if strategy:
                cursor.execute('''
                    SELECT strategy, total_trades, wins, losses, total_pnl, avg_pnl,
                           win_rate, profit_factor, sharpe_ratio, max_drawdown, last_updated
                    FROM strategy_summary WHERE strategy = ?
                ''', (strategy,))
                row = cursor.fetchone()
                if row:
                    return {
                        'strategy': row[0],
                        'total_trades': row[1],
                        'wins': row[2],
                        'losses': row[3],
                        'total_pnl': row[4],
                        'avg_pnl': row[5],
                        'win_rate': row[6],
                        'profit_factor': row[7],
                        'sharpe_ratio': row[8],
                        'max_drawdown': row[9],
                        'last_updated': row[10]
                    }
                return {}
            else:
                cursor.execute('''
                    SELECT strategy, total_trades, wins, losses, total_pnl, avg_pnl,
                           win_rate, profit_factor, sharpe_ratio, max_drawdown, last_updated
                    FROM strategy_summary
                ''')
                results = {}
                for row in cursor.fetchall():
                    results[row[0]] = {
                        'strategy': row[0],
                        'total_trades': row[1],
                        'wins': row[2],
                        'losses': row[3],
                        'total_pnl': row[4],
                        'avg_pnl': row[5],
                        'win_rate': row[6],
                        'profit_factor': row[7],
                        'sharpe_ratio': row[8],
                        'max_drawdown': row[9],
                        'last_updated': row[10]
                    }
                return results
    
    def get_all_trades(self, strategy: str = None, limit: int = 100) -> List[Dict]:
        """Get all trades, optionally filtered by strategy"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if strategy:
                cursor.execute('''
                    SELECT * FROM trades WHERE strategy = ? 
                    ORDER BY entry_time DESC LIMIT ?
                ''', (strategy, limit))
            else:
                cursor.execute('''
                    SELECT * FROM trades 
                    ORDER BY entry_time DESC LIMIT ?
                ''', (limit,))
            
            columns = [description[0] for description in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results
    
    def get_comparison_report(self) -> Dict:
        """Generate a comparison report of all strategies"""
        summaries = self.get_strategy_summary()
        
        if not summaries:
            return {'status': 'no_data', 'message': 'No trades recorded yet'}
        
        # Rank strategies by different metrics
        by_win_rate = sorted(summaries.items(), key=lambda x: x[1]['win_rate'], reverse=True)
        by_pnl = sorted(summaries.items(), key=lambda x: x[1]['total_pnl'], reverse=True)
        by_sharpe = sorted(summaries.items(), key=lambda x: x[1]['sharpe_ratio'], reverse=True)
        by_profit_factor = sorted(summaries.items(), key=lambda x: x[1]['profit_factor'], reverse=True)
        
        return {
            'generated_at': datetime.now().isoformat(),
            'summaries': summaries,
            'rankings': {
                'by_win_rate': [{'strategy': s[0], 'value': s[1]['win_rate']} for s in by_win_rate],
                'by_total_pnl': [{'strategy': s[0], 'value': s[1]['total_pnl']} for s in by_pnl],
                'by_sharpe': [{'strategy': s[0], 'value': s[1]['sharpe_ratio']} for s in by_sharpe],
                'by_profit_factor': [{'strategy': s[0], 'value': s[1]['profit_factor']} for s in by_profit_factor]
            },
            'best_overall': self._determine_best_strategy(summaries),
            'recommendation': self._generate_recommendation(summaries)
        }
    
    def _determine_best_strategy(self, summaries: Dict) -> str:
        """Determine the best performing strategy using weighted scoring"""
        scores = defaultdict(float)
        
        for strategy, stats in summaries.items():
            # Need minimum trades for consideration
            if stats['total_trades'] < 10:
                continue
            
            # Score components (normalized 0-1)
            win_rate_score = stats['win_rate']
            pnl_score = min(stats['total_pnl'] / 10, 1.0)  # Cap at $10
            sharpe_score = min(max(stats['sharpe_ratio'] / 2, 0), 1.0)  # Cap at 2.0
            pf_score = min(stats['profit_factor'] / 3, 1.0)  # Cap at 3.0
            
            # Weighted sum
            scores[strategy] = (
                win_rate_score * 0.30 +
                pnl_score * 0.30 +
                sharpe_score * 0.25 +
                pf_score * 0.15
            )
        
        if not scores:
            return 'insufficient_data'
        
        return max(scores.items(), key=lambda x: x[1])[0]
    
    def _generate_recommendation(self, summaries: Dict) -> str:
        """Generate a trading recommendation based on performance"""
        best = self._determine_best_strategy(summaries)
        
        if best == 'insufficient_data':
            return "Insufficient data. Continue testing all strategies."
        
        stats = summaries.get(best, {})
        
        if stats.get('win_rate', 0) < 0.50:
            return f"{best} is leading but win rate {stats['win_rate']:.1%} is below 50%. Monitor closely."
        
        if stats.get('sharpe_ratio', 0) < 0.5:
            return f"{best} is leading but Sharpe {stats['sharpe_ratio']:.2f} is low. Risk-adjusted returns need improvement."
        
        return f"✅ {best} is the current best strategy. Consider allocating more capital."
    
    def print_report(self):
        """Print a formatted performance report"""
        report = self.get_comparison_report()
        
        print("\n" + "="*70)
        print("STRATEGY PERFORMANCE COMPARISON REPORT")
        print("="*70)
        print(f"Generated: {report.get('generated_at', 'N/A')}")
        print("-"*70)
        
        summaries = report.get('summaries', {})
        if not summaries:
            print("No data available yet.")
            return
        
        print(f"{'Strategy':<20} {'Trades':<8} {'Win%':<8} {'P&L':<10} {'Sharpe':<8} {'PF':<8}")
        print("-"*70)
        
        for strategy, stats in sorted(summaries.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
            print(f"{strategy:<20} {stats['total_trades']:<8} "
                  f"{stats['win_rate']:.1%}    "
                  f"${stats['total_pnl']:+.2f}    "
                  f"{stats['sharpe_ratio']:.2f}    "
                  f"{stats['profit_factor']:.2f}")
        
        print("-"*70)
        print(f"🏆 Best Overall: {report.get('best_overall', 'N/A')}")
        print(f"💡 Recommendation: {report.get('recommendation', 'N/A')}")
        print("="*70 + "\n")


# Global tracker instance
tracker = StrategyPerformanceTracker()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'report':
        tracker.print_report()
    elif len(sys.argv) > 1 and sys.argv[1] == 'test':
        # Add some test data
        print("Adding test data...")
        
        # Mean reversion test trades
        for i in range(5):
            trade = TradeRecord(
                trade_id=f"mr_test_{i}",
                strategy='mean_reversion',
                market_id=f"BTC-5m",
                coin='BTC',
                side='YES' if i % 2 == 0 else 'NO',
                entry_price=0.45,
                exit_price=0.48 if i < 3 else 0.42,
                amount=1.0,
                pnl=0.03 if i < 3 else -0.03,
                pnl_pct=6.67 if i < 3 else -6.67,
                entry_time=datetime.now().isoformat(),
                exit_time=datetime.now().isoformat(),
                exit_reason='profit_target' if i < 3 else 'stop_loss',
                timeframe=5,
                paper_mode=True
            )
            tracker.record_entry(trade)
            tracker.record_exit(trade.trade_id, trade.exit_price, trade.pnl, 
                               trade.pnl_pct, trade.exit_time, trade.exit_reason)
        
        # Momentum test trades
        for i in range(3):
            trade = TradeRecord(
                trade_id=f"mom_test_{i}",
                strategy='momentum',
                market_id=f"ETH-15m",
                coin='ETH',
                side='YES',
                entry_price=0.50,
                exit_price=0.52 if i < 2 else 0.48,
                amount=1.0,
                pnl=0.02 if i < 2 else -0.02,
                pnl_pct=4.0 if i < 2 else -4.0,
                entry_time=datetime.now().isoformat(),
                exit_time=datetime.now().isoformat(),
                exit_reason='take_profit' if i < 2 else 'stop_loss',
                timeframe=15,
                paper_mode=True
            )
            tracker.record_entry(trade)
            tracker.record_exit(trade.trade_id, trade.exit_price, trade.pnl,
                               trade.pnl_pct, trade.exit_time, trade.exit_reason)
        
        print("Test data added. Generating report...")
        tracker.print_report()
    else:
        print("Usage: python3 strategy_performance_tracker.py [report|test]")
        print("  report - Generate performance report")
        print("  test   - Add test data and generate report")
