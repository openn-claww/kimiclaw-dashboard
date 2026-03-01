# PROMPT FOR SECOND OPINION: Trading Bot Strategy Review

## Context
I'm running a Polymarket trading bot simulation and need expert advice on strategy selection. I've tested two versions and need help deciding which to use in production.

## The Bot Versions

### 1. Production Bot (ultimate_bot_v4_production.py)
**Features:**
- Volume Filter + Sentiment + Adaptive Exits + Multi-Timeframe
- Price bounds: 0.15 - 0.85 (filters extreme prices)
- NO dead zone filter
- Takes all valid trades within bounds

**Real Simulation Results:**
- Trades: 2 total (1 completed, 1 open)
- Win Rate: 100% (1 win, 0 losses)
- Total PnL: +$195.00
- Current Balance: $690.00 (started at $500)
- **Notable Win:** ETH YES @ 0.025 → +3900% return (bought at 0.025, resolved at 1.0)

### 2. Zoned Bot (ultimate_bot_v4_zoned.py)
**Features:**
- Same as Production PLUS:
- **Dead Zone Filter:** Blocks trades in [0.35, 0.65] range
- Logic: Only trades when price < 0.35 or price > 0.65
- More selective, theoretically higher edge

## Backtest Results (50,000 simulated trades)

| Metric | Production | Zoned |
|--------|-----------|-------|
| Final Bankroll | $440,540 | $365,238 |
| Total Return | 88,008% | 72,948% |
| Trades Taken | 2,325 | 533 |
| Win Rate | 51.6% | 55.9% |
| Avg Trade PnL | $189 | $684 |
| Blocked by Zone | 0 | 25,323 (50.6%) |

## The Specific Trade That Made $195

**Trade Details:**
- Market: ETH 15m Up/Down
- Side: YES
- Entry: 0.025 (extreme discount)
- Amount: $5.00
- Outcome: ETH price went UP during window
- PnL: +$195.00 (39x return)

**Both bots would have taken this trade** (0.025 is outside dead zone).

## My Questions

### 1. Strategy Selection
- Given backtest shows Production wins by $75K despite lower win rate, should I stick with Production?
- Is the zone filter too conservative for a high-volatility strategy?
- Should I consider a "soft zone" (reduce size in dead zone vs hard block)?

### 2. Win Rate vs Volume Trade-off
- Production: 51.6% WR, 2,325 trades
- Zoned: 55.9% WR, 533 trades
- Which matters more for long-term growth: win rate or trade volume?

### 3. Position Sizing
- Current: 5% of bankroll per trade
- Should this be adjusted based on edge (distance from 0.50)?
- Kelly criterion application for binary outcomes?

### 4. The 0.025 Entry Question
- This extreme entry (0.025) generated 39x return
- How often do these opportunities occur?
- Should I have a "moonshot" allocation for <0.10 or >0.90 entries?

### 5. Risk Management
- Current: 5% risk per trade, max 5 positions
- With 100% win rate so far (small sample), am I under-leveraged?
- What's appropriate risk for 50-55% win rate strategy?

### 6. Real vs Backtest Discrepancy
- Real: 100% WR (1/1)
- Backtest: 51.6% WR
- Is this just variance or is my simulation wrong?

### 7. Market Resolution Issues
- My ETH trade took 6+ hours to resolve (Polymarket manual resolution)
- How should I handle capital tied up in pending resolutions?
- Should I free capital after X hours if unresolved?

## What I Need

1. **Clear recommendation:** Which bot version should I run?
2. **Position sizing formula:** How much to bet based on edge?
3. **Risk parameters:** Max positions, max drawdown, stop rules?
4. **Resolution handling:** How long to wait for market resolution?
5. **Any red flags:** What am I missing that could blow up the strategy?

## Additional Context

- Trading 15m crypto markets on Polymarket
- Using Coinbase/Binance price feeds for resolution when API fails
- Virtual bankroll: $500 (simulation)
- Goal: Maximize growth while avoiding ruin

Please analyze and give specific, actionable advice.
