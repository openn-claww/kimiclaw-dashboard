#!/usr/bin/env python3
"""
50,000 Trade Backtest: V4 vs Master Bot V5
Tests both bots under identical market conditions with realistic costs.
"""

import random
import json
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from collections import deque
import statistics

# Configuration
NUM_TRADES = 50000
INITIAL_BANKROLL = 500.0
RANDOM_SEED = 42

# Market parameters
COINS = ['BTC', 'ETH', 'SOL', 'XRP']
TIMEFRAMES = [5, 15]
REGIMES = ['TREND_UP', 'TREND_DOWN', 'CHOPPY', 'HIGH_VOL', 'LOW_VOL']

# Trading costs
TAKER_FEE = 0.005  # 0.5% per side
SLIPPAGE_RANGE = (0.001, 0.03)  # 0.1% to 3%
MIN_ORDER = 1.0

# Edge cases (realistic trading failures)
EDGE_CASES = {
    'partial_fill': 0.05,
    'rejected': 0.03,
    'network_delay': 0.08,
    'spread_widen': 0.10,
    'price_slip': 0.15,
    'no_liquidity': 0.02,
    'rate_limit': 0.01,
}

@dataclass
class Trade:
    trade_id: int
    bot_version: str  # 'v4' or 'v5'
    coin: str
    timeframe: int
    regime: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    fees: float
    slippage: float
    gross_pnl: float
    net_pnl: float
    edge_case: Optional[str]
    filtered_by: Optional[str] = None  # Why V5 filtered it out
    won: bool = False

class MarketSimulator:
    """Realistic market simulation with edge cases."""

    def __init__(self, seed=42):
        random.seed(seed)
        np.random.seed(seed)

    def generate_signal(self, coin: str, regime: str) -> dict:
        """Generate a trade signal with realistic edge."""
        # Different regimes have different win rates
        regime_win_rates = {
            'TREND_UP': 0.58,
            'TREND_DOWN': 0.52,
            'CHOPPY': 0.48,
            'HIGH_VOL': 0.45,
            'LOW_VOL': 0.55,
        }

        base_win_rate = regime_win_rates.get(regime, 0.50)

        # Generate entry price (0.20 to 0.80 range mostly)
        entry = random.uniform(0.25, 0.75)

        # Determine if winner
        is_winner = random.random() < base_win_rate

        # Generate exit based on win/loss
        if is_winner:
            exit_price = min(0.95, entry * (1 + random.uniform(0.05, 0.35)))
        else:
            exit_price = max(0.05, entry * (1 - random.uniform(0.05, 0.30)))

        # Side based on regime bias
        if regime == 'TREND_UP':
            side = 'YES' if random.random() < 0.65 else 'NO'
        elif regime == 'TREND_DOWN':
            side = 'NO' if random.random() < 0.65 else 'YES'
        else:
            side = random.choice(['YES', 'NO'])

        return {
            'entry': entry,
            'exit': exit_price,
            'side': side,
            'expected_win': is_winner,
            'regime': regime,
        }

    def apply_edge_case(self) -> Tuple[str, float]:
        """Apply random edge case with slippage impact."""
        roll = random.random()
        cumulative = 0

        for case, prob in EDGE_CASES.items():
            cumulative += prob
            if roll < cumulative:
                # Return case type and extra slippage
                slippage_map = {
                    'partial_fill': random.uniform(0.01, 0.03),
                    'rejected': 0,
                    'network_delay': random.uniform(0.005, 0.015),
                    'spread_widen': random.uniform(0.015, 0.05),
                    'price_slip': random.uniform(0.02, 0.06),
                    'no_liquidity': random.uniform(0.05, 0.10),
                    'rate_limit': random.uniform(0.01, 0.02),
                }
                return case, slippage_map.get(case, 0.01)

        return 'normal', random.uniform(*SLIPPAGE_RANGE)

class V4Strategy:
    """Original V4 strategy - lighter filters."""

    def __init__(self):
        self.trade_count = 0
        self.wins = 0
        self.losses = 0

    def should_trade(self, signal: dict, bankroll: float) -> Tuple[bool, Optional[str], float]:
        """Returns (should_trade, filter_reason, position_size)."""
        self.trade_count += 1

        # Basic checks
        if bankroll < 20:
            return False, 'insufficient_balance', 0

        # Regime timeframe filter (V4 specific)
        regime = signal['regime']
        # V4 skips certain timeframe/regime combos (30% chance)
        if regime in ['TREND_UP', 'TREND_DOWN'] and random.random() < 0.3:
            return False, 'regime_timeframe_mismatch', 0

        # Simple position sizing (5% of bankroll, adjusted by edge)
        base_size = bankroll * 0.05
        size = min(50, max(20, base_size))

        return True, None, size

    def calculate_pnl(self, entry: float, exit: float, size: float, side: str) -> float:
        if side == 'YES':
            return (exit - entry) * size
        else:
            return (entry - exit) * size

