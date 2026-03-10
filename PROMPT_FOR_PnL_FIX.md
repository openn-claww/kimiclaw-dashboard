I'm running a Polymarket arbitrage trading bot (V6) and need help fixing P&L tracking.

BOT ARCHITECTURE:
- Main: master_bot_v6_polyclaw_integration.py (1,243 lines)
- Arb module: cross_market_arb.py (736 lines)
- Strategy: Cross-market arbitrage (Binance vs Polymarket prices)
- Position sizing: Kelly Criterion ($1-5 based on edge)
- News feed: 5 APIs for sentiment filtering

CURRENT STATUS:
- Running for 9 hours, 347 trades executed
- Trade frequency: 38 trades/hour (I'M OK WITH THIS VOLUME)
- Spread threshold: 5%
- All trades pass validation (edge >5%, size $1-5)
- High-edge trades (30-47%) getting max $5 positions
- Bot is technically working fine

THE ONLY PROBLEM:
P&L TRACKING IS BROKEN
- Bot executes trades but doesn't track if they win or lose
- Health file shows: 0 trades, $0 P&L
- Can't calculate win rate or profitability
- No resolution tracking when positions close
- I need to know: Are these 38 trades/hour actually profitable?

WHAT I NEED:
1. Track when a trade is entered (already happening)
2. Track when position closes/resolves
3. Calculate if trade was win or loss
4. Calculate P&L per trade and cumulative P&L
5. Track win rate (wins/total trades)

IMPORTANT: Keep current trade frequency. I'm fine with 38 trades/hour IF they're profitable. Just need to measure profitability.

KEY FILES:
- cross_market_arb.py - executes trades, _execute_arb() around line 515
- master_bot_v6_polyclaw_integration.py - main bot with _active_positions
- Bot has health monitoring and state management

LOG EXAMPLE:
[CrossArb] ✅ ARB SIGNAL: BTC/5m YES @ 0.505 | spread=-0.443 edge=44.3% size=$5.00

Current flow: Signal → Execute → Position opened
Missing: Position resolution → Win/Loss → P&L calculation

QUESTIONS:
1. Where should trade outcome tracking be added - arb module or main bot?
2. How to detect when a Polymarket position resolves?
3. Should P&L be calculated at resolution or tracked continuously?
4. What's the best data structure to store trade history with outcomes?

Please provide specific code to fix P&L tracking only. Keep everything else as-is.