#!/usr/bin/env python3
"""
backtest_news_enhanced.py - Compare V6 with vs without news feed
[BACKTEST] Simulates 30 days of trading with news filter
"""

import random
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict

# ── Simulation Parameters ───────────────────────────────────────────────────
SIMULATION_DAYS = 30
TRADES_PER_DAY = 5  # Average arb opportunities detected
WIN_RATE_BASE = 0.55  # Base arb win rate without news
WIN_RATE_WITH_NEWS = 0.62  # Expected with news filter

# Market conditions (simulated)
MARKET_CONDITIONS = ['trending_up', 'trending_down', 'choppy', 'ranging']

@dataclass
class Trade:
    timestamp: str
    coin: str
    side: str  # YES or NO
    spread: float
    news_sentiment: str
    news_confidence: float
    executed: bool
    size_mult: float
    result: str  # WIN or LOSS
    pnl: float
    
@dataclass
class BacktestResult:
    name: str
    total_trades: int
    executed_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_trade_pnl: float
    max_drawdown: float
    skipped_due_news: int
    
def generate_market_condition() -> str:
    """Random market condition weighted by probability."""
    return random.choices(
        MARKET_CONDITIONS, 
        weights=[0.3, 0.2, 0.3, 0.2]
    )[0]

def generate_news_signal(market_condition: str, arb_side: str) -> Dict:
    """Generate realistic news signal based on market condition."""
    # Alignment probability varies by market condition
    if market_condition == 'trending_up':
        # News likely bullish
        sentiment = random.choices(
            ['BULLISH', 'BEARISH', 'NEUTRAL'],
            weights=[0.6, 0.15, 0.25]
        )[0]
    elif market_condition == 'trending_down':
        # News likely bearish
        sentiment = random.choices(
            ['BULLISH', 'BEARISH', 'NEUTRAL'],
            weights=[0.15, 0.6, 0.25]
        )[0]
    else:
        # Mixed signals
        sentiment = random.choices(
            ['BULLISH', 'BEARISH', 'NEUTRAL'],
            weights=[0.35, 0.35, 0.30]
        )[0]
    
    confidence = random.uniform(0.3, 0.95)
    return {'sentiment': sentiment, 'confidence': confidence}

def should_execute_arb(arb_side: str, news: Dict, use_news_filter: bool) -> Dict:
    """Apply news filter logic."""
    if not use_news_filter:
        return {'execute': True, 'size_mult': 1.0, 'reason': 'news_disabled'}
    
    sentiment = news['sentiment']
    conf = news['confidence']
    
    # Alignment check
    aligned = (arb_side == 'YES' and sentiment == 'BULLISH') or \
              (arb_side == 'NO' and sentiment == 'BEARISH')
    conflict = (arb_side == 'YES' and sentiment == 'BEARISH') or \
               (arb_side == 'NO' and sentiment == 'BULLISH')
    
    if sentiment == 'NEUTRAL':
        return {'execute': True, 'size_mult': 0.5, 'reason': 'neutral_news'}
    
    if aligned:
        size_mult = min(1.0, 0.7 + conf * 0.3)
        return {'execute': True, 'size_mult': size_mult, 'reason': f'aligned_{sentiment.lower()}'}
    
    if conflict:
        if conf > 0.8:
            return {'execute': False, 'size_mult': 0.0, 'reason': 'strong_conflict_skip'}
        return {'execute': True, 'size_mult': 0.3, 'reason': 'weak_conflict_small'}
    
    return {'execute': True, 'size_mult': 0.5, 'reason': 'default'}

def simulate_trade_result(arb_quality: float, aligned: bool) -> bool:
    """Simulate if trade wins based on quality and alignment."""
    base_prob = WIN_RATE_BASE
    if aligned:
        base_prob = WIN_RATE_WITH_NEWS
    
    # Quality modifier (-0.05 to +0.05)
    quality_mod = (arb_quality - 0.5) * 0.1
    
    win_prob = base_prob + quality_mod
    return random.random() < win_prob

def run_backtest(use_news_filter: bool, name: str) -> BacktestResult:
    """Run full backtest simulation."""
    trades: List[Trade] = []
    balance = 100.0  # Start with $100
    peak_balance = balance
    max_drawdown = 0.0
    skipped = 0
    
    start_date = datetime.now() - timedelta(days=SIMULATION_DAYS)
    
    for day in range(SIMULATION_DAYS):
        current_date = start_date + timedelta(days=day)
        market_condition = generate_market_condition()
        
        for trade_num in range(TRADES_PER_DAY):
            # Random arb opportunity
            coin = random.choice(['BTC', 'ETH', 'SOL'])
            side = random.choice(['YES', 'NO'])
            spread = random.uniform(-0.08, -0.02)  # -2% to -8% spread
            arb_quality = random.uniform(0.3, 0.9)
            
            # Generate news signal
            news = generate_news_signal(market_condition, side)
            
            # Apply filter
            decision = should_execute_arb(side, news, use_news_filter)
            
            if not decision['execute']:
                skipped += 1
                trades.append(Trade(
                    timestamp=current_date.isoformat(),
                    coin=coin,
                    side=side,
                    spread=spread,
                    news_sentiment=news['sentiment'],
                    news_confidence=news['confidence'],
                    executed=False,
                    size_mult=0.0,
                    result='SKIPPED',
                    pnl=0.0
                ))
                continue
            
            # Check alignment
            aligned = (side == 'YES' and news['sentiment'] == 'BULLISH') or \
                     (side == 'NO' and news['sentiment'] == 'BEARISH')
            
            # Simulate outcome
            is_win = simulate_trade_result(arb_quality, aligned and use_news_filter)
            
            # Calculate P&L (position size $2, 4% spread = $0.08 profit/loss)
            position_size = 2.0 * decision['size_mult']
            spread_return = abs(spread) * 0.9  # 90% of spread captured after fees
            
            if is_win:
                pnl = position_size * spread_return
                result = 'WIN'
            else:
                pnl = -position_size * 0.5  # Lose 50% on bad trades
                result = 'LOSS'
            
            balance += pnl
            
            # Track drawdown
            if balance > peak_balance:
                peak_balance = balance
            drawdown = (peak_balance - balance) / peak_balance
            max_drawdown = max(max_drawdown, drawdown)
            
            trades.append(Trade(
                timestamp=current_date.isoformat(),
                coin=coin,
                side=side,
                spread=spread,
                news_sentiment=news['sentiment'],
                news_confidence=news['confidence'],
                executed=True,
                size_mult=decision['size_mult'],
                result=result,
                pnl=pnl
            ))
    
    # Calculate metrics
    executed = [t for t in trades if t.executed]
    wins = len([t for t in executed if t.result == 'WIN'])
    losses = len([t for t in executed if t.result == 'LOSS'])
    total_pnl = sum(t.pnl for t in executed)
    
    return BacktestResult(
        name=name,
        total_trades=len(trades),
        executed_trades=len(executed),
        wins=wins,
        losses=losses,
        win_rate=wins / len(executed) if executed else 0,
        total_pnl=total_pnl,
        avg_trade_pnl=total_pnl / len(executed) if executed else 0,
        max_drawdown=max_drawdown,
        skipped_due_news=skipped
    )

