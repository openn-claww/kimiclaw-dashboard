# Self-Improvement Loop — ACTIVE

## After EVERY Trade

### 1. Log Full Details
```python
from memory.improvement import get_improvement
imp = get_improvement()

trade_id = imp.log_trade_full(
    market_id="703258",
    market_question="Will Jesus Christ return before 2027?",
    side="NO",
    size_usd=5.0,
    entry_price=0.97,
    strategy="Conservative NO on low-probability event",
    reasoning="No historical precedent, 10 months remaining, high volume market",
    risk_percent=50,  # of available capital
    tags="high_confidence,religious,long_term"
)
```

### 2. Reflect When Trade Closes
```python
result = imp.reflect_on_trade(
    trade_id=trade_id,
    exit_price=1.0,  # market resolved
    pnl_usd=0.15,
    reflection="Prediction correct. Entry timing was good. Could have sized larger given confidence."
)
```

### 3. Auto-Generated Lessons
- Wins → `win_pattern` memories (high confidence)
- Losses → `loss_lesson` memories (high confidence)
- Strategy updates triggered automatically

## Every 2 Days: Full Analysis

**Cron Job:** `trading-analysis-report`
- **Schedule:** Every 48 hours
- **Output:** Discord report with:
  - Win rate %
  - Total P&L
  - Average profit/loss per trade
  - Biggest win/loss
  - Active positions
  - Lessons learned
  - Strategy recommendations

## Files

| File | Purpose |
|------|---------|
| `memory/improvement.py` | Self-improvement engine |
| `memory/memory.db` | All trades, reflections, lessons |
| Reports | Auto-generated every 2 days → Discord |

## Current Status

- ✅ Improvement system: ACTIVE
- ✅ 2-day analysis cron: SCHEDULED
- ✅ Discord reports: ENABLED
- 🔄 Awaiting first trade to begin learning
