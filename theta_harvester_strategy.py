#!/usr/bin/env python3
"""
theta_decay_strategy.py - Time-Decay Theta Harvesting Strategy

STRATEGY: "Theta Harvester"
TYPE: Time-Decay Arbitrage / Statistical Arbitrage

PRINCIPLE:
Binary options on Polymarket lose time value (theta) as expiration approaches.
When the underlying price is STABLE and FAR from the strike, the probability
of finishing ITM barely changes, yet the option price reflects this time decay.

EDGE:
- Buy options with high probability (>70%) when theta decay creates value
- Target 5-15 minute windows where price is stable
- Capture the "theta premium" as time passes

AGENCY PATTERN IMPLEMENTATION:
- AI Engineer: Clean, modular code
- Quant Researcher: Statistical edge validation
- Risk Manager: Strict position sizing and stops
"""

import math
import json
import time
import random
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('theta_harvester')


@dataclass
class ThetaSignal:
    """Signal from theta decay strategy"""
    coin: str
    side: str
    entry_price: float
    confidence: float
    time_to_expiry: float  # minutes
    distance_from_strike: float  # % distance
    price_volatility: float  # recent volatility
    expected_theta: float  # expected time decay profit
    

class ThetaHarvesterStrategy:
    """
    Theta Harvesting Strategy for Polymarket Binary Options
    
    CAPTURES TIME PREMIUM DECAY:
    - When underlying is stable and far from strike
    - Probability doesn't change much, but time passes
    - Buy high-probability options, hold through theta decay
    - Exit before expiration or on profit target
    """
    
    # Strategy Identity
    NAME = "ThetaHarvester"
    DESCRIPTION = "Captures time value decay in stable, high-probability binary options"
    VERSION = "1.0.0"
    
    # Entry Parameters
    MIN_PROBABILITY = 0.70      # Minimum 70% chance of winning
    MAX_PROBABILITY = 0.92      # Cap at 92% (avoid theta collapse)
    MIN_TIME_TO_EXPIRY = 3.0    # Minimum 3 minutes remaining
    MAX_TIME_TO_EXPIRY = 20.0   # Maximum 20 minutes (focus on short gamma)
    
    # Volatility Filters
    MAX_PRICE_VOLATILITY = 0.015  # Max 1.5% volatility in last 5 minutes
    MIN_DISTANCE_FROM_STRIKE = 0.02  # At least 2% away from strike
    
    # Exit Parameters
    PROFIT_TARGET = 0.05        # 5% profit (theta capture)
    STOP_LOSS = 0.08           # 8% loss (volatility expansion)
    TIME_CUTOFF = 2.0           # Exit if <2 minutes to expiry
    
    # Risk Management
    MAX_POSITION_PCT = 0.20     # Max 20% of bankroll
    ABS_MAX_BET = 1.0           # Hard $1 cap for $5 budget
    MIN_BET = 0.10              # Minimum $0.10
    
    def __init__(self, bankroll: float = 5.0):
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        
        # Price history for volatility calculation
        self.price_history: Dict[str, deque] = {}
        self.volatility_cache: Dict[str, float] = {}
        
        # Position tracking
        self.positions: Dict[str, Dict] = {}
        
        # Performance metrics
        self.trades: List[Dict] = []
        self.stats = {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit': 0.0,
            'total_fees': 0.0,
            'theta_captured': 0.0
        }
        
        log.info(f"🎯 {self.NAME} v{self.VERSION} initialized")
        log.info(f"   Bankroll: ${bankroll:.2f}")
        log.info(f"   Strategy: {self.DESCRIPTION}")
    
    def _get_key(self, coin: str, timeframe: int) -> str:
        return f"{coin.upper()}-{timeframe}m"
    
    def update_price(self, coin: str, price: float, timeframe: int = 5):
        """Update price history and calculate volatility"""
        key = self._get_key(coin, timeframe)
        
        if key not in self.price_history:
            self.price_history[key] = deque(maxlen=20)
        
        self.price_history[key].append(price)
        
        # Calculate volatility if we have enough data
        if len(self.price_history[key]) >= 10:
            prices = list(self.price_history[key])
            returns = [abs(prices[i] - prices[i-1]) / prices[i-1] 
                      for i in range(1, len(prices))]
            self.volatility_cache[key] = sum(returns) / len(returns)
    
    def calculate_probability(self, spot: float, strike: float, 
                            time_remaining: float, volatility: float = 0.003) -> float:
        """
        Calculate probability of finishing above strike using log-normal model
        """
        if time_remaining <= 0 or spot <= 0 or strike <= 0:
            return 0.5
        
        T = time_remaining / 60.0  # Convert to hours
        
        try:
            d = math.log(spot / strike) / (volatility * math.sqrt(T))
            # Approximate normal CDF
            prob = 0.5 * (1 + math.erf(d / math.sqrt(2)))
            return max(0.01, min(0.99, prob))
        except:
            return 0.5
    
    def calculate_theta(self, price: float, probability: float, 
                       time_remaining: float) -> float:
        """
        Estimate theta (time decay) per minute
        Theta is higher when:
        - Closer to expiration
        - Price is near 0.50 (ATM)
        - Probability is near 50%
        """
        if time_remaining <= 0:
            return 0.0
        
        # Simplified theta model for binary options
        # Theta accelerates as t -> 0
        time_factor = 1.0 / max(time_remaining, 0.5)
        
        # Moneyness factor (max theta at 0.50, min at extremes)
        moneyness = 1.0 - abs(probability - 0.5) * 2.0
        
        # Base theta (simplified)
        base_theta = 0.002  # 0.2% per minute base
        
        theta = base_theta * time_factor * moneyness
        return theta
    
    def generate_signal(self, coin: str, yes_price: float, no_price: float,
                       spot_price: float, strike_price: float,
                       time_remaining_sec: float, timeframe: int = 5) -> Optional[ThetaSignal]:
        """
        Generate theta harvesting signal
        
        ENTRY CONDITIONS:
        1. Time remaining in sweet spot (3-20 min)
        2. High probability of winning (70-92%)
        3. Low recent volatility (price stable)
        4. Sufficient distance from strike
        """
        key = self._get_key(coin, timeframe)
        market_id = key
        
        # Check if already in position
        if market_id in self.positions:
            return None
        
        # Convert time to minutes
        time_remaining = time_remaining_sec / 60.0
        
        # Check time constraints
        if not (self.MIN_TIME_TO_EXPIRY <= time_remaining <= self.MAX_TIME_TO_EXPIRY):
            return None
        
        # Calculate probabilities
        prob_above = self.calculate_probability(spot_price, strike_price, time_remaining_sec)
        
        # Determine which side to trade
        cushion = spot_price - strike_price
        
        if cushion > 0:
            # Price above strike, buy YES
            side = 'YES'
            market_price = yes_price
            real_prob = prob_above
        else:
            # Price below strike, buy NO
            side = 'NO'
            market_price = no_price
            real_prob = 1.0 - prob_above
        
        # Check probability constraints
        if not (self.MIN_PROBABILITY <= real_prob <= self.MAX_PROBABILITY):
            return None
        
        # Check volatility constraint
        volatility = self.volatility_cache.get(key, 0.01)
        if volatility > self.MAX_PRICE_VOLATILITY:
            return None
        
        # Check distance from strike
        distance = abs(cushion) / strike_price
        if distance < self.MIN_DISTANCE_FROM_STRIKE:
            return None
        
        # Calculate expected theta
        expected_theta = self.calculate_theta(market_price, real_prob, time_remaining)
        
        # Calculate edge (our probability vs market price)
        edge = real_prob - market_price
        
        # Need positive edge + theta
        if edge < 0.02:  # Need at least 2% edge
            return None
        
        # Calculate confidence based on multiple factors
        prob_confidence = (real_prob - self.MIN_PROBABILITY) / (self.MAX_PROBABILITY - self.MIN_PROBABILITY)
        vol_confidence = 1.0 - (volatility / self.MAX_PRICE_VOLATILITY)
        time_confidence = 1.0 - abs(time_remaining - 10) / 10  # Peak at 10 min
        
        confidence = (prob_confidence + vol_confidence + time_confidence) / 3.0
        
        return ThetaSignal(
            coin=coin,
            side=side,
            entry_price=market_price,
            confidence=confidence,
            time_to_expiry=time_remaining,
            distance_from_strike=distance,
            price_volatility=volatility,
            expected_theta=expected_theta
        )
    
    def calculate_position_size(self, signal: ThetaSignal) -> float:
        """
        Kelly Criterion sizing for theta harvesting
        More aggressive than mean reversion due to time decay certainty
        """
        # Base Kelly assumes 75% win rate for theta harvesting
        base_win_rate = 0.75
        
        # Adjust by confidence
        win_rate = min(0.85, base_win_rate + (signal.confidence * 0.1))
        
        # Calculate odds
        entry = signal.entry_price
        if entry <= 0 or entry >= 1:
            return 0.0
        
        odds = (1 - entry) / entry
        
        # Kelly fraction
        q = 1 - win_rate
        kelly = (win_rate * odds - q) / max(odds, 0.001)
        kelly = max(0, min(kelly, 0.30))  # Cap at 30%
        
        # Quarter-Kelly for safety
        kelly = kelly * 0.25
        
        # Calculate bet size
        bet = self.bankroll * kelly
        
        # Apply constraints
        bet = min(bet, self.ABS_MAX_BET)
        bet = min(bet, self.bankroll * self.MAX_POSITION_PCT)
        bet = max(self.MIN_BET, bet)
        
        return round(bet, 2)
    
    def enter_position(self, signal: ThetaSignal, amount: float) -> Dict:
        """Record position entry"""
        market_id = f"{signal.coin.upper()}-5m"
        
        position = {
            'market_id': market_id,
            'coin': signal.coin,
            'side': signal.side,
            'entry_price': signal.entry_price,
            'amount': amount,
            'shares': amount / signal.entry_price,
            'entry_time': time.time(),
            'time_to_expiry_at_entry': signal.time_to_expiry,
            'confidence': signal.confidence,
            'expected_theta': signal.expected_theta
        }
        
        self.positions[market_id] = position
        self.bankroll -= amount
        
        log.info(f"📈 THETA ENTRY: {market_id} {signal.side} @ {signal.entry_price:.3f} "
                f"T-{signal.time_to_expiry:.1f}m | Size=${amount:.2f} | "
                f"Edge={signal.confidence:.2f}")
        
        return position
    
    def check_exit(self, market_id: str, yes_price: float, no_price: float,
                   time_remaining_sec: float) -> Optional[Dict]:
        """
        Check if theta position should be exited
        
        EXIT CONDITIONS:
        1. Profit target reached (theta captured)
        2. Stop loss hit (volatility expansion)
        3. Time cutoff (too close to expiry)
        4. Theta exhausted (time decay complete)
        """
        if market_id not in self.positions:
            return None
        
        pos = self.positions[market_id]
        current_price = yes_price if pos['side'] == 'YES' else no_price
        
        # Calculate P&L
        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
        pnl = pos['amount'] * pnl_pct
        
        exit_reason = None
        
        # 1. Profit target (theta captured)
        if pnl_pct >= self.PROFIT_TARGET:
            exit_reason = 'theta_captured'
        
        # 2. Stop loss (volatility expansion)
        elif pnl_pct <= -self.STOP_LOSS:
            exit_reason = 'vol_expansion'
        
        # 3. Time cutoff
        time_remaining = time_remaining_sec / 60.0
        if time_remaining <= self.TIME_CUTOFF:
            exit_reason = 'time_cutoff'
        
        # 4. Theta exhausted (held for expected duration)
        hold_time = (time.time() - pos['entry_time']) / 60.0
        if hold_time >= pos['time_to_expiry_at_entry'] * 0.8:
            exit_reason = 'theta_exhausted'
        
        if exit_reason:
            return {
                'market_id': market_id,
                'exit_reason': exit_reason,
                'exit_price': current_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'hold_time': hold_time,
                'time_remaining': time_remaining
            }
        
        return None
    
    def exit_position(self, market_id: str, exit_info: Dict) -> Dict:
        """Record position exit and update stats"""
        if market_id not in self.positions:
            return {}
        
        pos = self.positions[market_id]
        pnl = exit_info['pnl']
        won = pnl > 0
        
        # Update bankroll
        proceeds = pos['amount'] + pnl
        self.bankroll += proceeds * 0.98  # 2% fee
        
        # Update stats
        self.stats['trades'] += 1
        if won:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        self.stats['total_profit'] += pnl
        self.stats['total_fees'] += pos['amount'] * 0.02
        
        if exit_info['exit_reason'] == 'theta_captured':
            self.stats['theta_captured'] += pnl
        
        # Record trade
        trade = {
            'timestamp': datetime.now().isoformat(),
            'market_id': market_id,
            'side': pos['side'],
            'entry_price': pos['entry_price'],
            'exit_price': exit_info['exit_price'],
            'amount': pos['amount'],
            'pnl': pnl,
            'pnl_pct': exit_info['pnl_pct'],
            'exit_reason': exit_info['exit_reason'],
            'hold_time': exit_info['hold_time'],
            'confidence': pos['confidence']
        }
        self.trades.append(trade)
        
        del self.positions[market_id]
        
        emoji = "✅" if won else "❌"
        log.info(f"{emoji} THETA EXIT: {market_id} | {exit_info['exit_reason']} | "
                f"P&L: ${pnl:+.2f} ({exit_info['pnl_pct']:+.1f}%)")
        
        return trade
    
    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        n = self.stats['trades']
        if n == 0:
            return {
                'trades': 0,
                'win_rate': 0.0,
                'profit': 0.0,
                'bankroll': self.bankroll,
                'roi_pct': 0.0,
                'expectancy': 0.0,
                'profit_factor': 0.0,
                'sharpe': 0.0,
                'theta_captured': 0.0
            }
        
        win_rate = self.stats['wins'] / n
        roi = (self.bankroll - self.initial_bankroll) / self.initial_bankroll
        
        wins = [t['pnl'] for t in self.trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in self.trades if t['pnl'] <= 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        profit_factor = sum(wins) / sum(losses) if losses and sum(losses) > 0 else float('inf')
        
        # Sharpe-like ratio
        if len(self.trades) >= 2:
            pnls = [t['pnl'] for t in self.trades]
            avg_pnl = sum(pnls) / len(pnls)
            variance = sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)
            std_pnl = math.sqrt(variance) if variance > 0 else 0.0001
            sharpe = avg_pnl / std_pnl * math.sqrt(n)
        else:
            sharpe = 0.0
        
        return {
            'trades': n,
            'wins': self.stats['wins'],
            'losses': self.stats['losses'],
            'win_rate': round(win_rate, 4),
            'profit': round(self.stats['total_profit'], 4),
            'fees': round(self.stats['total_fees'], 4),
            'bankroll': round(self.bankroll, 4),
            'roi_pct': round(roi * 100, 2),
            'expectancy': round(expectancy, 4),
            'profit_factor': round(profit_factor, 4),
            'sharpe': round(sharpe, 4),
            'theta_captured': round(self.stats['theta_captured'], 4),
            'open_positions': len(self.positions)
        }


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTESTING FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_theta_scenario() -> Tuple[float, float, float, float]:
    """
    Simulate a realistic theta harvesting scenario
    Returns: (spot, strike, time_remaining, volatility)
    """
    # Scenario: Price stable above strike, time passing
    strike = random.choice([65000, 67000, 68000, 69000, 70000])
    cushion = random.uniform(0.02, 0.08)  # 2-8% above strike
    spot = strike * (1 + cushion)
    time_remaining = random.uniform(3, 20)  # 3-20 minutes
    volatility = random.uniform(0.001, 0.003)  # Low volatility
    
    return spot, strike, time_remaining, volatility


