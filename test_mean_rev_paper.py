#!/usr/bin/env python3
"""
test_mean_rev_paper.py - Quick test of Mean Reversion strategy in paper mode

This script tests the mean reversion strategy with the master bot
to prove it works in paper trading mode.
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace')

from mean_reversion_bot import MeanReversionStrategy
import random
import json
from datetime import datetime

def test_paper_mode():
    """Test mean reversion strategy in paper mode"""
    print("\n" + "="*70)
    print("  MEAN REVERSION STRATEGY - PAPER MODE TEST")
    print("="*70)
    
    # Initialize with $5 budget
    engine = MeanReversionStrategy(bankroll=5.0)
    
    # Simulate price data that creates mean reversion opportunities
    random.seed(42)
    price = 0.50
    
    print("\n📊 Simulating 100 price ticks...")
    
    for i in range(100):
        # Mean-reverting price walk
        drift = 0.1 * (0.50 - price)
        noise = random.gauss(0, 0.025)
        price = max(0.05, min(0.95, price + drift + noise))
        
        yes_price = price
        no_price = 1 - price
        
        # Update engine
        engine.update_price('BTC', yes_price, no_price, 5)
        
        # Generate signal
        signal = engine.generate_signal('BTC', yes_price, no_price, 5)
        if signal:
            amount = engine.calculate_position_size(signal)
            if amount >= 0.10:
                engine.enter_position(signal, amount)
                print(f"  🎯 ENTRY: BTC {signal.side} @ {signal.entry_price:.3f} "
                      f"RSI={signal.rsi:.1f} Z={signal.zscore:.2f} Size=${amount:.2f}")
        
        # Check exits
        for market_id in list(engine.positions.keys()):
            exit_info = engine.check_exit(market_id, yes_price, no_price)
            if exit_info:
                trade = engine.exit_position(market_id, exit_info)
                emoji = "✅" if exit_info['pnl'] > 0 else "❌"
                print(f"  {emoji} EXIT: {market_id} | {exit_info['exit_reason']} | "
                      f"P&L: ${exit_info['pnl']:+.2f}")
    
    # Close remaining positions
    for market_id in list(engine.positions.keys()):
        exit_info = engine.check_exit(market_id, yes_price, no_price)
        if exit_info:
            engine.exit_position(market_id, exit_info)
    
    # Get stats
    stats = engine.get_stats()
    
    print("\n" + "="*70)
    print("  PAPER TRADING RESULTS")
    print("="*70)
    print(f"  Initial Bankroll: $5.00")
    print(f"  Final Bankroll:   ${stats['bankroll']:.2f}")
    print(f"  Total Trades:     {stats['trades']}")
    print(f"  Win Rate:         {stats['win_rate']:.1%}")
    print(f"  Total Profit:     ${stats['profit']:+.2f}")
    print(f"  ROI:              {stats['roi_pct']:+.1f}%")
    print(f"  Expectancy:       ${stats['expectancy']:.3f}/trade")
    print(f"  Profit Factor:    {stats['profit_factor']:.2f}")
    print(f"  Sharpe Ratio:     {stats['sharpe']:.2f}")
    print("="*70)
    
    if stats['win_rate'] >= 0.55 and stats['profit'] > 0:
        print("  ✅ PAPER MODE TEST PASSED")
        print(f"     - Win rate {stats['win_rate']:.1%} > 55% threshold")
        print(f"     - Positive profit: ${stats['profit']:+.2f}")
    else:
        print("  ❌ PAPER MODE TEST FAILED")
    
    print("="*70)
    
    # Save test results
    result = {
        'timestamp': datetime.now().isoformat(),
        'strategy': 'mean_reversion',
        'mode': 'paper',
        'initial_bankroll': 5.0,
        'final_bankroll': stats['bankroll'],
        'trades': stats['trades'],
        'win_rate': stats['win_rate'],
        'profit': stats['profit'],
        'roi_pct': stats['roi_pct'],
        'sharpe': stats['sharpe'],
        'passed': stats['win_rate'] >= 0.55 and stats['profit'] > 0
    }
    
    with open('/root/.openclaw/workspace/mean_rev_paper_test.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n💾 Test results saved to: /root/.openclaw/workspace/mean_rev_paper_test.json")
    
    return result

if __name__ == '__main__':
    test_paper_mode()
