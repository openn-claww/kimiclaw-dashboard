# CRITICAL ISSUE: Bot Trading Virtual Instead of Real Money

## Problem
Bot is detecting arbitrage signals and logging trades, but all trades show `virtual=True` - NO REAL MONEY IS BEING SPENT.

**Evidence from logs:**
```
2026-03-10 04:17:45  INFO      [CrossArb] 📈 #201 ARB EXECUTED ETH/5m YES @ 0.505 | $1.00 | virtual=True
2026-03-10 04:22:42  INFO      [CrossArb] 📈 #202 ARB EXECUTED BTC/5m YES @ 0.505 | $2.62 | virtual=True
2026-03-10 04:27:24  INFO      [CrossArb] 📈 #203 ARB EXECUTED ETH/5m YES @ 0.505 | $1.14 | virtual=True
```

**Real wallet balance:** $56.71 USDC (unchanged - no money being spent!)

## What Should Happen
Trades should execute via PolyClaw CLI and show `virtual=False` with real blockchain TX.

## Environment Configuration
```bash
POLY_PAPER_TRADING=false
POLY_LIVE_ENABLED=true
POLY_DRY_RUN=false
HTTPS_PROXY=http://user:pass@geo.iproyal.com:12321  (working - tested earlier)
```

## Relevant Code Sections

### File 1: cross_market_arb.py (lines 640-680)
This is the execution logic:
```python
live_result = {
    'success': False, 'fill_price': entry_price,
    'filled_size': amount / max(entry_price, 0.001),
    'order_id': None, 'virtual': True,
}

paper = getattr(self.bot, 'IS_PAPER_TRADING', True)
if not paper:  # <-- This should be False for live trading
    try:
        import subprocess
        cmd = [
            'bash', '-c',
            f'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py buy {market_key} {side} {amount:.2f}'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and "Trade executed successfully" in result.stdout:
            tx_match = None
            for line in result.stdout.split('\n'):
                if 'Split TX:' in line:
                    tx_match = line.split('Split TX:')[1].strip()
                    break
            
            live_result.update({
                'success': True,
                'virtual': False,  # <-- Should be False after real trade
                'order_id': tx_match or 'polyclaw_cli',
            })
    except Exception as e:
        log.error(f"[LIVE] PolyClaw CLI exception: {e}")
else:
    live_result['success'] = True  # paper mode — simulate fill
```

### File 2: master_bot_v6_polyclaw_integration.py (line 213)
```python
IS_PAPER_TRADING = os.getenv('POLY_PAPER_TRADING', 'true').lower() == 'true'
```

### File 3: Systemd service environment
```
Environment="POLY_PAPER_TRADING=false"
Environment="POLY_LIVE_ENABLED=true"
Environment="POLY_DRY_RUN=false"
```

## Issue Analysis Needed
1. `IS_PAPER_TRADING` appears to be `True` despite env var being `false`
2. Either the env var isn't being read correctly, OR
3. The `paper` variable is being set incorrectly from `getattr(self.bot, 'IS_PAPER_TRADING', True)`
4. The default value `True` in `getattr` might be the issue if the bot doesn't have the attribute set

## What to Debug
1. Is `IS_PAPER_TRADING` actually `False` in the running bot?
2. Is `self.bot.IS_PAPER_TRADING` properly set?
3. Why is `paper` evaluating to `True` when it should be `False`?

## Expected Fix
Bot should execute real trades via PolyClaw CLI, return `virtual=False`, and actual USDC should be spent.

## Additional Context
- Proxy is working (tested manually earlier - CLOB sell succeeded)
- Manual CLI trades work and spend real money
- Only automated bot trades are virtual
- Bot was restarted after adding warmup logic

**Provide fix or additional debugging steps.**