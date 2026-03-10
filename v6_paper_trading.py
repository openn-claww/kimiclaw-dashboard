#!/usr/bin/env python3
"""
v6_paper_trading.py - V6 Paper Trading Launcher with $250 virtual balance
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/root/.openclaw/workspace/v6_paper_trading.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('v6_paper')

# Virtual balance configuration
VIRTUAL_BALANCE = 250.0
PAPER_MODE = True

class PaperTradingMonitor:
    """Monitor V6 paper trading performance."""
    
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.starting_balance = VIRTUAL_BALANCE
        self.current_balance = VIRTUAL_BALANCE
        self.trades = []
        self.wins = 0
        self.losses = 0
        
    def update_from_health(self, health_data: dict):
        """Update stats from bot health file."""
        arb_data = health_data.get('arb_engine', {})
        news_data = health_data.get('news_feed', {})
        
        # Track arb performance
        trades = arb_data.get('trades', 0)
        wins = arb_data.get('wins', 0)
        pnl = arb_data.get('pnl_usd', 0)
        
        self.wins = wins
        self.losses = trades - wins if trades > 0 else 0
        self.current_balance = self.starting_balance + pnl
        
        return {
            'trades': trades,
            'wins': wins,
            'win_rate': (wins / trades * 100) if trades > 0 else 0,
            'pnl': pnl,
            'balance': self.current_balance,
            'roi': (pnl / self.starting_balance * 100) if self.starting_balance > 0 else 0,
            'news_sentiment': news_data.get('sentiment', 'UNKNOWN'),
            'news_confidence': news_data.get('confidence', 0),
        }
    
    def get_summary(self) -> dict:
        """Get current summary."""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        hours = elapsed / 3600
        
        return {
            'started_at': self.start_time.isoformat(),
            'elapsed_hours': round(hours, 2),
            'starting_balance': self.starting_balance,
            'current_balance': round(self.current_balance, 2),
            'pnl': round(self.current_balance - self.starting_balance, 2),
            'roi_pct': round((self.current_balance - self.starting_balance) / self.starting_balance * 100, 2),
            'trades': self.wins + self.losses,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(self.wins / (self.wins + self.losses) * 100, 1) if (self.wins + self.losses) > 0 else 0,
        }

def main():
    """Start paper trading monitor."""
    log.info("=" * 70)
    log.info("     V6 PAPER TRADING - $250 Virtual Balance")
    log.info("=" * 70)
    log.info(f"Starting virtual balance: ${VIRTUAL_BALANCE}")
    log.info(f"Paper mode: {PAPER_MODE}")
    log.info(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    log.info("=" * 70)
    
    monitor = PaperTradingMonitor()
    
    # Save initial state
    state_file = '/root/.openclaw/workspace/v6_paper_state.json'
    with open(state_file, 'w') as f:
        json.dump(monitor.get_summary(), f, indent=2)
    
    log.info(f"Initial state saved to: {state_file}")
    log.info("")
    log.info("To start the actual V6 bot, run:")
    log.info("  export POLY_PAPER_TRADING=true")
    log.info("  export VIRTUAL_BALANCE=250")
    log.info("  python master_bot_v6_polyclaw_integration.py")
    log.info("")
    log.info("Monitoring will continue in background...")
    
    # Monitor loop
    try:
        while True:
            time.sleep(60)  # Check every minute
            
            # Try to read health file
            health_file = '/root/.openclaw/workspace/master_v6_health.json'
            try:
                with open(health_file) as f:
                    health = json.load(f)
                
                stats = monitor.update_from_health(health)
                summary = monitor.get_summary()
                
                # Log every 10 minutes
                if int(time.time()) % 600 < 60:
                    log.info(f"[UPDATE] Balance: ${summary['current_balance']:.2f} | "
                            f"PnL: ${summary['pnl']:.2f} ({summary['roi_pct']:+.2f}%) | "
                            f"Trades: {summary['trades']} | "
                            f"Win Rate: {summary['win_rate']:.1f}%")
                
                # Save state
                with open(state_file, 'w') as f:
                    json.dump(summary, f, indent=2)
                    
            except FileNotFoundError:
                pass  # Bot not running yet
            except Exception as e:
                log.debug(f"Health read error: {e}")
                
    except KeyboardInterrupt:
        log.info("\nMonitoring stopped.")
        summary = monitor.get_summary()
        log.info(f"Final Summary: {json.dumps(summary, indent=2)}")

if __name__ == '__main__':
    main()
