"""
correlation_limiter.py — OpenClaw Correlation Risk Manager
===========================================================
Prevents the bot from entering multiple highly-correlated positions
simultaneously, which would disguise concentrated risk as diversification.

Core rules enforced:
  1. MAX_CORRELATED_POSITIONS — no more than N open positions in the same
     correlation group (e.g. BTC+ETH+SOL+XRP are all "crypto_large_cap")
  2. MAX_GROUP_EXPOSURE_PCT   — total $ in any one group capped as % of balance
  3. MAX_TOTAL_EXPOSURE_PCT   — total open position $ capped as % of balance
  4. SAME_DIRECTION_LIMIT     — max N positions all pointing the same way (YES/NO)

Usage:
    from correlation_limiter import CorrelationLimiter, Position

    cl = CorrelationLimiter(portfolio_value=453.08)

    # Before entering a trade:
    ok, reason = cl.can_enter(coin="BTC", side="YES", size_usd=22.65)
    if not ok:
        return  # skip entry

    # After order confirmed:
    cl.open_position(coin="BTC", side="YES", size_usd=22.65, market_id="abc123")

    # After position closes:
    cl.close_position(position_id)
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


# ─── Correlation Map ──────────────────────────────────────────────────────────
# Group coins by how correlated they behave in crypto prediction markets.
# Same group = treat as same underlying risk factor.

CORRELATION_GROUPS: dict[str, list[str]] = {
    "crypto_large_cap": ["BTC", "ETH", "SOL", "XRP"],  # all move together on macro
    # Future groups:
    # "crypto_mid_cap":  ["AVAX", "MATIC", "LINK"],
    # "crypto_stable":   ["USDT", "USDC"],
    # "macro":           ["SPY", "QQQ", "GOLD"],
}

# Reverse map: coin → group name (built at import time)
COIN_TO_GROUP: dict[str, str] = {
    coin: group
    for group, coins in CORRELATION_GROUPS.items()
    for coin in coins
}


# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class CorrelationConfig:
    # Per-group limits
    max_correlated_positions: int   = 2      # max open positions in same group
    max_group_exposure_pct:   float = 0.10   # max 10% of portfolio in one group

    # Portfolio-wide limits
    max_total_exposure_pct:   float = 0.15   # max 15% of portfolio open at once
    max_same_direction:       int   = 3      # max N positions all YES or all NO

    # Per-position size cap (independent of above)
    max_single_position_pct:  float = 0.05   # max 5% per trade


# ─── Position ─────────────────────────────────────────────────────────────────

@dataclass
class Position:
    id:         str
    coin:       str
    group:      str
    side:       str            # "YES" or "NO"
    size_usd:   float
    market_id:  str
    opened_at:  datetime
    closed_at:  Optional[datetime] = None
    pnl:        Optional[float]    = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


# ─── Correlation Limiter ──────────────────────────────────────────────────────

class CorrelationLimiter:
    """
    Stateful position tracker and correlation risk enforcer.
    One instance per bot session, shared across all coins.
    """

    def __init__(
        self,
        portfolio_value: float,
        config: Optional[CorrelationConfig] = None,
    ):
        self.portfolio_value  = portfolio_value
        self.config           = config or CorrelationConfig()
        self._positions:      dict[str, Position] = {}   # id → Position
        self._closed_history: list[Position]      = []

    # ── Public API ────────────────────────────────────────────────────────────

    def update_portfolio_value(self, new_value: float) -> None:
        """Call after each trade to keep exposure % calculations accurate."""
        self.portfolio_value = new_value

    def can_enter(
        self,
        coin:     str,
        side:     str,
        size_usd: float,
    ) -> tuple[bool, str]:
        """
        Check all correlation rules before entering a trade.
        Returns (True, "OK") or (False, human-readable reason).
        Call this BEFORE placing any order.
        """
        cfg   = self.config
        group = COIN_TO_GROUP.get(coin.upper(), "unknown")
        open_positions = self._open_positions()

        # ── 1. Single position size cap ──
        single_pct = size_usd / self.portfolio_value if self.portfolio_value else 0
        if single_pct > cfg.max_single_position_pct:
            return False, (
                f"Position size ${size_usd:.2f} = {single_pct:.1%} exceeds "
                f"max single position {cfg.max_single_position_pct:.1%}"
            )

        # ── 2. Total exposure cap ──
        current_exposure    = sum(p.size_usd for p in open_positions)
        new_total_exposure  = current_exposure + size_usd
        new_exposure_pct    = new_total_exposure / self.portfolio_value if self.portfolio_value else 0
        if new_exposure_pct > cfg.max_total_exposure_pct:
            return False, (
                f"Total exposure would be ${new_total_exposure:.2f} = {new_exposure_pct:.1%} "
                f"(max={cfg.max_total_exposure_pct:.1%}) | "
                f"Current open: ${current_exposure:.2f}"
            )

        # ── 3. Correlated position count ──
        group_positions = [p for p in open_positions if p.group == group]
        if len(group_positions) >= cfg.max_correlated_positions:
            coins_open = [p.coin for p in group_positions]
            return False, (
                f"Group '{group}' already has {len(group_positions)} open positions "
                f"{coins_open} (max={cfg.max_correlated_positions}). "
                f"These coins are correlated — would not add diversification."
            )

        # ── 4. Group exposure cap ──
        group_exposure     = sum(p.size_usd for p in group_positions)
        new_group_exposure = group_exposure + size_usd
        group_pct          = new_group_exposure / self.portfolio_value if self.portfolio_value else 0
        if group_pct > cfg.max_group_exposure_pct:
            return False, (
                f"Group '{group}' exposure would be ${new_group_exposure:.2f} = {group_pct:.1%} "
                f"(max={cfg.max_group_exposure_pct:.1%})"
            )

        # ── 5. Same-direction concentration ──
        same_direction = [p for p in open_positions if p.side == side]
        if len(same_direction) >= cfg.max_same_direction:
            return False, (
                f"Already have {len(same_direction)} open {side} positions "
                f"(max={cfg.max_same_direction}). "
                f"All-{side} book creates one-directional macro risk."
            )

        # ── 6. Duplicate coin check ──
        duplicate = [p for p in open_positions if p.coin.upper() == coin.upper()]
        if duplicate:
            return False, (
                f"Already have an open {duplicate[0].side} position in {coin}. "
                f"Close it before re-entering."
            )

        return True, "OK"

    def open_position(
        self,
        coin:      str,
        side:      str,
        size_usd:  float,
        market_id: str = "",
    ) -> Position:
        """
        Register a new open position AFTER order is confirmed by exchange.
        Returns the Position object (store the .id if you need to close it later).
        """
        group = COIN_TO_GROUP.get(coin.upper(), "unknown")
        pos   = Position(
            id        = str(uuid.uuid4())[:8],
            coin      = coin.upper(),
            group     = group,
            side      = side,
            size_usd  = size_usd,
            market_id = market_id,
            opened_at = datetime.now(timezone.utc),
        )
        self._positions[pos.id] = pos
        logger.info(
            "📬 Position OPENED [%s] %s %s $%.2f | group=%s | open_count=%d",
            pos.id, side, coin, size_usd, group, len(self._open_positions())
        )
        return pos

    def close_position(
        self,
        position_id: str,
        pnl:         float = 0.0,
    ) -> Optional[Position]:
        """
        Mark position as closed AFTER it resolves.
        Returns the closed Position, or None if id not found.
        """
        pos = self._positions.get(position_id)
        if pos is None:
            logger.warning("close_position: id '%s' not found", position_id)
            return None
        pos.closed_at = datetime.now(timezone.utc)
        pos.pnl       = pnl
        self._closed_history.append(pos)
        del self._positions[position_id]
        logger.info(
            "📭 Position CLOSED [%s] %s %s | pnl=%+.2f | open_count=%d",
            pos.id, pos.side, pos.coin, pnl, len(self._open_positions())
        )
        return pos

    def close_by_coin(self, coin: str, pnl: float = 0.0) -> Optional[Position]:
        """Convenience: close the open position for a given coin."""
        for pos in self._open_positions():
            if pos.coin.upper() == coin.upper():
                return self.close_position(pos.id, pnl)
        logger.warning("close_by_coin: no open position found for %s", coin)
        return None

    # ── Status / Reporting ────────────────────────────────────────────────────

    def status(self) -> dict:
        open_pos  = self._open_positions()
        total_exp = sum(p.size_usd for p in open_pos)

        group_summary = {}
        for group in CORRELATION_GROUPS:
            gp = [p for p in open_pos if p.group == group]
            if gp:
                group_summary[group] = {
                    "count":      len(gp),
                    "coins":      [p.coin for p in gp],
                    "exposure":   round(sum(p.size_usd for p in gp), 2),
                    "sides":      [p.side for p in gp],
                }

        return {
            "open_positions":      len(open_pos),
            "total_exposure_usd":  round(total_exp, 2),
            "total_exposure_pct":  round(total_exp / self.portfolio_value, 4) if self.portfolio_value else 0,
            "portfolio_value":     self.portfolio_value,
            "positions":           [
                {"id": p.id, "coin": p.coin, "side": p.side,
                 "size": p.size_usd, "group": p.group,
                 "opened": p.opened_at.strftime("%H:%M:%S")}
                for p in open_pos
            ],
            "group_summary":       group_summary,
            "closed_today":        len(self._closed_history),
        }

    def risk_report(self) -> str:
        """Human-readable risk snapshot for logging/heartbeat."""
        s    = self.status()
        cfg  = self.config
        lines = [
            f"── Correlation Risk Report ──",
            f"  Portfolio:  ${self.portfolio_value:.2f}",
            f"  Exposure:   ${s['total_exposure_usd']:.2f} ({s['total_exposure_pct']:.1%})"
            f"  [limit: {cfg.max_total_exposure_pct:.0%}]",
            f"  Open pos:   {s['open_positions']}",
        ]
        if s["group_summary"]:
            for group, info in s["group_summary"].items():
                lines.append(
                    f"  Group [{group}]: {info['coins']} "
                    f"${info['exposure']:.2f} | sides={info['sides']}"
                )
        else:
            lines.append("  No open positions.")
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.is_open]


# ─── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import json

    print("\n=== Correlation Limiter Smoke Test ===\n")
    cl = CorrelationLimiter(portfolio_value=453.08)

    scenarios = [
        # (coin,  side,   size,   expect_ok, label)
        ("BTC",  "YES",  20.00,  True,  "First BTC position — should pass"),
        ("ETH",  "YES",  20.00,  True,  "Second position — different coin, same group — passes (max=2)"),
        ("SOL",  "YES",  20.00,  False, "Third crypto_large_cap — should BLOCK (group limit=2)"),
        ("BTC",  "YES",  20.00,  False, "Duplicate BTC — should BLOCK"),
        ("XRP",  "NO",   50.00,  False, "Size too large (>5% of $453) — should BLOCK"),
    ]

    for coin, side, size, expect_ok, label in scenarios:
        ok, reason = cl.can_enter(coin, side, size)
        result = "✓ PASS" if ok == expect_ok else "✗ FAIL"
        status = "ALLOWED" if ok else f"BLOCKED: {reason}"
        print(f"  {result} | {label}")
        print(f"         → {status}")
        if ok:
            cl.open_position(coin, side, size)
        print()

    print(cl.risk_report())
    print("\n--- Full Status ---")
    print(json.dumps(cl.status(), indent=2))
