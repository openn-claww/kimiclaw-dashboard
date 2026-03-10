#!/usr/bin/env python3
"""
Backtest comparison: V4 Base vs V4 + Live Trading Integration

This script:
1. Loads historical trades from wallet_v4_production.json
2. Simulates what would have happened with live CLOB orders
3. Compares virtual P&L vs live trading P&L
4. Identifies slippage impact, execution delays, etc.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace')
sys.path.insert(0, '/root/.openclaw/workspace/live_trading')

from live_trading.clob_integration import LiveTrader
from live_trading.integration_example import V4BotLiveIntegration

# Load V4 historical data
V4_STATE_FILE = "/root/.openclaw/workspace/wallet_v4_production.json"
V4_LOG_FILE = "/root/.openclaw/workspace/trades_v4_production.json"

def load_v4_data():
    """Load V4 bot historical performance."""
    try:
        with open(V4_STATE_FILE) as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {"trades": [], "bankroll_current": 500.0, "bankroll_start": 500.0}
    
    # Trades are in the state file under "trades" key
    trades = state.get("trades", [])
    
    return state, trades

def analyze_virtual_performance(state, trades):
    """Analyze V4 virtual trading performance."""
    print("=" * 70)
    print("V4 BASE BOT PERFORMANCE (Virtual/Paper Trading)")
    print("=" * 70)
    
    starting_balance = state.get("bankroll_start", 500.0)
    current_balance = state.get("bankroll_current", 500.0)
    total_pnl = current_balance - starting_balance
    total_pnl_pct = (total_pnl / starting_balance) * 100
    
    print(f"Starting Balance: ${starting_balance:.2f}")
    print(f"Current Balance:  ${current_balance:.2f}")
    print(f"Total P&L:        ${total_pnl:+.2f} ({total_pnl_pct:+.1f}%)")
    print(f"Total Trades:     {len(trades)}")
    
    if trades:
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        
        total_wins = sum(t.get("pnl", 0) for t in wins)
        total_losses = abs(sum(t.get("pnl", 0) for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        print(f"Win Rate:         {win_rate:.1f}% ({len(wins)}/{len(trades)})")
        print(f"Profit Factor:    {profit_factor:.2f}")
        print(f"Avg Win:          ${total_wins/len(wins) if wins else 0:.2f}")
        print(f"Avg Loss:         ${-total_losses/len(losses) if losses else 0:.2f}")
        
        # Show best and worst trades
        if trades:
            best = max(trades, key=lambda x: x.get("pnl", 0))
            worst = min(trades, key=lambda x: x.get("pnl", 0))
            print(f"\nBest Trade:  +${best.get('pnl', 0):.2f} on {best.get('market', 'N/A')}")
            print(f"Worst Trade: ${worst.get('pnl', 0):.2f} on {worst.get('market', 'N/A')}")
    
    return {
        "starting_balance": starting_balance,
        "current_balance": current_balance,
        "total_pnl": total_pnl,
        "total_trades": len(trades),
        "win_rate": win_rate if trades else 0,
    }

def simulate_live_trading(state, trades):
    """
    Simulate what live trading would look like vs virtual trading.
    
    Key differences:
    - Slippage: Live orders fill at market price, not mid
    - Fees: CLOB has 0.5% taker fee (approx)
    - Minimum size: $1.00 minimum order
    - Partial fills: Possible on large orders
    """
    print("\n" + "=" * 70)
    print("V4 + LIVE TRADING SIMULATION (CLOB Integration)")
    print("=" * 70)
    
    # Live trading assumptions
    TAKER_FEE = 0.005  # 0.5% taker fee
    AVG_SLIPPAGE = 0.01  # 1% slippage on entry/exit (conservative)
    
    print(f"Assumptions:")
    print(f"  - Taker Fee:    {TAKER_FEE:.1%}")
    print(f"  - Avg Slippage: {AVG_SLIPPAGE:.1%}")
    print(f"  - Min Order:    $1.00")
    
    if not trades:
        print("\nNo trades to simulate.")
        return None
    
    simulated_pnl = 0
    live_costs = 0
    skipped_trades = 0
    
    for trade in trades:
        entry = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        size = trade.get("amount", 0)
        side = trade.get("side", "YES")
        
        # Skip tiny trades that wouldn't meet minimum
        if size < 1.0:
            skipped_trades += 1
            continue
        
        # Calculate with slippage
        # Entry: buy at slightly worse price (higher)
        live_entry = entry * (1 + AVG_SLIPPAGE) if side == "YES" else entry * (1 - AVG_SLIPPAGE)
        
        # Exit: sell at slightly worse price (lower)
        live_exit = exit_price * (1 - AVG_SLIPPAGE) if side == "YES" else exit_price * (1 + AVG_SLIPPAGE)
        
        # Calculate P&L
        if side == "YES":
            gross_pnl = (live_exit - live_entry) * (size / entry) if entry > 0 else 0
        else:  # NO side
            gross_pnl = (live_entry - live_exit) * (size / (1 - entry)) if entry < 1 else 0
        
        # Deduct fees (both entry and exit)
        fees = size * TAKER_FEE * 2  # Entry + exit
        live_costs += fees
        
        net_pnl = gross_pnl - fees
        simulated_pnl += net_pnl
    
    starting_balance = state.get("bankroll_start", 500.0)
    simulated_balance = starting_balance + simulated_pnl
    
    print(f"\nSimulated Results:")
    print(f"  Starting Balance: ${starting_balance:.2f}")
    print(f"  Simulated Balance: ${simulated_balance:.2f}")
    print(f"  Simulated P&L:     ${simulated_pnl:+.2f}")
    print(f"  Total Fees Paid:   ${live_costs:.2f}")
    print(f"  Skipped Trades:    {skipped_trades} (below $1 min)")
    
    return {
        "starting_balance": starting_balance,
        "simulated_balance": simulated_balance,
        "simulated_pnl": simulated_pnl,
        "total_fees": live_costs,
        "skipped_trades": skipped_trades,
    }

def compare_results(virtual, live_sim):
    """Compare virtual vs live trading results."""
    if not live_sim:
        return
    
    print("\n" + "=" * 70)
    print("COMPARISON: VIRTUAL vs LIVE TRADING")
    print("=" * 70)
    
    virtual_pnl = virtual["total_pnl"]
    live_pnl = live_sim["simulated_pnl"]
    difference = live_pnl - virtual_pnl
    
    print(f"Virtual Trading P&L:  ${virtual_pnl:+.2f}")
    print(f"Live Trading P&L:     ${live_pnl:+.2f}")
    print(f"Difference:           ${difference:+.2f}")
    print(f"Impact:               {difference/virtual_pnl*100 if virtual_pnl != 0 else 0:+.1f}%")
    
    print("\nKey Insights:")
    if difference < -10:
        print("  ⚠️  Live trading significantly reduces profitability")
        print("      Consider: larger position sizes, limit orders, lower fees")
    elif difference < 0:
        print("  ℹ️  Live trading has moderate cost impact")
        print("      Fees and slippage are eating into profits")
    else:
        print("  ✅ Live trading may actually improve results")
        print("      (better execution than virtual mid-price)")
    
    print(f"\nRecommendation:")
    if virtual["win_rate"] > 60 and virtual["total_trades"] > 10:
        print("  ✅ Strategy shows edge. Ready for live trading with proper risk management.")
    else:
        print("  ⚠️  Strategy needs more testing. Consider more paper trades before going live.")

def main():
    print("\n" + "=" * 70)
    print("V4 BOT BACKTEST COMPARISON")
    print("Base (Virtual) vs Live Trading (CLOB Integration)")
    print("=" * 70)
    
    state, trades = load_v4_data()
    
    virtual_results = analyze_virtual_performance(state, trades)
    live_results = simulate_live_trading(state, trades)
    
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
    print("   Modify integration_example.py with real token ID")
    print("   Run with --live flag after dry_run succeeds")
    print("")
    print("4. Integrate with V4 bot:")
    print("   Replace virtual trade calls with V4BotLiveIntegration")
    print("=" * 70)

if __name__ == "__main__":
    main()
