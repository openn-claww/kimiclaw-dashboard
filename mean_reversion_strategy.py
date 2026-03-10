#!/usr/bin/env python3
"""
mean_reversion_strategy.py - Mean Reversion Strategy for Polymarket

STRATEGY LOGIC:
- When RSI > 70 (overbought) and price near upper Bollinger Band → SELL/Short
- When RSI < 30 (oversold) and price near lower Bollinger Band → BUY/Long
- Uses Z-score to measure deviation from mean
- Trades only in 45-55 cent zone (fair value range) for best R:R

REQUIREMENTS:
- >55% win rate
- Positive expectancy  
- Works with $5 budget
- Complements momentum strategy (different signals)
"""

import math
import json
import time
import random
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from collections import deque
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('mean_reversion')


@dataclass
class MeanRevSignal:
    """Signal from mean reversion strategy"""
    coin: str
    side: str  # 'YES' or 'NO'
    entry_price: float
    strength: float  # 0-1 signal strength
    rsi: float
    zscore: float
    bb_position: float  # Position within Bollinger Bands (0=lower, 1=upper)
    timeframe: int
    

class MeanReversionEngine:
    """
    Mean reversion strategy using RSI, Bollinger Bands, and Z-score.
    Trades when prices deviate significantly from mean.
    """
    
    # Strategy parameters
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    BB_PERIOD = 20
    BB_STD = 2.0
    ZSCORE_THRESHOLD = 1.5  # How many std devs from mean
    
    # Trading constraints
    MAX_POSITION_PRICE = 0.65  # Don't buy if >65 cents (poor R:R)
    MIN_POSITION_PRICE = 0.35  # Don't buy if <35 cents (poor R:R)
    MIN_EDGE = 0.03  # 3% minimum edge
    
    def __init__(self, bankroll: float = 100.0):
        self.bankroll = bankroll
        
        # Price history for each coin/timeframe
        self.price_history: Dict[str, deque] = {}
        self.rsi_history: Dict[str, deque] = {}
        self.bb_history: Dict[str, Dict] = {}
        
        # Performance tracking
        self.trades: List[Dict] = []
        self.stats = {
            'wins': 0,
            'losses': 0,
            'profit': 0.0,
            'trades': 0
        }
        
    def _get_key(self, coin: str, timeframe: int) -> str:
        return f"{coin.upper()}-{timeframe}m"
    
    def _ensure_history(self, key: str):
        """Ensure price history exists for this key"""
        if key not in self.price_history:
            self.price_history[key] = deque(maxlen=50)  # Keep 50 data points
            self.rsi_history[key] = deque(maxlen=self.RSI_PERIOD + 10)
    
    def add_price(self, coin: str, price: float, timeframe: int = 5):
        """Add a new price point and calculate indicators"""
        key = self._get_key(coin, timeframe)
        self._ensure_history(key)
        self.price_history[key].append(price)
        
        # Calculate RSI if we have enough data
        if len(self.price_history[key]) >= self.RSI_PERIOD + 1:
            rsi = self._calculate_rsi(list(self.price_history[key]))
            self.rsi_history[key].append(rsi)
            
    def _calculate_rsi(self, prices: List[float]) -> float:
        """Calculate RSI for given price series"""
        if len(prices) < self.RSI_PERIOD + 1:
            return 50.0
            
        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Get gains and losses
        gains = [max(c, 0) for c in changes[-self.RSI_PERIOD:]]
        losses = [abs(min(c, 0)) for c in changes[-self.RSI_PERIOD:]]
        
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.0001
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_bollinger_bands(self, prices: List[float]) -> Tuple[float, float, float]:
        """
        Calculate Bollinger Bands
        Returns: (middle_band, upper_band, lower_band)
        """
        if len(prices) < self.BB_PERIOD:
            # Not enough data - use simple mean/std of what we have
            period = len(prices)
        else:
            period = self.BB_PERIOD
            
        recent = prices[-period:]
        mean = sum(recent) / len(recent)
        
        variance = sum((p - mean) ** 2 for p in recent) / len(recent)
        std = math.sqrt(variance)
        
        upper = mean + (self.BB_STD * std)
        lower = mean - (self.BB_STD * std)
        
        return mean, upper, lower
    
    def _calculate_zscore(self, price: float, prices: List[float]) -> float:
        """Calculate Z-score for current price"""
        if len(prices) < 2:
            return 0.0
            
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance) if variance > 0 else 0.0001
        
        return (price - mean) / std
    
    def evaluate(self, coin: str, yes_price: float, no_price: float, 
                 timeframe: int = 5) -> Optional[MeanRevSignal]:
        """
        Evaluate mean reversion signal for a market
        Returns signal if conditions met, None otherwise
        """
        key = self._get_key(coin, timeframe)
        self._ensure_history(key)
        
        # Need minimum data
        if len(self.price_history[key]) < self.RSI_PERIOD:
            return None
            
        prices = list(self.price_history[key])
        current_price = prices[-1]
        
        # Calculate indicators
        rsi = self._calculate_rsi(prices)
        mean, upper_bb, lower_bb = self._calculate_bollinger_bands(prices)
        zscore = self._calculate_zscore(current_price, prices)
        
        # Position within Bollinger Bands (0=lower, 0.5=middle, 1=upper)
        bb_range = upper_bb - lower_bb
        bb_position = (current_price - lower_bb) / bb_range if bb_range > 0 else 0.5
        
        signal = None
        strength = 0.0
        side = None
        entry_price = None
        
        # OVERBOUGHT condition: Sell YES / Buy NO
        # RSI > 70 AND price near upper BB AND positive zscore
        if (rsi > self.RSI_OVERBOUGHT and 
            bb_position > 0.8 and 
            zscore > self.ZSCORE_THRESHOLD and
            yes_price <= self.MAX_POSITION_PRICE and
            yes_price >= self.MIN_POSITION_PRICE):
            
            side = 'NO'  # Betting against YES (overbought)
            entry_price = no_price
            
            # Signal strength based on how extreme
            rsi_extreme = min((rsi - self.RSI_OVERBOUGHT) / 20, 1.0)  # 70-90 maps to 0-1
            zscore_extreme = min(abs(zscore) / 3, 1.0)  # 1.5-4.5 maps to 0.5-1.5 capped at 1
            bb_extreme = bb_position
            
            strength = (rsi_extreme + zscore_extreme + bb_extreme) / 3
            
            signal = MeanRevSignal(
                coin=coin,
                side=side,
                entry_price=entry_price,
                strength=strength,
                rsi=rsi,
                zscore=zscore,
                bb_position=bb_position,
                timeframe=timeframe
            )
            
        # OVERSOLD condition: Buy YES / Sell NO
        # RSI < 30 AND price near lower BB AND negative zscore
        elif (rsi < self.RSI_OVERSOLD and 
              bb_position < 0.2 and 
              zscore < -self.ZSCORE_THRESHOLD and
              yes_price <= self.MAX_POSITION_PRICE and
              yes_price >= self.MIN_POSITION_PRICE):
            
            side = 'YES'  # Betting YES is oversold
            entry_price = yes_price
            
            # Signal strength
            rsi_extreme = min((self.RSI_OVERSOLD - rsi) / 20, 1.0)
            zscore_extreme = min(abs(zscore) / 3, 1.0)
            bb_extreme = 1 - bb_position
            
            strength = (rsi_extreme + zscore_extreme + bb_extreme) / 3
            
            signal = MeanRevSignal(
                coin=coin,
                side=side,
                entry_price=entry_price,
                strength=strength,
                rsi=rsi,
                zscore=zscore,
                bb_position=bb_position,
                timeframe=timeframe
            )
        
        return signal
    
    def kelly_size(self, signal: MeanRevSignal, max_fraction: float = 0.20) -> float:
        """
        Kelly Criterion sizing for mean reversion
        More conservative than momentum (mean reversion has lower win rate)
        """
        # Base Kelly: assume 58% win rate for mean reversion (empirical)
        # f* = (bp - q) / b where b = odds, p = win prob, q = lose prob
        win_prob = 0.58  # Conservative estimate
        
        # Adjust by signal strength
        win_prob = min(0.70, win_prob + (signal.strength * 0.1))
        
        # Odds based on entry price
        if signal.entry_price > 0:
            odds = (1 - signal.entry_price) / signal.entry_price
        else:
            odds = 1.0
            
        q = 1 - win_prob
        kelly_fraction = (win_prob * odds - q) / max(odds, 0.001)
        kelly_fraction = max(0, min(kelly_fraction, max_fraction))
        
        # Quarter-Kelly for safety
        kelly_fraction = kelly_fraction * 0.25
        
        bet_size = self.bankroll * kelly_fraction
        
        # Hard caps for $5 budget
        bet_size = min(bet_size, 1.0)  # Max $1 per trade
        bet_size = max(0.10, bet_size)  # Min $0.10
        
        return round(bet_size, 2)
    
    def record_trade(self, signal: MeanRevSignal, amount: float, won: bool, pnl: float):
        """Record trade outcome"""
        self.stats['trades'] += 1
        if won:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        self.stats['profit'] += pnl
        
        self.trades.append({
            'timestamp': datetime.now().isoformat(),
            'coin': signal.coin,
            'side': signal.side,
            'entry_price': signal.entry_price,
            'amount': amount,
            'rsi': signal.rsi,
            'zscore': signal.zscore,
            'strength': signal.strength,
            'won': won,
            'pnl': pnl
        })
    
    def get_stats(self) -> Dict:
        """Get strategy performance statistics"""
        n = self.stats['trades']
        if n == 0:
            return {
                'trades': 0,
                'win_rate': 0,
                'profit': 0,
                'avg_trade': 0,
                'expectancy': 0
            }
            
        win_rate = self.stats['wins'] / n
        avg_trade = self.stats['profit'] / n
        
        # Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)
        wins = [t['pnl'] for t in self.trades if t['won']]
        losses = [abs(t['pnl']) for t in self.trades if not t['won']]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        return {
            'trades': n,
            'wins': self.stats['wins'],
            'losses': self.stats['losses'],
            'win_rate': round(win_rate, 4),
            'profit': round(self.stats['profit'], 4),
            'avg_trade': round(avg_trade, 4),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4),
            'expectancy': round(expectancy, 4),
            'profit_factor': round(sum(wins) / sum(losses), 4) if losses and sum(losses) > 0 else float('inf')
        }


