#!/usr/bin/env python3
"""
mean_reversion_integration.py - Integration module for MasterBot V6

This module integrates the mean reversion strategy into the existing bot
infrastructure. It runs alongside momentum and arbitrage strategies.
"""

import json
import time
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass

# Import the mean reversion engine
try:
    from mean_reversion_bot import MeanReversionStrategy, MeanRevSignal
    _MEANREV_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Mean reversion module not available: {e}")
    _MEANREV_AVAILABLE = False
    MeanReversionStrategy = None
    MeanRevSignal = None


log = logging.getLogger('mean_rev_integration')


@dataclass
class MeanRevTradeResult:
    """Result of a mean reversion trade"""
    success: bool
    market_id: str
    side: str
    amount: float
    fill_price: float
    shares: float
    error: Optional[str] = None


class MeanReversionIntegration:
    """
    Integration layer for mean reversion strategy in MasterBot V6.
    
    This class:
    1. Manages the mean reversion strategy engine
    2. Interfaces with the bot's position tracking
    3. Handles trade execution (paper or live)
    4. Reports performance metrics
    """
    
    def __init__(self, bot_instance, bankroll: float = 5.0):
        """
        Initialize integration
        
        Args:
            bot_instance: The MasterBotV6 instance
            bankroll: Starting bankroll for this strategy
        """
        self.bot = bot_instance
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        
        if not _MEANREV_AVAILABLE or MeanReversionStrategy is None:
            log.error("Mean Reversion Strategy not available - integration disabled")
            self.engine = None
            self.enabled = False
            return
        
        # Create the strategy engine
        self.engine = MeanReversionStrategy(bankroll=bankroll)
        self.enabled = True
        
        # Track which markets we've registered prices for
        self.price_registry: Dict[str, Dict] = {}
        
        log.info(f"✅ Mean Reversion Integration initialized with ${bankroll:.2f} bankroll")
    
    def update_market_data(self, coin: str, yes_price: float, no_price: float,
                          timeframe: int = 5, market_data: Dict = None):
        """
        Update market data for mean reversion calculations
        
        Args:
            coin: Cryptocurrency (BTC, ETH, SOL, XRP)
            yes_price: Current YES price
            no_price: Current NO price
            timeframe: Timeframe in minutes (5 or 15)
            market_data: Optional additional market data
        """
        if not self.enabled or self.engine is None:
            return
        
        # Update price in engine
        self.engine.update_price(coin, yes_price, no_price, timeframe)
        
        # Store market data for trade execution
        key = f"{coin.upper()}-{timeframe}m"
        self.price_registry[key] = {
            'coin': coin,
            'yes_price': yes_price,
            'no_price': no_price,
            'timeframe': timeframe,
            'market_data': market_data or {},
            'timestamp': time.time()
        }
    
    def evaluate_and_trade(self, coin: str, yes_price: float, no_price: float,
                          timeframe: int = 5, market_data: Dict = None,
                          paper_mode: bool = True) -> Optional[MeanRevTradeResult]:
        """
        Evaluate mean reversion signal and execute trade if conditions met
        
        Args:
            coin: Cryptocurrency
            yes_price: Current YES price
            no_price: Current NO price
            timeframe: Timeframe in minutes
            market_data: Additional market data (clobTokenIds, etc.)
            paper_mode: If True, simulate trades
            
        Returns:
            TradeResult if trade executed, None otherwise
        """
        if not self.enabled or self.engine is None:
            return None
        
        # Update data
        self.update_market_data(coin, yes_price, no_price, timeframe, market_data)
        
        # Generate signal
        signal = self.engine.generate_signal(coin, yes_price, no_price, timeframe)
        if signal is None:
            return None
        
        # Check if we already have a position for this market in bot
        market_id = f"{coin.upper()}-{timeframe}m"
        if hasattr(self.bot, '_active_positions') and market_id in self.bot._active_positions:
            log.debug(f"Mean Rev: Already in position for {market_id}")
            return None
        
        # Calculate position size
        amount = self.engine.calculate_position_size(signal)
        if amount <= 0.10:  # Minimum bet
            log.debug(f"Mean Rev: Position size too small (${amount:.2f})")
            return None
        
        # Check if we have enough bankroll
        if amount > self.bankroll * 0.5:  # Don't risk more than 50% on one trade
            log.debug(f"Mean Rev: Position size exceeds risk limit")
            return None
        
        # Execute trade
        if paper_mode:
            result = self._execute_paper_trade(signal, amount, market_data)
        else:
            result = self._execute_live_trade(signal, amount, market_data)
        
        if result and result.success:
            # Record in engine
            self.engine.enter_position(signal, amount,
                yes_asset_id=market_data.get('yes_asset_id', '') if market_data else '',
                no_asset_id=market_data.get('no_asset_id', '') if market_data else '')
            
            log.info(f"✅ Mean Rev Trade: {market_id} {signal.side} ${amount:.2f} @ {signal.entry_price:.3f}")
        
        return result
    
    def _execute_paper_trade(self, signal: MeanRevSignal, amount: float,
                            market_data: Dict) -> MeanRevTradeResult:
        """Execute paper trade"""
        market_id = f"{signal.coin.upper()}-{signal.timeframe}m"
        
        # Calculate shares
        shares = amount / signal.entry_price if signal.entry_price > 0 else 0
        
        return MeanRevTradeResult(
            success=True,
            market_id=market_id,
            side=signal.side,
            amount=amount,
            fill_price=signal.entry_price,
            shares=shares
        )
    
    def _execute_live_trade(self, signal: MeanRevSignal, amount: float,
                           market_data: Dict) -> MeanRevTradeResult:
        """Execute live trade via PolyClaw"""
        market_id = f"{signal.coin.upper()}-{signal.timeframe}m"
        
        try:
            # Use PolyClaw CLI for execution
            import subprocess
            
            cmd = [
                'bash', '-c',
                f'cd /root/.openclaw/skills/polyclaw && source .env && '
                f'uv run python scripts/polyclaw.py buy {market_id} {signal.side} {amount:.2f}'
            ]
            
            log.info(f"[LIVE] Mean Rev executing: {market_id} {signal.side} ${amount:.2f}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and "Trade executed successfully" in result.stdout:
                # Parse TX from output
                tx_match = None
                for line in result.stdout.split('\n'):
                    if 'Split TX:' in line:
                        tx_match = line.split('Split TX:')[1].strip()
                        break
                
                shares = amount / signal.entry_price if signal.entry_price > 0 else 0
                
                return MeanRevTradeResult(
                    success=True,
                    market_id=market_id,
                    side=signal.side,
                    amount=amount,
                    fill_price=signal.entry_price,
                    shares=shares
                )
            else:
                return MeanRevTradeResult(
                    success=False,
                    market_id=market_id,
                    side=signal.side,
                    amount=amount,
                    fill_price=signal.entry_price,
                    shares=0,
                    error=result.stderr or "CLI execution failed"
                )
        except Exception as e:
            log.error(f"Mean Rev live trade failed: {e}")
            return MeanRevTradeResult(
                success=False,
                market_id=market_id,
                side=signal.side,
                amount=amount,
                fill_price=signal.entry_price,
                shares=0,
                error=str(e)
            )
    
    def check_exits(self, market_id: str, yes_price: float, no_price: float,
                   paper_mode: bool = True) -> Optional[Dict]:
        """
        Check if any mean reversion positions should be exited
        
        Args:
            market_id: Market identifier
            yes_price: Current YES price
            no_price: Current NO price
            paper_mode: If True, simulate exits
            
        Returns:
            Exit info dict if position exited, None otherwise
        """
        if not self.enabled or self.engine is None:
            return None
        
        # Check for exit signal
        exit_info = self.engine.check_exit(market_id, yes_price, no_price)
        if exit_info is None:
            return None
        
        # Execute exit
        trade_record = self.engine.exit_position(market_id, exit_info)
        
        # Update bankroll
        pnl = exit_info['pnl']
        self.bankroll += pnl
        
        # Notify bot of exit if it has position tracking
        if hasattr(self.bot, '_execute_exit'):
            # Find position in bot
            if hasattr(self.bot, '_active_positions') and market_id in self.bot._active_positions:
                pos = self.bot._active_positions[market_id]
                
                # Create exit reason enum if available
                try:
                    from master_bot_v6_polyclaw_integration import ExitReason
                    
                    reason_map = {
                        'rsi_reversion': ExitReason.TAKE_PROFIT,
                        'profit_target': ExitReason.TAKE_PROFIT,
                        'stop_loss': ExitReason.STOP_LOSS,
                        'time_stop': ExitReason.TIME_STOP
                    }
                    reason = reason_map.get(exit_info['exit_reason'], ExitReason.TAKE_PROFIT)
                    
                    # Get exit price
                    exit_price = exit_info['exit_price']
                    
                    # Call bot's exit handler
                    self.bot._execute_exit(pos, reason, exit_price)
                except Exception as e:
                    log.debug(f"Could not notify bot of exit: {e}")
        
        return trade_record
    
    def get_allocation(self) -> float:
        """Get current strategy allocation (how much of bankroll is available)"""
        if not self.enabled or self.engine is None:
            return 0.0
        return self.engine.bankroll
    
    def get_stats(self) -> Dict:
        """Get strategy performance statistics"""
        if not self.enabled or self.engine is None:
            return {'enabled': False}
        
        stats = self.engine.get_stats()
        stats['strategy'] = 'mean_reversion'
        stats['enabled'] = True
        stats['allocation'] = self.bankroll
        stats['allocation_pct'] = self.bankroll / self.initial_bankroll if self.initial_bankroll > 0 else 0
        
        return stats
    
    def get_status(self) -> Dict:
        """Get status for health monitoring"""
        if not self.enabled:
            return {'enabled': False, 'reason': 'module_not_available'}
        
        return {
            'enabled': True,
            'bankroll': round(self.bankroll, 2),
            'open_positions': len(self.engine.positions) if self.engine else 0,
            'total_trades': self.engine.stats['trades'] if self.engine else 0,
            'win_rate': self.engine.get_stats().get('win_rate', 0) if self.engine else 0
        }
    
    def reset(self):
        """Reset strategy state"""
        if self.engine:
            self.engine = MeanReversionStrategy(bankroll=self.initial_bankroll)
        self.bankroll = self.initial_bankroll
        self.price_registry.clear()
        log.info("Mean Reversion Strategy reset")


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

def run_comprehensive_backtest(n_simulations: int = 500, n_steps: int = 1000,
                                bankroll: float = 5.0) -> Dict:
    """
    Run comprehensive Monte Carlo backtest
    """
    import random
    from mean_reversion_bot import MeanReversionStrategy
    
    log.info(f"Running {n_simulations} Monte Carlo simulations...")
    
    all_results = []
    
    for sim in range(n_simulations):
        engine = MeanReversionStrategy(bankroll=bankroll)
        random.seed(sim)
        
        # Generate mean-reverting price path
        price = random.uniform(0.40, 0.60)
        volatility = random.uniform(0.015, 0.035)
        mean_reversion_strength = random.uniform(0.08, 0.15)
        
        for i in range(n_steps):
            # Mean-reverting random walk
            drift = mean_reversion_strength * (0.50 - price)
            noise = random.gauss(0, volatility)
            price = max(0.05, min(0.95, price + drift + noise))
            
            yes_price = price
            no_price = 1 - price
            
            # Update and evaluate
            engine.update_price('BTC', yes_price, no_price, 5)
            
            # Check entries
            signal = engine.generate_signal('BTC', yes_price, no_price, 5)
            if signal:
                amount = engine.calculate_position_size(signal)
                if amount >= 0.10:
                    engine.enter_position(signal, amount)
            
            # Check exits
            for market_id in list(engine.positions.keys()):
                exit_info = engine.check_exit(market_id, yes_price, no_price)
                if exit_info:
                    engine.exit_position(market_id, exit_info)
        
        # Close any remaining positions at current price
        for market_id in list(engine.positions.keys()):
            exit_info = engine.check_exit(market_id, yes_price, no_price)
            if exit_info:
                engine.exit_position(market_id, exit_info)
        
        stats = engine.get_stats()
        all_results.append({
            'final_bankroll': engine.bankroll,
            'trades': stats['trades'],
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': stats['win_rate'],
            'profit': stats['profit'],
            'roi_pct': stats['roi_pct'],
            'sharpe': stats.get('sharpe', 0),
            'expectancy': stats.get('expectancy', 0)
        })
    
    # Aggregate statistics
    total_trades = sum(r['trades'] for r in all_results)
    profitable = sum(1 for r in all_results if r['profit'] > 0)
    
    win_rates = [r['win_rate'] for r in all_results if r['trades'] > 0]
    profits = [r['profit'] for r in all_results]
    rois = [r['roi_pct'] for r in all_results]
    sharpes = [r['sharpe'] for r in all_results if r['trades'] > 0]
    
    return {
        'simulations': n_simulations,
        'total_trades': total_trades,
        'avg_trades_per_sim': total_trades / n_simulations,
        'profitable_sims': profitable,
        'profitable_pct': profitable / n_simulations,
        'avg_win_rate': sum(win_rates) / len(win_rates) if win_rates else 0,
        'avg_profit': sum(profits) / len(profits),
        'avg_roi_pct': sum(rois) / len(rois),
        'avg_sharpe': sum(sharpes) / len(sharpes) if sharpes else 0,
        'median_profit': sorted(profits)[len(profits)//2],
        'worst_case': min(profits),
        'best_case': max(profits),
        'std_profit': (sum((p - sum(profits)/len(profits))**2 for p in profits) / len(profits)) ** 0.5,
        'initial_bankroll': bankroll
    }


def print_backtest_report(results: Dict):
    """Print formatted backtest report"""
    print("\n" + "=" * 70)
    print("  MEAN REVERSION STRATEGY - COMPREHENSIVE BACKTEST REPORT")
    print("=" * 70)
    print(f"\n  SIMULATION PARAMETERS:")
    print(f"    Simulations:      {results['simulations']}")
    print(f"    Total trades:     {results['total_trades']}")
    print(f"    Initial bankroll: ${results['initial_bankroll']:.2f}")
    
    print(f"\n  PERFORMANCE METRICS:")
    print(f"    Profitable sims:  {results['profitable_sims']}/{results['simulations']} ({results['profitable_pct']:.1%})")
    print(f"    Avg win rate:     {results['avg_win_rate']:.1%}")
    print(f"    Avg profit:       ${results['avg_profit']:.2f}")
    print(f"    Avg ROI:          {results['avg_roi_pct']:+.2f}%")
    print(f"    Avg Sharpe:       {results['avg_sharpe']:.2f}")
    print(f"    Median profit:    ${results['median_profit']:.2f}")
    
    print(f"\n  RISK METRICS:")
    print(f"    Worst case:       ${results['worst_case']:.2f}")
    print(f"    Best case:        ${results['best_case']:.2f}")
    print(f"    Std dev:          ${results['std_profit']:.2f}")
    
    print(f"\n  KELLY CRITERION CALCULATION:")
    w = results['avg_win_rate']
    if results['avg_win_rate'] > 0:
        # Estimate avg win/loss from profit and trade count
        avg_trade = results['avg_profit'] / max(results['avg_trades_per_sim'], 1)
        
        # For prediction markets with ~50c entries
        avg_win = avg_trade / w if w > 0 else 0
        avg_loss = abs(avg_trade) / (1 - w) if w < 1 else 1
        
        # b = avg_win / avg_loss
        b = avg_win / max(avg_loss, 0.001)
        
        # Kelly = (bp - q) / b
        p = w
        q = 1 - w
        kelly = (b * p - q) / max(b, 0.001)
        kelly = max(0, min(kelly, 0.5))  # Cap at 50%
        
        print(f"    Win rate (p):     {w:.1%}")
        print(f"    Loss rate (q):    {q:.1%}")
        print(f"    Avg win:loss (b): {b:.2f}")
        print(f"    Full Kelly:       {kelly:.1%}")
        print(f"    Quarter Kelly:    {kelly * 0.25:.1%}")
        print(f"    Suggested bet:    ${results['initial_bankroll'] * kelly * 0.25:.2f}")
    
    print(f"\n  VERDICT:")
    if results['avg_win_rate'] >= 0.55 and results['avg_profit'] > 0:
        print("  ✅ STRATEGY IS VIABLE FOR LIVE TRADING")
        print(f"     - Win rate {results['avg_win_rate']:.1%} > 55% threshold")
        print(f"     - Positive average profit: ${results['avg_profit']:.2f}")
        print(f"     - Profitable in {results['profitable_pct']:.1%} of simulations")
    else:
        print("  ❌ STRATEGY NEEDS IMPROVEMENT")
        if results['avg_win_rate'] < 0.55:
            print(f"     - Win rate {results['avg_win_rate']:.1%} < 55% threshold")
        if results['avg_profit'] <= 0:
            print(f"     - Negative average profit: ${results['avg_profit']:.2f}")
    
    print("=" * 70)


if __name__ == '__main__':
    print("\n🔄 Mean Reversion Strategy - Comprehensive Backtest\n")
    
    results = run_comprehensive_backtest(
        n_simulations=500,
        n_steps=1000,
        bankroll=5.0
    )
    
    print_backtest_report(results)
    
    # Save results
    import json
    from pathlib import Path
    output = Path('/root/.openclaw/workspace/mean_rev_backtest_comprehensive.json')
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to: {output}")
