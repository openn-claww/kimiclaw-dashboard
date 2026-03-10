## ISSUE DESCRIPTION FOR SECOND OPINION

### Problem Statement
Bot cannot execute live trades on Polymarket due to CLOB (Central Limit Order Book) geo-blocking, despite successful manual CLI trades.

### Background
- User executed $1 real trade successfully via PolyClaw CLI
- User reports autonomous real trades occurred in February 2026 without manual intervention
- Current bot setup shows `virtual=True` for all trades
- CLOB API returns 403 "Trading restricted in your region"

### Technical Flow

**PolyClaw CLI Trade Execution:**
```
1. Split Transaction (on-chain)
   USDC.e → YES tokens + NO tokens
   ✅ Always works (direct blockchain)

2. CLOB Sell (off-chain API)
   Sell unwanted side via Polymarket CLOB
   ❌ Geo-blocked (403 error)
   Result: User holds BOTH tokens
```

**Current Bot Architecture:**
```
Bot Signal → execute_buy() → V4BotLiveIntegration → CLOB API
                                                    ↓
                                              Geo-blocked
                                                    ↓
                                           Falls back to virtual
```

### Evidence

**Manual CLI worked:**
```
Split TX submitted: f6aa3a5a...591b1deb
Split confirmed in block 83976555
Trade executed successfully!
CLOB: Failed - Trading restricted in your region
```

**Bot logs show:**
```
virtual=True (all trades)
LIVE SELL FAILED BTC-5m — queuing for manual retry
No order_id with 0x prefix found
```

### February Trades Analysis

From TRADING_JOURNAL.md:
- Multiple real trades with TX hashes (e.g., `1577fd729e8e645d...`)
- Auto-redeemed positions
- Profits recorded (+$2.39, +$1.00, etc.)

**Open Questions:**
1. How did February trades bypass CLOB geo-block?
2. Was a proxy configured then but not now?
3. Did they use `--skip-sell` mode (hold both tokens)?

### Potential Solutions

**Option 1: Residential Proxy** (Recommended by PolyClaw docs)
- IPRoyal: ~$7-15/mo
- Environment: `HTTPS_PROXY=http://user:pass@geo.iproyal.com:12321`
- CLOB client has built-in retry logic with IP rotation

**Option 2: Skip CLOB Sell (`--skip-sell`)**
- Keep both YES and NO tokens
- No directional exposure (neutral position)
- Auto-redeem still works at resolution
- **Problem:** Cannot profit from predictions

**Option 3: Direct Blockchain Integration**
- Bypass CLOB entirely
- Use on-chain AMM (if available)
- **Problem:** Polymarket only has CLOB, no AMM liquidity

### Key Constraint

`split_position()` creates **complete sets** (YES + NO). To get directional exposure:
- MUST sell unwanted side
- CLOB is the ONLY liquid venue
- Geo-block prevents automated access without proxy

### Question for Reviewer

Given that:
1. User insists February trades were autonomous (no manual CLI)
2. No proxy is currently configured
3. CLOB is geo-blocked now

**How could February trades have worked autonomously without proxy?**

Possible explanations:
- CLOB blocking was less strict in February
- Different IP/ISP that wasn't blocked
- Proxy was configured but later removed (user forgot)
- Trades were actually manual (user misremembering)
- Bot used different execution path that's now broken

**What would you recommend as the cleanest fix?**
