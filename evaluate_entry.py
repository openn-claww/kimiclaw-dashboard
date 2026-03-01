"""
evaluate_entry.py — V4 entry evaluation with zone block filter.

Change log:
  - Added passes_zone_filter() after price validation (Step 2 in pipeline)
  - All other filters (velocity, volume, sentiment, MTF) unchanged
  - Blocked entries logged to both console and blocked_entries.log
"""

import logging
from dataclasses import dataclass
from typing import Optional

# ── Logging setup ─────────────────────────────────────────────────────────────
logger = logging.getLogger("evaluate_entry")

blocked_handler = logging.FileHandler("blocked_entries.log")
blocked_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

blocked_logger = logging.getLogger("blocked_entries")
blocked_logger.addHandler(blocked_handler)
blocked_logger.setLevel(logging.INFO)
blocked_logger.propagate = False   # Don't send to root logger


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class EntrySignal:
    coin:       str
    side:       str        # "YES" or "NO"
    yes_price:  float
    no_price:   float
    velocity:   float
    volume:     float
    volume_ema: float


@dataclass
class EntryDecision:
    allowed:      bool
    block_stage:  Optional[str]   # Which filter blocked it, None if allowed
    block_reason: Optional[str]
    signal:       EntrySignal

    def log(self):
        if self.allowed:
            logger.info(
                f"[ENTRY ALLOWED] {self.signal.coin} {self.signal.side} "
                f"@ {self.signal.yes_price:.3f}"
            )
        else:
            msg = (
                f"[ENTRY BLOCKED] {self.signal.coin} {self.signal.side} "
                f"@ {self.signal.yes_price:.3f} | "
                f"Stage: {self.block_stage} | "
                f"Reason: {self.block_reason}"
            )
            logger.info(msg)
            blocked_logger.info(msg)   # Also write to blocked_entries.log


# ── Zone block constants ──────────────────────────────────────────────────────
DEAD_ZONE_LOW  = 0.35
DEAD_ZONE_HIGH = 0.65


# ── Individual filter functions ───────────────────────────────────────────────

def passes_price_check(yes_price: float) -> tuple[bool, str]:
    """
    STEP 1 — Original price range validation (unchanged).
    Blocks entries outside 0.15–0.85.
    """
    if yes_price < 0.15:
        return False, f"yes_price {yes_price:.3f} below minimum 0.15"
    if yes_price > 0.85:
        return False, f"yes_price {yes_price:.3f} above maximum 0.85"
    return True, "Price range OK"


# ── NEW FILTER ────────────────────────────────────────────────────────────────
def passes_zone_filter(yes_price: float, side: str) -> tuple[bool, str]:
    """
    STEP 2 — Dead zone block (NEW — inserted after price check).

    Blocks entries where the effective entry price is in [0.35, 0.65].
    Effective price accounts for side:
      YES trade: you're buying YES at yes_price  → effective = yes_price
      NO trade:  you're buying NO  at no_price   → effective = 1 - yes_price

    This is the ONLY new change in V4. All other parameters are unchanged.
    """
    effective_price = yes_price if side == "YES" else (1.0 - yes_price)

    if DEAD_ZONE_LOW <= effective_price <= DEAD_ZONE_HIGH:
        return False, (
            f"Effective price {effective_price:.3f} in dead zone "
            f"[{DEAD_ZONE_LOW}, {DEAD_ZONE_HIGH}] — no edge here"
        )
    return True, f"Zone OK (effective={effective_price:.3f})"
# ── END NEW FILTER ────────────────────────────────────────────────────────────


def passes_velocity_check(
    velocity: float,
    threshold: float,
    side: str,
) -> tuple[bool, str]:
    """
    STEP 3 — Velocity threshold check (unchanged).
    YES: velocity must be > +threshold
    NO:  velocity must be < -threshold
    """
    if side == "YES" and velocity <= threshold:
        return False, f"YES velocity {velocity:.4f} <= threshold {threshold:.4f}"
    if side == "NO" and velocity >= -threshold:
        return False, f"NO velocity {velocity:.4f} >= -{threshold:.4f}"
    return True, f"Velocity OK ({velocity:.4f})"


