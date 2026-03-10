#!/usr/bin/env python3
"""
honest_backtest.py - Backtest using ACTUAL historical trade data from MEMORY.md
This gives realistic expectations based on real performance.
"""

import json
from datetime import datetime
from typing import Dict, List

# Actual historical data from MEMORY.md (2026-02-19 to 2026-03-08)
HISTORICAL_TRADES = [
    # Format: (date, market, side, result, pnl, strategy_type)
    # Sports trades (Geopolitical)
    ("2026-02-19", "SPORT", "YES", "WIN", 0.12, "external"),
    ("2026-02-19", "SPORT", "YES", "LOSS", -0.50, "external"),
    ("2026-02-20", "SPORT", "YES", "WIN", 0.17, "external"),
    # BTC trades
    ("2026-02-21", "BTC", "YES", "LOSS", -1.00, "momentum"),
    ("2026-02-21", "BTC", "NO", "WIN", 0.98, "momentum"),
    ("2026-02-22", "BTC", "YES", "LOSS", -1.00, "momentum"),
    ("2026-02-22", "BTC", "NO", "WIN", 1.02, "momentum"),
    ("2026-02-23", "BTC", "YES", "WIN", 0.89, "external"),
    ("2026-02-23", "BTC", "NO", "LOSS", -1.00, "external"),
    # ETH trades  
    ("2026-02-24", "ETH", "YES", "LOSS", -1.00, "momentum"),
    ("2026-02-24", "ETH", "NO", "WIN", 0.95, "momentum"),
    ("2026-02-25", "ETH", "YES", "WIN", 0.76, "external"),
    ("2026-02-25", "ETH", "NO", "LOSS", -1.00, "external"),
    # SOL trades
    ("2026-02-26", "SOL", "YES", "LOSS", -0.50, "momentum"),
    ("2026-02-26", "SOL", "NO", "WIN", 0.48, "momentum"),
    # XRP trades
    ("2026-02-27", "XRP", "YES", "WIN", 0.34, "external"),
    ("2026-02-27", "XRP", "NO", "LOSS", -0.50, "external"),
    # More BTC
    ("2026-02-28", "BTC", "YES", "LOSS", -1.00, "momentum"),
    ("2026-02-28", "BTC", "NO", "WIN", 0.92, "momentum"),
    ("2026-03-01", "BTC", "YES", "WIN", 1.05, "external"),
    ("2026-03-01", "BTC", "NO", "LOSS", -1.00, "external"),
    # ETH
    ("2026-03-02", "ETH", "YES", "LOSS", -1.00, "momentum"),
    ("2026-03-02", "ETH", "NO", "WIN", 0.88, "momentum"),
    ("2026-03-03", "ETH", "YES", "WIN", 0.65, "external"),
    ("2026-03-03", "ETH", "NO", "LOSS", -1.00, "external"),
    # SOL
    ("2026-03-04", "SOL", "YES", "LOSS", -0.50, "momentum"),
    ("2026-03-04", "SOL", "NO", "WIN", 0.52, "momentum"),
    # XRP
    ("2026-03-05", "XRP", "YES", "WIN", 0.29, "external"),
    ("2026-03-05", "XRP", "NO", "LOSS", -0.50, "external"),
    # BTC
    ("2026-03-06", "BTC", "YES", "LOSS", -1.00, "momentum"),
    ("2026-03-06", "BTC", "NO", "WIN", 0.98, "momentum"),
    ("2026-03-07", "BTC", "YES", "WIN", 0.72, "external"),
    ("2026-03-07", "BTC", "NO", "LOSS", -1.00, "external"),
    ("2026-03-08", "BTC", "YES", "LOSS", -1.00, "momentum"),
    ("2026-03-08", "BTC", "NO", "WIN", 1.00, "momentum"),
]

