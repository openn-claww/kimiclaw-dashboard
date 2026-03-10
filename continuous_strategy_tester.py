#!/usr/bin/env python3
"""
continuous_strategy_tester.py - 24/7 Strategy Testing Agent
Runs multiple strategies in parallel, tracks performance, and auto-selects best performer.
"""

import os
import sys
import json
import time
import signal
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/root/.openclaw/workspace/continuous_tester.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('continuous_tester')

WORKSPACE = Path('/root/.openclaw/workspace')

@dataclass
class StrategyConfig:
    """Configuration for a strategy"""
    name: str
    enabled: bool
    paper_mode: bool
    allocation_pct: float  # Percentage of total bankroll
    min_trades: int = 50
    min_hours: int = 24
    timeframe: str = "5m,15m"
    coins: str = "BTC,ETH,SOL,XRP"

class ContinuousStrategyTester:
    """
    Continuous testing agent that:
    1. Monitors all strategies in parallel
    2. Tracks performance metrics
    3. Compares strategies head-to-head
    4. Auto-selects best performer
    5. Reports failures and successes
    """
    
    STRATEGIES = ['mean_reversion', 'momentum', 'arbitrage', 'external_arb']
    
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.metrics: Dict[str, Dict] = {}
        self.last_report_time = time.time()
        self.report_interval = 3600  # Hourly reports
        self.summary_interval = 300  # Summary every 5 minutes
        
        # Strategy configurations
        self.configs = {
            'mean_reversion': StrategyConfig(
                name='mean_reversion',
                enabled=os.getenv('MEANREV_ENABLED', 'true').lower() == 'true',
                paper_mode=True,
                allocation_pct=0.20,
                min_trades=50,
                min_hours=24
            ),
            'momentum': StrategyConfig(
                name='momentum',
                enabled=True,
                paper_mode=True,
                allocation_pct=0.40,
                min_trades=50,
                min_hours=24
            ),
            'arbitrage': StrategyConfig(
                name='arbitrage',
                enabled=True,
                paper_mode=True,
                allocation_pct=0.30,
                min_trades=30,
                min_hours=12
            ),
            'external_arb': StrategyConfig(
                name='external_arb',
                enabled=True,
                paper_mode=True,
                allocation_pct=0.10,
                min_trades=20,
                min_hours=12
            )
        }
        
        self.start_time = time.time()
        
        # Load strategy performance tracker
        try:
            from strategy_performance_tracker import StrategyPerformanceTracker
            self.tracker = StrategyPerformanceTracker()
            log.info("✅ Strategy performance tracker loaded")
        except ImportError as e:
            log.error(f"❌ Could not load tracker: {e}")
            self.tracker = None
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        log.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self):
        """Start the continuous testing agent"""
        log.info("="*70)
        log.info("CONTINUOUS STRATEGY TESTING AGENT STARTED")
        log.info("="*70)
        log.info(f"Strategies: {[s for s, c in self.configs.items() if c.enabled]}")
        log.info(f"Paper mode: All strategies")
        log.info(f"Min trades per strategy: {min(c.min_trades for c in self.configs.values())}")
        log.info(f"Min test duration: {min(c.min_hours for c in self.configs.values())} hours")
        log.info("="*70)
        
        self.running = True
        
        # Start monitoring threads
        threads = [
            threading.Thread(target=self._monitor_trades, name='trade_monitor', daemon=True),
            threading.Thread(target=self._hourly_report, name='hourly_reporter', daemon=True),
            threading.Thread(target=self._performance_summary, name='summary_reporter', daemon=True),
            threading.Thread(target=self._health_check, name='health_checker', daemon=True),
        ]
        
        for t in threads:
            t.start()
            log.info(f"Started thread: {t.name}")
        
        # Main loop
        try:
            while self.running and not self.stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the testing agent"""
        log.info("Stopping continuous testing agent...")
        self.running = False
        self.stop_event.set()
        self._generate_final_report()
    
    def _monitor_trades(self):
        """Monitor trades from the bot's log files"""
        log.info("[Monitor] Starting trade monitor")
        
        trade_files = {
            'mean_reversion': WORKSPACE / 'mean_reversion_trades.json',
            'momentum': WORKSPACE / 'master_v6_meanrev_trades.json',
            'arbitrage': WORKSPACE / 'master_v6_meanrev_trades.json',
        }
        
        last_check = {k: 0 for k in trade_files.keys()}
        
        while not self.stop_event.is_set():
            try:
                # Check each trade file for new trades
                for strategy, filepath in trade_files.items():
                    if not filepath.exists():
                        continue
                    
                    try:
                        mtime = filepath.stat().st_mtime
                        if mtime > last_check[strategy]:
                            last_check[strategy] = mtime
                            self._process_new_trades(strategy, filepath)
                    except Exception as e:
                        log.debug(f"[Monitor] Error checking {strategy}: {e}")
                
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                log.error(f"[Monitor] Error: {e}")
                time.sleep(10)
    
    def _process_new_trades(self, strategy: str, filepath: Path):
        """Process new trades from a file"""
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            trades = data.get('trades', [])
            if not trades:
                return
            
            # Filter for this strategy
            strategy_trades = [t for t in trades if t.get('strategy') == strategy or 
                             (strategy == 'mean_reversion' and t.get('type') == 'MEAN_REVERSION')]
            
            if strategy_trades:
                log.info(f"[Monitor] {strategy}: {len(strategy_trades)} trades found")
                
        except Exception as e:
            log.debug(f"[Monitor] Error processing {strategy}: {e}")
    
    def _hourly_report(self):
        """Generate hourly performance reports"""
        while not self.stop_event.is_set():
            try:
                time.sleep(self.report_interval)
                
                if not self.running:
                    break
                
                log.info("="*70)
                log.info("HOURLY PERFORMANCE REPORT")
                log.info("="*70)
                
                elapsed = time.time() - self.start_time
                log.info(f"Elapsed time: {elapsed/3600:.1f} hours")
                
                if self.tracker:
                    self.tracker.print_report()
                else:
                    log.warning("Tracker not available")
                
                # Check if any strategy has met minimum requirements
                self._check_strategy_milestones()
                
                log.info("="*70)
                
            except Exception as e:
                log.error(f"[Hourly] Error: {e}")
    
    def _performance_summary(self):
        """Generate brief performance summaries every 5 minutes"""
        while not self.stop_event.is_set():
            try:
                time.sleep(self.summary_interval)
                
                if not self.running:
                    break
                
                elapsed = time.time() - self.start_time
                elapsed_str = str(timedelta(seconds=int(elapsed)))
                
                # Get current stats from tracker
                if self.tracker:
                    summaries = self.tracker.get_strategy_summary()
                    
                    total_trades = sum(s.get('total_trades', 0) for s in summaries.values())
                    total_pnl = sum(s.get('total_pnl', 0) for s in summaries.values())
                    
                    log.info(f"[Summary] Uptime: {elapsed_str} | Total trades: {total_trades} | Total P&L: ${total_pnl:+.2f}")
                    
                    for strategy, stats in summaries.items():
                        if stats.get('total_trades', 0) > 0:
                            log.info(f"[Summary] {strategy}: {stats['total_trades']} trades, "
                                   f"{stats['win_rate']:.1%} WR, ${stats['total_pnl']:+.2f} P&L")
                else:
                    log.info(f"[Summary] Uptime: {elapsed_str} | Tracker not ready")
                
            except Exception as e:
                log.error(f"[Summary] Error: {e}")
    
    def _health_check(self):
        """Check bot health and file statuses"""
        while not self.stop_event.is_set():
            try:
                time.sleep(60)  # Check every minute
                
                if not self.running:
                    break
                
                # Check if health file is being updated
                health_file = WORKSPACE / 'master_v6_meanrev_health.json'
                if health_file.exists():
                    mtime = health_file.stat().st_mtime
                    age = time.time() - mtime
                    if age > 120:  # No update in 2 minutes
                        log.warning(f"[Health] Health file stale ({age:.0f}s) - bot may be stuck")
                    else:
                        log.debug(f"[Health] Bot healthy (last update {age:.0f}s ago)")
                else:
                    log.warning("[Health] Health file not found")
                
            except Exception as e:
                log.error(f"[Health] Error: {e}")
    
    def _check_strategy_milestones(self):
        """Check if any strategy has met minimum testing requirements"""
        if not self.tracker:
            return
        
        summaries = self.tracker.get_strategy_summary()
        elapsed_hours = (time.time() - self.start_time) / 3600
        
        for strategy, stats in summaries.items():
            config = self.configs.get(strategy)
            if not config:
                continue
            
            trades = stats.get('total_trades', 0)
            meets_trades = trades >= config.min_trades
            meets_time = elapsed_hours >= config.min_hours
            
            if meets_trades and meets_time:
                log.info(f"🎯 [Milestone] {strategy} has met minimum requirements: "
                        f"{trades} trades over {elapsed_hours:.1f} hours")
                
                # Check if it's a candidate for best strategy
                win_rate = stats.get('win_rate', 0)
                if win_rate >= 0.55 and stats.get('total_pnl', 0) > 0:
                    log.info(f"✅ [Candidate] {strategy} is viable: {win_rate:.1%} win rate, "
                            f"${stats.get('total_pnl', 0):+.2f} P&L")
    
    def _generate_final_report(self):
        """Generate final comprehensive report"""
        log.info("="*70)
        log.info("FINAL COMPREHENSIVE REPORT")
        log.info("="*70)
        
        elapsed = time.time() - self.start_time
        log.info(f"Total runtime: {elapsed/3600:.1f} hours")
        
        if self.tracker:
            report = self.tracker.get_comparison_report()
            
            log.info("\nSTRATEGY PERFORMANCE:")
            for strategy, stats in report.get('summaries', {}).items():
                log.info(f"  {strategy}:")
                log.info(f"    Trades: {stats['total_trades']} (W: {stats['wins']} L: {stats['losses']})")
                log.info(f"    Win Rate: {stats['win_rate']:.1%}")
                log.info(f"    Total P&L: ${stats['total_pnl']:+.2f}")
                log.info(f"    Sharpe: {stats['sharpe_ratio']:.2f}")
                log.info(f"    Profit Factor: {stats['profit_factor']:.2f}")
            
            log.info(f"\n🏆 BEST OVERALL: {report.get('best_overall', 'N/A')}")
            log.info(f"💡 RECOMMENDATION: {report.get('recommendation', 'N/A')}")
        
        # Save report to file
        report_file = WORKSPACE / f"final_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        if self.tracker:
            report = self.tracker.get_comparison_report()
            report['runtime_seconds'] = elapsed
            report['runtime_hours'] = elapsed / 3600
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            log.info(f"\nReport saved to: {report_file}")
        
        log.info("="*70)


def main():
    """Main entry point"""
    tester = ContinuousStrategyTester()
    
    try:
        tester.start()
    except Exception as e:
        log.critical(f"Fatal error: {e}", exc_info=True)
        tester.stop()
        sys.exit(1)


if __name__ == '__main__':
    main()
