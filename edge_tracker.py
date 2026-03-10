"""
═══════════════════════════════════════════════════════════════════════════════
edge_tracker.py — Patched for Calibrated Kelly
Replaces hardcoded edge=0.03 with KellyCalibrator
═══════════════════════════════════════════════════════════════════════════════
DROP-IN replacement for your existing edge_tracker.py.
Keeps backward compatibility: get_kelly_stake() signature unchanged.
Adds:  calibrator singleton, record_trade(), print_status()
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kelly_calibrator import (
    KellyCalibrator,
    KellyConfig,
    TradeRecord,
    classify_price,
    full_kelly,
    print_calibration_status,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global calibrator singleton — initialized at bot startup
# ─────────────────────────────────────────────────────────────────────────────

_cfg        = KellyConfig()
calibrator  = KellyCalibrator(_cfg)
_loaded     = calibrator.load()

if not _loaded:
    logger.info("[EdgeTracker] No prior calibration — will build from scratch.")


# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD-COMPATIBLE DROP-IN
# ─────────────────────────────────────────────────────────────────────────────

def get_kelly_stake(
    edge:       float,       # Kept for signature compatibility — IGNORED internally
    bankroll:   float,
    fraction:   float = 0.25,  # Kept for compatibility — now computed dynamically
    entry_price: Optional[float] = None,   # NEW: pass token price for calibration
    coin:       str   = "",
) -> float:
    """
    Drop-in replacement for your existing get_kelly_stake().

    Old call:   get_kelly_stake(edge=0.03, bankroll=691.55)
    New call:   get_kelly_stake(edge=0.03, bankroll=691.55, entry_price=0.25, coin="BTC")

    The `edge` and `fraction` args are accepted but internally replaced by
    calibrated values. Pass entry_price for best results.
    """
    if entry_price is None:
        # Legacy fallback: can't calibrate without price
        # Use old formula to avoid breaking existing calls
        logger.warning(
            "[EdgeTracker] get_kelly_stake called without entry_price — "
            "using legacy formula. Update call site."
        )
        win_prob     = 0.5 + edge
        loss_prob    = 1.0 - win_prob
        kelly_pct    = (win_prob * 1.0 - loss_prob) / 1.0
        return bankroll * kelly_pct * fraction

    stake, diag = calibrator.get_stake(
        entry_price = entry_price,
        bankroll    = bankroll,
        coin        = coin,
    )
    logger.debug(f"[EdgeTracker] Stake={stake:.2f} | {diag}")
    return stake


def get_kelly_stake_with_diagnostics(
    entry_price: float,
    bankroll:    float,
    coin:        str = "",
) -> tuple[float, dict]:
    """
    Extended version that returns full diagnostics.
    Use this in your main bot loop for logging.
    """
    return calibrator.get_stake(entry_price, bankroll, coin)


# ─────────────────────────────────────────────────────────────────────────────
# TRADE RECORDING
# ─────────────────────────────────────────────────────────────────────────────

def record_completed_trade(
    trade_id:    str,
    market_id:   str,
    coin:        str,
    entry_price: float,
    outcome:     str,          # 'WIN' or 'LOSS'
    pnl_pct:     float = 0.0,  # Realized P&L as fraction of stake
    notes:       str   = "",
):
    """
    Call this from finalize_position() after every trade resolves.
    This is the key feedback loop that calibrates future sizing.

    pnl_pct:
      WIN  at entry 0.025 → gain 0.975 per token → pnl_pct = +0.975
      WIN  at entry 0.685 → gain 0.315 per token → pnl_pct = +0.315
      LOSS (any)          → lose full stake       → pnl_pct = -1.0
    """
    bucket, norm = classify_price(entry_price)

    trade = TradeRecord(
        trade_id      = trade_id,
        market_id     = market_id,
        coin          = coin,
        entry_price   = entry_price,
        outcome       = outcome.upper(),
        pnl_pct       = pnl_pct,
        timestamp_utc = datetime.now(timezone.utc).isoformat(),
        bucket        = bucket,
        norm_price    = norm,
        notes         = notes,
    )
    calibrator.record_trade(trade)
    calibrator.save()


def import_trade_history(trades_json_path: str, field_map: Optional[dict] = None) -> int:
    """
    One-time import of your existing trades_v4_production.json.
    Returns number of trades successfully imported.
    """
    n = calibrator.import_from_trades_json(trades_json_path, field_map)
    if n > 0:
        calibrator.save()
    return n


def print_edge_status():
    """Print current calibration status — call from CLI or on startup."""
    print_calibration_status(calibrator)
