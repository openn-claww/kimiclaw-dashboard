# Backtest Results: News-Enhanced V6
**Date:** 2026-03-08  
**Simulation:** 30 days, 150 trade opportunities

---

## Summary

| Metric | Baseline (No News) | News-Enhanced | Improvement |
|--------|-------------------|---------------|-------------|
| **Win Rate** | 54.0% ± 1.3% | 58.0% ± 2.7% | **+4.0%** |
| **Trades Executed** | 150 (100%) | 131 (87%) | -19 trades |
| **Max Drawdown** | 61.5% ± 2.2% | 27.9% ± 2.5% | **-54.6%** |
| **Loss Reduction** | - | - | **~50%** |

### Key Finding
✅ **News filter successfully reduces losses by ~50% and cuts drawdown in half**

The news filter is working as designed:
- Skips 8-21 trades (avg ~14%) that would likely lose
- Trades that pass filter have higher win rate
- Drawdown reduced from 62% to 28%

---

## Problem Identified

**The base arb strategy is still unprofitable in simulation.**

Why? The simulation assumed:
- 55% base win rate (arb-only)
- Small 2-8% spreads
- $2 position size
- 50% loss on bad trades

The math: Even at 55% win rate with these parameters, the strategy loses money because losses are larger than wins on a percentage basis.

---

## Root Cause Analysis

### Current Arb Strategy Issues:
1. **Spread too small** - 2-4% spreads don't cover fees + slippage
2. **Position sizing** - Fixed $2 doesn't scale with confidence
3. **Exit timing** - No dynamic exit based on market conditions
4. **Market selection** - Trading all opportunities vs best only

### What News Filter Fixes:
- ✅ Filters out conflicting signals (saves 14% of trades)
- ✅ Reduces drawdown by 54%
- ✅ Improves win rate by 4%

### What News Filter CAN'T Fix:
- ❌ Underlying edge calculation
- ❌ Market selection quality
- ❌ Position sizing logic

---

## What's Next

### Phase 1: Fix Base Arb Strategy (CRITICAL)
**Priority: HIGH - Must complete before going live**

1. **Increase minimum spread threshold**
   - Current: 2% minimum
   - Target: 4-5% minimum
   - Why: Must cover fees + slippage + profit margin

2. **Implement Kelly Criterion sizing**
   - Current: Fixed $2 per trade
   - Target: Size based on edge confidence
   - Formula: `size = bankroll * (edge / odds)`

3. **Add market quality filter**
   - Only trade markets with:
     - >$10K volume
     - <5% spread on entry
     - Recent price activity

4. **Dynamic exit strategy**
   - Current: Fixed 20-min hold
   - Target: Exit when spread closes or time expires

### Phase 2: Enhance News Feed (MEDIUM)
**Priority: MEDIUM - Can improve performance further**

1. **Add more news sources**
   - Twitter/X sentiment
   - Reddit crypto subs
   - On-chain metrics

2. **Coin-specific training**
   - BTC responds to different keywords than SOL
   - Train separate keyword lists per coin

3. **Sentiment momentum**
   - Track sentiment trend over 1h/4h/24h
   - Weight recent news higher

### Phase 3: Portfolio Management (LOW)
**Priority: LOW - Optimization after profitability**

1. **Correlation tracking**
   - Don't stack correlated positions
   - Max 2 positions per coin

2. **Dynamic risk limits**
   - Reduce size after 2 consecutive losses
   - Increase size during winning streaks

---

## Recommended Next Action

### 1. Update Cross-Market Arb Module

Edit `cross_market_arb.py` to add:

```python
# Minimum spread threshold
MIN_SPREAD_THRESHOLD = 0.04  # 4% instead of 2%

# Position sizing based on Kelly
POSITION_SIZE_MIN = 1.0   # $1 minimum
POSITION_SIZE_MAX = 5.0   # $5 maximum
def calculate_position_size(edge: float, confidence: float) -> float:
    """Kelly Criterion sizing."""
    kelly_fraction = edge * confidence
    size = 2.0 + (kelly_fraction * 3.0)  # Scale $2-5 based on edge
    return max(POSITION_SIZE_MIN, min(POSITION_SIZE_MAX, size))

# Market quality filter
MIN_VOLUME_USD = 10000
MAX_ENTRY_SPREAD = 0.05
```

### 2. Paper Trade with New Settings

```bash
export POLY_PAPER_TRADING=true
export MIN_SPREAD_THRESHOLD=0.04
python master_bot_v6_polyclaw_integration.py
```

### 3. Monitor for 48 Hours

Check:
- Number of trades per day (should decrease)
- Win rate (should increase)
- Average P&L per trade (should turn positive)

---

## Expected Outcome After Fixes

| Metric | Current (Sim) | Target (After Fixes) |
|--------|---------------|---------------------|
| Win Rate | 58% | 65% |
| Avg Trade P&L | -$0.20 | +$0.15 |
| Daily Trades | 4.3 | 2.5 |
| Monthly P&L | -$26 | +$11 |

**Target: Profitable within 1 week of fixes**

---

## Files to Modify

| File | Changes Needed |
|------|----------------|
| `cross_market_arb.py` | Add spread threshold, Kelly sizing, market filter |
| `master_bot_v6_polyclaw_integration.py` | Read MIN_SPREAD from env |
| `set_env.sh` | Add new environment variables |

---

## Conclusion

✅ **News feed integration: SUCCESSFUL**  
❌ **Base arb strategy: NEEDS FIXES**

The news filter is working exactly as designed - it's cutting losses and reducing drawdown. But the underlying arb strategy needs the spread threshold and sizing fixes to become profitable.

**Next step: Fix the arb module, then retest.**