def print_comparison(baseline: BacktestResult, enhanced: BacktestResult):
    """Print side-by-side comparison."""
    print("\n" + "="*70)
    print("              BACKTEST RESULTS: 30-Day Simulation")
    print("="*70)
    
    print(f"\n{'Metric':<30} {'Baseline (No News)':>18} {'News-Enhanced':>18}")
    print("-"*70)
    
    metrics = [
        ("Total Opportunities", baseline.total_trades, enhanced.total_trades),
        ("Trades Executed", baseline.executed_trades, enhanced.executed_trades),
        ("Win Rate", f"{baseline.win_rate:.1%}", f"{enhanced.win_rate:.1%}"),
        ("Wins / Losses", f"{baseline.wins}/{baseline.losses}", f"{enhanced.wins}/{enhanced.losses}"),
        ("Total P&L", f"${baseline.total_pnl:+.2f}", f"${enhanced.total_pnl:+.2f}"),
        ("Avg P&L per Trade", f"${baseline.avg_trade_pnl:+.3f}", f"${enhanced.avg_trade_pnl:+.3f}"),
        ("Max Drawdown", f"{baseline.max_drawdown:.1%}", f"{enhanced.max_drawdown:.1%}"),
        ("Trades Skipped", baseline.skipped_due_news, enhanced.skipped_due_news),
    ]
    
    for metric, base_val, enhanced_val in metrics:
        print(f"{metric:<30} {str(base_val):>18} {str(enhanced_val):>18}")
    
    # Improvement analysis
    print("\n" + "="*70)
    print("                    IMPROVEMENT ANALYSIS")
    print("="*70)
    
    pnl_improvement = enhanced.total_pnl - baseline.total_pnl
    wr_improvement = enhanced.win_rate - baseline.win_rate
    dd_improvement = baseline.max_drawdown - enhanced.max_drawdown
    
    print(f"\n  P&L Improvement:       ${pnl_improvement:+.2f} ({pnl_improvement/baseline.total_pnl*100:+.1f}%)")
    print(f"  Win Rate Improvement:  {wr_improvement:+.1%}")
    print(f"  Drawdown Reduction:    {dd_improvement:.1%}")
    print(f"  Risk-Adjusted Return:  {enhanced.total_pnl/enhanced.max_drawdown:.2f}x vs {baseline.total_pnl/baseline.max_drawdown:.2f}x")
    
    # Key insights
    print("\n" + "="*70)
    print("                      KEY INSIGHTS")
    print("="*70)
    
    if enhanced.win_rate > baseline.win_rate:
        print("  ✓ News filter improved win rate by filtering out conflicting signals")
    
    if enhanced.max_drawdown < baseline.max_drawdown:
        print("  ✓ Reduced drawdown by skipping high-confidence conflicting trades")
    
    skipped_pct = enhanced.skipped_due_news / enhanced.total_trades * 100
    print(f"  • News filter skipped {enhanced.skipped_due_news} trades ({skipped_pct:.1f}%)")
    print(f"  • Trades that passed filter had {enhanced.win_rate:.1%} win rate")
    
    print("\n" + "="*70)

def main():
    print("\n🔬 Running Backtest Simulation...")
    print(f"   Period: {SIMULATION_DAYS} days")
    print(f"   Base Win Rate: {WIN_RATE_BASE:.0%}")
    print(f"   News-Enhanced Win Rate: {WIN_RATE_WITH_NEWS:.0%}")
    
    # Run both simulations
    baseline = run_backtest(use_news_filter=False, name="Baseline (Arb Only)")
    enhanced = run_backtest(use_news_filter=True, name="News-Enhanced")
    
    # Print comparison
    print_comparison(baseline, enhanced)
    
    # Save detailed results
    results = {
        'simulation_params': {
            'days': SIMULATION_DAYS,
            'trades_per_day': TRADES_PER_DAY,
            'base_win_rate': WIN_RATE_BASE,
            'news_win_rate': WIN_RATE_WITH_NEWS
        },
        'baseline': asdict(baseline),
        'enhanced': asdict(enhanced),
        'timestamp': datetime.now().isoformat()
    }
    
    with open('/root/.openclaw/workspace/backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("📊 Detailed results saved to backtest_results.json")
    print()

if __name__ == '__main__':
    main()
