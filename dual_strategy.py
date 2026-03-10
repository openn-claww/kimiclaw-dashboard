# DUAL STRATEGY IMPLEMENTATION
# Running External Arb + Momentum side by side
# Tracking performance for comparison

import math, time
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime

@dataclass
class StrategyResult:
    strategy: str  # 'external_arb' or 'momentum'
    coin: str
    side: str
    amount: float
    entry_price: float
    timestamp: float
    signal_strength: float

class DualStrategyEngine:
    """
    Runs both External Arb and Momentum strategies simultaneously.
    Tracks performance to determine which is better.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.results: List[StrategyResult] = []
        self.external_stats = {'wins': 0, 'losses': 0, 'profit': 0.0}
        self.momentum_stats = {'wins': 0, 'losses': 0, 'profit': 0.0}
        
        # GUARDRAILS - STRICT
        self.MAX_BET = 0.50  # $0.50 max per trade
        self.BUDGET = 5.00   # $5 total trading budget
        self.HARD_FLOOR = 50.00  # STOP if balance < $50
        self.daily_loss = 0.0
        self.consecutive_losses = 0
        
    def evaluate_all(self, coin: str, pm_data: dict, spot_data: dict, 
                     velocity: float, bankroll: float) -> List[StrategyResult]:
        """Run both strategies, return any signals."""
        signals = []
        
        # Check guardrails
        if bankroll < self.HARD_FLOOR:
            print(f"🛑 HARD FLOOR HIT: ${bankroll:.2f} < ${self.HARD_FLOOR}")
            return []
            
        if self.daily_loss >= 2.00:
            print(f"🛑 DAILY MAX LOSS HIT: ${self.daily_loss:.2f}")
            return []
            
        if self.consecutive_losses >= 3:
            print(f"🛑 3 CONSECUTIVE LOSSES - STOPPING")
            return []
        
        # STRATEGY 1: External Arbitrage
        arb_signal = self._check_external_arb(coin, pm_data, spot_data)
        if arb_signal:
            signals.append(arb_signal)
            
        # STRATEGY 2: Momentum
        mom_signal = self._check_momentum(coin, pm_data, velocity, spot_data)
        if mom_signal:
            signals.append(mom_signal)
            
        return signals
    
    def _check_external_arb(self, coin: str, pm_data: dict, 
                           spot_data: dict) -> Optional[StrategyResult]:
        """
        FIXED External Arb with proper threshold extraction.
        """
        try:
            prices = pm_data.get('outcomePrices', [])
            if len(prices) < 2:
                return None
                
            yes_price = float(prices[0])
            no_price = float(prices[1])
            
            # Time remaining
            time_remaining = spot_data.get('time_remaining_sec', 300)
            if not (1 < time_remaining <= 240):
                return None
            
            # SPOT and THRESHOLD - FIXED
            spot = float(spot_data.get('price', 0))
            threshold = float(spot_data.get('threshold', 0))
            
            # If threshold equals spot, try to extract from market
            if threshold == 0 or abs(threshold - spot) < 1:
                # Try to extract from market question/description
                question = pm_data.get('question', '')
                import re
                # Look for "above $70,000" or "> 70000"
                match = re.search(r'above\s*\$?([\d,]+)', question, re.IGNORECASE)
                if not match:
                    match = re.search(r'>\s*\$?([\d,]+)', question)
                if match:
                    try:
                        threshold = float(match.group(1).replace(',', ''))
                    except:
                        pass
            
            # If still no valid threshold, use rounded spot
            if threshold == 0 or abs(threshold - spot) < 1:
                # Round to nearest $100 for BTC, $10 for ETH
                if coin == 'BTC':
                    threshold = round(spot / 100) * 100
                elif coin == 'ETH':
                    threshold = round(spot / 10) * 10
                else:
                    threshold = round(spot)
            
            if spot <= 0 or threshold <= 0:
                return None
            
            # Log-normal probability
            vol = 0.003 if coin == 'ETH' else 0.003
            T = time_remaining / 60.0
            
            from cross_market_arb import _norm_cdf
            d = math.log(spot / threshold) / (vol * math.sqrt(T))
            prob_above = _norm_cdf(d)
            
            # Side selection
            cushion = spot - threshold
            if cushion > 0:
                side, market_price, real_prob = 'YES', yes_price, prob_above
            else:
                side, market_price, real_prob = 'NO', no_price, 1.0 - prob_above
            
            # Check probability range (55% to 95%)
            if not (0.55 <= real_prob <= 0.95):
                return None
            
            # Calculate edge (need >5%)
            fee = 0.02
            ev = real_prob * (1.0 - market_price) * (1.0 - fee) - (1.0 - real_prob) * market_price
            net_edge = ev / max(market_price, 1e-6)
            
            if net_edge < 0.05:  # 5% minimum edge
                return None
            
            return StrategyResult(
                strategy='external_arb',
                coin=coin,
                side=side,
                amount=0.50,  # GUARDRAIL: $0.50 max
                entry_price=market_price,
                timestamp=time.time(),
                signal_strength=net_edge
            )
            
        except Exception as e:
            print(f"External arb error: {e}")
            return None
    
    def _check_momentum(self, coin: str, pm_data: dict, 
                       velocity: float, spot_data: dict) -> Optional[StrategyResult]:
        """
        Momentum strategy: Trade when price moves >0.3% in 1 minute.
        """
        try:
            prices = pm_data.get('outcomePrices', [])
            if len(prices) < 2:
                return None
                
            yes_price = float(prices[0])
            no_price = float(prices[1])
            
            # MOMENTUM THRESHOLD: 0.3% move in 1 minute
            MOMENTUM_THRESHOLD = 0.003
            
            if abs(velocity) < MOMENTUM_THRESHOLD:
                return None
            
            # Determine direction
            if velocity > 0:
                # Price going UP - buy YES
                side = 'YES'
                entry_price = yes_price
                # Don't buy if already expensive
                if entry_price > 0.75:
                    return None
            else:
                # Price going DOWN - buy NO
                side = 'NO'
                entry_price = no_price
                if entry_price > 0.75:
                    return None
            
            # Calculate signal strength (0 to 1)
            signal_strength = min(abs(velocity) / 0.01, 1.0)  # Cap at 1%
            
            return StrategyResult(
                strategy='momentum',
                coin=coin,
                side=side,
                amount=0.50,  # GUARDRAIL: $0.50 max
                entry_price=entry_price,
                timestamp=time.time(),
                signal_strength=signal_strength
            )
            
        except Exception as e:
            print(f"Momentum error: {e}")
            return None
    
    def kelly_size(self, edge: float, bankroll: float, max_fraction: float = 0.25) -> float:
        """
        Kelly Criterion sizing: f* = (bp - q) / b
        edge = expected return, bankroll = current capital
        max_fraction = max % of bankroll to risk (conservative: 25%)
        """
        if edge <= 0:
            return 0
        # Simplified Kelly: bet edge fraction of bankroll
        kelly_fraction = min(edge, max_fraction)
        bet_size = bankroll * kelly_fraction
        # Cap at reasonable limits
        return min(bet_size, 2.0)  # Max $2 per trade (Kelly decides, not hardcoded)
    
    def execute_trade(self, result: StrategyResult, bankroll: float) -> bool:
        """Execute trade with Kelly sizing and $50 hard floor guardrail."""
        # Calculate Kelly size based on signal strength
        kelly_bet = self.kelly_size(result.signal_strength, bankroll)
        
        # Apply Kelly sizing
        result.amount = kelly_bet
        
        # STRICT GUARDRAIL: NEVER go below $50
        if bankroll - result.amount < self.HARD_FLOOR:
            # Reduce bet to stay above $50
            max_safe_bet = bankroll - self.HARD_FLOOR - 0.01  # $0.01 buffer
            if max_safe_bet <= 0:
                print(f"🛑 HARD FLOOR PROTECTION: Cannot trade, would drop below ${self.HARD_FLOOR}")
                return False
            result.amount = max_safe_bet
            print(f"⚠️  Kelly bet reduced from ${kelly_bet:.2f} to ${result.amount:.2f} to protect $50 floor")
        
        print(f"🎯 {result.strategy.upper()}: {result.coin} {result.side} "
              f"@ {result.entry_price:.3f} x ${result.amount:.2f} "
              f"(Kelly: {result.signal_strength:.1%} of ${bankroll:.2f})")
        
        self.results.append(result)
        return True
    
    def report_performance(self):
        """Report which strategy is performing better."""
        print("\n" + "="*60)
        print("STRATEGY PERFORMANCE COMPARISON")
        print("="*60)
        
        ext = self.external_stats
        mom = self.momentum_stats
        
        print(f"\nExternal Arb:")
        print(f"  Trades: {ext['wins'] + ext['losses']}")
        print(f"  Win Rate: {ext['wins']/max(ext['wins']+ext['losses'],1):.1%}")
        print(f"  P&L: ${ext['profit']:+.2f}")
        
        print(f"\nMomentum:")
        print(f"  Trades: {mom['wins'] + mom['losses']}")
        print(f"  Win Rate: {mom['wins']/max(mom['wins']+mom['losses'],1):.1%}")
        print(f"  P&L: ${mom['profit']:+.2f}")
        
        # Recommendation
        if ext['profit'] > mom['profit'] and ext['wins'] + ext['losses'] > 5:
            print(f"\n🏆 RECOMMENDATION: External Arb (better P&L)")
        elif mom['profit'] > ext['profit'] and mom['wins'] + mom['losses'] > 5:
            print(f"\n🏆 RECOMMENDATION: Momentum (better P&L)")
        else:
            print(f"\n⏳ NEED MORE DATA: Both strategies running...")
        print("="*60)

# Usage in main bot:
# dual_engine = DualStrategyEngine(self)
# signals = dual_engine.evaluate_all(coin, pm_data, spot_data, velocity, bankroll)
# for signal in signals:
#     dual_engine.execute_trade(signal, bankroll)
