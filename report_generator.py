#!/usr/bin/env python3
"""
Automated Reporting System
Daily and weekly P&L reports with insights
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, '/root/.openclaw/workspace')
from data_aggregator import DataAggregator

DB_PATH = Path("/root/.openclaw/skills/polytrader/trades.db")
REPORTS_DIR = Path("/root/.openclaw/workspace/reports")
REPORTS_DIR.mkdir(exist_ok=True)

class ReportGenerator:
    def __init__(self):
        self.aggregator = DataAggregator()
    
    def get_trade_stats(self, days=1):
        """Get trade statistics for period"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Period trades
        period_trades = conn.execute(
            "SELECT * FROM trades WHERE date(timestamp) >= ?",
            (since,)
        ).fetchall()
        
        # All trades
        all_trades = conn.execute("SELECT * FROM trades").fetchall()
        
        # Calculate stats
        total_pnl = sum(t['pnl_usd'] or 0 for t in all_trades)
        period_pnl = sum(t['pnl_usd'] or 0 for t in period_trades if t['pnl_usd'])
        
        open_positions = [t for t in all_trades if t['status'] == 'OPEN']
        closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']
        
        wins = len([t for t in closed_trades if (t['pnl_usd'] or 0) > 0])
        losses = len([t for t in closed_trades if (t['pnl_usd'] or 0) <= 0])
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0
        
        total_invested = sum(t['size_usd'] for t in all_trades)
        
        conn.close()
        
        return {
            'period_days': days,
            'period_trades': len(period_trades),
            'total_trades': len(all_trades),
            'open_positions': len(open_positions),
            'closed_trades': len(closed_trades),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'period_pnl': period_pnl,
            'total_invested': total_invested,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested else 0,
            'avg_trade_size': total_invested / len(all_trades) if all_trades else 0
        }
    
    def generate_daily_report(self):
        """Generate daily report"""
        print("Generating daily report...")
        
        stats = self.get_trade_stats(days=1)
        market_data = self.aggregator.get_coingecko_data('bitcoin')
        opportunities = self.aggregator.scan_opportunities()
        
        report = {
            'type': 'daily',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'trades_today': stats['period_trades'],
                'total_trades': stats['total_trades'],
                'open_positions': stats['open_positions'],
                'pnl_today': stats['period_pnl'],
                'total_pnl': stats['total_pnl'],
                'win_rate': stats['win_rate'],
                'roi_percent': stats['roi_percent']
            },
            'market_data': market_data,
            'opportunities': opportunities,
            'insights': self._generate_insights(stats, opportunities)
        }
        
        # Save
        filename = f"daily_{datetime.now().strftime('%Y%m%d')}.json"
        with open(REPORTS_DIR / filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def generate_weekly_report(self):
        """Generate weekly report"""
        print("Generating weekly report...")
        
        stats = self.get_trade_stats(days=7)
        
        report = {
            'type': 'weekly',
            'week_ending': datetime.now().strftime('%Y-%m-%d'),
            'generated_at': datetime.now().isoformat(),
            'summary': stats,
            'performance': self._calculate_performance_metrics(stats),
            'recommendations': self._generate_recommendations(stats)
        }
        
        filename = f"weekly_{datetime.now().strftime('%Y%m%d')}.json"
        with open(REPORTS_DIR / filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def _generate_insights(self, stats, opportunities):
        """Generate trading insights"""
        insights = []
        
        if stats['win_rate'] > 50:
            insights.append(f"✅ Win rate is strong at {stats['win_rate']:.1f}%")
        elif stats['win_rate'] < 30 and stats['closed_trades'] > 5:
            insights.append(f"⚠️  Win rate is low at {stats['win_rate']:.1f}% - review strategy")
        
        if stats['roi_percent'] > 10:
            insights.append(f"🚀 Excellent ROI: {stats['roi_percent']:.2f}%")
        elif stats['roi_percent'] < -10:
            insights.append(f"📉 Negative ROI: {stats['roi_percent']:.2f}% - consider risk management")
        
        if opportunities:
            insights.append(f"🎯 {len(opportunities)} trading opportunity(s) detected")
        
        if stats['open_positions'] > 5:
            insights.append(f"📊 High position count: {stats['open_positions']} open trades")
        
        return insights
    
    def _calculate_performance_metrics(self, stats):
        """Calculate advanced performance metrics"""
        return {
            'sharpe_ratio': 'N/A',  # Would need returns history
            'max_drawdown': 'N/A',  # Would need equity curve
            'profit_factor': abs(stats['total_pnl']) / (stats['total_invested'] - stats['total_pnl']) if stats['total_invested'] != stats['total_pnl'] else 0,
            'risk_adjusted_return': stats['roi_percent'] / stats['open_positions'] if stats['open_positions'] else 0
        }
    
    def _generate_recommendations(self, stats):
        """Generate trading recommendations"""
        recs = []
        
        if stats['win_rate'] < 40:
            recs.append("Consider reducing position sizes until win rate improves")
        
        if stats['open_positions'] > 10:
            recs.append("High number of open positions - consider closing some")
        
        if stats['avg_trade_size'] < 1:
            recs.append("Small average trade size - confidence may be low")
        
        recs.append("Continue monitoring BTC/ETH markets for opportunities")
        
        return recs
    
    def print_report(self, report):
        """Print formatted report"""
        print("\n" + "="*60)
        print(f"📊 {report['type'].upper()} TRADING REPORT")
        print("="*60)
        
        summary = report['summary']
        print(f"\n📈 Summary:")
        print(f"   Period Trades: {summary['trades_today'] if 'trades_today' in summary else summary['period_trades']}")
        print(f"   Total Trades: {summary['total_trades']}")
        print(f"   Open Positions: {summary['open_positions']}")
        print(f"   Win Rate: {summary['win_rate']:.1f}%")
        print(f"   Total P&L: ${summary['total_pnl']:.2f}")
        print(f"   ROI: {summary['roi_percent']:.2f}%")
        
        if 'insights' in report:
            print(f"\n💡 Insights:")
            for insight in report['insights']:
                print(f"   {insight}")
        
        if 'opportunities' in report and report['opportunities']:
            print(f"\n🎯 Opportunities:")
            for opp in report['opportunities']:
                print(f"   {opp['market']}: {opp['recommendation']} (edge: {opp['edge']:.1%})")
        
        print("="*60 + "\n")

def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', choices=['daily', 'weekly'], default='daily')
    args = parser.parse_args()
    
    generator = ReportGenerator()
    
    if args.type == 'daily':
        report = generator.generate_daily_report()
    else:
        report = generator.generate_weekly_report()
    
    generator.print_report(report)
    
    print(f"✅ Report saved to: {REPORTS_DIR}")

if __name__ == "__main__":
    main()
