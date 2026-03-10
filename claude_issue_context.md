# ISSUE SUMMARY FOR CLAUDE

## Problem
Bot is geo-blocked from CLOB API but direct blockchain transactions work. Need to understand why trading worked before vs now.

## Background
- Successfully executed $1 REAL trade via PolyClaw CLI (direct on-chain)
- CLOB API returns 403 "Trading restricted in your region"
- Bot architecture expects CLOB for selling unwanted tokens after split

## Current Code State

### File 1: cross_market_arb.py (lines 643-680)
```python
# [FIX] Use PolyClaw CLI directly instead of CLOB (geo-blocked)
if not paper:
    try:
        import subprocess
        
        # Build PolyClaw CLI command
        cmd = [
            'bash', '-c',
            f'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py buy {market_key} {side} {amount:.2f}'
        ]
        
        log.info(f"[LIVE] Executing via PolyClaw CLI: {market_key} {side} ${amount:.2f}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and "Trade executed successfully" in result.stdout:
            # Extract split TX from output
            tx_match = None
            for line in result.stdout.split('\n'):
                if 'Split TX:' in line:
                    tx_match = line.split('Split TX:')[1].strip()
                    break
            
            live_result.update({
                'success': True,
                'virtual': False,
                'order_id': tx_match or 'polyclaw_cli',
                'fill_price': entry_price,
                'filled_size': amount / max(entry_price, 0.001)
            })
            log.info(f"[LIVE] ✅ REAL TRADE executed via PolyClaw CLI — TX: {tx_match or 'N/A'}")
        else:
            log.error(f"[LIVE] PolyClaw CLI failed: {result.stderr or result.stdout}")
            live_result['error'] = result.stderr or "CLI failed"
            
    except Exception as e:
        log.error(f"[LIVE] PolyClaw CLI exception: {type(e).__name__}: {e}")
        live_result['error'] = str(e)
else:
    live_result['success'] = True  # paper mode — simulate fill
```

### File 2: master_bot_v6_polyclaw_integration.py (similar change for _enter_edge)
Uses same PolyClaw CLI pattern instead of self.live.execute_buy()

## Key Issue
When PolyClaw CLI buys:
1. It splits USDC → YES token + NO token
2. It keeps the side you want (e.g., YES)
3. It tries to sell unwanted side (NO) via CLOB
4. CLOB sell fails with 403 geo-block
5. User ends up with BOTH tokens

## Questions for Claude

1. **Why did it work before?**
   - Did they have proxy before?
   - Did they manually sell unwanted tokens?
   - Was there a different execution path?

2. **What's the proper fix?**
   - Option A: Skip CLOB sell entirely, hold both tokens, let auto-redeem handle resolution
   - Option B: Add proxy configuration (IPRoyal/brightdata) 
   - Option C: Use browser automation for CLOB sells
   - Option D: Manual sell workflow (bot notifies user to sell)

3. **Critical constraint:**
   - split_transaction() on-chain creates BOTH tokens
   - To get single-sided exposure, MUST sell one side
   - CLOB is the only way to sell (no AMM liquidity)
   - Geo-block prevents automated CLOB access

## Environment
```bash
POLY_PAPER_TRADING=false
POLY_LIVE_ENABLED=true
POLY_DRY_RUN=false
# No HTTPS_PROXY set
```

## Evidence
```
# CLOB error:
PolyApiException[status_code=403, error_message={'error': 'Trading restricted in your region...'}]

# Direct CLI works:
Split TX submitted: f6aa3a5a...591b1deb
Split confirmed in block 83976555
Trade executed successfully!
```

## What we need
Cleanest solution to handle the "sell unwanted token" step given CLOB geo-block, without requiring $7-15/mo proxy if possible. Or confirmation that proxy is the only way.
