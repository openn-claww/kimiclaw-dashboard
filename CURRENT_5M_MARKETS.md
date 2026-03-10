# Current 5-Minute Markets Found

**Timestamp:** 2026-03-07 05:12 UTC  
**Slot:** 1772831400

---

## 🟠 BTC 5-Minute Market

| Field | Value |
|-------|-------|
| **Market** | Bitcoin Up or Down - March 6, 4:10PM-4:15PM ET |
| **Market ID** | 1510272 |
| **Slug** | `btc-updown-5m-1772831400` |
| **YES Price** | 0.495 |
| **NO Price** | 0.505 |
| **Spread** | 0.00% |
| **✅ YES Token ID** | `73950949096749154424446492703396670862722387929300913292116192586780320843085` |
| **✅ NO Token ID** | `105972256988770137059486000965353246591215872934708440704425424299013840682368` |

---

## 🟣 ETH 5-Minute Market

| Field | Value |
|-------|-------|
| **Market** | Ethereum Up or Down - March 6, 4:10PM-4:15PM ET |
| **Market ID** | 1510275 |
| **Slug** | `eth-updown-5m-1772831400` |
| **YES Price** | 0.495 |
| **NO Price** | 0.505 |
| **Spread** | 0.00% |
| **✅ YES Token ID** | `90334556577184391255772660226932382607130726661685158038107056877958129209525` |
| **✅ NO Token ID** | `87815661780034033786559128848196471419890385211955933417825480196944806941550` |

---

## Summary

**✅ 5-MINUTE MARKETS ARE LIVE AND AVAILABLE!**

The markets exist on Polymarket CLOB. Issue #1 (429 errors / market not found) was likely due to:

1. **Timezone confusion** - Markets use ET in titles but UTC for slot calculation
2. **JSON parsing** - `clobTokenIds` returned as JSON string, not array
3. **Market expiration** - 5m markets expire quickly (need active slot calculation)

---

## Usage in V4 Bot

These token IDs can be used directly with the live trading integration:

```python
from live_trading import LiveTrader
import os

trader = LiveTrader(
    os.environ['POLY_PRIVATE_KEY'],
    os.environ['POLY_ADDRESS']
)

# Buy YES on BTC 5m
result = trader.place_buy_order(
    token_id="73950949096749154424446492703396670862722387929300913292116192586780320843085",
    amount=5.0,  # $5
    price=0.495,
    side="BUY"
)
```

---

## Next Slots

5m markets roll over every 5 minutes. Current slot formula:
```python
slot = (int(time.time()) // 300) * 300
slug = f"btc-updown-5m-{slot}"
```

Next slots:
- `1772831700` (05:15:00)
- `1772832000` (05:20:00)
- `1772832300` (05:25:00)
