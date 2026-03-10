#!/usr/bin/env python3
"""
Backtest comparison: V4 Base vs V4 + Live Trading Integration
BIG DATA VERSION - Uses InternalLog.json with 9000+ records
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace')
sys.path.insert(0, '/root/.openclaw/workspace/live_trading')

# Load from multiple sources for bigger dataset
DATA_SOURCES = [
    "/root/.openclaw/workspace/InternalLog.json",
    "/root/.openclaw/workspace/wallet1_new_trades.json", 
    "/root/.openclaw/workspace/wallet_ultimate_trades.json",
]

def load_all_trades():
    """Load trades from all available sources."""
    all_trades = []
    
    for source in DATA_SOURCES:
        try:
            with open(source) as f:
                data = json.load(f)
            
            if isinstance(data, list):
                # InternalLog format - filter for actual trades
                trades = [e for e in data if e.get('event_type') in ['trade_real', 'trade_paper', 'BUY', 'SELL']]
                for t in trades:
                    t['_source'] = source.split('/')[-1]
                all_trades.extend(trades)
            elif isinstance(data, dict) and 'trades' in data:
                # Wallet format
                trades = data['trades']
                for t in trades:
                    t['_source'] = source.split('/')[-1]
                all_trades.extend(trades)
                
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Warning: Error loading {source}: {e}")
    
    # Sort by timestamp
    all_trades.sort(key=lambda x: x.get('timestamp_utc', ''))
    return all_trades

def analyze_virtual_performance(trades):
    """Analyze virtual trading performance."""
    print("=" * 70)
    print("V4 BASE BOT PERFORMANCE (Virtual/Paper Trading)")
    print(f"Dataset: {len(trades):,} trades from multiple sources")
    print("=" * 70)
    
    if not trades:
        print("No trades found.")
        return None
    
    # Calculate P&L from different fields depending on source
    total_pnl = 0
    wins = 0
    losses = 0
    total_fees_virtual = 0
    
    for t in trades:
        # Try different P&L field names
        pnl = t.get('pnl', t.get('virtual_pnl_impact', t.get('realized_pnl', 0)))
        total_pnl += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
    
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
    
    # Estimate starting balance from trades
    amounts = [t.get('amount', 0) for t in trades if t.get('amount', 0) > 0]
    avg_trade = sum(amounts) / len(amounts) if amounts else 5
    estimated_start = avg_trade * 100  # Rough estimate
    
    print(f"Total Trades:     {len(trades):,}")
    print(f"Winning Trades:   {wins:,}")
    print(f"Losing Trades:    {losses:,}")
    print(f"Win Rate:         {win_rate:.1f}%")
    print(f"Total P&L:        ${total_pnl:+.2f}")
    
    if total_closed > 0:
        avg_win = total_pnl / wins if wins > 0 else 0
        avg_loss = total_pnl / losses if losses > 0 else 0
        print(f"Avg Trade P&L:    ${total_pnl/len(trades):+.2f}")
    
    # Source breakdown
    sources = {}
    for t in trades:
        src = t.get('_source', 'unknown')
        sources[src] = sources.get(src, 0) + 1
    
    print(f"\nData Sources:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  - {src}: {count:,} trades")
    
    return {
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_trade_size": avg_trade,
    }

def simulate_live_trading(trades):
    """
    Simulate live CLOB trading with realistic costs.
    
    Live trading differences:
    - Taker fee: 0.5% per side (1% round trip)
    - Slippage: 0.5-2% depending on liquidity
    - Minimum order: $1.00
    - Spread crossing: Market orders hit the spread
    """
    print("\n" + "=" * 70)
    print("V4 + LIVE TRADING SIMULATION (CLOB Integration)")
    print("=" * 70)
    
    # Live trading parameters
    TAKER_FEE = 0.005  # 0.5% per trade
    AVG_SLIPPAGE = 0.015  # 1.5% slippage (conservative for crypto)
    MIN_ORDER = 1.00
    
    print(f"Live Trading Parameters:")
    print(f"  - Taker Fee:    {TAKER_FEE:.1%} per side ({TAKER_FEE*2:.1%} round trip)")
    print(f"  - Avg Slippage: {AVG_SLIPPAGE:.1%}")
    print(f"  - Min Order:    ${MIN_ORDER:.2f}")
    
    if not trades:
        return None
    
    simulated_pnl = 0
    total_fees = 0
    total_slippage_cost = 0
    skipped_trades = 0
    
    for t in trades:
        amount = t.get('amount', 0)
        
        # Skip tiny trades
        if amount < MIN_ORDER:
            skipped_trades += 1
            continue
        
        # Get base P&L
        base_pnl = t.get('pnl', t.get('virtual_pnl_impact', 0))
        
        # Calculate entry/exit prices
        entry = t.get('entry_price', 0.5)
        
        # Slippage impact: entry worse by slippage, exit worse by slippage
        # For a winning trade, this reduces profit
        # For a losing trade, this increases loss
        slippage_cost = amount * AVG_SLIPPAGE * 2  # entry + exit
        total_slippage_cost += slippage_cost
        
        # Fees on notional (entry + exit)
        notional = amount
        fees = notional * TAKER_FEE * 2
        total_fees += fees
        
        # Adjusted P&L
        adjusted_pnl = base_pnl - slippage_cost - fees
        simulated_pnl += adjusted_pnl
    
    # Calculate metrics
    win_count = sum(1 for t in trades if t.get('pnl', t.get('virtual_pnl_impact', 0)) > 0)
    
    print(f"\nSimulated Live Trading Results:")
    print(f"  Trades Processed:   {len(trades) - skipped_trades:,}")
    print(f"  Skipped (<<$1):      {skipped_trades:,}")
    print(f"  Gross P&L:          ${sum(t.get('pnl', t.get('virtual_pnl_impact', 0)) for t in trades):+.2f}")
    print(f"  Slippage Cost:      ${total_slippage_cost:.2f}")
    print(f"  Total Fees:         ${total_fees:.2f}")
    print(f"  Net P&L (Live):     ${simulated_pnl:+.2f}")
    print(f"  Cost Impact:        {(total_fees + total_slippage_cost):.2f} ({(total_fees + total_slippage_cost)/abs(sum(t.get('pnl', 0) for t in trades))*100 if sum(t.get('pnl', 0) for t in trades) != 0 else 0:.1f}% of gross)")
    
    return {
        "simulated_pnl": simulated_pnl,
        "total_fees": total_fees,
        "slippage_cost": total_slippage_cost,
        "skipped": skipped_trades,
    }

def compare_results(virtual, live):
    """Compare virtual vs live results."""
    if not live:
        return
    
    print("\n" + "=" * 70)
    print("COMPARISON: VIRTUAL vs LIVE TRADING")
    print("=" * 70)
    
    virtual_pnl = virtual["total_pnl"]
    live_pnl = live["simulated_pnl"]
    difference = live_pnl - virtual_pnl
    pct_diff = (difference / abs(virtual_pnl) * 100) if virtual_pnl != 0 else 0
    
    print(f"Virtual Trading P&L:   ${virtual_pnl:+,.2f}")
    print(f"Live Trading P&L:      ${live_pnl:+,.2f}")
    print(f"Difference:            ${difference:+,.2f} ({pct_diff:+.1f}%)")
    print(f"\nCost Breakdown:")
    print(f"  - Trading Fees:      ${live['total_fees']:.2f}")
    print(f"  - Slippage:          ${live['slippage_cost']:.2f}")
    print(f"  - Total Costs:       ${live['total_fees'] + live['slippage_cost']:.2f}")
    
    # Breakeven analysis
    print(f"\n" + "=" * 70)
    print("BREAKEVEN ANALYSIS")
    print("=" * 70)
    
    if virtual["total_trades"] > 0:
        avg_profit_per_trade = virtual_pnl / virtual["total_trades"]
        avg_cost_per_trade = (live["total_fees"] + live["slippage_cost"]) / virtual["total_trades"]
        
        print(f"Avg Profit/Trade:      ${avg_profit_per_trade:+.2f}")
        print(f"Avg Cost/Trade:        ${avg_cost_per_trade:.2f}")
        
        if avg_cost_per_trade >= avg_profit_per_trade:
            print(f"\n⚠️  WARNING: Trading costs exceed average profit!")
            print(f"    Strategy may not be profitable after live costs.")
        else:
            cushion = (avg_profit_per_trade - avg_cost_per_trade) / avg_profit_per_trade * 100
            print(f"\n✅ Profit cushion: {cushion:.1f}% after costs")
    
    # Recommendations
    print(f"\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    
    if virtual["win_rate"] > 55 and virtual["total_trades"] > 50:
        print("✅ Strategy shows strong edge (good win rate + volume)")
    elif virtual["win_rate"] > 50:
        print("ℹ️  Strategy shows marginal edge")
    else:
        print("⚠️  Strategy may lack edge - more testing needed")
    
    if abs(difference) / abs(virtual_pnl) < 0.2 if virtual_pnl != 0 else True:
        print("✅ Live costs are manageable (<20% of profits)")
    else:
        print("⚠️  Live costs are significant - consider:")
        print("     - Larger position sizes (scale economies)")
        print("     - Limit orders instead of market orders")
        print("     - Lower fee tier (higher volume)")

def main():
    print("\n" + "=" * 70)
    print("V4 BOT BACKTEST COMPARISON - BIG DATA VERSION")
    print("Base (Virtual) vs Live Trading (CLOB Integration)")
    print("=" * 70)
    
    trades = load_all_trades()
    
    if not trades:
        print("No trade data found!")
        return
    
    virtual_results = analyze_virtual_performance(trades)
    live_results = simulate_live_trading(trades)
    
    if live_results:
        compare_results(virtual_results, live_results)
    
    print("\n" + "=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print("1. Set environment variables:")
    print("   export POLY_PRIVATE_KEY='0x...'")
    print("   export POLY_ADDRESS='0x...'")
    print("")
    print("2. Run pre-flight checks:")
    print("   python live_trading/integration_example.py")
    print("")
    print("3. Execute $1 test order:")
    print("   python live_trading/integration_example.py --live")
    print("")
    print("4. Integrate with V4 bot (3 options):")
    print("   a) Fix the 8 test mocking issues")
    print("   b) Solve Issue #1 (5M market monitor)")  
    print("   c) Create V4 bot integration patch ← RECOMMENDED")
    print("=" * 70)

if __name__ == "__main__":
    main()