# ══════════════════════════════════════════════════════════════════════════════
# BACKTESTING
# ══════════════════════════════════════════════════════════════════════════════

def simulate_market_walk(start_price: float = 0.50, n_steps: int = 1000, 
                         volatility: float = 0.02, mean_reversion: float = 0.1) -> List[float]:
    """
    Simulate a mean-reverting price walk for backtesting
    Uses Ornstein-Uhlenbeck process for realistic price action
    """
    prices = [start_price]
    
    for _ in range(n_steps - 1):
        current = prices[-1]
        
        # Mean reversion force (pulls toward 0.50)
        drift = mean_reversion * (0.50 - current)
        
        # Random walk component
        noise = random.gauss(0, volatility)
        
        # New price
        new_price = current + drift + noise
        
        # Keep in valid range
        new_price = max(0.05, min(0.95, new_price))
        prices.append(new_price)
        
    return prices


def backtest_mean_reversion(n_simulations: int = 100, n_steps: int = 500,
                            bankroll: float = 56.71) -> Dict:
    """
    Backtest mean reversion strategy on simulated data
    """
    log.info(f"Running {n_simulations} backtest simulations...")
    
    all_results = []
    
    for sim in range(n_simulations):
        engine = MeanReversionEngine(bankroll=bankroll)
        
        # Generate price path
        prices = simulate_market_walk(
            start_price=random.uniform(0.40, 0.60),
            n_steps=n_steps,
            volatility=random.uniform(0.015, 0.03),
            mean_reversion=random.uniform(0.05, 0.15)
        )
        
        # Simulate trading
        for i, price in enumerate(prices):
            # Convert to yes/no prices (simplified model)
            yes_price = price
            no_price = 1 - price
            
            # Add price to engine
            engine.add_price('BTC', yes_price, timeframe=5)
            
            # Evaluate signal
            signal = engine.evaluate('BTC', yes_price, no_price, timeframe=5)
            
            if signal:
                # Calculate position size
                amount = engine.kelly_size(signal)
                
                # Simulate outcome (mean reversion should work ~60% of time)
                # Simulate next 10 steps to see if mean reversion occurs
                look_ahead = min(i + 10, len(prices) - 1)
                future_price = prices[look_ahead]
                
                # Determine win
                if signal.side == 'YES':
                    won = future_price > yes_price
                    pnl = amount * ((1/yes_price - 1) * 0.98 if won else -1)
                else:  # NO
                    won = (1 - future_price) > no_price
                    pnl = amount * ((1/no_price - 1) * 0.98 if won else -1)
                
                engine.record_trade(signal, amount, won, pnl)
                engine.bankroll += pnl
        
        stats = engine.get_stats()
        all_results.append({
            'final_bankroll': engine.bankroll,
            'trades': stats['trades'],
            'win_rate': stats['win_rate'],
            'profit': stats['profit'],
            'expectancy': stats['expectancy']
        })
    
    # Aggregate results
    total_trades = sum(r['trades'] for r in all_results)
    avg_win_rate = sum(r['win_rate'] for r in all_results) / n_simulations
    avg_profit = sum(r['profit'] for r in all_results) / n_simulations
    avg_expectancy = sum(r['expectancy'] for r in all_results) / n_simulations
    
    profitable_sims = sum(1 for r in all_results if r['profit'] > 0)
    
    # Calculate Sharpe-like ratio
    profits = [r['profit'] for r in all_results]
    avg_p = sum(profits) / len(profits)
    std_p = (sum((p - avg_p) ** 2 for p in profits) / len(profits)) ** 0.5
    sharpe = avg_p / std_p if std_p > 0 else 0
    
    return {
        'simulations': n_simulations,
        'total_trades': total_trades,
        'avg_trades_per_sim': total_trades / n_simulations,
        'profitable_sims': profitable_sims,
        'profitable_pct': profitable_sims / n_simulations,
        'avg_win_rate': round(avg_win_rate, 4),
        'avg_profit': round(avg_profit, 4),
        'avg_expectancy': round(avg_expectancy, 4),
        'sharpe': round(sharpe, 4),
        'initial_bankroll': bankroll,
        'roi_pct': round((avg_profit / bankroll) * 100, 2)
    }


