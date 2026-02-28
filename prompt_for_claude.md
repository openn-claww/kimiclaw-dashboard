# PROMPT FOR CLAUDE 3.5 - BOT IMPROVEMENTS REVIEW

## Context
We have a working Polymarket prediction market trading bot that:
- Trades BTC/ETH Up-Down markets on 5m/15m timeframes
- Uses velocity-based signals with regime detection
- Has entry validation (blocks 0.015-0.85 prices)
- Has risk management (20% stop, 40% profit, 5% position size)
- Currently on paper trading, ~55-70% win rate

## Current Issues to Fix
1. Only 2 coins (BTC, ETH) - missing SOL, XRP
2. Fixed timeframes (5m/15m) - not adaptive
3. No order book analysis
4. No news/sentiment data
5. Simple velocity only - missing volume, momentum

## Proposed Improvements

### Phase 1: Add More Coins
- Add SOL, XRP to COINS list
- Adjust velocity thresholds per coin volatility
- Update WebSocket to subscribe to SOLUSDT, XRPUSDT
- Add coin-specific regime parameters

### Phase 2: Add Volume & Momentum
- Extract volume from Binance trade stream
- Calculate RSI (14-period)
- Add volume-weighted velocity
- Only trade when volume > average

### Phase 3: News/Sentiment with Rotation
- Primary: CryptoPanic API (free tier)
- Fallback: Alternative.me Fear & Greed Index
- Rotate when rate limits hit
- Use sentiment to adjust position size (reduce in negative sentiment)

### Phase 4: Dynamic Timeframes
- Analyze win rate per timeframe per regime
- Auto-switch to best performing timeframe
- Add 1m, 30m, 1h options

## Questions for You
1. Is this the right priority order?
2. Any architectural concerns with this approach?
3. Better free sentiment APIs we should consider?
4. Should we add order book analysis (requires Polymarket auth)?
5. Any risk management improvements needed before scaling?

## Deliverables Needed
- Reviewed implementation plan
- Code structure recommendations
- Any missing considerations

Current bot files:
- ultimate_bot_v5_reconnect.py (main bot)
- entry_validation.py (entry guards)
- backtest_reconnect.py (strategy tester)
