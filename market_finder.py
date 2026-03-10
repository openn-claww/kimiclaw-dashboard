"""
market_finder.py — Correct slug generation and market lookup for Polymarket updown markets.

ROOT CAUSE DIAGNOSIS:
  Your bot is querying slugs with timestamps from 365 days ago.
  
  Example: btc-updown-5m-1741267200
    → That timestamp is 2025-03-06 (one year ago)
    → Gamma API correctly returns 404 — that market expired last year
  
  What the bot SHOULD query right now:
    → btc-updown-5m-1772805300  (today)
    → btc-updown-15m-1772804700 (today)

  Two bugs compounding:
    1. Timestamp is stale (cached or hardcoded from a year ago)
    2. Wrong API endpoint: /markets/slug/ → should be /events/slug/

FIXES IN THIS FILE:
  - get_current_slug(): always computes from time.time(), never cached
  - get_market(): uses /events/slug/ (correct endpoint)
  - MarketFinder: drop-in replacement for your evaluate_market() logic
"""

import time
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("market_finder")

# ── Constants ─────────────────────────────────────────────────────────────────

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"

COINS      = ["btc", "eth", "sol", "xrp"]
TIMEFRAMES = {"5m": 300, "15m": 900}

# How many seconds before window close to stop accepting new entries
# (avoids entering a market with only 10s left)
ENTRY_CUTOFF_SECS = 30


@dataclass
class PolyMarket:
    """Represents one live updown market window."""
    coin:         str          # "btc"
    timeframe:    str          # "5m"
    slug:         str          # "btc-updown-5m-1772805300"
    condition_id: str
    yes_token_id: str
    no_token_id:  str
    yes_price:    float        # Current YES price (0.0–1.0)
    no_price:     float
    window_start: int          # Unix timestamp
    window_end:   int          # Unix timestamp
    seconds_remaining: float

    @property
    def is_tradeable(self) -> bool:
        """False if window is about to close or already closed."""
        return self.seconds_remaining > ENTRY_CUTOFF_SECS

    @property
    def effective_price(self) -> float:
        """YES price — what you'd pay to bet UP."""
        return self.yes_price

    def __str__(self):
        return (
            f"{self.coin.upper()} {self.timeframe} | "
            f"YES={self.yes_price:.3f} NO={self.no_price:.3f} | "
            f"{self.seconds_remaining:.0f}s remaining | "
            f"slug={self.slug}"
        )


# ── Core fix: correct slug generation ────────────────────────────────────────

