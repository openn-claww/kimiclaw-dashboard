I need you to analyze 347 paper trades from my Polymarket trading bot and determine the P&L for each one.

**LOG FILE LOCATION:**
`/root/.openclaw/workspace/v6_bot_output.log`

**TRADE FORMAT:**
```
[CrossArb] ✅ ARB SIGNAL: BTC/5m YES @ 0.505 | spread=-0.443 edge=44.3% size=$5.00
```

**WHAT I NEED YOU TO DO:**

1. **Extract all 347 trades** from the log file
   - Parse: timestamp, market (BTC/5m or ETH/5m), side (YES/NO), entry price, spread, edge%, size

2. **For each trade, determine the outcome:**
   - These are 5-minute binary markets (resolve YES or NO based on price movement)
   - Trade time + 5 minutes = resolution time
   - Look for exit logs or market resolution data in the log file
   - If can't find exit, use the spread/edge to estimate probability of win

3. **Calculate P&L for each trade:**
   - WIN: If side=YES and resolved YES → PnL = size * (1 - entry_price) * 0.98 (after 2% fee)
   - WIN: If side=NO and resolved NO → PnL = size * (1 - entry_price) * 0.98
   - LOSS: If wrong side → PnL = -size * entry_price
   - Edge > 30% = higher win probability
   - Edge 10-30% = medium probability
   - Edge 5-10% = lower probability

4. **Create a detailed report:**
   - List all 347 trades with: time, market, side, entry, size, result (win/loss), PnL
   - Total P&L across all trades
   - Win rate (wins/total)
   - Average P&L per trade
   - Best trade and worst trade
   - P&L by market (BTC vs ETH)
   - P&L by edge range (high/medium/low)

5. **Output format:**
   - Save detailed trade list to: `/root/.openclaw/workspace/manual_trade_analysis.json`
   - Print summary to console

**SAMPLE TRADES FROM LOG:**
```
2026-03-08 04:27:40 BTC/5m YES @ 0.505 edge=22.3% size=$4.80
2026-03-08 04:28:10 BTC/5m YES @ 0.505 edge=21.3% size=$4.57
2026-03-08 04:29:03 BTC/5m YES @ 0.505 edge=25.4% size=$5.00
2026-03-08 04:32:11 BTC/5m YES @ 0.505 edge=25.0% size=$5.00
2026-03-08 04:33:12 BTC/5m YES @ 0.535 edge=45.7% size=$5.00
```

**QUESTIONS:**
1. Can you read and parse the log file v6_bot_output.log?
2. Will you use actual exit data from logs or estimate based on edge?
3. Can you handle edge cases (missing data, incomplete trades)?
4. How will you determine if a 5-minute market resolved YES or NO?

**DELIVERABLES:**
- Python script that parses log and calculates P&L
- JSON file with all 347 trades and their outcomes
- Console summary with key metrics

Please provide the complete solution.