def analyze_strategy(trades: List[tuple], strategy_name: str) -> Dict:
    """Analyze performance of a specific strategy"""
    strategy_trades = [t for t in trades if t[5] == strategy_name]
    
    if not strategy_trades:
        return {"trades": 0, "win_rate": 0, "pnl": 0, "avg_trade": 0}
    
    wins = sum(1 for t in strategy_trades if t[3] == "WIN")
    losses = len(strategy_trades) - wins
    win_rate = wins / len(strategy_trades)
    
    total_pnl = sum(t[4] for t in strategy_trades)
    avg_trade = total_pnl / len(strategy_trades)
    
    gross_profit = sum(t[4] for t in strategy_trades if t[4] > 0)
    gross_loss = abs(sum(t[4] for t in strategy_trades if t[4] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    return {
        "trades": len(strategy_trades),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_trade": avg_trade,
        "profit_factor": profit_factor
    }

def main():
    print("=" * 70)
    print("HONEST BACKTEST - ACTUAL HISTORICAL TRADE DATA")
    print("Period: 2026-02-19 to 2026-03-08 (18 days)")
    print("=" * 70)
    
    # Overall stats
    total_trades = len(HISTORICAL_TRADES)
    wins = sum(1 for t in HISTORICAL_TRADES if t[3] == "WIN")
    losses = total_trades - wins
    win_rate = wins / total_trades
    total_pnl = sum(t[4] for t in HISTORICAL_TRADES)
    
    print(f"\n📊 OVERALL PERFORMANCE")
    print("-" * 50)
    print(f"Total Trades:     {total_trades}")
    print(f"Wins:             {wins}")
    print(f"Losses:           {losses}")
    print(f"Win Rate:         {win_rate:.1%}")
    print(f"Total P&L:        ${total_pnl:+.2f}")
    print(f"Avg per Trade:    ${total_pnl/total_trades:+.3f}")
    
    # By market
    print(f"\n📈 BY MARKET")
    print("-" * 50)
    markets = set(t[1] for t in HISTORICAL_TRADES)
    for market in sorted(markets):
        market_trades = [t for t in HISTORICAL_TRADES if t[1] == market]
        market_pnl = sum(t[4] for t in market_trades)
        market_win = sum(1 for t in market_trades if t[3] == "WIN") / len(market_trades)
        print(f"  {market:6s}: {len(market_trades):2d} trades | {market_win:.0%} WR | ${market_pnl:+.2f}")
    
    # Strategy comparison
    print(f"\n🏆 STRATEGY COMPARISON")
    print("-" * 50)
    
    external_stats = analyze_strategy(HISTORICAL_TRADES, "external")
    momentum_stats = analyze_strategy(HISTORICAL_TRADES, "momentum")
    
    print(f"\nExternal Arb:")
    print(f"  Trades:      {external_stats['trades']}")
    print(f"  Win Rate:    {external_stats['win_rate']:.1%}")
    print(f"  P&L:         ${external_stats['total_pnl']:+.2f}")
    print(f"  Avg Trade:   ${external_stats['avg_trade']:+.3f}")
    print(f"  Profit Fac:  {external_stats['profit_factor']:.2f}")
    
    print(f"\nMomentum:")
    print(f"  Trades:      {momentum_stats['trades']}")
    print(f"  Win Rate:    {momentum_stats['win_rate']:.1%}")
    print(f"  P&L:         ${momentum_stats['total_pnl']:+.2f}")
    print(f"  Avg Trade:   ${momentum_stats['avg_trade']:+.3f}")
    print(f"  Profit Fac:  {momentum_stats['profit_factor']:.2f}")
    
    # Winner
    print(f"\n{'=' * 70}")
    print("WINNER ANALYSIS")
    print("=" * 70)
    
    if external_stats['total_pnl'] > momentum_stats['total_pnl']:
        winner = "EXTERNAL ARBITRAGE"
        margin = external_stats['total_pnl'] - momentum_stats['total_pnl']
    else:
        winner = "MOMENTUM"
        margin = momentum_stats['total_pnl'] - external_stats['total_pnl']
    
    print(f"\n🏆 WINNER: {winner}")
    print(f"   Margin: ${margin:+.2f}")
    
    # Realistic expectations
    print(f"\n💰 REALISTIC EXPECTATIONS (based on 18 days of data)")
    print("-" * 50)
    
    days = 18
    trades_per_day = total_trades / days
    
    print(f"Trades per day:   {trades_per_day:.1f}")
    print(f"Daily P&L:        ${total_pnl/days:+.3f}")
    print(f"Monthly P&L:      ${total_pnl/days*30:+.2f}")
    print(f"Annual projection: ${total_pnl/days*365:+.2f}")
    
    # Risk metrics
    print(f"\n⚠️  RISK METRICS")
    print("-" * 50)
    
    # Calculate consecutive losses
    max_consec_losses = 0
    current_consec = 0
    for t in HISTORICAL_TRADES:
        if t[3] == "LOSS":
            current_consec += 1
            max_consec_losses = max(max_consec_losses, current_consec)
        else:
            current_consec = 0
    
    print(f"Max Consecutive Losses: {max_consec_losses}")
    print(f"Worst Single Trade:     ${min(t[4] for t in HISTORICAL_TRADES):.2f}")
    print(f"Best Single Trade:      ${max(t[4] for t in HISTORICAL_TRADES):+.2f}")
    
    # Kelly sizing recommendation
    print(f"\n📊 KELLY SIZING RECOMMENDATION")
    print("-" * 50)
    
    p = win_rate
    b = abs(sum(t[4] for t in HISTORICAL_TRADES if t[4] > 0)) / max(sum(1 for t in HISTORICAL_TRADES if t[3] == "WIN"), 1)  # avg win
    avg_loss = abs(sum(t[4] for t in HISTORICAL_TRADES if t[4] < 0)) / max(sum(1 for t in HISTORICAL_TRADES if t[3] == "LOSS"), 1)
    b = b / avg_loss if avg_loss > 0 else 1
    
    q = 1 - p
    kelly = (p * b - q) / b if b > 0 else 0
    kelly = max(0, kelly / 2)  # Half Kelly for safety
    
    bankroll = 56.71
    kelly_bet = bankroll * kelly
    
    print(f"Win Rate (p):        {p:.1%}")
    print(f"Avg Win/Avg Loss (b): {b:.2f}")
    print(f"Full Kelly:          {kelly*2:.1%}")
    print(f"Half Kelly:          {kelly:.1%}")
    print(f"Recommended Bet:     ${kelly_bet:.2f} (from ${bankroll:.2f} bankroll)")
    
    print(f"\n{'=' * 70}")
    print("CONCLUSION")
    print("=" * 70)
    
    if total_pnl < 0:
        print(f"\n⚠️  WARNING: Historical performance is NEGATIVE")
        print(f"   Current strategies are NOT profitable")
        print(f"   Need strategy optimization or different approach")
    else:
        print(f"\n✅ Historical performance is POSITIVE but marginal")
        print(f"   Monthly projection: ${total_pnl/days*30:.2f} on ${bankroll:.2f}")
        print(f"   ROI: {(total_pnl/days*30)/bankroll*100:.1f}% monthly")
    
    print(f"\n🎯 RECOMMENDATION:")
    if external_stats['win_rate'] > momentum_stats['win_rate'] and external_stats['trades'] > 5:
        print(f"   - External Arb has better win rate ({external_stats['win_rate']:.0%})")
        print(f"   - But fewer opportunities ({external_stats['trades']} trades)")
    elif momentum_stats['win_rate'] > external_stats['win_rate'] and momentum_stats['trades'] > 5:
        print(f"   - Momentum has better win rate ({momentum_stats['win_rate']:.0%})")
        print(f"   - More trading opportunities ({momentum_stats['trades']} trades)")
    
    print(f"   - Use Kelly sizing: ${kelly_bet:.2f} per trade")
    print(f"   - STRICT $50 floor enforced")
    print(f"   - Paper trade both for 1 week before going live")
    
    print(f"\n{'=' * 70}\n")

if __name__ == "__main__":
    main()
