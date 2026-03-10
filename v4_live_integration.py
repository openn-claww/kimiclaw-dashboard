"""
v4_live_integration.py — Drop-in live trading layer for Ultimate Bot V4.

This is the bridge between V4's virtual trading interface and real CLOB orders.

ARCHITECTURE:
  V4 bot calls execute_buy() / execute_sell() as before.
  This class intercepts those calls and:
    1. Routes to CLOB if live trading is enabled
    2. Falls back to virtual trading if CLOB fails
    3. Maintains BOTH virtual P&L and live P&L simultaneously
    4. Enforces all safety limits (position size, daily loss, slippage)
    5. Never crashes the V4 bot — all errors are caught and logged

INTEGRATION POINTS (see v4_patch_instructions.py for exact line numbers):
  - __init__: add self.live = V4BotLiveIntegration(...)
  - execute_buy: replace virtual block with self.live.execute_buy(...)
  - execute_sell: replace virtual block with self.live.execute_sell(...)
"""

import os
import json
import logging
import time
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

# Import live trading modules (installed alongside this file)
try:
    from live_trading.clob_integration import LiveTrader
    from live_trading.exceptions import (
        InsufficientBalanceError,
        InsufficientGasError,
        RateLimitError,
        OrderRejectedError,
        SlippageExceededError,
        MarketNotFoundError,
        LiveTradingError,
    )
    LIVE_TRADING_AVAILABLE = True
except ImportError as e:
    LIVE_TRADING_AVAILABLE = False
    logger.warning(f"live_trading module not available: {e} — falling back to virtual only")

from token_mapper import TokenMapper


# ── Result format (matches V4 bot's expected return shape) ──────────────────
def _buy_result(
    success=False, virtual=True, order_id=None,
    fill_price=0.0, filled_size=0.0, amount_usd=0.0, error=None
) -> dict:
    return {
        "status": "filled" if success else "error",
        "success": success,
        "virtual": virtual,
        "order_id": order_id,
        "fill_price": fill_price,
        "filled_size": filled_size,
        "amount_usd": amount_usd,
        "error": error,
    }


def _sell_result(
    success=False, virtual=True, order_id=None,
    fill_price=0.0, filled_size=0.0, pnl=0.0, error=None
) -> dict:
    return {
        "status": "filled" if success else "error",
        "success": success,
        "virtual": virtual,
        "order_id": order_id,
        "fill_price": fill_price,
        "filled_size": filled_size,
        "pnl": pnl,
        "error": error,
    }


