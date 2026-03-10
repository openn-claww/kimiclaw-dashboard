# COMPREHENSIVE STRATEGY FIX REQUEST

## Executive Summary
Cross-market arbitrage bot for Polymarket 5-minute BTC/ETH binaries is mathematically guaranteed to lose money. Need complete strategy rebuild with working edge calculation.

**Current State:**
- Virtual P&L: -$24 on $58 bankroll (41% loss)
- Win rate: 0% on last 8 trades
- Real wallet: $56.71 USDC (not yet touched - GOOD)
- Bot now capable of real trading (bug fixed) - URGENT

---

## Issue #1: FATAL - Binary Implied Probability is Wrong

**Current Code (cross_market_arb.py):**
```python
def detect_arbitrage(self, pm_data: dict, spot_data: dict) -> dict:
    yes_price = float(pm_data.get('outcomePrices', [0.5, 0.5])[0])
    threshold = spot_data.get('threshold', 0)
    current_price = spot_data.get('price', 0)
    
    # WRONG: This is current state, not forward probability
    spot_above = current_price > threshold
    implied_prob = 1.0 if spot_above else 0.0  # ← FATAL FLAW
    
    market_prob = yes_price
    spread = implied_prob - market_prob  # e.g., 1.0 - 0.505 = 0.495
    
    if abs(spread) > 0.20:  # 20% edge threshold
        side = 'YES' if spread > 0 else 'NO'
        return {'signal': True, 'side': side, 'spread': spread, 'edge': abs(spread)}
```

**Problem:** BTC at $69,023 vs $68,000 threshold ≠ 100% probability of staying above. This ignores:
- Time remaining in window
- BTC volatility
- Mean reversion
- Execution lag

**Market maker price of 0.505 is rational** - it accounts for all these factors.

---

## Issue #2: Timing Bug - Buying After Resolution

**Evidence:** 
```
BTC >$60K Mar 9 | Entry: $1.00 | Current: $0.00 | P&L: -$1.00
```

**Problem:** Paying $1.00 (max price) for a binary suggests buying AFTER the outcome is known or when the window has already expired. The entry logic has no time-to-expiry validation.

**Missing:**
```python
# No check for:
- Is market still open?
- How much time remaining?
- Has resolution already happened?
```

---

## Issue #3: Fee Structure Makes Strategy Negative EV

**Math:**
- Round-trip fee: 2%
- Break-even win rate: 54% (not 50%)
- At 50% win rate: Lose 2% per trade
- At 17 trades/hour: Guaranteed ruin

**Current virtual results (-$24/208 trades = -$0.115 per trade)** confirm this.

---

## Issue #4: Risk Controls Inadequate

**Current (insufficient):**
```python
# Circuit breaker on 8 trades - statistically meaningless
if circuit_breaker.sample_size >= 8:
    if win_rate < 0.40:
        trip_circuit_breaker()

# Max daily loss 15% - too high for $56 bankroll
MAX_DAILY_LOSS_PCT = 0.15  # $8.40
```

**Missing:**
- Time-to-expiry checks
- Volatility adjustment
- Position concentration limits (you have 2 BTC >$68K positions simultaneously)
- Entry timing restrictions

---

## MULTIPLE SOLUTION APPROACHES

### Solution A: Volatility-Adjusted Probability (Recommended)

Replace binary implied_prob with Black-Scholes-style calculation:

```python
import math
from scipy.stats import norm

def calc_real_probability(spot, threshold, volatility_annual, time_remaining_minutes):
    """
    Probability that spot stays above threshold for T minutes
    Using log-normal model: Φ((ln(S/K)) / (σ × √T))
    """
    T = time_remaining_minutes / (365 * 24 * 60)  # Convert to years
    sigma = volatility_annual
    
    if T <= 0:
        return 1.0 if spot > threshold else 0.0
    
    d = math.log(spot / threshold) / (sigma * math.sqrt(T))
    prob_above = norm.cdf(d)  # Probability spot > threshold at expiry
    
    return prob_above
```

**Pros:** Mathematically sound, accounts for time + volatility
**Cons:** Requires volatility data feed

---

### Solution B: Time-Decay Weighting (Simpler)

Only trade when time_remaining < 60 seconds AND cushion > $500:

```python
def should_trade(spot, threshold, time_remaining_sec):
    if time_remaining_sec > 60:
        return False  # Too much uncertainty
    if time_remaining_sec < 10:
        return False  # Execution risk
    
    cushion = abs(spot - threshold)
    cushion_pct = cushion / threshold
    
    # Need $500+ cushion in final minute
    if cushion < 500:
        return False
    
    # Edge = cushion_pct - market_price
    edge = cushion_pct - market_price
    return edge > 0.15  # 15% edge minimum
```

