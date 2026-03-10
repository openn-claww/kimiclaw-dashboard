URGENT: Comprehensive V6 Trading Bot Debug and Fix

MODEL TO USE: Claude 3.5 Sonnet (https://claude.ai)

=== ALL ISSUES WE NEED FIXED ===

ISSUE 1: P&L TRACKER NOT RECORDING TRADES
- pnl_tracker.py module created and working (tested independently)
- Integration added to cross_market_arb.py and master_bot_v6_polyclaw_integration.py
- Trades execute (8 trades since 17:50) but NO entries recorded in pnl_tracker
- pnl_trades.json shows 0 trades
- PnL entry code IS in _execute_arb() after position creation
- PnL exit code IS in _execute_exit() before _save_state()
- But tracker.summary() shows 0 trades
- WHY ISN'T IT WORKING?

ISSUE 2: BOT CRASHING / FAILING TO START
- v6-bot.service shows "failed" status frequently
- Needs manual restart multiple times
- Error: "Connection to remote host was lost" in logs
- Sometimes starts, sometimes fails
- How to make it stable?

ISSUE 3: HIGH TRADE FREQUENCY (38-52 trades/hour)
- Even after raising min spread to 15%
- Still getting 7-8 trades in 8 minutes
- Is the slot_tracker working correctly?
- Is 1-arb-per-candle gate actually blocking?

ISSUE 4: DUPLICATE TRADES
- Claude found 95 consecutive same-market pairs
- 5 identical BTC/5m NO entries within 90 seconds
- Even after moving record_arb() BEFORE _execute_arb()
- Why are duplicates still happening?

ISSUE 5: P&L TRACKER INTEGRATION DEBUG
Code in cross_market_arb.py:
```python
pnl_tracker = getattr(self.bot, 'pnl_tracker', None)
if pnl_tracker:
    try:
        pnl_tracker.record_entry(
            trade_id    = market_key,
            market_id   = market_key,
            side        = side,
            entry_price = fill_price,
            shares      = filled_size,
            amount_usd  = amount,
            coin        = coin,
            strategy    = 'ARB',
            spread      = opportunity.get('spread', 0),
            edge        = opportunity.get('edge', 0),
        )
    except Exception as e:
        log.debug(f"[PnL] record_entry error: {e}")
```

Code in master_bot_v6_polyclaw_integration.py:
```python
# [PnL] Record trade exit
if self.pnl_tracker:
    try:
        self.pnl_tracker.record_exit(
            trade_id    = pos.market_id,
            exit_price  = cur_price,
            exit_reason = reason.value,
        )
    except Exception as e:
        log.debug(f"[PnL] record_exit error: {e}")
```

WHY ISN'T THIS RECORDING?

=== WHAT WE NEED ===

1. Fix P&L tracker integration - make it actually record trades
2. Fix bot stability - stop random crashes
3. Confirm trade frequency fix - verify 15% threshold working
4. Confirm duplicate fix - verify no more rapid-fire entries
5. Provide working code for all fixes
6. Give exact file locations and line numbers for changes

=== FILES INVOLVED ===
- /root/.openclaw/workspace/master_bot_v6_polyclaw_integration.py (main bot)
- /root/.openclaw/workspace/cross_market_arb.py (arb module)
- /root/.openclaw/workspace/pnl_tracker.py (P&L module)
- /root/.openclaw/workspace/v6_bot_output.log (trading log)

=== CONTEXT ===
- Bot running for 10+ hours
- 382 trades made (paper trading, $250 virtual)
- Expected P&L: +$163 (+15% ROI) from Claude's analysis
- But actual P&L: UNKNOWN (tracker not working)
- Bot technically profitable but we can't verify

=== QUESTIONS ===
1. Why is pnl_tracker.record_entry() not executing even though code is there?
2. Is the exception handler catching silent failures?
3. Should we add visible logging (not just debug) to confirm execution?
4. Is self.bot.pnl_tracker actually initialized and accessible?
5. What's causing the "Connection to remote host was lost" crashes?
6. How to make the bot restart automatically on crash?
7. Is the 15% spread threshold actually being enforced?
8. Why are we still seeing ~7-8 trades in 8 minutes after raising to 15%?

=== DELIVERABLES ===
1. Fixed code for P&L integration
2. Fixed code for bot stability
3. Verification that trade frequency is reduced
4. Verification that duplicates are stopped
5. Exact commands to restart bot with fixes

Get this bot working properly. We're so close but these bugs are blocking us from knowing if it's actually profitable.
