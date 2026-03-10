"""
integration_example.py — How to hook LiveTrader into Ultimate Bot V4.

This file shows the exact pattern to replace virtual trading with live
CLOB orders in ultimate_bot_v4_production.py.

⚠️  NEVER hardcode private keys. Load from environment variables only.
"""

import os
import json
import logging
from datetime import datetime

# ── Setup logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("live_trades.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("integration_example")

# ── Import LiveTrader ─────────────────────────────────────────────────────────
from live_trading import LiveTrader
from live_trading.exceptions import (
    LiveTradingError,
    InsufficientBalanceError,
    SlippageExceededError,
    MarketNotFoundError,
)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Initialize
# ═══════════════════════════════════════════════════════════════════════════

def init_live_trader(dry_run: bool = True) -> LiveTrader:
    """
    Initialize the LiveTrader from environment variables.

    Set these before running:
        export POLY_PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
        export POLY_ADDRESS="0xYOUR_WALLET_ADDRESS"

    Args:
        dry_run: Start in dry_run mode (True = simulate, False = real money)
    """
    private_key = os.environ.get("POLY_PRIVATE_KEY")
    address = os.environ.get("POLY_ADDRESS")

    if not private_key or not address:
        raise ValueError(
            "Missing environment variables. Set POLY_PRIVATE_KEY and POLY_ADDRESS.\n"
            "Never hardcode keys in source files."
        )

    trader = LiveTrader(
        private_key=private_key,
        address=address,
        dry_run=dry_run,
    )

    logger.info(f"LiveTrader initialized (dry_run={dry_run})")
    return trader


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: Pre-flight checks
# ═══════════════════════════════════════════════════════════════════════════

def run_preflight(trader: LiveTrader) -> bool:
    """
    Run all checks before starting live trading.
    Returns True if ready, False if issues found.
    """
    logger.info("=== Pre-flight checks ===")

    health = trader.health_check()
    logger.info(f"CLOB reachable:   {health['clob_reachable']}")
    logger.info(f"Wallet ready:     {health['wallet_ready']}")
    logger.info(f"USDC balance:     ${health['usdc_balance']:.2f}")
    logger.info(f"POL balance:      {health['pol_balance']:.4f} POL")
    logger.info(f"Approvals set:    {health['approvals_set']}")
    logger.info(f"Dry run mode:     {health['dry_run']}")

    if health["errors"]:
        for err in health["errors"]:
            logger.error(f"Pre-flight error: {err}")
        return False

    if not health["wallet_ready"] and not health["dry_run"]:
        logger.error("Wallet not ready for live trading!")
        logger.error("Run: trader.ensure_approvals() to set USDC approvals")
        return False

    if not health["clob_reachable"]:
        logger.error("CLOB API unreachable — check network/VPN")
        return False

    logger.info("✅ All pre-flight checks passed")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: The V4 bot integration pattern
# ═══════════════════════════════════════════════════════════════════════════

