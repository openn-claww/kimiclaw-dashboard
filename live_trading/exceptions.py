"""
Custom exceptions for Polymarket live trading module.
"""


class LiveTradingError(Exception):
    """Base exception for all live trading errors."""
    pass


class InsufficientBalanceError(LiveTradingError):
    """Raised when wallet has insufficient USDC.e for the trade."""
    def __init__(self, required: float, available: float):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient balance: need ${required:.2f} USDC, have ${available:.2f} USDC"
        )


class InsufficientGasError(LiveTradingError):
    """Raised when wallet has insufficient POL for gas fees."""
    def __init__(self, available_pol: float):
        self.available_pol = available_pol
        super().__init__(
            f"Insufficient POL for gas: {available_pol:.6f} POL available (need ~0.01 POL)"
        )


class MarketNotFoundError(LiveTradingError):
    """Raised when the token_id / market doesn't exist."""
    def __init__(self, token_id: str):
        self.token_id = token_id
        super().__init__(f"Market not found for token_id: {token_id}")


class OrderNotFoundError(LiveTradingError):
    """Raised when an order_id doesn't exist."""
    def __init__(self, order_id: str):
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")


class RateLimitError(LiveTradingError):
    """Raised when CLOB API returns 429 Too Many Requests."""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit hit — retry after {retry_after}s")


class OrderRejectedError(LiveTradingError):
    """Raised when CLOB rejects an order (bad price, size, etc.)."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Order rejected by CLOB: {reason}")


class SlippageExceededError(LiveTradingError):
    """Raised when best available price exceeds max slippage."""
    def __init__(self, desired: float, actual: float, max_slippage: float):
        self.desired = desired
        self.actual = actual
        self.max_slippage = max_slippage
        super().__init__(
            f"Slippage exceeded: desired={desired:.4f}, actual={actual:.4f}, "
            f"max_slippage={max_slippage:.4f}"
        )


class ApprovalNotSetError(LiveTradingError):
    """Raised when USDC.e approval for CTF Exchange is not set."""
    def __init__(self):
        super().__init__(
            "USDC.e not approved for CTF Exchange. "
            "Run wallet_manager.ensure_approvals() first."
        )


class CLOBConnectionError(LiveTradingError):
    """Raised when cannot connect to CLOB API."""
    def __init__(self, url: str, reason: str):
        self.url = url
        super().__init__(f"Cannot connect to CLOB at {url}: {reason}")


class PartialFillError(LiveTradingError):
    """Raised when a FOK order is only partially filled (should never fill partial)."""
    def __init__(self, order_id: str, filled: float, requested: float):
        self.order_id = order_id
        self.filled = filled
        self.requested = requested
        super().__init__(
            f"Partial fill on FOK order {order_id}: "
            f"filled {filled:.4f} of {requested:.4f}"
        )


# Error code mapping for external error strings from CLOB API
CLOB_ERROR_MAP = {
    "insufficient_balance": InsufficientBalanceError,
    "market_not_found": MarketNotFoundError,
    "rate_limit_exceeded": RateLimitError,
    "order_not_found": OrderNotFoundError,
}
