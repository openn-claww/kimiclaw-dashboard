# STRATEGY REVIEW REQUEST - Cross-Market Arbitrage Bot

## Current Situation (CRITICAL)

**The Good:** Fixed the `virtual=True` bug. Bot now ready to trade REAL money.
**The Bad:** Virtual backtesting shows **0% win rate** and **-$24 loss** on $58 bankroll.
**The Risk:** If we trade real money now with current strategy, we lose money.

---

## Root Cause of Virtual Trading Bug (FIXED)

**File:** `cross_market_arb.py` line 664-667
**Problem:** `getattr(self.bot, 'IS_PAPER_TRADING', True)` always returned `True`
**Fix Applied:** Now reads module-level constant correctly

```python
# OLD (broken - always virtual):
paper = getattr(self.bot, 'IS_PAPER_TRADING', True)  # ← Always True, attr doesn't exist

# NEW (fixed - respects env var):
_bot_module = getattr(self.bot, '__class__', None)
_bot_module = getattr(_bot_module, '__module__', '') if _bot_module else ''
import sys as _sys, os as _os
_master_mod = _sys.modules.get(_bot_module) or _sys.modules.get('__main__')
paper = getattr(_master_mod, 'IS_PAPER_TRADING',
        _os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true')
```

---

## Strategy Performance Data

**Virtual Trading Results:**
- Total trades: 208
- Win rate (last 8): 0%
- P&L: -$24.08 (41% loss)
- Kill switch: TRIGGERED
- Circuit breaker: TRIPPED

**Real Positions Currently Open:**
| Market | Side | Entry | Current | P&L | Status |
|--------|------|-------|---------|-----|--------|
| Jesus return 2027 | NO | $1.00 | $0.96 | -$0.08 | ⏳ Open |
| BTC >$60K Mar 9 | NO | $1.00 | $0.00 | **-$1.00** | ❌ LOST |
| BTC >$68K Mar 10 | YES | $1.00 | $0.69 | -$0.31 | ⏳ Open |
| BTC >$68K Mar 10 | YES | $0.73 | $0.69 | -$0.04 | ⏳ Open |

**Real wallet:** $56.71 USDC

---

## The Arbitrage Strategy Logic

**File:** `cross_market_arb.py` - `detect_arbitrage()` method

```python
def detect_arbitrage(self, pm_data: dict, spot_data: dict) -> dict:
    """
    Detects cross-market arbitrage between Polymarket odds and spot price.
    
    Logic:
    1. Get Polymarket YES price (pm_data['outcomePrices'][0])
    2. Calculate implied probability from spot price vs threshold
    3. If spread > threshold → arbitrage signal
    """
    # Extract prices
    pm_prices = pm_data.get('outcomePrices', [])
    if len(pm_prices) < 2:
        return None
    
    yes_price = float(pm_prices[0])
    no_price = float(pm_prices[1])
    
    # Calculate implied probability from spot
    threshold = spot_data.get('threshold', 0)  # e.g., $68,000
    current_price = spot_data.get('price', 0)  # e.g., $69,023
    
    # Is spot above threshold?
    spot_above = current_price > threshold
    
    # Implied probability
    implied_prob = 1.0 if spot_above else 0.0
    
    # Market probability
    market_prob = yes_price  # e.g., 0.505 = 50.5%
    
    # Spread = difference
    spread = implied_prob - market_prob  # e.g., 1.0 - 0.505 = 0.495
    
    # Signal if spread > threshold
    min_spread = 0.20  # 20% edge required
    
    if abs(spread) > min_spread:
        side = 'YES' if spread > 0 else 'NO'
        return {
            'signal': True,
            'side': side,
            'spread': spread,
            'edge': abs(spread),
            'market_price': yes_price if side == 'YES' else no_price,
            'implied_prob': implied_prob,
        }
    return None
```

**Execution Logic:**
```python
def _execute_arb(self, market_key: str, side: str, amount: float, edge: float):
    # Check kill switch, position limits
    # Execute via PolyClaw CLI
    # Log trade with virtual=False (now fixed)
```

---

## My Questions & Concerns

### 1. The Core Strategy Flaw
**My hypothesis:** The strategy assumes spot price predicts 5-minute resolution accurately. But:
- Spot can move AFTER we buy
- 5-minute binary options are extremely noisy
- High edge (20%+) might indicate the market knows something we don't

**Question:** Is comparing spot price to Polymarket odds actually predictive for 5-minute binaries?

### 2. Entry Timing
- Market maker spreads on Polymarket
- Slippage when executing
- By the time CLI executes, edge may be gone

**Question:** Should we add execution delay checks? Pre-validate price hasn't moved?

### 3. Over-Trading
- 208 trades in ~12 hours = 17 trades/hour
- During warmup, $1 trades
- High frequency = high fees (2% per trade)

**Question:** Is trade frequency too high? Should we add cooldown between trades?

### 4. Edge Calculation
```python
spread = implied_prob - market_prob
if abs(spread) > 0.20:  # 20% minimum edge
```

**Question:** Is 20% edge realistic or does it indicate stale data? Should edge threshold be dynamic?

### 5. Risk Management Gaps
- No per-market max loss
- No time-based position limits (e.g., max 1 position per 5-min window)
- Circuit breaker based on win rate but sample size is small (8 trades)

**Question:** What risk controls are missing?

### 6. Expected Value Math
For each trade:
- Win probability: ~55% (assuming spot is predictive)
- Payout: ~2:1 (buy at $0.50, win $1.00)
- Expected value: (0.55 × $0.50) - (0.45 × $0.50) = +$0.05 per $1 trade
- After 2% fees: -$0.01 per trade (NEGATIVE EV!)

**Question:** Is the math wrong? Are fees making this unprofitable even with 55% win rate?

---

## What I Need

1. **Strategy critique:** Is cross-market arbitrage viable for 5-minute binaries?
2. **Risk assessment:** Should we trade real money with this strategy as-is?
3. **Improvements:** Specific code changes to improve win rate
4. **Safety measures:** What stops to add before trading real money
5. **Testing plan:** How to validate strategy without risking $56

---

## Environment
- Exchange: Polymarket (Polygon)
- Markets: BTC/ETH 5-minute Up/Down binaries
- Capital: $56 USDC
- Proxy: IPRoyal (working)
- Execution: PolyClaw CLI
- Fees: 2% per trade (round trip)

---

## My Gut Feeling
This strategy is losing money because:
1. **Noise > Signal:** 5-minute price movements are random
2. **Fees eat profits:** 2% fees require >54% win rate just to break even
3. **Market maker advantage:** Polymarket makers set prices knowing retail flow
4. **Execution lag:** By the time we execute, edge is gone

**I think we should NOT trade real money until win rate improves to 60%+ in virtual mode.**

---

## Request

Please review and provide:
1. **Is the strategy fundamentally sound?** (Yes/No + Why)
2. **What specific changes to make?** (Code-level recommendations)
3. **Risk controls to add** (Before trading real money)
4. **Testing methodology** (How to validate without losing $56)
5. **Expected realistic returns** (Given fees and market dynamics)

**Time sensitive:** Bot is now capable of trading real money. Need decision ASAP.