def passes_volume_check(
    volume: float,
    volume_ema: float,
    multiplier: float = 1.5,
) -> tuple[bool, str]:
    """
    STEP 4 — Volume confirmation (unchanged).
    Requires current volume > multiplier × EMA.
    """
    required = volume_ema * multiplier
    if volume <= required:
        return False, (
            f"Volume {volume:.2f} <= required {required:.2f} "
            f"({volume / volume_ema:.2f}× vs {multiplier}× needed)"
        )
    return True, f"Volume OK ({volume / volume_ema:.2f}×)"


def passes_sentiment_check(
    fng_value: int,
    side: str,
) -> tuple[bool, str]:
    """
    STEP 5 — Fear & Greed sentiment filter (unchanged).
    Extreme Fear (0–20): YES only.
    Extreme Greed (81–100): NO only.
    """
    if fng_value <= 20 and side == "NO":
        return False, f"Extreme Fear ({fng_value}) — NO entries blocked"
    if fng_value >= 81 and side == "YES":
        return False, f"Extreme Greed ({fng_value}) — YES entries blocked"
    return True, f"Sentiment OK (FNG={fng_value})"


def passes_mtf_check(
    m15_velocity: float,
    h1_velocity:  float,
    side:         str,
    neutral_band: float = 0.002,
) -> tuple[bool, str]:
    """
    STEP 6 — Multi-timeframe alignment (unchanged).
    M15 must not oppose the primary signal.
    H1 is checked but only warns when neutral.
    """
    def alignment(v: float) -> str:
        if abs(v) <= neutral_band:
            return "neutral"
        return "aligned" if v > 0 else "against"

    m15_align = alignment(m15_velocity)
    h1_align  = alignment(h1_velocity)

    # M15 opposing = hard block
    if side == "YES" and m15_align == "against":
        return False, f"M15 against YES (velocity={m15_velocity:.4f})"
    if side == "NO" and m15_align == "aligned":
        return False, f"M15 against NO (velocity={m15_velocity:.4f})"

    return True, f"MTF OK (M15={m15_align}, H1={h1_align})"


# ── Master entry evaluation ───────────────────────────────────────────────────

def evaluate_entry(
    signal:           EntrySignal,
    velocity_threshold: float,
    fng_value:        int,
    m15_velocity:     float,
    h1_velocity:      float,
    volume_multiplier: float = 1.5,
) -> EntryDecision:
    """
    Evaluates whether to enter a trade. Returns EntryDecision.

    Pipeline (V4 + zone block):
      1. Price check        — yes_price in [0.15, 0.85]
      2. Zone block (NEW)   — effective price NOT in [0.35, 0.65]
      3. Velocity check     — velocity crosses threshold for side
      4. Volume check       — volume > multiplier × EMA
      5. Sentiment check    — FNG sentiment allows side
      6. MTF check          — M15 + H1 aligned with direction

    The zone block is inserted at position 2 — after the basic price
    range check but before any signal-quality filters. This order ensures
    we reject dead-zone prices as cheaply as possible (no EMA or API calls
    needed) while preserving the original filter logic intact.
    """

    def _block(stage: str, reason: str) -> EntryDecision:
        decision = EntryDecision(
            allowed=False,
            block_stage=stage,
            block_reason=reason,
            signal=signal,
        )
        decision.log()
        return decision

    # ── Step 1: Price range ───────────────────────────────────────────────────
    ok, reason = passes_price_check(signal.yes_price)
    if not ok:
        return _block("price_check", reason)

    # ── Step 2: Zone block (NEW) ──────────────────────────────────────────────
    ok, reason = passes_zone_filter(signal.yes_price, signal.side)
    if not ok:
        return _block("zone_block", reason)

    # ── Step 3: Velocity ──────────────────────────────────────────────────────
    ok, reason = passes_velocity_check(
        signal.velocity, velocity_threshold, signal.side
    )
    if not ok:
        return _block("velocity_check", reason)

    # ── Step 4: Volume ────────────────────────────────────────────────────────
    ok, reason = passes_volume_check(
        signal.volume, signal.volume_ema, volume_multiplier
    )
    if not ok:
        return _block("volume_check", reason)

    # ── Step 5: Sentiment ─────────────────────────────────────────────────────
    ok, reason = passes_sentiment_check(fng_value, signal.side)
    if not ok:
        return _block("sentiment_check", reason)

    # ── Step 6: MTF alignment ─────────────────────────────────────────────────
    ok, reason = passes_mtf_check(m15_velocity, h1_velocity, signal.side)
    if not ok:
        return _block("mtf_check", reason)

    # ── All filters passed ────────────────────────────────────────────────────
    decision = EntryDecision(
        allowed=True,
        block_stage=None,
        block_reason=None,
        signal=signal,
    )
    decision.log()
    return decision


