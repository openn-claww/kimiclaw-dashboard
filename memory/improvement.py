#!/usr/bin/env python3
"""
Self-Improvement Loop for PolyClaw Trading
Logs trades, reflects on outcomes, updates strategy.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path("/root/.openclaw/workspace/memory/memory.db")

class TradingImprovement:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def log_trade_full(self, market_id: str, market_question: str, side: str,
                       size_usd: float, entry_price: float, strategy: str,
                       reasoning: str, risk_percent: float, tags: str = "") -> int:
        """Log complete trade details for later analysis"""
        cursor = self.conn.execute(
            """INSERT INTO trades 
               (market_id, market_question, side, size_usd, entry_price, 
                status, strategy, tags)
               VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
            (market_id, market_question, side, size_usd, entry_price, 
             f"{strategy}|{reasoning}|risk:{risk_percent}%", tags)
        )
        self.conn.commit()
        
        # Also log as conversation for context
        self.conn.execute(
            """INSERT INTO conversations 
               (user_message, assistant_message, tags, importance)
               VALUES (?, ?, ?, 9)""",
            (f"EXECUTED TRADE: {market_id} {side} ${size_usd}",
             f"Strategy: {strategy}. Reasoning: {reasoning}",
             f"trade,executed,{market_id}")
        )
        self.conn.commit()
        
        return cursor.lastrowid
    
    def reflect_on_trade(self, trade_id: int, exit_price: float, 
                         pnl_usd: float, reflection: str) -> Dict:
        """Deep reflection after trade closes"""
        # Calculate metrics
        trade = self.conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        
        if not trade:
            return {"error": "Trade not found"}
        
        entry = trade['entry_price']
        side = trade['side']
        
        # Determine if prediction was correct
        if side == 'YES':
            predicted_outcome = 'YES' if exit_price > entry else 'NO'
            actual_outcome = 'YES' if exit_price >= 0.5 else 'NO'
        else:  # NO
            predicted_outcome = 'NO' if exit_price < entry else 'YES'
            actual_outcome = 'NO' if exit_price < 0.5 else 'YES'
        
        prediction_correct = (predicted_outcome == actual_outcome)
        
        # Update trade
        pnl_percent = (pnl_usd / trade['size_usd']) * 100 if trade['size_usd'] else 0
        self.conn.execute(
            """UPDATE trades SET 
               exit_price = ?, pnl_usd = ?, pnl_percent = ?, 
               status = 'CLOSED', reflection = ?
               WHERE id = ?""",
            (exit_price, pnl_usd, pnl_percent, reflection, trade_id)
        )
        
        # Extract lesson
        lesson_type = "win_pattern" if pnl_usd > 0 else "loss_lesson"
        lesson = f"Trade #{trade_id} ({trade['market_id']}): {reflection}"
        
        self.conn.execute(
            """INSERT INTO memories (type, content, source_trade_id, confidence)
               VALUES (?, ?, ?, ?)""",
            (lesson_type, lesson, trade_id, 8 if abs(pnl_usd) > 1 else 6)
        )
        
        self.conn.commit()
        
        return {
            "trade_id": trade_id,
            "pnl_usd": pnl_usd,
            "pnl_percent": pnl_percent,
            "prediction_correct": prediction_correct,
            "lesson_saved": True
        }
    
    def analyze_period(self, days: int = 2) -> Dict:
        """Analyze trades over N days and generate report"""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Get all trades in period
        trades = self.conn.execute(
            """SELECT * FROM trades 
               WHERE timestamp >= ? 
               ORDER BY timestamp DESC""",
            (since,)
        ).fetchall()
        
        if not trades:
            return {"message": "No trades in this period", "trades": 0}
        
        # Calculate metrics
        total_trades = len(trades)
        closed_trades = [t for t in trades if t['status'] == 'CLOSED']
        winning_trades = [t for t in closed_trades if t['pnl_usd'] and t['pnl_usd'] > 0]
        losing_trades = [t for t in closed_trades if t['pnl_usd'] and t['pnl_usd'] <= 0]
        
        total_pnl = sum(t['pnl_usd'] or 0 for t in closed_trades)
        avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
        
        win_rate = len(winning_trades) / len(closed_trades) * 100 if closed_trades else 0
        
        biggest_win = max((t['pnl_usd'] for t in winning_trades), default=0)
        biggest_loss = min((t['pnl_usd'] for t in losing_trades), default=0)
        
        # Get lessons learned
        lessons = self.conn.execute(
            """SELECT * FROM memories 
               WHERE type IN ('win_pattern', 'loss_lesson') 
               AND timestamp >= ?
               ORDER BY timestamp DESC""",
            (since,)
        ).fetchall()
        
        # Strategy recommendations based on data
        recommendations = []
        
        if win_rate < 50:
            recommendations.append("Win rate below 50% - tighten entry criteria")
        if avg_pnl < 0:
            recommendations.append("Negative average P&L - reduce position sizes")
        if biggest_loss < -2:
            recommendations.append(f"Large loss detected (${biggest_loss:.2f}) - implement tighter stops")
        if len([t for t in winning_trades if t['pnl_percent'] > 10]) > 2:
            recommendations.append("Multiple high-return wins - consider increasing conviction trades")
        
        # Get active positions
        active = [t for t in trades if t['status'] == 'OPEN']
        
        report = {
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_trades": total_trades,
                "closed_trades": len(closed_trades),
                "active_positions": len(active),
                "win_rate_percent": round(win_rate, 1),
                "total_pnl_usd": round(total_pnl, 2),
                "avg_pnl_per_trade": round(avg_pnl, 2),
                "biggest_win": round(biggest_win, 2),
                "biggest_loss": round(biggest_loss, 2)
            },
            "active_positions": [
                {
                    "market_id": t['market_id'],
                    "side": t['side'],
                    "size": t['size_usd'],
                    "entry": t['entry_price']
                } for t in active
            ],
            "lessons_learned": [l['content'] for l in lessons],
            "recommendations": recommendations,
            "strategy_update": self._generate_strategy_update(recommendations, lessons)
        }
        
        # Save report to database
        self.conn.execute(
            """INSERT INTO memories (type, content, confidence)
               VALUES (?, ?, ?)""",
            ("periodic_report", json.dumps(report), 9)
        )
        self.conn.commit()
        
        return report
    
    def _generate_strategy_update(self, recommendations: List[str], lessons) -> str:
        """Generate updated strategy based on analysis"""
        strategy = "Updated Strategy:\n"
        
        if not recommendations:
            strategy += "- Current strategy performing well. Continue with same approach.\n"
        else:
            for rec in recommendations:
                strategy += f"- {rec}\n"
        
        if lessons:
            strategy += "\nKey Patterns:\n"
            for lesson in lessons[:3]:
                strategy += f"- {lesson['content'][:100]}...\n"
        
        return strategy
    
    def get_improvement_stats(self) -> Dict:
        """Get overall improvement metrics"""
        total_lessons = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE type IN ('win_pattern', 'loss_lesson')"
        ).fetchone()[0]
        
        total_reports = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE type = 'periodic_report'"
        ).fetchone()[0]
        
        return {
            "lessons_learned": total_lessons,
            "periodic_reports": total_reports,
            "improvement_active": True
        }
    
    def close(self):
        self.conn.close()

# Singleton
_improvement = None

def get_improvement() -> TradingImprovement:
    global _improvement
    if _improvement is None:
        _improvement = TradingImprovement()
    return _improvement

if __name__ == "__main__":
    import sys
    imp = get_improvement()
    
    if len(sys.argv) < 2:
        print("Usage: python improvement.py {analyze|stats|report}")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "analyze":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        report = imp.analyze_period(days)
        print(json.dumps(report, indent=2, default=str))
    elif cmd == "stats":
        print(json.dumps(imp.get_improvement_stats(), indent=2))
    elif cmd == "report":
        report = imp.analyze_period(2)
        print("=== TRADING PERFORMANCE REPORT ===")
        print(f"Period: Last {report['period_days']} days")
        print(f"Trades: {report['summary']['total_trades']}")
        print(f"Win Rate: {report['summary']['win_rate_percent']}%")
        print(f"Total P&L: ${report['summary']['total_pnl_usd']}")
        print(f"\nRecommendations:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
    else:
        print(f"Unknown command: {cmd}")