class V5Strategy:
    """Master Bot V5 strategy - 7-layer filters."""

    def __init__(self):
        self.trade_count = 0
        self.wins = 0
        self.losses = 0
        self.consec_losses = 0
        self.circuit_breaker_tripped = False
        self.outcomes = deque(maxlen=50)  # For circuit breaker
        self.daily_trades = []  # Track today's trades for daily loss
        self.current_day = 0  # Track day for reset

        # Safety limits
        self.max_daily_loss_pct = 0.15
        self.max_consec_losses = 7
        self.min_win_rate = 0.45
        self.max_single_trade = 75
        self.max_exposure_pct = 0.50

    def check_circuit_breaker(self) -> bool:
        """Stop if win rate < 45% over last 50 trades."""
        if len(self.outcomes) < 50:
            return False
        wr = sum(self.outcomes) / len(self.outcomes)
        if wr < self.min_win_rate:
            self.circuit_breaker_tripped = True
            return True
        return False

    def reset_daily_if_needed(self, day: int):
        """Reset daily counters on new day."""
        if day != self.current_day:
            self.current_day = day
            self.daily_trades = []

    def get_daily_loss(self) -> float:
        """Calculate actual daily loss."""
        return sum(t.net_pnl for t in self.daily_trades if t.net_pnl < 0)

    def should_trade(self, signal: dict, bankroll: float, exposure: float, day: int) -> Tuple[bool, Optional[str], float]:
        """7-layer filter stack."""
        self.trade_count += 1

        # Reset daily counters if new day
        self.reset_daily_if_needed(day)

        # Layer 1: Circuit breaker (only after 50 trades)
        if len(self.outcomes) >= 50 and self.check_circuit_breaker():
            return False, 'circuit_breaker_tripped', 0

        # Layer 2: Kill switch - daily loss (only after some trades)
        daily_loss = abs(self.get_daily_loss())
        if len(self.daily_trades) > 20 and daily_loss / INITIAL_BANKROLL >= self.max_daily_loss_pct:
            return False, 'kill_switch_daily_loss', 0

        # Layer 3: Kill switch - consecutive losses (only check after 7+ trades today)
        if self.consec_losses >= self.max_consec_losses and len(self.daily_trades) > 10:
            return False, 'kill_switch_consec_losses', 0

        # Layer 4: Balance check
        if bankroll < 20:
            return False, 'insufficient_balance', 0

        # Layer 5: Exposure limit
        if exposure / bankroll > self.max_exposure_pct:
            return False, 'max_exposure', 0

        # Layer 6: Zone filter (OFF by default, but check anyway)
        entry = signal['entry']
        side = signal['side']
        effective_price = entry if side == 'YES' else (1 - entry)
        if 0.35 <= effective_price <= 0.65:
            # Only filter if zone filter enabled (simulated 20% of time)
            if random.random() < 0.2:
                return False, 'zone_filter', 0

        # Layer 7: Volume filter (simulated - 15% fail)
        if random.random() < 0.15:
            return False, 'volume_filter', 0

        # Layer 8: Sentiment filter (simulated - 10% fail)
        if random.random() < 0.10:
            return False, 'sentiment_filter', 0

        # Kelly sizing (simplified)
        # Estimate edge from signal quality
        edge = abs(0.5 - entry) * 2  # Higher edge when price extreme
        if edge < 0.10:
            return False, 'kelly_low_edge', 0

        # Kelly fraction (simplified)
        kelly_fraction = edge / 0.5  # Simplified
        kelly_size = bankroll * kelly_fraction * 0.25  # Quarter Kelly

        # Apply limits
        size = min(kelly_size, self.max_single_trade, bankroll * 0.10)
        size = max(MIN_ORDER, size)

        if size < 20:
            return False, 'kelly_size_too_small', 0

        return True, None, size

    def record_outcome(self, won: bool, trade: 'Trade'):
        self.outcomes.append(1 if won else 0)
        self.daily_trades.append(trade)
        if won:
            self.wins += 1
            self.consec_losses = 0
        else:
            self.losses += 1
            self.consec_losses += 1

    def calculate_pnl(self, entry: float, exit: float, size: float, side: str) -> float:
        if side == 'YES':
            return (exit - entry) * size
        else:
            return (entry - exit) * size

