#!/usr/bin/env python3
"""
mean_reversion_bot.py - Mean Reversion Strategy Integration for MasterBot V6

Integrates mean reversion signals into the existing bot infrastructure.
Trades alongside momentum strategy (different entry conditions = less correlation).
"""

import math
import json
import time
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('mean_reversion_bot')


@dataclass
class MeanRevPosition:
    """Active mean reversion position"""
    market_id: str
    coin: str
    side: str
    entry_price: float
    shares: float
    amount: float
    entry_time: float
    rsi_at_entry: float
    zscore_at_entry: float
    signal_strength: float
    timeframe: int = 5


@dataclass
class MeanRevSignal:
    """Mean reversion trade signal"""
    coin: str
    side: str
    entry_price: float
    strength: float
    rsi: float
    zscore: float
    bb_position: float
    timeframe: int


class MeanReversionStrategy:
    """
    Production-ready mean reversion strategy for Polymarket.
    
    STRATEGY:
    - RSI > 70 + Price near upper Bollinger Band → Short/Buy NO
    - RSI < 30 + Price near lower Bollinger Band → Long/Buy YES
    - Exit when RSI returns to neutral (40-60) OR timeout
    """
    
    # Technical indicators
    RSI_PERIOD = 14
    BB_PERIOD = 20
    BB_STD = 2.0
    
    # Signal thresholds
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    ZSCORE_THRESHOLD = 1.5
    
    # Position constraints
    MIN_PRICE = 0.35  # Don't trade outside 35-65 cent zone
    MAX_PRICE = 0.65
    MAX_HOLD_MINUTES = 30  # Mean reversion is faster than momentum
    
    # Risk management
    MAX_POSITION_PCT = 0.15  # Max 15% of bankroll per trade
    ABS_MAX_BET = 1.0  # Hard $1 cap for $5 budget
    
    def __init__(self, bankroll: float = 5.0):
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        
        # Price histories per market
        self.price_history: Dict[str, deque] = {}
        self.rsi_cache: Dict[str, float] = {}
        self.bb_cache: Dict[str, Tuple[float, float, float]] = {}
        
        # Active positions
        self.positions: Dict[str, MeanRevPosition] = {}
        
        # Performance tracking
        self.trade_history: List[Dict] = []
        self.stats = {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit': 0.0,
            'total_fees': 0.0
        }
        
    def _get_key(self, coin: str, timeframe: int) -> str:
        """Generate unique key for market"""
        return f"{coin.upper()}-{timeframe}m"
    
    def update_price(self, coin: str, yes_price: float, no_price: float, timeframe: int = 5):
        """Update price history and recalculate indicators"""
        key = self._get_key(coin, timeframe)
        
        if key not in self.price_history:
            self.price_history[key] = deque(maxlen=50)
        
        # Store YES price for indicator calculation
        self.price_history[key].append(yes_price)
        
        # Calculate indicators if we have enough data
        if len(self.price_history[key]) >= self.RSI_PERIOD:
            prices = list(self.price_history[key])
            self.rsi_cache[key] = self._calculate_rsi(prices)
            self.bb_cache[key] = self._calculate_bollinger_bands(prices)
    
    def _calculate_rsi(self, prices: List[float]) -> float:
        """Calculate RSI indicator"""
        if len(prices) < self.RSI_PERIOD + 1:
            return 50.0
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [max(c, 0) for c in changes[-self.RSI_PERIOD:]]
        losses = [abs(min(c, 0)) for c in changes[-self.RSI_PERIOD:]]
        
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.0001
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_bollinger_bands(self, prices: List[float]) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands (middle, upper, lower)"""
        period = min(len(prices), self.BB_PERIOD)
        recent = prices[-period:]
        
        mean = sum(recent) / len(recent)
        variance = sum((p - mean) ** 2 for p in recent) / len(recent)
        std = math.sqrt(variance)
        
        upper = mean + (self.BB_STD * std)
        lower = mean - (self.BB_STD * std)
        
        return mean, upper, lower
    
    def _calculate_zscore(self, price: float, prices: List[float]) -> float:
        """Calculate Z-score"""
        if len(prices) < 2:
            return 0.0
        
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance) if variance > 0 else 0.0001
        
        return (price - mean) / std
    
    def generate_signal(self, coin: str, yes_price: float, no_price: float, 
                       timeframe: int = 5) -> Optional[MeanRevSignal]:
        """
        Generate mean reversion signal if conditions met
        Returns None if no signal
        """
        key = self._get_key(coin, timeframe)
        
        # Check if we have enough data
        if key not in self.price_history or len(self.price_history[key]) < self.RSI_PERIOD:
            return None
        
        # Check if already in position for this market
        market_id = f"{coin.upper()}-{timeframe}m"
        if market_id in self.positions:
            return None
        
        prices = list(self.price_history[key])
        current_price = prices[-1]
        
        # Get cached indicators
        rsi = self.rsi_cache.get(key, 50.0)
        mean, upper_bb, lower_bb = self.bb_cache.get(key, (0.5, 0.7, 0.3))
        zscore = self._calculate_zscore(current_price, prices)
        
        # Calculate position within Bollinger Bands
        bb_range = upper_bb - lower_bb
        bb_position = (current_price - lower_bb) / bb_range if bb_range > 0 else 0.5
        
        # OVERBOUGHT: RSI > 70, price near upper BB, positive zscore
        if (rsi > self.RSI_OVERBOUGHT and 
            bb_position > 0.75 and 
            zscore > self.ZSCORE_THRESHOLD and
            self.MIN_PRICE <= yes_price <= self.MAX_PRICE):
            
            # Calculate signal strength
            rsi_strength = min((rsi - self.RSI_OVERBOUGHT) / 20, 1.0)
            zscore_strength = min(abs(zscore) / 3, 1.0)
            bb_strength = bb_position
            strength = (rsi_strength + zscore_strength + bb_strength) / 3
            
            return MeanRevSignal(
                coin=coin,
                side='NO',
                entry_price=no_price,
                strength=strength,
                rsi=rsi,
                zscore=zscore,
                bb_position=bb_position,
                timeframe=timeframe
            )
        
        # OVERSOLD: RSI < 30, price near lower BB, negative zscore
        elif (rsi < self.RSI_OVERSOLD and 
              bb_position < 0.25 and 
              zscore < -self.ZSCORE_THRESHOLD and
              self.MIN_PRICE <= yes_price <= self.MAX_PRICE):
            
            # Calculate signal strength
            rsi_strength = min((self.RSI_OVERSOLD - rsi) / 20, 1.0)
            zscore_strength = min(abs(zscore) / 3, 1.0)
            bb_strength = 1 - bb_position
            strength = (rsi_strength + zscore_strength + bb_strength) / 3
            
            return MeanRevSignal(
                coin=coin,
                side='YES',
                entry_price=yes_price,
                strength=strength,
                rsi=rsi,
                zscore=zscore,
                bb_position=bb_position,
                timeframe=timeframe
            )
        
        return None
    
    def calculate_position_size(self, signal: MeanRevSignal) -> float:
        """
        Calculate position size using modified Kelly Criterion
        Conservative sizing for mean reversion
        """
        # Base Kelly assumes 60% win rate for mean reversion
        base_win_rate = 0.60
        
        # Adjust by signal strength
        win_rate = min(0.70, base_win_rate + (signal.strength * 0.08))
        
        # Calculate odds
        entry = signal.entry_price
        if entry <= 0 or entry >= 1:
            return 0.0
        
        odds = (1 - entry) / entry
        
        # Kelly fraction: f* = (bp - q) / b
        q = 1 - win_rate
        kelly = (win_rate * odds - q) / max(odds, 0.001)
        kelly = max(0, min(kelly, 0.25))  # Cap at 25%
        
        # Quarter-Kelly for safety
        kelly = kelly * 0.25
        
        # Calculate bet size
        bet = self.bankroll * kelly
        
        # Apply hard limits for $5 budget
        bet = min(bet, self.ABS_MAX_BET)
        bet = min(bet, self.bankroll * self.MAX_POSITION_PCT)
        bet = max(0.10, bet)  # Minimum $0.10
        
        return round(bet, 2)
    
    def enter_position(self, signal: MeanRevSignal, amount: float, 
                      yes_asset_id: str = '', no_asset_id: str = '') -> MeanRevPosition:
        """Record new position entry"""
        market_id = f"{signal.coin.upper()}-{signal.timeframe}m"
        
        # Calculate shares
        shares = amount / signal.entry_price if signal.entry_price > 0 else 0
        
        position = MeanRevPosition(
            market_id=market_id,
            coin=signal.coin,
            side=signal.side,
            entry_price=signal.entry_price,
            shares=shares,
            amount=amount,
            entry_time=time.time(),
            rsi_at_entry=signal.rsi,
            zscore_at_entry=signal.zscore,
            signal_strength=signal.strength,
            timeframe=signal.timeframe
        )
        
        self.positions[market_id] = position
        self.bankroll -= amount
        
        log.info(f"📊 MEAN REV ENTRY: {market_id} {signal.side} @ {signal.entry_price:.3f} "
                f"RSI={signal.rsi:.1f} Z={signal.zscore:.2f} Strength={signal.strength:.2f} "
                f"Size=${amount:.2f}")
        
        return position
    
    def check_exit(self, market_id: str, yes_price: float, no_price: float) -> Optional[Dict]:
        """
        Check if position should be exited
        Returns exit info or None
        """
        if market_id not in self.positions:
            return None
        
        position = self.positions[market_id]
        coin = position.coin
        timeframe = position.timeframe
        key = self._get_key(coin, timeframe)
        
        # Update price history for exit calculation
        self.update_price(coin, yes_price, no_price, timeframe)
        
        # Get current price based on side
        current_price = yes_price if position.side == 'YES' else no_price
        
        # Calculate P&L
        pnl = position.shares * (current_price - position.entry_price)
        pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
        
        # Exit conditions
        exit_reason = None
        exit_price = current_price
        
        # 1. RSI reversion to neutral (40-60)
        if key in self.rsi_cache:
            current_rsi = self.rsi_cache[key]
            if position.side == 'YES' and current_rsi >= 50:  # RSI recovered
                exit_reason = 'rsi_reversion'
            elif position.side == 'NO' and current_rsi <= 50:  # RSI normalized
                exit_reason = 'rsi_reversion'
        
        # 2. Profit target (mean reversion typically 3-5%)
        if pnl_pct >= 5.0:
            exit_reason = 'profit_target'
        
        # 3. Stop loss (mean reversion failed)
        if pnl_pct <= -8.0:
            exit_reason = 'stop_loss'
        
        # 4. Time stop (max hold time)
        hold_time = (time.time() - position.entry_time) / 60
        if hold_time >= self.MAX_HOLD_MINUTES:
            exit_reason = 'time_stop'
        
        if exit_reason:
            return {
                'market_id': market_id,
                'exit_reason': exit_reason,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'hold_time_minutes': hold_time
            }
        
        return None
    
    def exit_position(self, market_id: str, exit_info: Dict) -> Dict:
        """Record position exit and update stats"""
        if market_id not in self.positions:
            return {}
        
        position = self.positions[market_id]
        
        # Calculate final values
        exit_price = exit_info['exit_price']
        pnl = exit_info['pnl']
        won = pnl > 0
        
        # Update bankroll
        proceeds = position.shares * exit_price * 0.98  # 2% fee
        self.bankroll += proceeds
        
        # Update stats
        self.stats['trades'] += 1
        if won:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        self.stats['total_profit'] += pnl
        self.stats['total_fees'] += position.shares * exit_price * 0.02
        
        # Record trade
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'market_id': market_id,
            'coin': position.coin,
            'side': position.side,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'amount': position.amount,
            'shares': position.shares,
            'pnl': pnl,
            'pnl_pct': exit_info['pnl_pct'],
            'exit_reason': exit_info['exit_reason'],
            'hold_time': exit_info['hold_time_minutes'],
            'rsi_entry': position.rsi_at_entry,
            'zscore_entry': position.zscore_at_entry,
            'signal_strength': position.signal_strength
        }
        self.trade_history.append(trade_record)
        
        # Remove position
        del self.positions[market_id]
        
        emoji = "✅" if won else "❌"
        log.info(f"{emoji} MEAN REV EXIT: {market_id} | {exit_info['exit_reason']} | "
                f"P&L: ${pnl:+.2f} ({exit_info['pnl_pct']:+.1f}%)")
        
        return trade_record
    
    def get_stats(self) -> Dict:
        """Get current strategy statistics"""
        n = self.stats['trades']
        if n == 0:
            return {
                'trades': 0,
                'win_rate': 0.0,
                'profit': 0.0,
                'bankroll': self.bankroll,
                'roi_pct': 0.0
            }
        
        win_rate = self.stats['wins'] / n
        roi = (self.bankroll - self.initial_bankroll) / self.initial_bankroll
        
        # Calculate expectancy
        wins = [t['pnl'] for t in self.trade_history if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in self.trade_history if t['pnl'] <= 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Profit factor
        profit_factor = sum(wins) / sum(losses) if losses and sum(losses) > 0 else float('inf')
        
        # Calculate Sharpe-like ratio
        if len(self.trade_history) >= 2:
            pnls = [t['pnl'] for t in self.trade_history]
            avg_pnl = sum(pnls) / len(pnls)
            variance = sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)
            std_pnl = math.sqrt(variance) if variance > 0 else 0.0001
            sharpe = avg_pnl / std_pnl * math.sqrt(n)  # Annualized-ish
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
            'open_positions': len(self.positions)
        }
    
    def get_status(self) -> Dict:
        """Get strategy status for health checks"""
        return {
            'strategy': 'mean_reversion',
            'active': True,
            'bankroll': round(self.bankroll, 2),
            'open_positions': len(self.positions),
            'stats': self.get_stats(),
            'tracked_markets': list(self.price_history.keys())
        }


# ══════════════════════════════════════════════════════════════════════════════
# BOT INTEGRATION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def create_mean_rev_engine(bankroll: float = 5.0) -> MeanReversionStrategy:
    """Factory function for creating strategy instance"""
    return MeanReversionStrategy(bankroll=bankroll)


# For direct testing
if __name__ == '__main__':
    print("\n🔄 Mean Reversion Strategy - Standalone Test\n")
    
    # Create engine
    engine = MeanReversionStrategy(bankroll=5.0)
    
    # Simulate price data
    import random
    random.seed(42)
    
    price = 0.50
    for i in range(200):
        # Generate mean-reverting price
        drift = 0.1 * (0.50 - price)
        noise = random.gauss(0, 0.025)
        price = max(0.05, min(0.95, price + drift + noise))
        
        yes_price = price
        no_price = 1 - price
        
        # Update engine
        engine.update_price('BTC', yes_price, no_price, 5)
        
        # Check for entry signal
        signal = engine.generate_signal('BTC', yes_price, no_price, 5)
        if signal:
            amount = engine.calculate_position_size(signal)
            if amount > 0:
                engine.enter_position(signal, amount)
        
        # Check for exits
        for market_id in list(engine.positions.keys()):
            exit_info = engine.check_exit(market_id, yes_price, no_price)
            if exit_info:
                engine.exit_position(market_id, exit_info)
    
    # Print results
    stats = engine.get_stats()
    print("\n" + "="*50)
    print("MEAN REVERSION STRATEGY RESULTS")
    print("="*50)
    print(f"Trades:       {stats['trades']}")
    print(f"Win Rate:     {stats['win_rate']:.1%}")
    print(f"Profit:       ${stats['profit']:+.2f}")
    print(f"Final Balance: ${stats['bankroll']:.2f}")
    print(f"ROI:          {stats['roi_pct']:+.1f}%")
    print(f"Expectancy:   ${stats['expectancy']:.3f}/trade")
    print(f"Sharpe:       {stats['sharpe']:.2f}")
    print("="*50)
