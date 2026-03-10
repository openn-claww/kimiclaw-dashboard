"""
token_mapper.py — Maps V4 bot market_id formats to Polymarket CLOB token IDs.

PROBLEM:
  V4 bot uses various market_id formats (condition IDs, question IDs, slugs).
  CLOB requires a specific token_id (the ERC-1155 outcome token address).

MAPPING STRATEGY:
  1. Check in-memory cache first (populated at startup)
  2. Try Gamma API lookup by condition_id or slug
  3. Fall back to CLOB direct lookup
  4. Cache successful mappings to avoid repeat API calls

TOKEN ID STRUCTURE on Polymarket:
  - Each market has 2 token IDs: one for YES, one for NO
  - token_id is a uint256 represented as a hex string
  - Found via: GET https://gamma-api.polymarket.com/markets?conditionIds=<id>
"""

import logging
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

# How long to cache a resolved mapping (seconds)
CACHE_TTL_SECS = 3600  # 1 hour


class TokenMapper:
    """
    Resolves Polymarket market/condition IDs to CLOB token IDs.

    V4 bot market_id can be any of:
      - condition_id:  "0xabc123..."  (hex, 66 chars)
      - question_id:   "0xdef456..."  (hex, 66 chars)
      - slug:          "will-btc-hit-100k-2025"
      - clob_token_id: already the right format (passthrough)

    Usage:
        mapper = TokenMapper()
        yes_token, no_token = mapper.resolve(market_id, side="YES")
        # Use yes_token for buying YES shares
    """

    def __init__(self):
        # cache: market_id → {"yes_token": str, "no_token": str, "cached_at": float}
        self._cache: dict = {}

    def resolve(self, market_id: str, side: str = "YES") -> Optional[str]:
        """
        Resolve a V4 market_id + side to the correct CLOB token_id.

        Args:
            market_id: Any Polymarket market identifier.
            side:      "YES" or "NO" — which outcome token to return.

        Returns:
            token_id string, or None if resolution failed.
        """
        side = side.upper()

        # ── 1. Check if already a token_id (64-char hex = raw token) ──
        if self._looks_like_token_id(market_id):
            logger.debug(f"market_id {market_id[:12]}... already looks like token_id")
            return market_id

        # ── 2. Cache hit ──
        cached = self._cache.get(market_id)
        if cached and (time.time() - cached["cached_at"]) < CACHE_TTL_SECS:
            token = cached.get(f"{side.lower()}_token")
            logger.debug(f"Cache hit for {market_id[:12]}... → {token[:12] if token else None}...")
            return token

        # ── 3. Gamma API lookup ──
        token_data = self._fetch_from_gamma(market_id)
        if token_data:
            self._cache[market_id] = {**token_data, "cached_at": time.time()}
            return token_data.get(f"{side.lower()}_token")

        # ── 4. CLOB direct lookup ──
        token_data = self._fetch_from_clob(market_id)
        if token_data:
            self._cache[market_id] = {**token_data, "cached_at": time.time()}
            return token_data.get(f"{side.lower()}_token")

        logger.error(f"Could not resolve token_id for market_id={market_id}")
        return None

    def resolve_both(self, market_id: str) -> Optional[dict]:
        """
        Return both YES and NO token IDs for a market.

        Returns:
            {"yes_token": str, "no_token": str} or None
        """
        yes = self.resolve(market_id, "YES")
        no  = self.resolve(market_id, "NO")
        if yes and no:
            return {"yes_token": yes, "no_token": no}
        return None

    def preload(self, market_ids: list) -> int:
        """
        Batch-resolve a list of market_ids at startup to warm the cache.

        Returns: number of successfully resolved markets.
        """
        resolved = 0
        for mid in market_ids:
            try:
                result = self._fetch_from_gamma(mid)
                if result:
                    self._cache[mid] = {**result, "cached_at": time.time()}
                    resolved += 1
                    time.sleep(0.1)  # gentle rate limiting
            except Exception as e:
                logger.warning(f"Preload failed for {mid}: {e}")
        logger.info(f"Preloaded {resolved}/{len(market_ids)} market token IDs")
        return resolved

    def add_manual(self, market_id: str, yes_token: str, no_token: str):
        """
        Manually register a known mapping (e.g. for markets you trade regularly).
        This takes priority over API lookups.
        """
        self._cache[market_id] = {
            "yes_token": yes_token,
            "no_token": no_token,
            "cached_at": time.time() + (CACHE_TTL_SECS * 8760),  # 1 year TTL
        }
        logger.info(f"Manual mapping added: {market_id[:12]}... → YES:{yes_token[:12]}...")

    # ── Private helpers ──────────────────────────────────────────────────────

    def _looks_like_token_id(self, s: str) -> bool:
        """Token IDs are 64-char hex strings (sometimes with 0x prefix = 66)."""
        clean = s.removeprefix("0x")
        return len(clean) == 64 and all(c in "0123456789abcdefABCDEF" for c in clean)

    def _fetch_from_gamma(self, market_id: str) -> Optional[dict]:
        """
        Try Gamma API for market token IDs.
        Handles both condition_id and slug formats.
        """
        endpoints = []

        # If it looks like a condition ID (hex), use conditionIds param
        if market_id.startswith("0x") and len(market_id) >= 40:
            endpoints.append(
                f"{GAMMA_API}/markets?conditionIds={market_id}&limit=1"
            )
        else:
            # Treat as slug
            endpoints.append(
                f"{GAMMA_API}/markets?slug={market_id}&limit=1"
            )
            # Also try question ID
            endpoints.append(
                f"{GAMMA_API}/markets?questionID={market_id}&limit=1"
            )

        for url in endpoints:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                markets = data if isinstance(data, list) else data.get("markets", [])

                if not markets:
                    continue

                market = markets[0]
                tokens = market.get("clobTokenIds") or market.get("clob_token_ids", [])

                if len(tokens) >= 2:
                    logger.debug(
                        f"Gamma resolved {market_id[:12]}... → YES:{tokens[0][:12]}..."
                    )
                    return {"yes_token": tokens[0], "no_token": tokens[1]}

            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                logger.debug(f"Gamma lookup failed for {url}: {e}")

        return None

    def _fetch_from_clob(self, market_id: str) -> Optional[dict]:
        """Try CLOB API directly for markets endpoint."""
        try:
            url = f"{CLOB_API}/markets/{market_id}"
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                return None

            market = resp.json()
            tokens = market.get("tokens", [])

            yes_token = next(
                (t["token_id"] for t in tokens if t.get("outcome", "").upper() == "YES"),
                None,
            )
            no_token = next(
                (t["token_id"] for t in tokens if t.get("outcome", "").upper() == "NO"),
                None,
            )

            if yes_token and no_token:
                logger.debug(
                    f"CLOB resolved {market_id[:12]}... → YES:{yes_token[:12]}..."
                )
                return {"yes_token": yes_token, "no_token": no_token}

        except (requests.RequestException, KeyError, ValueError) as e:
            logger.debug(f"CLOB direct lookup failed for {market_id}: {e}")

        return None