def run_backtest():
    """Run 50,000 trade backtest for both bots."""
    print("=" * 70)
    print("50,000 TRADE BACKTEST: V4 vs MASTER BOT V5")
    print("=" * 70)
    print(f"Starting bankroll: ${INITIAL_BANKROLL}")
    print(f"Trading costs: {TAKER_FEE*2:.1%} round-trip + slippage")
    print()
    
    sim = MarketSimulator(seed=42)
    v4 = V4Strategy()
    v5 = V5Strategy()
    
    v4_trades = []
    v5_trades = []
    
    v4_bankroll = INITIAL_BANKROLL
    v5_bankroll = INITIAL_BANKROLL
    v5_exposure = 0
    
    print("Running backtest...")
    
    # Simulate ~100 days of trading (500 trades per day)
    TRADES_PER_DAY = 500
    
    for i in range(NUM_TRADES):
        if i % 5000 == 0:
            print(f"  Progress: {i:,} / {NUM_TRADES:,}")
        
        # Calculate simulated day
        day = i // TRADES_PER_DAY
        
        coin = random.choice(COINS)
        tf = random.choice(TIMEFRAMES)
        regime = random.choice(REGIMES)
        
        signal = sim.generate_signal(coin, regime)
        
        # --- V4 Trade ---
        v4_ok, v4_filter, v4_size = v4.should_trade(signal, v4_bankroll)
        if v4_ok:
            edge_case, extra_slip = sim.apply_edge_case()
            entry_slip = random.uniform(*SLIPPAGE_RANGE) + extra_slip
            exit_slip = random.uniform(0.001, 0.02)
            
            # Adjusted prices with slippage
            entry = signal['entry'] * (1 + entry_slip) if signal['side'] == 'YES' else signal['entry'] * (1 - entry_slip)
            exit_p = signal['exit'] * (1 - exit_slip) if signal['side'] == 'YES' else signal['exit'] * (1 + exit_slip)
            
            gross = v4.calculate_pnl(entry, exit_p, v4_size, signal['side'])
            fees = v4_size * TAKER_FEE * 2
            net = gross - fees
            
            v4_bankroll += net
            won = net > 0
            v4.wins += 1 if won else 0
            v4.losses += 0 if won else 1
            
            v4_trades.append(Trade(
                trade_id=i, bot_version='v4', coin=coin, timeframe=tf, regime=regime,
                side=signal['side'], entry_price=entry, exit_price=exit_p,
                size=v4_size, fees=fees, slippage=entry_slip + exit_slip,
                gross_pnl=gross, net_pnl=net, edge_case=edge_case,
                won=won
            ))
        else:
            # Filtered trade - record as skipped
            v4_trades.append(Trade(
                trade_id=i, bot_version='v4', coin=coin, timeframe=tf, regime=regime,
                side=signal['side'], entry_price=0, exit_price=0, size=0, fees=0,
                slippage=0, gross_pnl=0, net_pnl=0, edge_case='filtered',
                filtered_by=v4_filter, won=False
            ))
        
        # --- V5 Trade ---
        v5_ok, v5_filter, v5_size = v5.should_trade(signal, v5_bankroll, v5_exposure, day)
        if v5_ok:
            edge_case, extra_slip = sim.apply_edge_case()
            entry_slip = random.uniform(*SLIPPAGE_RANGE) + extra_slip
            exit_slip = random.uniform(0.001, 0.02)
            
            entry = signal['entry'] * (1 + entry_slip) if signal['side'] == 'YES' else signal['entry'] * (1 - entry_slip)
            exit_p = signal['exit'] * (1 - exit_slip) if signal['side'] == 'YES' else signal['exit'] * (1 + exit_slip)
            
            gross = v5.calculate_pnl(entry, exit_p, v5_size, signal['side'])
            fees = v5_size * TAKER_FEE * 2
            net = gross - fees
            
            v5_bankroll += net
            won = net > 0
            
            trade = Trade(
                trade_id=i, bot_version='v5', coin=coin, timeframe=tf, regime=regime,
                side=signal['side'], entry_price=entry, exit_price=exit_p,
                size=v5_size, fees=fees, slippage=entry_slip + exit_slip,
                gross_pnl=gross, net_pnl=net, edge_case=edge_case,
                won=won
            )
            
            v5.record_outcome(won, trade)
            v5_exposure = max(0, v5_exposure - v5_size + (v5_size + net if won else 0))
            
            v5_trades.append(trade)
        else:
            v5_trades.append(Trade(
                trade_id=i, bot_version='v5', coin=coin, timeframe=tf, regime=regime,
                side=signal['side'], entry_price=0, exit_price=0, size=0, fees=0,
                slippage=0, gross_pnl=0, net_pnl=0, edge_case='filtered',
                filtered_by=v5_filter, won=False
            ))
    
    return v4_trades, v5_trades, v4, v5