**Pros:** Simple, no external data needed
**Cons:** Misses opportunities, still somewhat arbitrary

---

### Solution C: Market Maker Spread Arbitrage (Alternative Strategy)

Instead of predicting direction, exploit yes_price + no_price ≠ 1.0:

```python
def detect_mm_arbitrage(pm_data):
    yes_price = float(pm_data['outcomePrices'][0])
    no_price = float(pm_data['outcomePrices'][1])
    total = yes_price + no_price
    
    # If yes + no < 1.0, buy both = guaranteed profit
    if total < 0.98:  # 2% fee buffer
        return {'signal': 'BOTH_SIDES', 'guaranteed_profit': 1.0 - total - 0.02}
```

**Pros:** Risk-free if executable
**Cons:** Rare opportunity, may not exist on Polymarket

---

### Solution D: Trend Following (Directional)

Use short-term momentum instead of static price comparison:

```python
def detect_trend(signal_data):
    # 1-minute price change
    price_change_1m = get_price_change('BTCUSDT', minutes=1)
    
    # If trending up strongly in last minute
    if price_change_1m > 0.5:  # >0.5% in 1 minute
        # And we're in final 2 minutes
        if time_remaining < 120:
            return {'side': 'YES', 'reason': 'momentum_up'}
```

**Pros:** Captures actual market movement
**Cons:** Still noisy, needs backtesting

---

## REQUEST FOR CLAUDE

### Step 1: Analyze All Four Solutions
- Evaluate mathematical soundness of each
- Estimate realistic win rates
- Calculate EV for each
- Rank by expected profitability

### Step 2: Recommend THE BEST Solution
- Single recommended approach
- Full implementation code
- Integration with existing bot structure
- Risk controls included

### Step 3: Provide Complete Fixed Code
Replace this entire section in cross_market_arb.py:

```python
def detect_arbitrage(self, pm_data: dict, spot_data: dict) -> dict:
    # [YOUR COMPLETE FIX HERE]
    # Must include:
    # - Time-to-expiry check
    # - Real probability calculation (not binary 1.0/0.0)
    # - Volatility or cushion adjustment
    # - Fee-aware edge calculation
    # - Entry timing restrictions
    pass

def _execute_arb(self, ...):
    # [Any execution fixes needed]
    pass
```

### Step 4: Risk Control Specifications
Provide additions to:
- Entry restrictions (time windows, etc.)
- Position limits
- Circuit breaker improvements
- Kill switch enhancements

### Step 5: Testing Protocol
How to validate without risking $56:
- Backtest data source
- Statistical significance requirements
- Performance metrics to hit before live

---

## CRITICAL QUESTIONS FOR CLAUDE

1. **Which solution has highest probability of profitability?** (A, B, C, or D)

2. **What is realistic win rate for recommended solution?** (Need >54% to beat fees)

3. **How many backtest trades needed for statistical confidence?** (Current 8 is meaningless)

4. **Should we add a hard stop?** (e.g., "If virtual P&L < -$5 after 50 trades, stop entirely")

5. **Is the $56 bankroll even viable?** (With $1 min trade, 2% fees, limited diversification)

6. **What external data is required?** (Volatility feeds? Historical data?)

---

## VERIFY BEFORE RESPONDING

Please check your answer for:
- [ ] Math is correct (probabilities sum to 1, fees accounted for)
- [ ] Code compiles (valid Python syntax)
- [ ] Edge calculation is NOT binary (1.0/0.0)
- [ ] Time component included
- [ ] Win rate target > 54% (to beat 2% fees)
- [ ] Risk controls specific (not generic advice)

**This is urgent. Bot is live and capable of trading real money. Wrong answer = lose $56.**

---

## CONTEXT

**Files:**
- `/root/.openclaw/workspace/cross_market_arb.py` - Main strategy
- `/root/.openclaw/workspace/master_bot_v6_polyclaw_integration.py` - Bot orchestration
- `/root/.openclaw/skills/polyclaw/scripts/polyclaw.py` - Execution via CLI

**Environment:**
- Capital: $56.71 USDC
- Markets: BTC/ETH 5-minute Up/Down binaries
- Fees: 2% round-trip
- Execution: PolyClaw CLI via IPRoyal proxy
- Current: Virtual mode (safe for testing)

**Current Virtual Results:**
- 208 trades, -$24 P&L, 0% recent win rate
- Kill switch: TRIGGERED
- Circuit breaker: TRIPPED

**Goal:** Fix strategy, achieve >56% win rate in virtual, then trade real money.