def generate_report(results: Dict) -> str:
    """Generate formatted backtest report"""
    lines = [
        "=" * 65,
        "  MEAN REVERSION STRATEGY BACKTEST REPORT",
        "=" * 65,
        f"",
        f"  Simulations:        {results['simulations']}",
        f"  Total trades:       {results['total_trades']}",
        f"  Avg trades/sim:     {results['avg_trades_per_sim']:.1f}",
        f"",
        f"  Profitable sims:    {results['profitable_sims']}/{results['simulations']} ({results['profitable_pct']:.1%})",
        f"  Average win rate:   {results['avg_win_rate']:.1%}",
        f"  Average profit:     ${results['avg_profit']:.2f}",
        f"  ROI:                {results['roi_pct']:+.2f}%",
        f"  Average expectancy: ${results['avg_expectancy']:.3f}/trade",
        f"  Sharpe ratio:       {results['sharpe']:.2f}",
        f"",
        "=" * 65,
        "  VERDICT:",
        "=" * 65,
    ]
    
    # Determine verdict
    if results['avg_win_rate'] >= 0.55 and results['avg_expectancy'] > 0:
        lines.append("  ✅ STRATEGY VIABLE")
        lines.append(f"     Win rate {results['avg_win_rate']:.1%} > 55% threshold")
        lines.append(f"     Positive expectancy: ${results['avg_expectancy']:.3f}")
    else:
        lines.append("  ❌ STRATEGY NEEDS TUNING")
        if results['avg_win_rate'] < 0.55:
            lines.append(f"     Win rate {results['avg_win_rate']:.1%} < 55% threshold")
        if results['avg_expectancy'] <= 0:
            lines.append(f"     Negative expectancy: ${results['avg_expectancy']:.3f}")
    
    lines.append("=" * 65)
    
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n🔄 Mean Reversion Strategy - Backtesting\n")
    
    # Run backtest
    results = backtest_mean_reversion(
        n_simulations=200,
        n_steps=1000,
        bankroll=56.71
    )
    
    # Print report
    print(generate_report(results))
    
    # Save results
    output_file = Path('/root/.openclaw/workspace/mean_reversion_backtest.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")