def get_current_window_ts(timeframe: str) -> int:
    """
    Compute the Unix timestamp for the CURRENT active market window.

    This is the fix. Your bot was using a stale/cached timestamp.
    This function always derives it from the current wall clock.

    For 5m markets:  timestamp is always divisible by 300
    For 15m markets: timestamp is always divisible by 900

    Examples (verified against live Polymarket URLs):
      btc-updown-5m-1772749800  → datetime(2026,3,5,22,30,0, utc)
      btc-updown-15m-1772802000 → datetime(2026,3,6,13,0,0,  utc)
    """
    interval = TIMEFRAMES[timeframe]
    now      = int(time.time())
    return (now // interval) * interval


def get_current_slug(coin: str, timeframe: str) -> str:
    """
    Returns the slug for the currently active market window.
    Always computed fresh from system clock — never cached.
    """
    ts = get_current_window_ts(timeframe)
    return f"{coin.lower()}-updown-{timeframe}-{ts}"


def get_next_slug(coin: str, timeframe: str) -> str:
    """Returns slug for the NEXT window (useful to pre-fetch before rotation)."""
    interval = TIMEFRAMES[timeframe]
    ts       = get_current_window_ts(timeframe) + interval
    return f"{coin.lower()}-updown-{timeframe}-{ts}"


# ── API calls ─────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 5) -> Optional[dict]:
    """HTTP GET → parsed JSON. Returns None on any error."""
    try:
        # Add headers to avoid 403 Forbidden
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code != 404:
            logger.warning(f"HTTP {e.code}: {url}")
        return None
    except Exception as e:
        logger.warning(f"Fetch failed {url}: {e}")
        return None


def get_market(slug: str) -> Optional[PolyMarket]:
    """
    Fetch one market by slug from the Gamma API.

    IMPORTANT: The correct endpoint is /events/slug/{slug}
    Your bot was using /markets/slug/{slug} which returns 404 for these markets.

    Events endpoint returns the event wrapper which contains the market(s).
    """
    # ── FIX: use /events/slug/ not /markets/slug/ ─────────────────────────────
    data = _fetch(f"{GAMMA_BASE}/events/slug/{slug}")

    if not data:
        return None

    # Event is closed/resolved — window expired
    if data.get("closed") or data.get("resolved"):
        return None

    markets = data.get("markets", [])
    if not markets:
        return None

    m = markets[0]

    # Parse token IDs (stored as JSON string in the API response)
    try:
        token_ids = json.loads(m.get("clobTokenIds", "[]"))
    except (json.JSONDecodeError, TypeError):
        token_ids = []

    if len(token_ids) < 2:
        logger.debug(f"Market {slug}: insufficient token IDs {token_ids}")
        return None

    # Parse prices
    try:
        prices = json.loads(m.get("outcomePrices", "[0.5, 0.5]"))
        yes_price = float(prices[0])
        no_price  = float(prices[1])
    except (json.JSONDecodeError, TypeError, IndexError, ValueError):
        yes_price = 0.5
        no_price  = 0.5

    # Parse timestamps from slug (most reliable — Gamma API endDate can be null)
    parts = slug.split("-")
    try:
        window_start = int(parts[-1])
    except (ValueError, IndexError):
        window_start = 0

    timeframe = "5m" if "5m" in slug else "15m"
    interval  = TIMEFRAMES[timeframe]
    window_end = window_start + interval
    secs_remaining = max(0.0, window_end - time.time())

    # Parse coin from slug prefix
    coin = parts[0].upper()

    return PolyMarket(
        coin          = coin,
        timeframe     = timeframe,
        slug          = slug,
        condition_id  = m.get("conditionId", ""),
        yes_token_id  = token_ids[0],
        no_token_id   = token_ids[1],
        yes_price     = yes_price,
        no_price      = no_price,
        window_start  = window_start,
        window_end    = window_end,
        seconds_remaining = secs_remaining,
    )


# ── Market scanner ─────────────────────────────────────────────────────────────

class MarketFinder:
    """
    Drop-in replacement for whatever market discovery your bot uses.

    Usage:
        finder = MarketFinder()
        markets = finder.scan_all()
        for m in markets:
            if m.is_tradeable:
                print(m)
    """

    def __init__(self,
                 coins: list = None,
                 timeframes: list = None,
                 prefetch_next: bool = True):
        self.coins        = coins or COINS
        self.timeframes   = timeframes or list(TIMEFRAMES.keys())
        self.prefetch_next = prefetch_next
        self._cache: dict[str, PolyMarket] = {}

    def get_market_for(self, coin: str, timeframe: str) -> Optional[PolyMarket]:
        """
        Get the currently active market for a coin/timeframe pair.
        Tries current window, then next window (handles boundary cases).
        """
        for slug_fn in [get_current_slug, get_next_slug]:
            slug   = slug_fn(coin, timeframe)
            cached = self._cache.get(slug)

            if cached and cached.seconds_remaining > 0:
                return cached

            market = get_market(slug)
            if market:
                self._cache[slug] = market
                logger.debug(f"Found market: {market}")
                return market

        logger.debug(f"No active market for {coin} {timeframe}")
        return None

    def scan_all(self) -> list[PolyMarket]:
        """
        Scan all coin/timeframe combinations.
        Returns list of currently active, tradeable markets.
        """
        results = []
        for coin in self.coins:
            for tf in self.timeframes:
                market = self.get_market_for(coin, tf)
                if market:
                    results.append(market)

        logger.info(
            f"Scan complete: {len(results)}/{len(self.coins)*len(self.timeframes)} markets found"
        )
        return results

    def scan_tradeable(self) -> list[PolyMarket]:
        """Returns only markets with enough time remaining to enter."""
        return [m for m in self.scan_all() if m.is_tradeable]

    def get_seconds_to_next_window(self, timeframe: str) -> float:
        """How long until the next market window opens."""
        interval = TIMEFRAMES[timeframe]
        now      = time.time()
        current_window_end = ((int(now) // interval) + 1) * interval
        return current_window_end - now

    def wait_for_next_window(self, timeframe: str, buffer_secs: float = 2.0):
        """Block until the next window opens (plus buffer)."""
        wait = self.get_seconds_to_next_window(timeframe) + buffer_secs
        logger.info(f"Waiting {wait:.1f}s for next {timeframe} window...")
        time.sleep(max(0, wait))


# ── Drop-in evaluate_market() replacement ────────────────────────────────────

def evaluate_market(coin: str, timeframe: str) -> Optional[dict]:
    """
    Drop-in replacement for your bot's evaluate_market() function.

    Returns a dict compatible with whatever your bot expects, or None
    if no market is found / market is not tradeable.

    Swap your existing evaluate_market() call with this function.
    """
    finder = MarketFinder(coins=[coin], timeframes=[timeframe])
    market = finder.get_market_for(coin.lower(), timeframe)

    if not market or not market.is_tradeable:
        return None

    return {
        # Your bot's existing field names — adjust if different
        "slug":         market.slug,
        "condition_id": market.condition_id,
        "yes_token_id": market.yes_token_id,
        "no_token_id":  market.no_token_id,
        "yes_price":    market.yes_price,
        "no_price":     market.no_price,
        "window_start": market.window_start,
        "window_end":   market.window_end,
        "seconds_remaining": market.seconds_remaining,
        "coin":         coin.upper(),
        "timeframe":    timeframe,
        # Convenience fields your entry logic may use
        "price":        market.yes_price,   # Alias
        "is_tradeable": market.is_tradeable,
    }


# ── Quick verification script ─────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(message)s"
    )

    print("\n" + "="*60)
    print("  MARKET FINDER VERIFICATION")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("="*60)

    # Show what slugs we're generating
    print("\n[1] Slug generation (current windows):")
    for coin in ["btc", "eth", "sol", "xrp"]:
        for tf in ["5m", "15m"]:
            slug = get_current_slug(coin, tf)
            ts   = get_current_window_ts(tf)
            dt   = datetime.fromtimestamp(ts, tz=timezone.utc)
            print(f"  {slug}  → window opened at {dt.strftime('%H:%M:%S UTC')}")

    # Try to fetch one market
    print("\n[2] Fetching live market (BTC 5m)...")
    btc_5m = evaluate_market("btc", "5m")
    if btc_5m:
        print(f"  ✅ Found: YES={btc_5m['yes_price']:.3f} NO={btc_5m['no_price']:.3f} "
              f"| {btc_5m['seconds_remaining']:.0f}s remaining")
        print(f"  Slug:    {btc_5m['slug']}")
        print(f"  YES ID:  {btc_5m['yes_token_id'][:20]}...")
    else:
        print("  ❌ No market found — check network connectivity")

    # Full scan
    print("\n[3] Full scan (all coins, all timeframes)...")
    finder  = MarketFinder()
    markets = finder.scan_all()

    if markets:
        print(f"\n  Found {len(markets)} active market(s):\n")
        for m in markets:
            status = "✅ TRADEABLE" if m.is_tradeable else "⏳ closing soon"
            print(f"  {status} | {m}")
    else:
        print("  ❌ No markets found")
        print("\n  Troubleshooting:")
        print("  1. Check network: curl https://gamma-api.polymarket.com/events/slug/btc-updown-5m-$(python3 -c 'import time; print((int(time.time())//300)*300)')")
        print("  2. Verify time sync: your system clock should match UTC")
        print("  3. Markets may be temporarily unavailable (rare)")

    print("\n" + "="*60)
    print(f"  Next 5m window in:  {finder.get_seconds_to_next_window('5m'):.0f}s")
    print(f"  Next 15m window in: {finder.get_seconds_to_next_window('15m'):.0f}s")
    print("="*60 + "\n")