def analyze(trades: List[Trade], bot_name: str) -> dict:
    """Analyze backtest results."""
    executed = [t for t in trades if t.size > 0]
    winners = [t for t in executed if t.won]
    losers = [t for t in executed if not t.won]

    total_pnl = sum(t.net_pnl for t in executed)
    gross_pnl = sum(t.gross_pnl for t in executed)
    total_fees = sum(t.fees for t in executed)
    total_slip = sum(t.slippage for t in executed)

    win_rate = len(winners) / len(executed) * 100 if executed else 0

    # Profit factor
    total_wins = sum(t.net_pnl for t in winners)
    total_losses = abs(sum(t.net_pnl for t in losers))
    pf = total_wins / total_losses if total_losses > 0 else float('inf')

    # Filter analysis
    filtered = [t for t in trades if t.filtered_by]
    filter_reasons = {}
    for t in filtered:
        reason = t.filtered_by or 'unknown'
        filter_reasons[reason] = filter_reasons.get(reason, 0) + 1

    # Edge case analysis
    edge_cases = {}
    for t in executed:
        case = t.edge_case or 'normal'
        if case not in edge_cases:
            edge_cases[case] = {'count': 0, 'pnl': 0}
        edge_cases[case]['count'] += 1
        edge_cases[case]['pnl'] += t.net_pnl

    return {
        'name': bot_name,
        'total_attempts': len(trades),
        'executed': len(executed),
        'filtered': len(filtered),
        'winners': len(winners),
        'losers': len(losers),
        'win_rate': win_rate,
        'gross_pnl': gross_pnl,
        'total_fees': total_fees,
        'total_slippage': total_slip,
        'net_pnl': total_pnl,
        'return_pct': (total_pnl / INITIAL_BANKROLL) * 100,
        'profit_factor': pf,
        'avg_trade_pnl': total_pnl / len(executed) if executed else 0,
        'filter_reasons': filter_reasons,
        'edge_cases': edge_cases,
        'final_bankroll': INITIAL_BANKROLL + total_pnl,
    }

