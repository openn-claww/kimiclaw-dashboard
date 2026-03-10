# DUAL ARBITRAGE SYSTEMS - SIDE BY SIDE COMPARISON

## Current Setup (Both Running)

### SYSTEM 1: INTERNAL ARB (Built into Master Bot)
**Location:** `master_bot_v6_polyclaw_integration.py` lines 1241-1242

**Logic:**
```python
if yes_p + no_p < 0.985:  # If YES + NO < 98.5%
    self._enter_arb(coin, tf, yes_p, no_p, ...)
    return  # Exit - no other signals checked
```

**Strategy:** Simple spread arbitrage
- Buy the cheaper leg (YES if yes_p < no_p, else NO)
- Profit = (1 - (yes_p + no_p)) * 100
- Example: YES=0.49, NO=0.49, sum=0.98 < 0.985 → Trade!

**Sizing:** Quarter-Kelly based on edge
```python
edge = rp.get('edge', 0.0)
kelly_f = edge / (1.0 - entry_p)
amount = min(vf * kelly_f, vf * 0.08, $5.0)
```

**Timeframe:** No time filter - trades anytime during window
**Edge Required:** 1.5% (0.985 threshold)

---

### SYSTEM 2: EXTERNAL ARB (cross_market_arb.py)
**Location:** `cross_market_arb.py` - `CrossMarketArb` class

**Logic:**
```python
def detect_arbitrage(self, pm_data, spot_data):
    # 1. Time filter: 5s < t < 120s (relaxed)
    if not (5 < time_remaining <= 120): return None
    
    # 2. Log-normal probability
    d = math.log(spot / threshold) / (vol * sqrt(T))
    real_prob = norm_cdf(d)  # 0.0 to 1.0
    
    # 3. Probability range: 60% < p < 99% (relaxed)
    if not (0.60 <= real_prob <= 0.99): return None
    
    # 4. Edge calculation with fees
    ev = real_prob * (1 - market_price) * 0.98 - (1 - real_prob) * market_price
    net_edge = ev / market_price
    
    # 5. Minimum edge: 8% (relaxed)
    if net_edge < 0.08: return None
    
    return ArbSignal(...)
```

**Strategy:** Time-decay + log-normal probability
- Uses spot price + volatility + time to calculate real probability
- Trades when real_prob vs market_price has 8%+ edge
- Only in final 5-120 seconds (relaxed)

**Sizing:** Half-Kelly with caps
```python
b = (1 - market_price) / market_price
kelly_f = (p * b - (1 - p)) / b
half_k = kelly_f / 2
amount = min(bankroll * half_k, bankroll * 0.05, $5.0)
```

**Timeframe:** Only 5-120 seconds before expiry
**Edge Required:** 8% net after fees
**Probability Range:** 60% - 99%

---

## EXECUTION FLOW

```
Main Loop (every second):
    
    1. EXTERNAL ARB (line 1134):
       try:
           arb_opps = arb_engine.check_all()  # New strategy
       except:
           log.error("check_all failed")  # Currently failing!
    
    2. INTERNAL ARB (line 1241):
       if yes_p + no_p < 0.985:  # Old strategy
           _enter_arb(...)  # This is executing!
           return  # Stops here - doesn't check velocity/edge
    
    3. EDGE TRADES (after line 1241):
       if velocity > threshold:
           _enter_edge(...)  # Momentum trades
```

---

## CONFLICT ANALYSIS

### Problem: INTERNAL ARB RETURNS EARLY
```python
if yes_p + no_p < 0.985:
    self._enter_arb(...)  # Internal arb trades
    return  # ← EXITS HERE! External arb never gets data
```

When internal arb triggers, it **returns immediately**, so:
- External `check_all()` is called but results ignored? No...
- Actually `check_all()` is called BEFORE `_evaluate_http()`
- But internal arb gets fresh data via HTTP call
- External arb needs data passed to it

### Data Flow Issue:
```python
# External arb (check_all) expects:
arb_opps = arb_engine.check_all()  # No arguments!
# But needs: pm_data, spot_data, bankroll, paper

# Internal arb gets data directly:
resp = requests.get(f"{GAMMA_API}/events/slug/{slug}")
event = resp.json()  # Fresh data every call
```

**External arb `check_all()` has no way to get market data!**

---

## LOG EVIDENCE

```
# System 1 (Internal) - WORKING:
2026-03-10 22:53:14 INFO [CrossArb] Initialized — min_spread=15.0%
2026-03-10 22:53:14 INFO [CrossArb] BTC/5m | PM_yes=0.495 implied=0.500

# System 2 (External) - BROKEN:
[ARB] WARNING: cross_market_arb not found
[ARB] ERROR: arb_engine.check_all: 'CrossMarketArb' object has no attribute 'check_all'
```

---

## SUMMARY

| System | Status | Trades? | Quality |
|--------|--------|---------|---------|
| **Internal Arb** | ✅ Working | Yes (old logic) | Low (1.5% edge, no time filter) |
| **External Arb** | ❌ Broken | No | High (8% edge, time-decay) |

**Current State:** Only internal arb is executing trades
**Result:** 0 trades today because markets not showing 1.5% spread

**To Fix:**
1. Fix external arb import/API issues
2. OR disable internal arb and route all through external
3. OR merge both into unified system

**Your $56 is safe** - only paper trading, and current strategy too conservative to trade frequently.