def run_theta_backtest(n_simulations: int = 1000, bankroll: float = 5.0) -> Dict:
    """
    Run comprehensive backtest on theta harvesting strategy
    """
    log.info(f"🧪 Running {n_simulations} Theta Harvesting simulations...")
    
    results = []
    
    for sim in range(n_simulations):
        engine = ThetaHarvesterStrategy(bankroll=bankroll)
        random.seed(sim)
        
        # Simulate 50 time steps per simulation
        for step in range(50):
            # Generate scenario
            spot, strike, time_remaining, volatility = simulate_theta_scenario()
            
            # Calculate prices
            prob = engine.calculate_probability(spot, strike, time_remaining * 60, volatility)
            
            # Add some noise to market price (inefficiency)
            noise = random.gauss(0, 0.02)
            yes_price = max(0.05, min(0.95, prob + noise))
            no_price = 1 - yes_price
            
            # Update engine
            engine.update_price('BTC', yes_price, 5)
            
            # Generate signal
            signal = engine.generate_signal(
                'BTC', yes_price, no_price, spot, strike,
                time_remaining * 60, 5
            )
            
            if signal:
                amount = engine.calculate_position_size(signal)
                if amount >= 0.10:
                    engine.enter_position(signal, amount)
            
            # Check exits
            for market_id in list(engine.positions.keys()):
                # Simulate price evolution (mean reversion toward probability)
                exit_yes = yes_price + random.gauss(0, 0.01)
                exit_no = 1 - exit_yes
                
                exit_info = engine.check_exit(market_id, exit_yes, exit_no, 
                                            time_remaining * 60 * 0.9)  # Time passed
                if exit_info:
                    engine.exit_position(market_id, exit_info)
        
        # Close remaining positions
        for market_id in list(engine.positions.keys()):
            exit_info = engine.check_exit(market_id, yes_price, no_price, 1.0)
            if exit_info:
                engine.exit_position(market_id, exit_info)
        
        stats = engine.get_stats()
        results.append({
            'final_bankroll': engine.bankroll,
            'trades': stats.get('trades', 0),
            'wins': stats.get('wins', 0),
            'losses': stats.get('losses', 0),
            'win_rate': stats.get('win_rate', 0),
            'profit': stats.get('profit', 0),
            'theta_captured': stats.get('theta_captured', 0)
        })
    
    # Aggregate results
    profitable = sum(1 for r in results if r['profit'] > 0)
    total_trades = sum(r['trades'] for r in results)
    
    win_rates = [r['win_rate'] for r in results if r['trades'] > 0]
    avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
    
    return {
        'strategy': 'ThetaHarvester',
        'simulations': n_simulations,
        'total_trades': total_trades,
        'avg_trades_per_sim': total_trades / n_simulations,
        'profitable_sims': profitable,
        'profitable_pct': profitable / n_simulations,
        'avg_win_rate': avg_win_rate,
        'avg_profit': sum(r['profit'] for r in results) / n_simulations,
        'avg_theta_captured': sum(r['theta_captured'] for r in results) / n_simulations,
        'worst_case': min(r['profit'] for r in results),
        'best_case': max(r['profit'] for r in results),
        'initial_bankroll': bankroll
    }


