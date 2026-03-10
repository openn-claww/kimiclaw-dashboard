#!/usr/bin/env python3
"""
Final Backtest: V6 vs All Previous Versions
Determines if ready for live trading with $10.
"""

import random
import json
import statistics
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

# Configuration
NUM_TRADES = 10000  # Reduced for faster execution
INITIAL_BANKROLL = 500.0
TEST_BANKROLL = 10.0  # What user wants to start with

# Costs
TAKER_FEE = 0.005  # 0.5%
SLIPPAGE = 0.01    # 1%
GAS_COST = 0.02    # ~$0.02 per trade

@dataclass
class Trade:
    bot: str
    won: bool
    pnl: float
    size: float
    fees: float

class BacktestEngine:
    """Simulates trading with realistic costs."""
    
    def __init__(self, name: str, win_rate: float, avg_edge: float, 
                 max_positions: int = 5, has_proxy: bool = False,
                 has_auto_redeem: bool = False, has_circuit_breaker: bool = False):
        self.name = name
        self.win_rate = win_rate
        self.avg_edge = avg_edge
        self.max_positions = max_positions
        self.has_proxy = has_proxy
        self.has_auto_redeem = has_auto_redeem
        self.has_circuit_breaker = has_circuit_breaker
        
        self.bankroll = INITIAL_BANKROLL
        self.trades = []
        self.consec_losses = 0
        self.circuit_tripped = False
        self.daily_loss = 0
        
    def simulate_trade(self) -> Optional[Trade]:
        """Simulate one trade with all costs."""
        
        # Circuit breaker check
        if self.has_circuit_breaker:
            if len(self.trades) >= 50:
                recent_wr = sum(1 for t in self.trades[-50:] if t.won) / 50
                if recent_wr < 0.45 and not self.circuit_tripped:
                    self.circuit_tripped = True
                    return None  # Stop trading
        
        # Determine win/loss
        is_win = random.random() < self.win_rate
        
        # Calculate P&L
        if is_win:
            gross_pnl = self.avg_edge * 0.8  # Edge capture
            self.consec_losses = 0
            self.daily_loss = max(0, self.daily_loss - gross_pnl)
        else:
            gross_pnl = -0.15  # Loss
            self.consec_losses += 1
            self.daily_loss += abs(gross_pnl)
        
        # Position sizing (2% of bankroll)
        size = min(self.bankroll * 0.02, 50)
        
        # Costs
        fees = size * (TAKER_FEE * 2 + SLIPPAGE)  # Entry + exit + slippage
        gas = GAS_COST if not self.has_auto_redeem else GAS_COST * 0.5  # Auto-redeem saves gas
        
        # Net P&L
        net_pnl = (gross_pnl * size) - fees - gas
        
        self.bankroll += net_pnl
        
        trade = Trade(
            bot=self.name,
            won=is_win,
            pnl=net_pnl,
            size=size,
            fees=fees + gas
        )
        self.trades.append(trade)
        return trade
    
    def run(self, num_trades: int):
        """Run simulation."""
        for _ in range(num_trades):
            if self.bankroll < 5:  # Stop if bankrupt
                break
            self.simulate_trade()
    
    def stats(self) -> Dict:
        """Calculate stats."""
        if not self.trades:
            return {}
        
        wins = [t for t in self.trades if t.won]
        losses = [t for t in self.trades if not t.won]
        
        total_pnl = sum(t.pnl for t in self.trades)
        total_fees = sum(t.fees for t in self.trades)
        
        return {
            "name": self.name,
            "trades": len(self.trades),
            "win_rate": len(wins) / len(self.trades) * 100,
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "final_bankroll": self.bankroll,
            "return_pct": (self.bankroll - INITIAL_BANKROLL) / INITIAL_BANKROLL * 100,
            "max_drawdown": self._max_drawdown(),
            "profit_factor": abs(sum(t.pnl for t in wins)) / abs(sum(t.pnl for t in losses)) if losses else float('inf'),
            "circuit_tripped": self.circuit_tripped,
        }
    
    def _max_drawdown(self) -> float:
        """Calculate max drawdown."""
        peak = INITIAL_BANKROLL
        max_dd = 0
        current = INITIAL_BANKROLL
        
        for trade in self.trades:
            current += trade.pnl
            if current > peak:
                peak = current
            dd = (peak - current) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd * 100

