"""
clob_integration.py — Polymarket CLOB live trading module.

Wraps the py-clob-client library with:
  - Rate-limit-aware retries (exponential backoff)
  - Slippage protection
  - Full order lifecycle management (place, status, cancel)
  - Structured return dicts compatible with V4 bot interface
  - No private key exposure in logs (ever)

Minimum order size on Polymarket CLOB: $1.00 USDC
"""

import logging
import time
import os
from typing import Optional
from functools import wraps

from web3 import Web3

from .wallet_manager import WalletManager, POLYGON_RPC
from .exceptions import (
    LiveTradingError,
    RateLimitError,
    MarketNotFoundError,
    OrderNotFoundError,
    OrderRejectedError,
    SlippageExceededError,
    CLOBConnectionError,
)

# ── py-clob-client imports ───────────────────────────────────────────────────
# Install: pip install py-clob-client
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        OrderArgs,
        OrderType,
        PartialCreateOrderOptions,
        TradeParams,
        BookParams,
    )
    from py_clob_client.constants import POLYGON
    from py_clob_client.exceptions import PolyApiException
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    # Stub for type checking only — will raise at runtime if CLOB not installed
    class ClobClient:  # type: ignore
        pass
    class PolyApiException(Exception):  # type: ignore
        pass

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
CLOB_API_URL = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
MIN_ORDER_SIZE_USD = 1.0      # Polymarket minimum
MIN_ORDER_SIZE_TOKENS = 1.0   # Minimum shares
DEFAULT_MAX_SLIPPAGE = 0.02   # 2%
MAX_RETRIES = 5
BASE_BACKOFF_SECS = 1.0
CHAIN_ID = POLYGON if CLOB_AVAILABLE else 137

# Order result template
EMPTY_ORDER_RESULT = {
    "order_id": None,
    "filled": False,
    "fill_price": 0.0,
    "filled_size": 0.0,
    "status": "unknown",
    "error": None,
}


# ── Retry decorator ──────────────────────────────────────────────────────────

