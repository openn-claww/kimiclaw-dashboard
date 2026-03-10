"""
backtest_compare.py
Polymarket Binary Market Backtest — Fixed Payout Math
Compares Production (no dead zone) vs Zoned (blocks 0.35-0.65) strategies.

PAYOUT MODEL (correct):
  - Buy YES at price P with stake S
  - Win:  receive S / P (your shares) × 1.0 = S/P ... net profit = S * (1-P)/P - fee
  - Actually simpler: stake S buys S/P shares of YES at price P
    If win: receive (S/P) * 1.0 = S/P dollars → profit = S/P - S = S*(1-P)/P
    Fee = 2% of gross winnings only → fee = 0.02 * S*(1-P)/P
    Net profit = S*(1-P)/P * 0.98
  - Lose: lose S (no fee)

REALISTIC EDGE:
  - A good signal gives you 1-5% above the market's implied probability
  - 51-55% win rate on near-50/50 markets
  - Expected annual returns: 20-100%, NOT 88,000%
"""

import random
import statistics
from dataclasses import dataclass, field
from typing import List, Optional


# ─── CONFIG ──────────────────────────────────────────────────────────────────

STARTING_BANKROLL    = 500.0
N_TRADES             = 50_000
FIXED_STAKE          = 5.0         # Fixed $5 per trade (realistic for a $500 bot)
POLYMARKET_FEE       = 0.02        # 2% fee on gross winnings
PRICE_BOUNDS         = (0.15, 0.85)
DEAD_ZONE            = (0.35, 0.65)
TRUE_EDGE            = 0.03        # Bot has 3% edge over market price (realistic assumption)
RANDOM_SEED          = 42

# NOTE: Fixed stakes are used instead of % compounding because:
# 1. A $500 bot has market capacity constraints
# 2. Compounding with extreme-odds markets (0.025 = 39x) produces unrealistic numbers
# 3. Fixed stakes show true per-trade EV more honestly


# ─── DATA CLASSES ────────────────────────────────────────────────────────────

@dataclass
class TradeResult:
    trade_num:    int
    entry_price:  float
    stake:        float
    side:         str          # 'YES' or 'NO'
    won:          bool
    gross_pnl:    float
    fee:          float
    net_pnl:      float
    bankroll_after: float
    blocked_by_zone: bool = False


@dataclass
class BacktestStats:
    strategy_name:    str
    starting_bankroll: float
    final_bankroll:   float
    total_trades:     int
    wins:             int
    losses:           int
    blocked:          int
    total_net_pnl:    float
    win_rate:         float
    avg_net_pnl:      float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_approx:    float
    trade_pnls:       List[float] = field(default_factory=list)


# ─── PAYOUT CALCULATION ──────────────────────────────────────────────────────

def calculate_pnl(stake: float, entry_price: float, side: str, won: bool) -> tuple[float, float, float]:
    """
    Returns (gross_pnl, fee, net_pnl).

    Binary market mechanics:
      YES at price P:  stake S buys (S/P) shares
        Win  → receive S/P dollars, gross profit = S*(1-P)/P
        Lose → lose S, gross profit = -S

      NO at price P:  equivalent to YES at (1-P)
        Win  → gross profit = S * P / (1-P)
        Lose → lose S
    """
    if side == 'YES':
        if won:
            gross_profit = stake * (1 - entry_price) / entry_price
            fee          = POLYMARKET_FEE * gross_profit
            net_pnl      = gross_profit - fee
        else:
            gross_profit = -stake
            fee          = 0.0
            net_pnl      = -stake

    else:  # NO
        no_price = 1 - entry_price
        if won:
            gross_profit = stake * entry_price / no_price
            fee          = POLYMARKET_FEE * gross_profit
            net_pnl      = gross_profit - fee
        else:
            gross_profit = -stake
            fee          = 0.0
            net_pnl      = -stake

    return gross_profit, fee, net_pnl


# ─── MARKET SIMULATION ───────────────────────────────────────────────────────

def simulate_market_price(rng: random.Random) -> float:
    """
    Generate a realistic Polymarket entry price.
    15m crypto markets cluster near 0.50 but have fat tails.
    """
    # Mix of near-center and extreme prices
    roll = rng.random()
    if roll < 0.60:
        # Near-center trades (0.30–0.70)
        return rng.uniform(0.30, 0.70)
    elif roll < 0.85:
        # Edge trades (0.15–0.30 or 0.70–0.85)
        if rng.random() < 0.5:
            return rng.uniform(0.15, 0.30)
        else:
            return rng.uniform(0.70, 0.85)
    else:
        # Extreme prices (0.15–0.20 or 0.80–0.85) — rare moonshots
        if rng.random() < 0.5:
            return rng.uniform(0.15, 0.22)
        else:
            return rng.uniform(0.78, 0.85)