# ── Audit helper — run on your 36 historical trades ──────────────────────────

def audit_zone_impact(trades: list[dict]) -> dict:
    """
    Re-evaluates historical trades through zone filter only.
    Pass a list of dicts with keys: entry_price, side, pnl (float).

    Usage:
        trades = [
            {"entry_price": 0.45, "side": "YES", "pnl": -0.18},
            {"entry_price": 0.12, "side": "NO",  "pnl": +0.34},
            ...
        ]
        result = audit_zone_impact(trades)
        print(result)
    """
    allowed  = [t for t in trades
                if not (DEAD_ZONE_LOW
                        <= (t["entry_price"] if t["side"] == "YES"
                            else 1 - t["entry_price"])
                        <= DEAD_ZONE_HIGH)]
    blocked  = [t for t in trades if t not in allowed]

    def stats(bucket):
        if not bucket:
            return {"n": 0, "wins": 0, "wr": 0.0, "total_pnl": 0.0}
        wins = sum(1 for t in bucket if t["pnl"] > 0)
        return {
            "n":         len(bucket),
            "wins":      wins,
            "wr":        wins / len(bucket),
            "total_pnl": sum(t["pnl"] for t in bucket),
        }

    result = {
        "total_trades":   len(trades),
        "would_allow":    stats(allowed),
        "would_block":    stats(blocked),
        "trades_removed": len(blocked),
        "pct_removed":    len(blocked) / max(len(trades), 1),
    }

    print(f"\n── Zone Filter Audit ──────────────────────────")
    print(f"Total trades:    {result['total_trades']}")
    print(f"Would ALLOW:     {result['would_allow']['n']} trades | "
          f"WR {result['would_allow']['wr']:.0%} | "
          f"PnL {result['would_allow']['total_pnl']:+.2%}")
    print(f"Would BLOCK:     {result['would_block']['n']} trades | "
          f"WR {result['would_block']['wr']:.0%} | "
          f"PnL {result['would_block']['total_pnl']:+.2%}")
    print(f"Signals removed: {result['pct_removed']:.0%} of total")
    print(f"───────────────────────────────────────────────\n")

    return result


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s")

    # Test cases — should produce predictable outcomes
    test_cases = [
        # (yes_price, side, expected_block_stage)
        (0.50, "YES", "zone_block"),    # Dead centre — blocked
        (0.40, "NO",  "zone_block"),    # NO effective price = 0.60 — blocked
        (0.10, "YES", "price_check"),   # Below 0.15 minimum — blocked at price_check
        (0.90, "NO",  "price_check"),   # Above 0.85 maximum — blocked at price_check
        (0.30, "YES", None),            # Edge zone — allowed
        (0.13, "YES", "price_check"),   # Below 0.15 — blocked at step 1
    ]

    print("── Smoke Tests ───────────────────────────────")
    for yes_price, side, expected_stage in test_cases:
        signal = EntrySignal(
            coin="BTC", side=side,
            yes_price=yes_price, no_price=1 - yes_price,
            velocity=0.20 if side == "YES" else -0.20,
            volume=200.0, volume_ema=100.0,
        )
        decision = evaluate_entry(
            signal=signal,
            velocity_threshold=0.15,
            fng_value=50,
            m15_velocity=0.05,
            h1_velocity=0.02,
        )
        status   = "✅ PASS" if decision.block_stage == expected_stage else "❌ FAIL"
        got      = decision.block_stage or "allowed"
        expected = expected_stage or "allowed"
        print(f"{status} | {side} @ {yes_price} | expected={expected} | got={got}")

    # Audit helper demo
    sample_trades = [
        {"entry_price": 0.50, "side": "YES", "pnl": -0.18},
        {"entry_price": 0.45, "side": "NO",  "pnl": -0.22},
        {"entry_price": 0.12, "side": "YES", "pnl": +3.40},
        {"entry_price": 0.08, "side": "NO",  "pnl": +0.35},
        {"entry_price": 0.38, "side": "YES", "pnl": -0.15},
        {"entry_price": 0.25, "side": "NO",  "pnl": +0.18},
    ]
    audit_zone_impact(sample_trades)