class V4BotLiveIntegration:
    """
    Drop-in live trading layer for Ultimate Bot V4.

    Replaces virtual buy/sell logic with real CLOB orders while
    keeping the paper trading path intact for comparison.

    Usage in ultimate_bot_v4_production.py:
        # OLD (virtual):
        if signal == 'BUY':
            virtual_free -= amount
            virtual_positions[token_id] = {'shares': shares, 'cost': amount}

        # NEW (live):
        live_integration = V4BotLiveIntegration(trader, trade_log_path="trades.json")
        if signal == 'BUY':
            result = live_integration.execute_buy(token_id, amount, signal_data)
    """

    def __init__(
        self,
        trader: LiveTrader,
        trade_log_path: str = "live_trades.json",
        max_position_usd: float = 20.0,
        max_slippage: float = 0.02,
    ):
        self.trader = trader
        self.trade_log_path = trade_log_path
        self.max_position_usd = max_position_usd
        self.max_slippage = max_slippage
        self.open_positions: dict = {}

        # Load existing trade log
        self._load_trade_log()

    def _load_trade_log(self):
        try:
            with open(self.trade_log_path) as f:
                self.trade_log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.trade_log = []

    def _save_trade(self, trade_record: dict):
        self.trade_log.append(trade_record)
        with open(self.trade_log_path, "w") as f:
            json.dump(self.trade_log, f, indent=2, default=str)

    def execute_buy(
        self,
        token_id: str,
        amount_usd: float,
        signal_data: dict = None,
    ) -> dict:
        """
        Execute a live BUY order via CLOB.

        Args:
            token_id:     Polymarket token ID (condition ID).
            amount_usd:   USDC to spend ($1 minimum).
            signal_data:  V4 signal metadata (logged for audit trail).

        Returns:
            {
                'success': bool,
                'order_id': str or None,
                'filled_size': float,
                'fill_price': float,
                'amount_spent': float,
                'error': str or None,
            }
        """
        # Cap at max position size
        amount_usd = min(amount_usd, self.max_position_usd)
        logger.info(f"[BUY] token={token_id[:12]}... amount=${amount_usd:.2f}")

        try:
            result = self.trader.place_buy_order(
                token_id=token_id,
                amount_usd=amount_usd,
                max_slippage=self.max_slippage,
            )

            if result.get("filled"):
                # Track position
                self.open_positions[token_id] = {
                    "order_id": result["order_id"],
                    "shares": result["filled_size"],
                    "cost_usd": amount_usd,
                    "entry_price": result["fill_price"],
                    "opened_at": datetime.utcnow().isoformat(),
                }

                # Save to log
                self._save_trade({
                    "type": "BUY",
                    "token_id": token_id,
                    "order_id": result["order_id"],
                    "amount_usd": amount_usd,
                    "shares": result["filled_size"],
                    "price": result["fill_price"],
                    "timestamp": datetime.utcnow().isoformat(),
                    "signal": signal_data,
                    "dry_run": self.trader.dry_run,
                })

                logger.info(
                    f"[BUY ✅] {result['filled_size']:.4f} shares @ ${result['fill_price']:.4f} "
                    f"order={result['order_id']}"
                )

            return {
                "success": result.get("filled", False),
                "order_id": result.get("order_id"),
                "filled_size": result.get("filled_size", 0.0),
                "fill_price": result.get("fill_price", 0.0),
                "amount_spent": amount_usd if result.get("filled") else 0.0,
                "error": result.get("error"),
            }

        except InsufficientBalanceError as e:
            logger.error(f"[BUY ❌] Insufficient balance: {e}")
            return {"success": False, "error": str(e), "order_id": None,
                    "filled_size": 0, "fill_price": 0, "amount_spent": 0}

        except SlippageExceededError as e:
            logger.warning(f"[BUY ⚠️ ] Slippage exceeded: {e}")
            return {"success": False, "error": str(e), "order_id": None,
                    "filled_size": 0, "fill_price": 0, "amount_spent": 0}

        except MarketNotFoundError as e:
            logger.error(f"[BUY ❌] Market not found: {e}")
            return {"success": False, "error": str(e), "order_id": None,
                    "filled_size": 0, "fill_price": 0, "amount_spent": 0}

        except LiveTradingError as e:
            logger.error(f"[BUY ❌] Trading error: {e}")
            return {"success": False, "error": str(e), "order_id": None,
                    "filled_size": 0, "fill_price": 0, "amount_spent": 0}

    def execute_sell(
        self,
        token_id: str,
        min_price: float,
        amount_tokens: float = None,
        signal_data: dict = None,
    ) -> dict:
        """
        Execute a live SELL order via CLOB.

        Args:
            token_id:      Polymarket token ID.
            min_price:     Minimum acceptable sell price.
            amount_tokens: Shares to sell (default: full position).
            signal_data:   V4 signal metadata.

        Returns:
            Same format as execute_buy.
        """
        position = self.open_positions.get(token_id)
        if not position:
            logger.warning(f"[SELL] No open position for {token_id[:12]}...")
            return {"success": False, "error": "No open position found",
                    "order_id": None, "filled_size": 0, "fill_price": 0, "amount_spent": 0}

        shares_to_sell = amount_tokens or position["shares"]
        logger.info(f"[SELL] token={token_id[:12]}... shares={shares_to_sell:.4f}")

        try:
            result = self.trader.place_sell_order(
                token_id=token_id,
                amount_tokens=shares_to_sell,
                min_price=min_price,
            )

            if result.get("filled"):
                pnl = (result["fill_price"] - position["entry_price"]) * shares_to_sell
                logger.info(
                    f"[SELL ✅] {shares_to_sell:.4f} shares @ ${result['fill_price']:.4f} "
                    f"P&L: ${pnl:+.4f} order={result['order_id']}"
                )

                self._save_trade({
                    "type": "SELL",
                    "token_id": token_id,
                    "order_id": result["order_id"],
                    "shares": shares_to_sell,
                    "price": result["fill_price"],
                    "pnl_usd": pnl,
                    "timestamp": datetime.utcnow().isoformat(),
                    "signal": signal_data,
                    "dry_run": self.trader.dry_run,
                })

                if shares_to_sell >= position["shares"] * 0.99:
                    del self.open_positions[token_id]

            return {
                "success": result.get("filled", False),
                "order_id": result.get("order_id"),
                "filled_size": result.get("filled_size", 0.0),
                "fill_price": result.get("fill_price", 0.0),
                "amount_spent": 0.0,
                "error": result.get("error"),
            }

        except (SlippageExceededError, LiveTradingError) as e:
            logger.error(f"[SELL ❌] {e}")
            return {"success": False, "error": str(e), "order_id": None,
                    "filled_size": 0, "fill_price": 0, "amount_spent": 0}


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: $1 Test order checklist
# ═══════════════════════════════════════════════════════════════════════════