def did_win(entry_price: float, side: str, edge: float, rng: random.Random) -> bool:
    """
    Determine trade outcome.
    The bot's edge means its TRUE win probability is slightly better
    than what the market price implies.

    Market-implied YES prob = entry_price
    Bot's estimated true YES prob = entry_price + edge  (for YES trades)
    """
    if side == 'YES':
        true_prob = min(entry_price + edge, 0.95)
    else:
        true_prob = min((1 - entry_price) + edge, 0.95)

    return rng.random() < true_prob


# ─── STRATEGY FILTERS ────────────────────────────────────────────────────────

def production_filter(price: float) -> tuple[bool, str]:
    """No dead zone — take all trades within price bounds."""
    lo, hi = PRICE_BOUNDS
    if not (lo <= price <= hi):
        return False, 'out_of_bounds'
    return True, 'ok'


def zoned_filter(price: float) -> tuple[bool, str]:
    """Block trades in the dead zone (0.35–0.65)."""
    lo, hi = PRICE_BOUNDS
    dz_lo, dz_hi = DEAD_ZONE
    if not (lo <= price <= hi):
        return False, 'out_of_bounds'
    if dz_lo <= price <= dz_hi:
        return False, 'dead_zone'
    return True, 'ok'


# ─── SINGLE BACKTEST RUN ─────────────────────────────────────────────────────

def run_backtest(
    strategy_name: str,
    filter_fn,
    n_trades: int = N_TRADES,
    edge: float = TRUE_EDGE,
    seed: int = RANDOM_SEED,
) -> BacktestStats:

    rng        = random.Random(seed)
    bankroll   = STARTING_BANKROLL
    peak       = bankroll
    max_dd     = 0.0

    wins = losses = blocked = 0
    trade_pnls: List[float] = []
    results: List[TradeResult] = []

    for i in range(n_trades):
        price   = simulate_market_price(rng)
        side    = 'YES' if rng.random() < 0.5 else 'NO'
        allowed, reason = filter_fn(price)

        if not allowed:
            blocked += 1
            continue

        stake        = min(FIXED_STAKE, bankroll)  # can't bet more than remaining bankroll
        won          = did_win(price, side, edge, rng)
        gross, fee, net = calculate_pnl(stake, price, side, won)

        bankroll    += net
        bankroll     = max(bankroll, 0.0)  # floor at zero (ruin)

        # Drawdown tracking
        if bankroll > peak:
            peak = bankroll
        dd = (peak - bankroll) / peak * 100
        if dd > max_dd:
            max_dd = dd

        if won:
            wins += 1
        else:
            losses += 1

        trade_pnls.append(net)

        if bankroll <= 0:
            print(f"  [{strategy_name}] RUIN at trade {i+1}")
            break

    total_trades = wins + losses
    win_rate     = wins / total_trades if total_trades > 0 else 0
    avg_net_pnl  = statistics.mean(trade_pnls) if trade_pnls else 0
    total_net    = sum(trade_pnls)
    total_return = (bankroll - STARTING_BANKROLL) / STARTING_BANKROLL * 100

    # Approximate Sharpe (annualized, assuming 100 trades/day)
    if len(trade_pnls) > 1:
        pnl_std = statistics.stdev(trade_pnls)
        sharpe  = (avg_net_pnl / pnl_std * (100 ** 0.5)) if pnl_std > 0 else 0
    else:
        sharpe = 0

    return BacktestStats(
        strategy_name=strategy_name,
        starting_bankroll=STARTING_BANKROLL,
        final_bankroll=bankroll,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        blocked=blocked,
        total_net_pnl=total_net,
        win_rate=win_rate,
        avg_net_pnl=avg_net_pnl,
        total_return_pct=total_return,
        max_drawdown_pct=max_dd,
        sharpe_approx=sharpe,
        trade_pnls=trade_pnls,
    )


# ─── SENSITIVITY ANALYSIS ────────────────────────────────────────────────────

def run_sensitivity(filter_fn, filter_name: str):
    """Test multiple edge assumptions to see how sensitive results are."""
    print(f"\n  {'Edge':>6}  {'Win Rate':>9}  {'Final $':>10}  {'Return':>8}  {'MaxDD':>7}")
    print(f"  {'─'*6}  {'─'*9}  {'─'*10}  {'─'*8}  {'─'*7}")
    for edge in [0.00, 0.01, 0.02, 0.03, 0.05, 0.08]:
        stats = run_backtest(filter_name, filter_fn, edge=edge)
        print(f"  {edge:>6.2f}  {stats.win_rate:>8.1%}  "
              f"${stats.final_bankroll:>9,.2f}  "
              f"{stats.total_return_pct:>7.1f}%  "
              f"{stats.max_drawdown_pct:>6.1f}%")


# ─── PRINT REPORT ────────────────────────────────────────────────────────────

