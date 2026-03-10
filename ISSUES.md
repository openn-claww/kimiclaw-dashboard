# ACTIVE ISSUES

## Issue #1: 5M/15M Crypto Markets Not Available via API
**Status:** Open | **Priority:** High | **Created:** 2026-03-07 04:24 GMT+8

### Problem
- User can see 5-minute markets on Polymarket website (`polymarket.com/crypto/5M`)
- API returns "No live 5-minute polymarkets available at the moment"
- 15M and hourly markets also show as unavailable
- Current time: 4:21 AM ET (Asia/Shanghai 4:21 PM)

### Root Cause Analysis
| Factor | Finding |
|--------|---------|
| Time of day | 4:21 AM ET = US pre-market, low volatility |
| Market cycle | 5m/15m markets only spawn during active trading (9:30 AM - 4:00 PM ET) |
| API vs Frontend | Website may cache or show resolved markets; API returns real-time only |
| Geolocation | Possible region-specific market visibility |

### Workarounds Identified
1. **Cron Monitor** — Check every 5 min for new markets, alert when available
2. **Wait for US open** — Markets typically appear in ~5 hours
3. **Alternative timeframes** — Trade daily/weekly markets instead
4. **Direct CLOB API** — Query orderbook directly by market ID if user has specific market

### Action Items
- [ ] Await user's response on "clob thing"
- [ ] Then provide prompt to solve this issue
- [ ] Implement chosen solution

### Notes
- User requested this be documented and solved after handling clob response
- Bot V4 is in paper trading mode ($690 virtual, $11 real balance)