def print_comparison(v4_stats: dict, v5_stats: dict):
    """Print detailed comparison."""
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS COMPARISON")
    print("=" * 70)
    print()

    print(f"{'METRIC':<30} {'V4':>18} {'V5':>18} {'WINNER':>10}")
    print("-" * 80)

    def print_row(name, v4_val, v5_val, fmt=".2f", higher_is_better=True):
        if isinstance(v4_val, float):
            v4_str = f"{v4_val:{fmt}}"
            v5_str = f"{v5_val:{fmt}}"
        else:
            v4_str = str(v4_val)
            v5_str = str(v5_val)

        if higher_is_better:
            winner = "V4" if v4_val > v5_val else "V5" if v5_val > v4_val else "TIE"
        else:
            winner = "V4" if v4_val < v5_val else "V5" if v5_val < v4_val else "TIE"

        print(f"{name:<30} {v4_str:>18} {v5_str:>18} {winner:>10}")

    print_row("Starting Bankroll", INITIAL_BANKROLL, INITIAL_BANKROLL, ".2f", False)
    print_row("Final Bankroll", v4_stats['final_bankroll'], v5_stats['final_bankroll'], ".2f")
    print_row("Net P&L ($)", v4_stats['net_pnl'], v5_stats['net_pnl'], ".2f")
    print_row("Return (%)", v4_stats['return_pct'], v5_stats['return_pct'], ".2f")
    print()
    print_row("Trades Attempted", v4_stats['total_attempts'], v5_stats['total_attempts'], "", False)
    print_row("Trades Executed", v4_stats['executed'], v5_stats['executed'], "")
    print_row("Trades Filtered", v4_stats['filtered'], v5_stats['filtered'], "", False)
    print_row("Winners", v4_stats['winners'], v5_stats['winners'], "")
    print_row("Losers", v4_stats['losers'], v5_stats['losers'], "", False)
    print_row("Win Rate (%)", v4_stats['win_rate'], v5_stats['win_rate'], ".2f")
    print()
    print_row("Gross P&L ($)", v4_stats['gross_pnl'], v5_stats['gross_pnl'], ".2f")
    print_row("Total Fees ($)", v4_stats['total_fees'], v5_stats['total_fees'], ".2f", False)
    print_row("Total Slippage", v4_stats['total_slippage'], v5_stats['total_slippage'], ".4f", False)
    print_row("Profit Factor", v4_stats['profit_factor'], v5_stats['profit_factor'], ".3f")
    print_row("Avg Trade P&L ($)", v4_stats['avg_trade_pnl'], v5_stats['avg_trade_pnl'], ".3f")

    # Filter breakdown
    print("\n" + "=" * 70)
    print("V5 FILTER BREAKDOWN")
    print("=" * 70)
    print()
    for reason, count in sorted(v5_stats['filter_reasons'].items(), key=lambda x: -x[1]):
        pct = count / v5_stats['total_attempts'] * 100
        print(f"  {reason:<30} {count:>6} trades ({pct:>5.1f}%)")

    # Edge case analysis
    print("\n" + "=" * 70)
    print("EDGE CASE IMPACT")
    print("=" * 70)
    print()
    print(f"{'EDGE CASE':<20} {'V4 COUNT':>10} {'V4 P&L':>12} {'V5 COUNT':>10} {'V5 P&L':>12}")
    print("-" * 70)

    all_cases = set(v4_stats['edge_cases'].keys()) | set(v5_stats['edge_cases'].keys())
    for case in sorted(all_cases):
        v4_data = v4_stats['edge_cases'].get(case, {'count': 0, 'pnl': 0})
        v5_data = v5_stats['edge_cases'].get(case, {'count': 0, 'pnl': 0})
        print(f"{case:<20} {v4_data['count']:>10} ${v4_data['pnl']:>+10.2f} {v5_data['count']:>10} ${v5_data['pnl']:>+10.2f}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    v4_pnl = v4_stats['net_pnl']
    v5_pnl = v5_stats['net_pnl']

    if v5_pnl > v4_pnl:
        diff = v5_pnl - v4_pnl
        print(f"🏆 WINNER: Master Bot V5")
        print(f"   Outperformed V4 by ${diff:+.2f} ({diff/INITIAL_BANKROLL*100:+.1f}%)")
    elif v4_pnl > v5_pnl:
        diff = v4_pnl - v5_pnl
        print(f"🏆 WINNER: V4")
        print(f"   Outperformed V5 by ${diff:+.2f} ({diff/INITIAL_BANKROLL*100:+.1f}%)")
    else:
        print("🏆 RESULT: Tie")

    print()
    print("Key Insights:")
    print(f"  • V4 executed {v4_stats['executed']:,} trades ({v4_stats['executed']/500:.1f}% of attempts)")
    print(f"  • V5 executed {v5_stats['executed']:,} trades ({v5_stats['executed']/500:.1f}% of attempts)")
    print(f"  • V5 filtered out {v5_stats['filtered']:,} trades ({v5_stats['filtered']/500:.1f}%)")
    print(f"  • V5 win rate: {v5_stats['win_rate']:.1f}% vs V4: {v4_stats['win_rate']:.1f}%")

    if v5_stats['profit_factor'] > v4_stats['profit_factor']:
        print(f"  • V5 has better profit factor ({v5_stats['profit_factor']:.2f} vs {v4_stats['profit_factor']:.2f})")

    print()
    print("Trade-off Analysis:")
    print("  • V4: More trades, simpler filters, higher activity")
    print("  • V5: Fewer trades, strict filters, better risk control")
    print()
    print("Recommendation:")
    if v5_pnl > v4_pnl and v5_stats['win_rate'] > v4_stats['win_rate']:
        print("  ✅ Use Master Bot V5 - Better P&L AND win rate")
    elif v5_stats['win_rate'] > v4_stats['win_rate']:
        print("  ✅ Use Master Bot V5 - Better win rate (quality over quantity)")
    else:
        print("  ⚠️  V4 may be better for active trading, V5 for conservative")

if __name__ == '__main__':
    v4_trades, v5_trades, v4_bot, v5_bot = run_backtest()
    v4_stats = analyze(v4_trades, 'V4')
    v5_stats = analyze(v5_trades, 'V5')
    print_comparison(v4_stats, v5_stats)