def print_stats(s: BacktestStats):
    divider = "─" * 52
    print(f"\n{'═'*52}")
    print(f"  Strategy: {s.strategy_name}")
    print(f"{'═'*52}")
    print(f"  {'Starting Bankroll':<28} ${s.starting_bankroll:>10,.2f}")
    print(f"  {'Final Bankroll':<28} ${s.final_bankroll:>10,.2f}")
    print(f"  {'Total Net PnL':<28} ${s.total_net_pnl:>+10,.2f}")
    print(f"  {'Total Return':<28} {s.total_return_pct:>+10.2f}%")
    print(f"  {divider}")
    print(f"  {'Trades Taken':<28} {s.total_trades:>10,}")
    print(f"  {'Trades Blocked':<28} {s.blocked:>10,}")
    print(f"  {'Wins':<28} {s.wins:>10,}")
    print(f"  {'Losses':<28} {s.losses:>10,}")
    print(f"  {'Win Rate':<28} {s.win_rate:>10.2%}")
    print(f"  {divider}")
    print(f"  {'Avg Net PnL / Trade':<28} ${s.avg_net_pnl:>+10.4f}")
    print(f"  {'Max Drawdown':<28} {s.max_drawdown_pct:>10.2f}%")
    print(f"  {'Sharpe (approx)':<28} {s.sharpe_approx:>10.3f}")

    # Percentile distribution of trade PnLs
    if s.trade_pnls:
        sorted_pnls = sorted(s.trade_pnls)
        n = len(sorted_pnls)
        print(f"  {divider}")
        print(f"  PnL Percentiles:")
        for pct in [5, 25, 50, 75, 95]:
            idx = int(pct / 100 * n)
            print(f"    P{pct:>2}  ${sorted_pnls[idx]:>+8.4f}")


def print_comparison(prod: BacktestStats, zoned: BacktestStats):
    print(f"\n{'═'*60}")
    print(f"  HEAD-TO-HEAD COMPARISON ({N_TRADES:,} attempted trades)")
    print(f"{'═'*60}")
    metrics = [
        ("Final Bankroll",    f"${prod.final_bankroll:,.2f}",   f"${zoned.final_bankroll:,.2f}"),
        ("Total Return",      f"{prod.total_return_pct:+.2f}%", f"{zoned.total_return_pct:+.2f}%"),
        ("Trades Taken",      f"{prod.total_trades:,}",         f"{zoned.total_trades:,}"),
        ("Win Rate",          f"{prod.win_rate:.2%}",           f"{zoned.win_rate:.2%}"),
        ("Avg Trade PnL",     f"${prod.avg_net_pnl:+.4f}",     f"${zoned.avg_net_pnl:+.4f}"),
        ("Max Drawdown",      f"{prod.max_drawdown_pct:.2f}%",  f"{zoned.max_drawdown_pct:.2f}%"),
        ("Sharpe (approx)",   f"{prod.sharpe_approx:.3f}",      f"{zoned.sharpe_approx:.3f}"),
    ]
    print(f"  {'Metric':<22} {'Production':>16} {'Zoned':>16}")
    print(f"  {'─'*22} {'─'*16} {'─'*16}")
    for name, pv, zv in metrics:
        print(f"  {name:<22} {pv:>16} {zv:>16}")

    winner_return = "Production" if prod.total_return_pct > zoned.total_return_pct else "Zoned"
    winner_sharpe = "Production" if prod.sharpe_approx  > zoned.sharpe_approx  else "Zoned"
    print(f"\n  ▶ Higher Return: {winner_return}")
    print(f"  ▶ Better Risk-Adjusted: {winner_sharpe}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Polymarket Binary Market Backtest — Fixed Payout Model")
    print(f"N={N_TRADES:,} trades | Edge={TRUE_EDGE:.0%} | Fee={POLYMARKET_FEE:.0%} | Fixed Stake=${FIXED_STAKE:.2f}")

    print("\nRunning Production strategy...")
    prod_stats = run_backtest("Production (No Dead Zone)", production_filter)

    print("Running Zoned strategy...")
    zoned_stats = run_backtest("Zoned (Blocks 0.35-0.65)", zoned_filter)

    print_stats(prod_stats)
    print_stats(zoned_stats)
    print_comparison(prod_stats, zoned_stats)

    print(f"\n{'═'*52}")
    print("  SENSITIVITY ANALYSIS — Production Strategy")
    print("  (How results change with different edge assumptions)")
    print(f"{'═'*52}")
    run_sensitivity(production_filter, "Production")

    print(f"\n{'═'*52}")
    print("  SENSITIVITY ANALYSIS — Zoned Strategy")
    print(f"{'═'*52}")
    run_sensitivity(zoned_filter, "Zoned")

    print(f"\n{'═'*52}")
    print("  SANITY CHECK")
    print(f"{'═'*52}")
    no_edge = run_backtest("Zero Edge (Random)", production_filter, edge=0.0)
    print(f"  Zero-edge return: {no_edge.total_return_pct:+.2f}%  (should be near 0% or negative due to fees)")
    print(f"  Zero-edge win rate: {no_edge.win_rate:.2%}  (should be ~50%)")
    print(f"\n  If zero-edge shows >5% return, simulation has a bug.")
    print()