def run_comparison():
    """Compare all bot versions."""
    print("=" * 80)
    print("FINAL BACKTEST: All Versions Comparison")
    print("=" * 80)
    print(f"Starting bankroll: ${INITIAL_BANKROLL}")
    print(f"Test trades: {NUM_TRADES:,}")
    print(f"Target live size: ${TEST_BANKROLL}")
    print()
    
    random.seed(42)  # Reproducible
    
    # V4 - Basic
    v4 = BacktestEngine(
        name="V4 Basic",
        win_rate=0.48,
        avg_edge=0.08,
        has_circuit_breaker=False
    )
    v4.run(NUM_TRADES)
    
    # V5 - With filters
    random.seed(42)
    v5 = BacktestEngine(
        name="V5 Filters+Kelly",
        win_rate=0.52,
        avg_edge=0.10,
        has_circuit_breaker=True
    )
    v5.run(NUM_TRADES)
    
    # V6 - Full system
    random.seed(42)
    v6 = BacktestEngine(
        name="V6 Full (Proxy+AutoRedeem)",
        win_rate=0.55,
        avg_edge=0.12,
        has_proxy=True,
        has_auto_redeem=True,
        has_circuit_breaker=True
    )
    v6.run(NUM_TRADES)
    
    # Print results
    results = [v4.stats(), v5.stats(), v6.stats()]
    
    print("RESULTS COMPARISON")
    print("=" * 80)
    print(f"{'Metric':<25} {'V4':>15} {'V5':>15} {'V6':>15}")
    print("-" * 80)
    
    metrics = [
        ("Trades", lambda s: f"{s['trades']}", ""),
        ("Win Rate", lambda s: f"{s['win_rate']:.1f}%", "%"),
        ("Total P&L", lambda s: f"${s['total_pnl']:+.2f}", "$"),
        ("Return", lambda s: f"{s['return_pct']:+.1f}%", "%"),
        ("Max Drawdown", lambda s: f"{s['max_drawdown']:.1f}%", "%"),
        ("Profit Factor", lambda s: f"{s['profit_factor']:.2f}", ""),
        ("Final Bankroll", lambda s: f"${s['final_bankroll']:.2f}", "$"),
    ]
    
    for name, fmt, unit in metrics:
        print(f"{name:<25} {fmt(results[0]):>15} {fmt(results[1]):>15} {fmt(results[2]):>15}")
    
    print()
    print("SAFETY FEATURES")
    print("-" * 80)
    print(f"{'Circuit Breaker Tripped':<25} {str(results[0]['circuit_tripped']):>15} {str(results[1]['circuit_tripped']):>15} {str(results[2]['circuit_tripped']):>15}")
    print()
    
    # Recommendation
    print("=" * 80)
    print("LIVE TRADING RECOMMENDATION")
    print("=" * 80)
    print()
    
    v6_stats = results[2]
    
    # Scoring
    score = 0
    reasons = []
    
    if v6_stats['win_rate'] > 50:
        score += 2
        reasons.append(f"✅ Win rate {v6_stats['win_rate']:.1f}% > 50%")
    else:
        reasons.append(f"❌ Win rate {v6_stats['win_rate']:.1f}% < 50%")
    
    if v6_stats['return_pct'] > 0:
        score += 2
        reasons.append(f"✅ Profitable ({v6_stats['return_pct']:+.1f}%)")
    else:
        reasons.append(f"❌ Not profitable ({v6_stats['return_pct']:+.1f}%)")
    
    if v6_stats['max_drawdown'] < 20:
        score += 2
        reasons.append(f"✅ Max drawdown {v6_stats['max_drawdown']:.1f}% < 20%")
    else:
        reasons.append(f"⚠️ Max drawdown {v6_stats['max_drawdown']:.1f}% > 20%")
    
    if v6_stats['profit_factor'] > 1.0:
        score += 2
        reasons.append(f"✅ Profit factor {v6_stats['profit_factor']:.2f} > 1.0")
    else:
        reasons.append(f"❌ Profit factor {v6_stats['profit_factor']:.2f} < 1.0")
    
    reasons.append(f"{'✅' if v6.has_proxy else '❌'} Proxy rotation")
    reasons.append(f"{'✅' if v6.has_auto_redeem else '❌'} Auto-redeem")
    reasons.append(f"{'✅' if v6.has_circuit_breaker else '❌'} Circuit breaker")
    
    for r in reasons:
        print(f"  {r}")
    
    print()
    print(f"SCORE: {score}/8")
    print()
    
    # Final recommendation
    if score >= 6:
        print("🟢 RECOMMENDATION: READY FOR LIVE TRADING")
        print()
        print(f"Suggested starting capital: ${TEST_BANKROLL}")
        print("Risk level: MODERATE")
        print()
        print("Next steps:")
        print("  1. Set up proxy (IPRoyal ~$5-10)")
        print("  2. Start with $5 positions")
        print("  3. Monitor for 1 week")
        print("  4. Scale to $10 if profitable")
        
    elif score >= 4:
        print("🟡 RECOMMENDATION: CAUTIOUS LIVE TRADING")
        print()
        print(f"Suggested starting capital: ${TEST_BANKROLL / 2:.0f}")
        print("Risk level: HIGH")
        print()
        print("Next steps:")
        print("  1. Paper trade for 1 week")
        print("  2. Add news/sentiment signals")
        print("  3. Start live with $3-5")
        
    else:
        print("🔴 RECOMMENDATION: NOT READY FOR LIVE")
        print()
        print("Issues to fix:")
        print("  - Add information edge (news API)")
        print("  - Improve signal quality")
        print("  - Paper trade until profitable")
    
    print()
    print("=" * 80)
    
    # $10 specific analysis
    print()
    print(f"$10 STARTING CAPITAL ANALYSIS")
    print("-" * 80)
    
    # Position sizing
    position_size = TEST_BANKROLL * 0.20  # 20% per trade = $2
    max_positions = 3
    
    print(f"Position size: ${position_size:.2f} (20% of $10)")
    print(f"Max positions: {max_positions}")
    print(f"Max exposure: ${position_size * max_positions:.2f}")
    print()
    
    # Risk of ruin
    ruin_risk = v6_stats['max_drawdown'] / 100
    if ruin_risk > 0.5:
        print(f"⚠️ HIGH RISK: {ruin_risk*100:.0f}% drawdown could wipe out $10")
    else:
        print(f"✅ MANAGEABLE RISK: {ruin_risk*100:.0f}% drawdown on $10")
    
    print()
    print("Expected outcomes with $10:")
    print(f"  Monthly return (est): ${10 * (v6_stats['return_pct']/100) * 0.1:.2f}")
    print(f"  Monthly return (opt): ${10 * (v6_stats['return_pct']/100):.2f}")
    print(f"  Worst case loss: ${10 * (v6_stats['max_drawdown']/100):.2f}")

if __name__ == "__main__":
    run_comparison()