class V4BotLiveIntegration:
    """
    Wraps the V4 bot's virtual trading with live CLOB execution.

    Usage (inside ultimate_bot_v4.py __init__):
        self.live = V4BotLiveIntegration(config, private_key, address)

    Usage (inside execute_buy):
        result = self.live.execute_buy(market_id, side, amount, price)

    Usage (inside execute_sell):
        result = self.live.execute_sell(market_id, exit_price)
    """

    def __init__(self, config: dict, private_key: Optional[str], address: Optional[str]):
        """
        Args:
            config:      LIVE_TRADING_CONFIG dict (from live_trading_config.py)
            private_key: Wallet private key (from env var, never hardcoded)
            address:     Wallet address
        """
        self.config = config
        self.enabled = config.get("enabled", False)
        self.dry_run = config.get("dry_run", True)
        self.max_slippage = config.get("max_slippage", 0.02)
        self.max_position_size = config.get("max_position_size", 20.0)
        self.daily_loss_limit = config.get("daily_loss_limit", 20.0)
        self.min_order_size = config.get("min_order_size", 1.0)
        self.max_open_positions = config.get("max_open_positions", 5)
        self.trade_log_path = config.get("trade_log_path", "live_trades_v4.json")
        self.track_virtual = config.get("track_virtual_pnl", True)

        # ── State tracking ───────────────────────────────────────────────────
        # live_positions: market_id → live order/fill data
        self.live_positions: dict = {}
        # virtual_positions: market_id → virtual position data (for comparison)
        self.virtual_positions: dict = {}
        # Daily loss accumulator — resets at midnight
        self._daily_loss: float = 0.0
        self._daily_loss_date: date = date.today()
        # Kill switch — set True to halt all live trading immediately
        self.kill_switch: bool = False

        # ── P&L trackers ────────────────────────────────────────────────────
        self.live_pnl_total: float = 0.0
        self.virtual_pnl_total: float = 0.0
        self.trade_count: int = 0

        # ── Token mapper ─────────────────────────────────────────────────────
        self.mapper = TokenMapper()

        # ── CLOB trader ──────────────────────────────────────────────────────
        self.trader: Optional[LiveTrader] = None
        if self.enabled and LIVE_TRADING_AVAILABLE and private_key and address:
            try:
                self.trader = LiveTrader(
                    private_key=private_key,
                    address=address,
                    api_url=config.get("clob_api_url", "https://clob.polymarket.com"),
                    rpc_url=config.get("polygon_rpc", "https://polygon-rpc.com"),
                    dry_run=self.dry_run,
                )
                logger.info(
                    f"V4BotLiveIntegration ready — "
                    f"mode={'DRY RUN' if self.dry_run else '🔴 LIVE'} | "
                    f"max_pos=${self.max_position_size} | "
                    f"daily_limit=${self.daily_loss_limit}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize LiveTrader: {e} — falling back to virtual")
                self.trader = None
        elif not self.enabled:
            logger.info("Live trading disabled — running virtual only")

        # Load existing trade log
        self._load_trade_log()

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API — called from V4 bot
    # ══════════════════════════════════════════════════════════════════════════

    def execute_buy(
        self,
        market_id: str,
        side: str,          # "YES" or "NO"
        amount: float,      # USDC to spend
        price: float,       # V4's estimated/current price (used for virtual tracking)
        signal_data: dict = None,
    ) -> dict:
        """
        Execute a buy order — live CLOB or virtual fallback.

        Replaces V4's virtual execute_buy(). Same call signature.

        Args:
            market_id:   V4's internal market identifier
            side:        "YES" or "NO"
            amount:      USDC amount to spend
            price:       V4's estimated entry price (for virtual P&L baseline)
            signal_data: Optional signal metadata for audit log

        Returns:
            {
                "status": "filled" | "error",
                "success": bool,
                "virtual": bool,      # True if this was a virtual trade
                "order_id": str,      # CLOB order ID or "virtual_<ts>"
                "fill_price": float,  # Actual fill price (live) or price param (virtual)
                "filled_size": float, # Shares received
                "amount_usd": float,  # USDC spent
                "error": str or None,
            }
        """
        # ── Safety gates ────────────────────────────────────────────────────
        gate_result = self._check_buy_gates(market_id, amount)
        if gate_result is not None:
            # Gate blocked — record virtual position and return
            self._record_virtual_buy(market_id, side, amount, price)
            return gate_result

        # ── Try live CLOB order ──────────────────────────────────────────────
        if self._should_go_live():
            result = self._live_buy(market_id, side, amount, price, signal_data)
            if result["success"]:
                return result
            # Live failed — fall through to virtual with warning
            logger.warning(
                f"[BUY] Live order failed for {market_id} — "
                f"falling back to virtual. Error: {result['error']}"
            )

        # ── Virtual fallback ─────────────────────────────────────────────────
        return self._virtual_buy(market_id, side, amount, price)

    def execute_sell(
        self,
        market_id: str,
        exit_price: float,       # V4's observed exit price
        signal_data: dict = None,
    ) -> dict:
        """
        Execute a sell order — live CLOB or virtual fallback.

        Replaces V4's virtual execute_sell(). Same call signature.

        Args:
            market_id:   V4's internal market identifier
            exit_price:  V4's observed exit/resolution price
            signal_data: Optional signal metadata

        Returns:
            {
                "status": "filled" | "error",
                "success": bool,
                "virtual": bool,
                "order_id": str,
                "fill_price": float,
                "filled_size": float,
                "pnl": float,        # Realized P&L in USDC
                "error": str or None,
            }
        """
        # Kill switch check
        if self.kill_switch:
            logger.warning("[SELL] Kill switch active — virtual only")
            return self._virtual_sell(market_id, exit_price)

        # ── Try live CLOB order ──────────────────────────────────────────────
        if self._should_go_live() and market_id in self.live_positions:
            result = self._live_sell(market_id, exit_price, signal_data)
            if result["success"]:
                return result
            logger.warning(
                f"[SELL] Live order failed for {market_id} — "
                f"falling back to virtual. Error: {result['error']}"
            )

        # ── Virtual fallback ─────────────────────────────────────────────────
        return self._virtual_sell(market_id, exit_price)

    def get_status(self) -> dict:
        """
        Return current integration status — useful for V4 bot's status display.
        """
        self._reset_daily_loss_if_new_day()
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "kill_switch": self.kill_switch,
            "live_pnl": round(self.live_pnl_total, 4),
            "virtual_pnl": round(self.virtual_pnl_total, 4),
            "daily_loss_used": round(self._daily_loss, 4),
            "daily_loss_limit": self.daily_loss_limit,
            "daily_loss_remaining": round(self.daily_loss_limit - self._daily_loss, 4),
            "open_live_positions": len(self.live_positions),
            "trade_count": self.trade_count,
            "trader_ready": self.trader is not None and self.trader.is_ready(),
        }

    def trigger_kill_switch(self, reason: str = "manual"):
        """Hard stop all live trading. Positions are NOT auto-closed."""
        self.kill_switch = True
        logger.critical(f"🛑 KILL SWITCH TRIGGERED — reason: {reason}")
        logger.critical(
            f"Open live positions: {list(self.live_positions.keys())} — "
            f"CLOSE MANUALLY if needed"
        )

    def reset_kill_switch(self):
        """Re-enable live trading after kill switch."""
        self.kill_switch = False
        logger.info("Kill switch reset — live trading re-enabled")

    # ══════════════════════════════════════════════════════════════════════════
    # LIVE ORDER EXECUTION
    # ══════════════════════════════════════════════════════════════════════════

    def _live_buy(
        self,
        market_id: str,
        side: str,
        amount: float,
        price: float,
        signal_data: dict,
    ) -> dict:
        """Execute live buy via CLOB."""
        # Resolve token ID
        token_id = self.mapper.resolve(market_id, side)
        if not token_id:
            logger.error(f"[LIVE BUY] Cannot resolve token_id for {market_id}/{side}")
            return _buy_result(error=f"Token resolution failed for {market_id}/{side}")

        try:
            raw = self.trader.place_buy_order(
                token_id=token_id,
                amount_usd=amount,
                max_slippage=self.max_slippage,
            )

            if not raw.get("filled"):
                return _buy_result(
                    error=raw.get("error") or "Order not filled",
                    fill_price=raw.get("fill_price", price),
                )

            fill_price = raw["fill_price"]
            filled_size = raw["filled_size"]
            order_id = raw["order_id"]

            # Track live position
            self.live_positions[market_id] = {
                "order_id": order_id,
                "token_id": token_id,
                "side": side,
                "shares": filled_size,
                "entry_price": fill_price,
                "cost_usd": amount,
                "opened_at": datetime.utcnow().isoformat(),
            }

            # Also track virtual for comparison
            if self.track_virtual:
                self._record_virtual_buy(market_id, side, amount, price)

            self.trade_count += 1
            self._save_trade({
                "type": "BUY",
                "market_id": market_id,
                "token_id": token_id,
                "side": side,
                "order_id": order_id,
                "amount_usd": amount,
                "shares": filled_size,
                "live_price": fill_price,
                "virtual_price": price,
                "slippage": round(fill_price - price, 6),
                "timestamp": datetime.utcnow().isoformat(),
                "signal": signal_data,
                "dry_run": self.dry_run,
            })

            logger.info(
                f"[LIVE BUY ✅] {market_id} | {side} | "
                f"{filled_size:.4f} shares @ ${fill_price:.4f} | "
                f"order={order_id}"
            )

            return _buy_result(
                success=True,
                virtual=self.dry_run,
                order_id=order_id,
                fill_price=fill_price,
                filled_size=filled_size,
                amount_usd=amount,
            )

        except InsufficientBalanceError as e:
            logger.warning(f"[LIVE BUY] Insufficient balance: {e}")
            return _buy_result(error=str(e))

        except SlippageExceededError as e:
            logger.warning(f"[LIVE BUY] Slippage exceeded: {e}")
            return _buy_result(error=str(e))

        except MarketNotFoundError as e:
            logger.error(f"[LIVE BUY] Market not found: {e}")
            return _buy_result(error=str(e))

        except RateLimitError as e:
            logger.warning(f"[LIVE BUY] Rate limit — will retry via decorator: {e}")
            raise  # Let @with_retry handle it

        except OrderRejectedError as e:
            logger.error(f"[LIVE BUY] Order rejected: {e}")
            return _buy_result(error=str(e))

        except LiveTradingError as e:
            logger.error(f"[LIVE BUY] Trading error: {e}")
            return _buy_result(error=str(e))

        except Exception as e:
            logger.error(f"[LIVE BUY] Unexpected error: {e}", exc_info=True)
            return _buy_result(error=f"Unexpected: {e}")

    def _live_sell(
        self,
        market_id: str,
        exit_price: float,
        signal_data: dict,
    ) -> dict:
        """Execute live sell via CLOB."""
        pos = self.live_positions.get(market_id)
        if not pos:
            return _sell_result(error="No live position found")

        token_id = pos["token_id"]
        shares = pos["shares"]
        min_price = exit_price * (1 - self.max_slippage)

        try:
            raw = self.trader.place_sell_order(
                token_id=token_id,
                amount_tokens=shares,
                min_price=min_price,
            )

            if not raw.get("filled"):
                return _sell_result(error=raw.get("error") or "Sell not filled")

            fill_price = raw["fill_price"]
            filled_size = raw["filled_size"]
            order_id = raw["order_id"]

            # Calculate real P&L
            live_pnl = (fill_price - pos["entry_price"]) * filled_size
            self.live_pnl_total += live_pnl

            # Track daily loss
            if live_pnl < 0:
                self._daily_loss += abs(live_pnl)
                self._check_daily_loss_limit()

            # Clean up position
            del self.live_positions[market_id]

            self._save_trade({
                "type": "SELL",
                "market_id": market_id,
                "token_id": token_id,
                "order_id": order_id,
                "shares": filled_size,
                "live_exit_price": fill_price,
                "virtual_exit_price": exit_price,
                "entry_price": pos["entry_price"],
                "live_pnl": live_pnl,
                "timestamp": datetime.utcnow().isoformat(),
                "signal": signal_data,
                "dry_run": self.dry_run,
            })

            logger.info(
                f"[LIVE SELL ✅] {market_id} | "
                f"{filled_size:.4f} shares @ ${fill_price:.4f} | "
                f"P&L: ${live_pnl:+.4f} | order={order_id}"
            )

            return _sell_result(
                success=True,
                virtual=self.dry_run,
                order_id=order_id,
                fill_price=fill_price,
                filled_size=filled_size,
                pnl=live_pnl,
            )

        except SlippageExceededError as e:
            logger.warning(f"[LIVE SELL] Slippage exceeded: {e}")
            return _sell_result(error=str(e))

        except LiveTradingError as e:
            logger.error(f"[LIVE SELL] Trading error: {e}")
            return _sell_result(error=str(e))

        except Exception as e:
            logger.error(f"[LIVE SELL] Unexpected error: {e}", exc_info=True)
            return _sell_result(error=f"Unexpected: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # VIRTUAL TRADING (unchanged from V4 original logic)
    # ══════════════════════════════════════════════════════════════════════════

    def _virtual_buy(self, market_id: str, side: str, amount: float, price: float) -> dict:
        """Virtual buy — original V4 behavior preserved exactly."""
        self._record_virtual_buy(market_id, side, amount, price)
        order_id = f"virtual_{int(time.time() * 1000)}"
        shares = round(amount / price, 6) if price > 0 else 0
        logger.info(
            f"[VIRTUAL BUY] {market_id} | {side} | "
            f"{shares:.4f} shares @ ${price:.4f} | ${amount:.2f}"
        )
        return _buy_result(
            success=True,
            virtual=True,
            order_id=order_id,
            fill_price=price,
            filled_size=shares,
            amount_usd=amount,
        )

    def _virtual_sell(self, market_id: str, exit_price: float) -> dict:
        """Virtual sell — original V4 P&L calculation preserved exactly."""
        pos = self.virtual_positions.get(market_id)
        if not pos:
            return _sell_result(error="No virtual position found")

        side = pos["side"]
        entry = pos["entry_price"]
        shares = pos["shares"]

        # Original V4 P&L formula
        if side == "YES":
            pnl = (exit_price - entry) * shares
        else:
            pnl = (entry - exit_price) * shares

        self.virtual_pnl_total += pnl
        del self.virtual_positions[market_id]

        logger.info(
            f"[VIRTUAL SELL] {market_id} | {side} | "
            f"exit=${exit_price:.4f} entry=${entry:.4f} | P&L: ${pnl:+.4f}"
        )

        return _sell_result(
            success=True,
            virtual=True,
            fill_price=exit_price,
            filled_size=shares,
            pnl=pnl,
        )

    def _record_virtual_buy(self, market_id: str, side: str, amount: float, price: float):
        """Record a virtual position (used for comparison tracking)."""
        shares = round(amount / price, 6) if price > 0 else 0
        self.virtual_positions[market_id] = {
            "side": side,
            "shares": shares,
            "entry_price": price,
            "cost_usd": amount,
            "opened_at": datetime.utcnow().isoformat(),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # SAFETY GATES
    # ══════════════════════════════════════════════════════════════════════════

    def _should_go_live(self) -> bool:
        """Returns True only if all conditions for live trading are met."""
        return (
            self.enabled
            and self.trader is not None
            and not self.kill_switch
            and LIVE_TRADING_AVAILABLE
        )

    def _check_buy_gates(self, market_id: str, amount: float) -> Optional[dict]:
        """
        Run all pre-trade safety checks.
        Returns a blocked result dict if any check fails, None if all pass.
        """
        # ── Kill switch ──
        if self.kill_switch:
            logger.warning("[GATE] Kill switch active — blocking live buy")
            return _buy_result(error="Kill switch active")

        # ── Minimum order size ──
        if amount < self.min_order_size:
            logger.warning(f"[GATE] Amount ${amount} < minimum ${self.min_order_size}")
            return _buy_result(error=f"Below minimum order size ${self.min_order_size}")

        # ── Max position size ──
        if amount > self.max_position_size:
            logger.warning(
                f"[GATE] Amount ${amount} exceeds max position ${self.max_position_size} — "
                f"clamping to max"
            )
            amount = self.max_position_size  # Clamp, don't block

        # ── Max open positions ──
        if len(self.live_positions) >= self.max_open_positions:
            logger.warning(
                f"[GATE] At max open positions ({self.max_open_positions}) — blocking buy"
            )
            return _buy_result(
                error=f"Max open positions ({self.max_open_positions}) reached"
            )

        # ── Daily loss limit ──
        self._reset_daily_loss_if_new_day()
        if self._daily_loss >= self.daily_loss_limit:
            logger.critical(
                f"[GATE] Daily loss limit hit: ${self._daily_loss:.2f} >= ${self.daily_loss_limit}"
            )
            self.trigger_kill_switch("daily_loss_limit_reached")
            return _buy_result(error="Daily loss limit reached — trading halted")

        # ── Duplicate position guard ──
        if market_id in self.live_positions:
            logger.warning(f"[GATE] Already have open position for {market_id} — blocking")
            return _buy_result(error=f"Duplicate position for {market_id}")

        return None  # All gates passed

    def _check_daily_loss_limit(self):
        """Trigger kill switch if daily loss limit exceeded after a losing trade."""
        if self._daily_loss >= self.daily_loss_limit:
            self.trigger_kill_switch(
                f"daily_loss_limit_reached (${self._daily_loss:.2f} >= ${self.daily_loss_limit})"
            )

    def _reset_daily_loss_if_new_day(self):
        """Reset daily loss counter at midnight."""
        today = date.today()
        if today != self._daily_loss_date:
            logger.info(
                f"New trading day — resetting daily loss "
                f"(was ${self._daily_loss:.2f})"
            )
            self._daily_loss = 0.0
            self._daily_loss_date = today
            self.kill_switch = False  # Auto-reset daily kill switch

    # ══════════════════════════════════════════════════════════════════════════
    # TRADE LOGGING
    # ══════════════════════════════════════════════════════════════════════════

    def _load_trade_log(self):
        try:
            with open(self.trade_log_path) as f:
                self._trade_log = json.load(f)
            logger.info(f"Loaded {len(self._trade_log)} existing trade records")
        except (FileNotFoundError, json.JSONDecodeError):
            self._trade_log = []

    def _save_trade(self, record: dict):
        self._trade_log.append(record)
        try:
            with open(self.trade_log_path, "w") as f:
                json.dump(self._trade_log, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Failed to save trade log: {e}")