def with_retry(max_retries: int = MAX_RETRIES, base_delay: float = BASE_BACKOFF_SECS):
    """
    Exponential backoff decorator for CLOB API calls.
    Retries on RateLimitError and transient network errors.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except RateLimitError as e:
                    wait = min(e.retry_after, base_delay * (2 ** attempt))
                    logger.warning(
                        f"Rate limit hit on {fn.__name__} "
                        f"(attempt {attempt+1}/{max_retries}), "
                        f"waiting {wait:.1f}s..."
                    )
                    time.sleep(wait)
                except (ConnectionError, TimeoutError, OSError) as e:
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Network error on {fn.__name__} "
                        f"(attempt {attempt+1}/{max_retries}): {e}, "
                        f"retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                except (MarketNotFoundError, OrderNotFoundError,
                        OrderRejectedError, SlippageExceededError):
                    raise  # Non-retryable — re-raise immediately
                except PolyApiException as e:
                    if "429" in str(e) or "rate" in str(e).lower():
                        wait = base_delay * (2 ** attempt)
                        logger.warning(f"PolyAPI 429 on {fn.__name__}, waiting {wait:.1f}s")
                        time.sleep(wait)
                    else:
                        raise OrderRejectedError(str(e))
            raise LiveTradingError(
                f"{fn.__name__} failed after {max_retries} retries"
            )
        return wrapper
    return decorator


# ── LiveTrader ───────────────────────────────────────────────────────────────

class LiveTrader:
    """
    Production CLOB integration for Polymarket live trading.

    Usage:
        trader = LiveTrader(
            private_key=os.environ["POLY_PRIVATE_KEY"],
            address=os.environ["POLY_ADDRESS"],
        )

        # Check wallet
        balances = trader.get_wallet_balances()

        # Get order book
        book = trader.get_order_book(token_id="0xabc...")

        # Place trade
        result = trader.place_buy_order(
            token_id="0xabc...",
            amount_usd=5.0,
            max_slippage=0.02,
        )

    ⚠️  Never pass private_key as a log argument. This class never logs it.
    """

    def __init__(
        self,
        private_key: str,
        address: str,
        rpc_url: str = POLYGON_RPC,
        api_url: str = CLOB_API_URL,
        dry_run: bool = False,
    ):
        """
        Args:
            private_key: Hex private key (with or without 0x prefix).
                         Recommended: load from env var, never hardcode.
            address:     Wallet address (0x...).
            rpc_url:     Polygon RPC endpoint (default: polygon-rpc.com).
            api_url:     CLOB API base URL.
            dry_run:     If True, simulate orders without submitting.
                         Used for integration testing.
        """
        if not CLOB_AVAILABLE:
            raise ImportError(
                "py-clob-client is not installed. "
                "Run: pip install py-clob-client"
            )

        self.address = Web3.to_checksum_address(address)
        self.api_url = api_url
        self.dry_run = dry_run
        self._private_key = private_key  # stored privately, never logged

        # Initialize wallet manager
        self.wallet = WalletManager(address=self.address, rpc_url=rpc_url)

        # Initialize CLOB client
        self._clob = self._init_clob_client(private_key)

        mode = "DRY RUN" if dry_run else "LIVE"
        logger.info(f"LiveTrader initialized [{mode}] for {self.address}")

    def _init_clob_client(self, private_key: str) -> ClobClient:
        """Initialize and authenticate the CLOB client."""
        try:
            # Normalize private key
            pk = private_key if private_key.startswith("0x") else "0x" + private_key

            client = ClobClient(
                host=self.api_url,
                chain_id=CHAIN_ID,
                key=pk,
                signature_type=0,  # EOA signature
            )

            # Set API credentials (derives from private key)
            client.set_api_creds(client.create_or_derive_api_creds())
            logger.info("CLOB client authenticated successfully")
            return client

        except Exception as e:
            raise CLOBConnectionError(self.api_url, str(e))

    # ── Wallet ───────────────────────────────────────────────────────────────

    def get_wallet_balances(self) -> dict:
        """
        Query live wallet state.

        Returns:
            {
                'usdc_balance': float,
                'pol_balance': float,
                'ctf_approved': bool,
                'neg_risk_approved': bool,
                'address': str,
                'sufficient_gas': bool,
                'ready_to_trade': bool,
            }
        """
        return self.wallet.get_balances()

    def get_available_capital(self, reserve_pct: float = 0.05) -> float:
        """Return available USDC capital after reserving a buffer."""
        return self.wallet.get_available_capital(reserve_pct)

    def ensure_approvals(self) -> dict:
        """Set USDC.e max approval for CTF Exchange if not set."""
        return self.wallet.ensure_approvals(self._private_key)

    # ── Order Book ───────────────────────────────────────────────────────────

    @with_retry()
    def get_order_book(self, token_id: str) -> dict:
        """
        Fetch live order book for a Polymarket token.

        Args:
            token_id: Condition token ID (from Polymarket market URL or API)

        Returns:
            {
                'bids': [{'price': float, 'size': float}, ...],
                'asks': [{'price': float, 'size': float}, ...],
                'best_bid': float,
                'best_ask': float,
                'spread': float,
                'mid': float,
            }

        Raises:
            MarketNotFoundError: if token_id not found
        """
        try:
            raw_book = self._clob.get_order_book(token_id)
        except PolyApiException as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise MarketNotFoundError(token_id)
            raise

        bids = [
            {"price": float(level.price), "size": float(level.size)}
            for level in (raw_book.bids or [])
        ]
        asks = [
            {"price": float(level.price), "size": float(level.size)}
            for level in (raw_book.asks or [])
        ]

        # Sort: bids descending (best first), asks ascending
        bids.sort(key=lambda x: x["price"], reverse=True)
        asks.sort(key=lambda x: x["price"])

        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 1.0
        spread = round(best_ask - best_bid, 6)
        mid = round((best_bid + best_ask) / 2, 6) if (best_bid and best_ask) else 0.0

        book = {
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "mid": mid,
        }

        logger.debug(
            f"Order book [{token_id[:10]}...] "
            f"bid={best_bid:.4f} ask={best_ask:.4f} spread={spread:.4f}"
        )
        return book

    def get_mid_price(self, token_id: str) -> float:
        """Convenience: return mid price for a token."""
        book = self.get_order_book(token_id)
        return book["mid"]

    # ── Buy Order ────────────────────────────────────────────────────────────

    @with_retry()
    def place_buy_order(
        self,
        token_id: str,
        amount_usd: float,
        max_slippage: float = DEFAULT_MAX_SLIPPAGE,
        order_type: str = "GTC",
    ) -> dict:
        """
        Place a buy order on the CLOB.

        Strategy:
          - Fetches live ask price
          - Validates slippage against limit
          - Submits GTC limit order at ask (or FOK market order)
          - Returns fill result

        Args:
            token_id:    Token ID to buy.
            amount_usd:  USDC amount to spend (must be >= $1.00).
            max_slippage: Max acceptable price deviation (default: 2%).
            order_type:  "GTC" (Good Till Cancel) or "FOK" (Fill or Kill).

        Returns:
            {
                'order_id': str or None,
                'filled': bool,
                'fill_price': float,
                'filled_size': float,  # shares received
                'status': str,         # 'filled', 'open', 'cancelled', 'error'
                'error': str or None,
            }

        Raises:
            InsufficientBalanceError: if wallet balance < amount_usd
            SlippageExceededError: if best ask > desired price + slippage
            OrderRejectedError: if CLOB rejects the order
        """
        result = {**EMPTY_ORDER_RESULT}

        if amount_usd < MIN_ORDER_SIZE_USD:
            result["error"] = f"Minimum order size is ${MIN_ORDER_SIZE_USD:.2f} USD"
            logger.warning(f"Buy order rejected: amount ${amount_usd} < minimum")
            return result

        # Validate wallet before placing
        self.wallet.validate_for_trade(amount_usd)

        # Get current ask price
        book = self.get_order_book(token_id)
        best_ask = book["best_ask"]

        if best_ask <= 0:
            result["error"] = "No asks available in order book"
            return result

        # Slippage check (compare against mid price)
        mid = book["mid"]
        if mid > 0 and best_ask > mid * (1 + max_slippage):
            raise SlippageExceededError(
                desired=mid,
                actual=best_ask,
                max_slippage=max_slippage,
            )

        # Calculate shares to buy
        shares = round(amount_usd / best_ask, 4)

        logger.info(
            f"Placing BUY order: {shares:.4f} shares @ ${best_ask:.4f} "
            f"(${amount_usd:.2f} total) token={token_id[:12]}..."
        )

        if self.dry_run:
            logger.info("DRY RUN: Buy order simulated (not submitted)")
            return {
                "order_id": f"dry_run_{int(time.time())}",
                "filled": True,
                "fill_price": best_ask,
                "filled_size": shares,
                "status": "filled",
                "error": None,
            }

        # Build and submit order
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=best_ask,
                size=shares,
                side="BUY",
            )

            if order_type == "FOK":
                resp = self._clob.create_and_post_order(
                    order_args,
                    options=PartialCreateOrderOptions(tick_size=0.01),
                )
            else:  # GTC
                resp = self._clob.create_and_post_order(
                    order_args,
                    options=PartialCreateOrderOptions(tick_size=0.01),
                )

            order_id = resp.get("orderID") or resp.get("order_id", "")
            status = resp.get("status", "unknown")
            filled = status in ("MATCHED", "filled")
            fill_price = float(resp.get("price", best_ask))
            filled_size = float(resp.get("sizeMatched", 0)) or (shares if filled else 0)

            result.update({
                "order_id": order_id,
                "filled": filled,
                "fill_price": fill_price,
                "filled_size": filled_size,
                "status": status.lower(),
                "error": None,
            })

            logger.info(
                f"BUY order result: id={order_id} "
                f"filled={filled} price={fill_price:.4f} size={filled_size:.4f}"
            )

        except PolyApiException as e:
            err_msg = str(e)
            result["error"] = err_msg
            result["status"] = "error"
            logger.error(f"BUY order failed for {token_id[:12]}: {err_msg}")

        return result

    # ── Sell Order ───────────────────────────────────────────────────────────

    @with_retry()
    def place_sell_order(
        self,
        token_id: str,
        amount_tokens: float,
        min_price: float,
        order_type: str = "GTC",
    ) -> dict:
        """
        Place a sell order on the CLOB.

        Args:
            token_id:      Token ID to sell.
            amount_tokens: Number of shares to sell (must be >= 1.0).
            min_price:     Minimum acceptable sell price (slippage floor).
            order_type:    "GTC" or "FOK".

        Returns:
            Same format as place_buy_order.

        Raises:
            SlippageExceededError: if best bid < min_price
            OrderRejectedError: if CLOB rejects the order
        """
        result = {**EMPTY_ORDER_RESULT}

        if amount_tokens < MIN_ORDER_SIZE_TOKENS:
            result["error"] = f"Minimum sell size is {MIN_ORDER_SIZE_TOKENS} tokens"
            logger.warning(f"Sell order rejected: size {amount_tokens} < minimum")
            return result

        # Get current bid price
        book = self.get_order_book(token_id)
        best_bid = book["best_bid"]

        if best_bid <= 0:
            result["error"] = "No bids available in order book"
            return result

        # Price floor check
        if best_bid < min_price:
            raise SlippageExceededError(
                desired=min_price,
                actual=best_bid,
                max_slippage=0,
            )

        logger.info(
            f"Placing SELL order: {amount_tokens:.4f} shares @ ${best_bid:.4f} "
            f"(${amount_tokens * best_bid:.2f} total) token={token_id[:12]}..."
        )

        if self.dry_run:
            logger.info("DRY RUN: Sell order simulated (not submitted)")
            return {
                "order_id": f"dry_run_sell_{int(time.time())}",
                "filled": True,
                "fill_price": best_bid,
                "filled_size": amount_tokens,
                "status": "filled",
                "error": None,
            }

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=best_bid,
                size=amount_tokens,
                side="SELL",
            )

            resp = self._clob.create_and_post_order(
                order_args,
                options=PartialCreateOrderOptions(tick_size=0.01),
            )

            order_id = resp.get("orderID") or resp.get("order_id", "")
            status = resp.get("status", "unknown")
            filled = status in ("MATCHED", "filled")
            fill_price = float(resp.get("price", best_bid))
            filled_size = float(resp.get("sizeMatched", 0)) or (amount_tokens if filled else 0)

            result.update({
                "order_id": order_id,
                "filled": filled,
                "fill_price": fill_price,
                "filled_size": filled_size,
                "status": status.lower(),
                "error": None,
            })

            logger.info(
                f"SELL order result: id={order_id} "
                f"filled={filled} price={fill_price:.4f} size={filled_size:.4f}"
            )

        except PolyApiException as e:
            err_msg = str(e)
            result["error"] = err_msg
            result["status"] = "error"
            logger.error(f"SELL order failed for {token_id[:12]}: {err_msg}")

        return result

    # ── Order Management ─────────────────────────────────────────────────────

    @with_retry()
    def get_order_status(self, order_id: str) -> dict:
        """
        Query the current status of an order.

        Args:
            order_id: Order ID returned from place_buy/sell_order.

        Returns:
            {
                'order_id': str,
                'status': str,          # 'open', 'filled', 'cancelled', 'partial'
                'filled_size': float,   # shares filled so far
                'remaining_size': float,
                'avg_fill_price': float,
                'created_at': str,
                'error': str or None,
            }

        Raises:
            OrderNotFoundError: if order_id not found
        """
        try:
            order = self._clob.get_order(order_id)
        except PolyApiException as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise OrderNotFoundError(order_id)
            raise

        size_matched = float(order.get("size_matched", 0))
        size_total = float(order.get("original_size", 0))
        remaining = max(0.0, size_total - size_matched)
        avg_price = float(order.get("average_price", 0) or 0)
        raw_status = order.get("status", "unknown")

        # Normalize status
        if size_matched >= size_total and size_total > 0:
            status = "filled"
        elif size_matched > 0:
            status = "partial"
        elif raw_status.upper() in ("CANCELLED", "CANCELED"):
            status = "cancelled"
        else:
            status = "open"

        return {
            "order_id": order_id,
            "status": status,
            "filled_size": size_matched,
            "remaining_size": remaining,
            "avg_fill_price": avg_price,
            "created_at": order.get("created_at", ""),
            "error": None,
        }

    @with_retry()
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            True if successfully cancelled, False if already filled/cancelled.

        Raises:
            OrderNotFoundError: if order not found
        """
        try:
            resp = self._clob.cancel(order_id)
            cancelled = resp.get("cancelled", [])
            not_cancelled = resp.get("not_cancelled", [])

            success = order_id in cancelled
            if success:
                logger.info(f"Order cancelled: {order_id}")
            else:
                reason = not_cancelled[0] if not_cancelled else "unknown"
                logger.warning(f"Order not cancelled: {order_id} — reason: {reason}")

            return success

        except PolyApiException as e:
            if "not found" in str(e).lower():
                raise OrderNotFoundError(order_id)
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    @with_retry()
    def cancel_all_orders(self) -> dict:
        """
        Cancel ALL open orders for this wallet.

        Returns:
            {'cancelled': int, 'failed': int}
        """
        try:
            resp = self._clob.cancel_all()
            cancelled = len(resp.get("cancelled", []))
            not_cancelled = len(resp.get("not_cancelled", []))
            logger.info(f"Cancel all: {cancelled} cancelled, {not_cancelled} failed")
            return {"cancelled": cancelled, "failed": not_cancelled}
        except PolyApiException as e:
            logger.error(f"Cancel all failed: {e}")
            return {"cancelled": 0, "failed": 0}

    # ── Open Positions ────────────────────────────────────────────────────────

    @with_retry()
    def get_open_orders(self) -> list:
        """
        Return list of open orders for this wallet.

        Returns:
            List of order dicts with keys: order_id, token_id, side, price, size, status
        """
        try:
            orders = self._clob.get_orders()
            open_orders = []
            for o in (orders or []):
                if o.get("status", "").upper() in ("LIVE", "OPEN", "UNMATCHED"):
                    open_orders.append({
                        "order_id": o.get("id", ""),
                        "token_id": o.get("asset_id", ""),
                        "side": o.get("side", "").upper(),
                        "price": float(o.get("price", 0)),
                        "size": float(o.get("original_size", 0)),
                        "filled_size": float(o.get("size_matched", 0)),
                        "status": "open",
                    })
            logger.info(f"Found {len(open_orders)} open orders")
            return open_orders
        except PolyApiException as e:
            logger.error(f"get_open_orders failed: {e}")
            return []

    # ── Utility ──────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """Quick check: is the trader ready to place live orders?"""
        try:
            balances = self.get_wallet_balances()
            return balances["ready_to_trade"]
        except Exception as e:
            logger.warning(f"Readiness check failed: {e}")
            return False

    def health_check(self) -> dict:
        """
        Full system health check.

        Returns:
            {
                'clob_reachable': bool,
                'wallet_ready': bool,
                'usdc_balance': float,
                'pol_balance': float,
                'approvals_set': bool,
                'dry_run': bool,
                'errors': list[str],
            }
        """
        errors = []
        clob_ok = False
        wallet_state = {}

        try:
            # Ping CLOB
            self._clob.get_sampling_simplified_markets()
            clob_ok = True
        except Exception as e:
            errors.append(f"CLOB unreachable: {e}")

        try:
            wallet_state = self.get_wallet_balances()
        except Exception as e:
            errors.append(f"Wallet check failed: {e}")

        return {
            "clob_reachable": clob_ok,
            "wallet_ready": wallet_state.get("ready_to_trade", False),
            "usdc_balance": wallet_state.get("usdc_balance", 0.0),
            "pol_balance": wallet_state.get("pol_balance", 0.0),
            "approvals_set": wallet_state.get("ctf_approved", False),
            "dry_run": self.dry_run,
            "errors": errors,
        }