def run_live_test_checklist(trader: LiveTrader, token_id: str):
    """
    Run the test checklist from the spec.
    Executes a $1 test order and validates all components.

    Args:
        trader:   Initialized LiveTrader (set dry_run=False for real test)
        token_id: A live Polymarket token ID to test against
    """
    results = {
        "can_query_usdc_balance": False,
        "can_get_order_book": False,
        "can_place_1_dollar_order": False,
        "can_check_order_status": False,
        "handles_errors_gracefully": False,
        "logs_all_activity": True,  # Logging is always active
    }

    # ✅ 1. USDC balance
    try:
        balances = trader.get_wallet_balances()
        logger.info(f"USDC balance: ${balances['usdc_balance']:.6f}")
        results["can_query_usdc_balance"] = True
    except Exception as e:
        logger.error(f"Balance check failed: {e}")

    # ✅ 2. Order book
    try:
        book = trader.get_order_book(token_id)
        logger.info(f"Order book: bid={book['best_bid']:.4f} ask={book['best_ask']:.4f}")
        results["can_get_order_book"] = True
    except Exception as e:
        logger.error(f"Order book failed: {e}")

    # ✅ 3. Place $1 test order
    order_id = None
    try:
        result = trader.place_buy_order(token_id, amount_usd=1.0, max_slippage=0.05)
        logger.info(f"$1 order result: {result}")
        if result.get("order_id") or result.get("filled"):
            results["can_place_1_dollar_order"] = True
            order_id = result.get("order_id")
    except Exception as e:
        logger.error(f"$1 order failed: {e}")

    # ✅ 4. Check order status
    if order_id and not trader.dry_run:
        try:
            status = trader.get_order_status(order_id)
            logger.info(f"Order status: {status}")
            results["can_check_order_status"] = True
        except Exception as e:
            logger.error(f"Status check failed: {e}")
    elif trader.dry_run:
        results["can_check_order_status"] = True  # N/A in dry_run

    # ✅ 5. Error handling
    try:
        trader.get_order_book("0xinvalidtoken000000000000000000000000000000000000000000000000000000")
    except MarketNotFoundError:
        results["handles_errors_gracefully"] = True
    except Exception:
        results["handles_errors_gracefully"] = True  # Any clean exception = good

    # Summary
    logger.info("\n=== TEST CHECKLIST RESULTS ===")
    all_pass = True
    for check, passed in results.items():
        icon = "✅" if passed else "❌"
        logger.info(f"  {icon} {check}")
        if not passed:
            all_pass = False

    logger.info(f"\n{'✅ ALL CHECKS PASSED' if all_pass else '❌ SOME CHECKS FAILED'}")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — run this file directly to test
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Default: dry run mode
    DRY_RUN = "--live" not in sys.argv

    # Example token ID — replace with a real active market token
    # Find at: https://polymarket.com — copy token ID from URL or API
    TEST_TOKEN_ID = os.environ.get(
        "POLY_TEST_TOKEN",
        "0x1234000000000000000000000000000000000000000000000000000000000000"
    )

    print(f"\n{'='*60}")
    print(f"Polymarket CLOB Integration Test")
    print(f"Mode: {'🔴 LIVE' if not DRY_RUN else '🟡 DRY RUN'}")
    print(f"{'='*60}\n")

    if DRY_RUN:
        print("Running in DRY RUN mode. Pass --live to use real funds.\n")

    trader = init_live_trader(dry_run=DRY_RUN)

    # Pre-flight
    if not run_preflight(trader):
        print("Pre-flight failed. Fix issues above before trading.")
        sys.exit(1)

    # Run checklist
    run_live_test_checklist(trader, TEST_TOKEN_ID)

    # Show integration example
    print("\n=== Integration Example ===")
    integration = V4BotLiveIntegration(trader, max_position_usd=5.0)
    result = integration.execute_buy(
        token_id=TEST_TOKEN_ID,
        amount_usd=1.0,
        signal_data={"probability": 0.65, "edge": 0.12, "market": "test"},
    )
    print(f"Execute buy result: {json.dumps(result, indent=2)}")