def print_theta_report(results: Dict):
    """Print formatted backtest report"""
    print("\n" + "="*70)
    print(f"  THETA HARVESTER STRATEGY - BACKTEST REPORT")
    print("="*70)
    print(f"\n  SIMULATION PARAMETERS:")
    print(f"    Strategy:        {results['strategy']}")
    print(f"    Simulations:     {results['simulations']}")
    print(f"    Total Trades:    {results['total_trades']}")
    print(f"    Initial Budget:  ${results['initial_bankroll']:.2f}")
    
    print(f"\n  PERFORMANCE METRICS:")
    print(f"    Profitable Sims: {results['profitable_sims']}/{results['simulations']} ({results['profitable_pct']:.1%})")
    print(f"    Avg Win Rate:    {results['avg_win_rate']:.1%}")
    print(f"    Avg Profit:      ${results['avg_profit']:.2f}")
    print(f"    Theta Captured:  ${results['avg_theta_captured']:.2f}")
    
    print(f"\n  RISK METRICS:")
    print(f"    Worst Case:      ${results['worst_case']:.2f}")
    print(f"    Best Case:       ${results['best_case']:.2f}")
    
    print(f"\n  KELLY CRITERION:")
    w = results['avg_win_rate']
    if w > 0.5:
        b = 0.25  # Assumed win:loss ratio
        p = w
        q = 1 - w
        kelly = (b * p - q) / b
        kelly = max(0, min(kelly, 0.25))
        print(f"    Win Rate:        {w:.1%}")
        print(f"    Full Kelly:      {kelly:.1%}")
        print(f"    Quarter Kelly:   {kelly*0.25:.1%}")
    
    print(f"\n  VERDICT:")
    passed = (results['avg_win_rate'] >= 0.55 and 
              results['avg_profit'] > 0 and 
              results['profitable_pct'] >= 0.80)
    
    if passed:
        print("  ✅ STRATEGY VIABLE FOR LIVE TRADING")
        print(f"     - Win rate {results['avg_win_rate']:.1%} > 55% threshold")
        print(f"     - Profitable in {results['profitable_pct']:.1%} of sims")
        print(f"     - Positive expectancy: ${results['avg_profit']:.2f}")
    else:
        print("  ❌ NEEDS IMPROVEMENT")
    
    print("="*70)


if __name__ == '__main__':
    print("\n🎯 Theta Harvester Strategy - Agency Agent Implementation\n")
    
    results = run_theta_backtest(n_simulations=500, bankroll=5.0)
    print_theta_report(results)
    
    # Save results
    output = Path('/root/.openclaw/workspace/theta_harvester_backtest.json')
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to: {output}")
