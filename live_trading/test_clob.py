"""
test_clob.py — Unit tests for live_trading CLOB integration.

Tests use Mock objects to simulate CLOB and Web3 responses.
No real money, no network calls.

Run:
    pytest test_clob.py -v
    pytest test_clob.py -v -k "test_buy"  # run specific tests
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import time

# ── Test target imports ──────────────────────────────────────────────────────
from live_trading.exceptions import (
    InsufficientBalanceError,
    InsufficientGasError,
    MarketNotFoundError,
    OrderNotFoundError,
    SlippageExceededError,
    ApprovalNotSetError,
    RateLimitError,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

MOCK_ADDRESS = "0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF"
MOCK_TOKEN_ID = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

def make_mock_order_book_level(price: float, size: float):
    lvl = MagicMock()
    lvl.price = str(price)
    lvl.size = str(size)
    return lvl


def make_mock_raw_book(bids=None, asks=None):
    book = MagicMock()
    book.bids = bids or [
        make_mock_order_book_level(0.52, 100),
        make_mock_order_book_level(0.51, 200),
    ]
    book.asks = asks or [
        make_mock_order_book_level(0.54, 50),
        make_mock_order_book_level(0.55, 75),
    ]
    return book


@pytest.fixture
def mock_clob_client():
    """Returns a pre-configured mock ClobClient."""
    client = MagicMock()
    client.get_order_book.return_value = make_mock_raw_book()
    client.create_or_derive_api_creds.return_value = MagicMock()
    client.set_api_creds.return_value = None
    return client


@pytest.fixture
def mock_wallet_manager():
    """Returns a mock WalletManager that passes all checks."""
    wm = MagicMock()
    wm.get_balances.return_value = {
        "usdc_balance": 100.0,
        "pol_balance": 1.0,
        "ctf_approved": True,
        "neg_risk_approved": True,
        "address": MOCK_ADDRESS,
        "sufficient_gas": True,
        "ready_to_trade": True,
    }
    wm.get_usdc_balance.return_value = 100.0
    wm.get_pol_balance.return_value = 1.0
    wm.check_approval.return_value = True
    wm.validate_for_trade.return_value = None  # passes silently
    wm.get_available_capital.return_value = 95.0
    return wm


@pytest.fixture
def trader(mock_clob_client, mock_wallet_manager):
    """LiveTrader with all external dependencies mocked."""
    with patch("live_trading.clob_integration.ClobClient", return_value=mock_clob_client), \
         patch("live_trading.clob_integration.CLOB_AVAILABLE", True), \
         patch("live_trading.clob_integration.WalletManager", return_value=mock_wallet_manager):
        from live_trading.clob_integration import LiveTrader
        t = LiveTrader(
            private_key="0x" + "a" * 64,
            address=MOCK_ADDRESS,
            dry_run=False,
        )
        t._clob = mock_clob_client
        t.wallet = mock_wallet_manager
        return t


@pytest.fixture
def dry_run_trader(mock_clob_client, mock_wallet_manager):
    """LiveTrader in dry_run mode."""
    with patch("live_trading.clob_integration.ClobClient", return_value=mock_clob_client), \
         patch("live_trading.clob_integration.CLOB_AVAILABLE", True), \
         patch("live_trading.clob_integration.WalletManager", return_value=mock_wallet_manager):
        from live_trading.clob_integration import LiveTrader
        t = LiveTrader(
            private_key="0x" + "a" * 64,
            address=MOCK_ADDRESS,
            dry_run=True,
        )
        t._clob = mock_clob_client
        t.wallet = mock_wallet_manager
        return t


# ═══════════════════════════════════════════════════════════════════════════
# WALLET TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestWalletManager:

    def test_get_balances_returns_full_state(self, trader, mock_wallet_manager):
        balances = trader.get_wallet_balances()
        assert "usdc_balance" in balances
        assert "pol_balance" in balances
        assert "ctf_approved" in balances
        assert "ready_to_trade" in balances
        assert balances["usdc_balance"] == 100.0
        assert balances["ready_to_trade"] is True

    def test_get_available_capital_applies_reserve(self, trader, mock_wallet_manager):
        capital = trader.get_available_capital(reserve_pct=0.05)
        assert capital == 95.0  # 100 * 0.95

    def test_validate_trade_raises_insufficient_balance(self, trader, mock_wallet_manager):
        mock_wallet_manager.validate_for_trade.side_effect = InsufficientBalanceError(500.0, 100.0)
        with pytest.raises(InsufficientBalanceError) as exc:
            trader.wallet.validate_for_trade(500.0)
        assert exc.value.required == 500.0
        assert exc.value.available == 100.0

    def test_validate_trade_raises_insufficient_gas(self, trader, mock_wallet_manager):
        mock_wallet_manager.validate_for_trade.side_effect = InsufficientGasError(0.001)
        with pytest.raises(InsufficientGasError):
            trader.wallet.validate_for_trade(10.0)

    def test_validate_trade_raises_approval_error(self, trader, mock_wallet_manager):
        mock_wallet_manager.validate_for_trade.side_effect = ApprovalNotSetError()
        with pytest.raises(ApprovalNotSetError):
            trader.wallet.validate_for_trade(10.0)


# ═══════════════════════════════════════════════════════════════════════════
# ORDER BOOK TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestOrderBook:

    def test_get_order_book_structure(self, trader, mock_clob_client):
        book = trader.get_order_book(MOCK_TOKEN_ID)
        assert "bids" in book
        assert "asks" in book
        assert "best_bid" in book
        assert "best_ask" in book
        assert "spread" in book
        assert "mid" in book

    def test_order_book_best_prices(self, trader, mock_clob_client):
        book = trader.get_order_book(MOCK_TOKEN_ID)
        assert book["best_bid"] == 0.52  # highest bid
        assert book["best_ask"] == 0.54  # lowest ask
        assert book["spread"] == pytest.approx(0.02, abs=1e-6)
        assert book["mid"] == pytest.approx(0.53, abs=1e-6)

    def test_order_book_bids_sorted_descending(self, trader, mock_clob_client):
        book = trader.get_order_book(MOCK_TOKEN_ID)
        prices = [b["price"] for b in book["bids"]]
        assert prices == sorted(prices, reverse=True)

    def test_order_book_asks_sorted_ascending(self, trader, mock_clob_client):
        book = trader.get_order_book(MOCK_TOKEN_ID)
        prices = [a["price"] for a in book["asks"]]
        assert prices == sorted(prices)

    def test_order_book_market_not_found(self, trader, mock_clob_client):
        from py_clob_client.exceptions import PolyApiException
        mock_clob_client.get_order_book.side_effect = PolyApiException("404 not found")
        with pytest.raises(MarketNotFoundError):
            trader.get_order_book("0xbadtoken")

    def test_empty_order_book_handling(self, trader, mock_clob_client):
        mock_clob_client.get_order_book.return_value = make_mock_raw_book(bids=[], asks=[])
        book = trader.get_order_book(MOCK_TOKEN_ID)
        assert book["best_bid"] == 0.0
        assert book["best_ask"] == 1.0

    def test_get_mid_price(self, trader):
        mid = trader.get_mid_price(MOCK_TOKEN_ID)
        assert mid == pytest.approx(0.53, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# BUY ORDER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBuyOrder:

    def test_buy_order_minimum_size_guard(self, trader):
        result = trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=0.50)
        assert result["filled"] is False
        assert "minimum" in result["error"].lower()

    def test_buy_order_success(self, trader, mock_clob_client):
        mock_clob_client.create_and_post_order.return_value = {
            "orderID": "order_123",
            "status": "MATCHED",
            "price": "0.54",
            "sizeMatched": "1.85",
        }
        result = trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=1.0)
        assert result["filled"] is True
        assert result["order_id"] == "order_123"
        assert result["fill_price"] == 0.54
        assert result["error"] is None

    def test_buy_order_slippage_exceeded(self, trader, mock_clob_client):
        # Return a book where ask is 10% above mid
        high_ask_book = make_mock_raw_book(
            bids=[make_mock_order_book_level(0.50, 100)],
            asks=[make_mock_order_book_level(0.65, 50)],
        )
        mock_clob_client.get_order_book.return_value = high_ask_book
        with pytest.raises(SlippageExceededError):
            trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=5.0, max_slippage=0.02)

    def test_buy_order_insufficient_balance_propagates(self, trader, mock_wallet_manager):
        mock_wallet_manager.validate_for_trade.side_effect = InsufficientBalanceError(10.0, 5.0)
        with pytest.raises(InsufficientBalanceError):
            trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=10.0)

    def test_buy_order_dry_run(self, dry_run_trader):
        result = dry_run_trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=5.0)
        assert result["filled"] is True
        assert result["order_id"].startswith("dry_run_")
        assert result["fill_price"] == 0.54

    def test_buy_order_clob_rejection(self, trader, mock_clob_client):
        from py_clob_client.exceptions import PolyApiException
        mock_clob_client.create_and_post_order.side_effect = PolyApiException("invalid_size")
        result = trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=1.0)
        assert result["filled"] is False
        assert result["status"] == "error"
        assert result["error"] is not None

    def test_buy_order_no_asks(self, trader, mock_clob_client):
        mock_clob_client.get_order_book.return_value = make_mock_raw_book(asks=[])
        result = trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=1.0)
        assert result["filled"] is False
        assert "no asks" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# SELL ORDER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSellOrder:

    def test_sell_order_minimum_size_guard(self, trader):
        result = trader.place_sell_order(MOCK_TOKEN_ID, amount_tokens=0.5, min_price=0.50)
        assert result["filled"] is False
        assert "minimum" in result["error"].lower()

    def test_sell_order_success(self, trader, mock_clob_client):
        mock_clob_client.create_and_post_order.return_value = {
            "orderID": "sell_456",
            "status": "MATCHED",
            "price": "0.52",
            "sizeMatched": "10.0",
        }
        result = trader.place_sell_order(MOCK_TOKEN_ID, amount_tokens=10.0, min_price=0.50)
        assert result["filled"] is True
        assert result["order_id"] == "sell_456"

    def test_sell_order_price_floor_violated(self, trader, mock_clob_client):
        # best_bid = 0.52, but we want min 0.60
        with pytest.raises(SlippageExceededError):
            trader.place_sell_order(MOCK_TOKEN_ID, amount_tokens=5.0, min_price=0.60)

    def test_sell_order_dry_run(self, dry_run_trader):
        result = dry_run_trader.place_sell_order(MOCK_TOKEN_ID, amount_tokens=5.0, min_price=0.40)
        assert result["filled"] is True
        assert result["order_id"].startswith("dry_run_sell_")

    def test_sell_order_no_bids(self, trader, mock_clob_client):
        mock_clob_client.get_order_book.return_value = make_mock_raw_book(bids=[])
        result = trader.place_sell_order(MOCK_TOKEN_ID, amount_tokens=5.0, min_price=0.40)
        assert result["filled"] is False
        assert "no bids" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# ORDER STATUS TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestOrderStatus:

    def test_get_order_status_filled(self, trader, mock_clob_client):
        mock_clob_client.get_order.return_value = {
            "id": "order_123",
            "status": "MATCHED",
            "original_size": "10.0",
            "size_matched": "10.0",
            "average_price": "0.54",
            "created_at": "2025-01-01T00:00:00Z",
        }
        status = trader.get_order_status("order_123")
        assert status["status"] == "filled"
        assert status["filled_size"] == 10.0
        assert status["remaining_size"] == 0.0
        assert status["avg_fill_price"] == 0.54

    def test_get_order_status_partial_fill(self, trader, mock_clob_client):
        mock_clob_client.get_order.return_value = {
            "id": "order_456",
            "status": "LIVE",
            "original_size": "20.0",
            "size_matched": "5.0",
            "average_price": "0.53",
            "created_at": "2025-01-01T00:00:00Z",
        }
        status = trader.get_order_status("order_456")
        assert status["status"] == "partial"
        assert status["filled_size"] == 5.0
        assert status["remaining_size"] == 15.0

    def test_get_order_status_open(self, trader, mock_clob_client):
        mock_clob_client.get_order.return_value = {
            "id": "order_789",
            "status": "LIVE",
            "original_size": "10.0",
            "size_matched": "0.0",
            "average_price": "0",
            "created_at": "2025-01-01T00:00:00Z",
        }
        status = trader.get_order_status("order_789")
        assert status["status"] == "open"

    def test_get_order_status_not_found(self, trader, mock_clob_client):
        from py_clob_client.exceptions import PolyApiException
        mock_clob_client.get_order.side_effect = PolyApiException("404 not found")
        with pytest.raises(OrderNotFoundError):
            trader.get_order_status("nonexistent_order")


# ═══════════════════════════════════════════════════════════════════════════
# CANCEL ORDER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCancelOrder:

    def test_cancel_order_success(self, trader, mock_clob_client):
        mock_clob_client.cancel.return_value = {
            "cancelled": ["order_123"],
            "not_cancelled": [],
        }
        result = trader.cancel_order("order_123")
        assert result is True

    def test_cancel_order_already_filled(self, trader, mock_clob_client):
        mock_clob_client.cancel.return_value = {
            "cancelled": [],
            "not_cancelled": ["order_123"],
        }
        result = trader.cancel_order("order_123")
        assert result is False

    def test_cancel_all_orders(self, trader, mock_clob_client):
        mock_clob_client.cancel_all.return_value = {
            "cancelled": ["o1", "o2", "o3"],
            "not_cancelled": ["o4"],
        }
        result = trader.cancel_all_orders()
        assert result["cancelled"] == 3
        assert result["failed"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# RETRY LOGIC TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRetryLogic:

    def test_retries_on_rate_limit(self, trader, mock_clob_client):
        from py_clob_client.exceptions import PolyApiException
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PolyApiException("429 rate_limit_exceeded")
            return make_mock_raw_book()

        mock_clob_client.get_order_book.side_effect = side_effect

        with patch("time.sleep"):  # Don't actually wait
            book = trader.get_order_book(MOCK_TOKEN_ID)

        assert call_count == 3
        assert book["best_ask"] == 0.54

    def test_non_retryable_error_raises_immediately(self, trader, mock_clob_client):
        """Market not found should NOT be retried."""
        from py_clob_client.exceptions import PolyApiException
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise PolyApiException("404 not found")

        mock_clob_client.get_order_book.side_effect = side_effect

        with pytest.raises(MarketNotFoundError):
            trader.get_order_book("0xbadtoken")

        assert call_count == 1  # Should NOT retry


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurity:

    def test_private_key_not_in_repr(self, trader):
        """Private key must never appear in string representation."""
        trader_repr = repr(trader)
        assert "aaaa" not in trader_repr  # our mock key was all 'a's

    def test_private_key_not_in_str(self, trader):
        trader_str = str(trader)
        assert "aaaa" not in trader_str


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION SMOKE TESTS (dry-run, no network)
# ═══════════════════════════════════════════════════════════════════════════

class TestDryRunIntegration:
    """Full flow tests using dry_run mode."""

    def test_full_buy_flow(self, dry_run_trader):
        health = dry_run_trader.health_check()
        assert health["dry_run"] is True

        book = dry_run_trader.get_order_book(MOCK_TOKEN_ID)
        assert book["best_ask"] > 0

        result = dry_run_trader.place_buy_order(MOCK_TOKEN_ID, amount_usd=5.0)
        assert result["filled"] is True

        # In dry_run, order_id is fake — status check should work on live
        assert result["order_id"] is not None

    def test_full_sell_flow(self, dry_run_trader):
        result = dry_run_trader.place_sell_order(
            MOCK_TOKEN_ID, amount_tokens=5.0, min_price=0.40
        )
        assert result["filled"] is True
        assert result["fill_price"] == 0.52  # best_bid

    def test_is_ready_check(self, dry_run_trader):
        assert dry_run_trader.is_ready() is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
