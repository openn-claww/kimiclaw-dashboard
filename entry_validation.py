"""
entry_validation.py — OpenClaw Trade Entry Guard
Fixes: invalid market entries at extreme prices (0.015, etc.)
Deploy: import this module and replace calculate_edge() calls.
"""

from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ─── Safe Price Constants ─────────────────────────────────────────────────────

MIN_YES_PRICE   = 0.15   # Below this → market is nearly resolved NO
MAX_YES_PRICE   = 0.85   # Above this → market is nearly resolved YES
MIN_NO_PRICE    = 0.15   # Mirror for NO side - THE BUG FIX
MAX_NO_PRICE    = 0.85   # Mirror for NO side - THE BUG FIX

MIN_LIQUIDITY   = 50.0   # Minimum $ liquidity to enter
MIN_VOLUME_24H  = 100.0  # Minimum 24h volume
MIN_TIME_TO_CLOSE_HOURS = 1.0   # Reject markets closing in < 1 hour

# ─── Regime Params (FIXED — was missing min_price) ───────────────────────────

REGIME_PARAMS = {
    'trending': {
        'velocity_mult': 1.2,
        'min_price': MIN_YES_PRICE,   # ← NEW: was absent
        'max_price': 0.75,            # ← FIXED: was 0.60 but no floor guard
        'max_position_pct': 0.05,
        'label': 'trending',
    },
    'ranging': {
        'velocity_mult': 1.0,
        'min_price': MIN_YES_PRICE,
        'max_price': 0.70,
        'max_position_pct': 0.04,
        'label': 'ranging',
    },
    'volatile': {
        'velocity_mult': 1.5,
        'min_price': 0.20,            # Tighter floor in volatile markets
        'max_price': 0.65,
        'max_position_pct': 0.03,
        'label': 'volatile',
    },
    'default': {
        'velocity_mult': 1.0,
        'min_price': MIN_YES_PRICE,
        'max_price': 0.70,
        'max_position_pct': 0.03,
        'label': 'default',
    },
}

VELOCITY_THRESHOLDS = {
    # coin: {'raw': base_threshold}
    # Fill in your actual coins/markets here
    'BTC':     {'raw': 0.05},
    'ETH':     {'raw': 0.04},
    'DEFAULT': {'raw': 0.03},
}


# ─── 1. Market Status Checker ─────────────────────────────────────────────────

class MarketStatusError(Exception):
    """Raised when a market fails status validation."""

def check_market_status(market: dict) -> tuple[bool, str]:
    """
    Validate market is open, unresolved, and has time remaining.

    Args:
        market: dict with keys: resolved, close_time, question (optional)

    Returns:
        (True, "OK") if safe to trade
        (False, reason) if market should be rejected
    """
    # 1. Already resolved
    if market.get('resolved', False):
        return False, f"Market is resolved (result={market.get('result', 'unknown')})"

    # 2. Closed flag
    if market.get('closed', False):
        return False, "Market is closed"

    # 3. Time check
    close_time = market.get('close_time') or market.get('endDate')
    if close_time:
        if isinstance(close_time, str):
            try:
                close_dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
            except ValueError:
                return False, f"Cannot parse close_time: {close_time}"
        elif isinstance(close_time, (int, float)):
            close_dt = datetime.fromtimestamp(close_time / 1000, tz=timezone.utc)
        else:
            close_dt = close_time

        now = datetime.now(timezone.utc)
        # Make aware if naive
        if close_dt.tzinfo is None:
            close_dt = close_dt.replace(tzinfo=timezone.utc)

        hours_remaining = (close_dt - now).total_seconds() / 3600
        if hours_remaining < 0:
            return False, f"Market already closed {abs(hours_remaining):.1f}h ago"
        if hours_remaining < MIN_TIME_TO_CLOSE_HOURS:
            return False, f"Market closes in {hours_remaining:.2f}h — too soon (min={MIN_TIME_TO_CLOSE_HOURS}h)"

    return True, "OK"


# ─── 2. Pre-Trade Validation ──────────────────────────────────────────────────

def validate_trade(
    market: dict,
    yes_price: float,
    no_price:  float,
    side: str,
    regime_params: dict,
) -> tuple[bool, str]:
    """
    Full pre-trade gate. Call this BEFORE submitting any order.

    Returns:
        (True, "OK") → safe to enter
        (False, reason) → do NOT enter, reason explains why
    """
    reasons = []

    # ── Price sanity ──
    if not (0 < yes_price < 1):
        reasons.append(f"yes_price out of range: {yes_price}")
    if not (0 < no_price < 1):
        reasons.append(f"no_price out of range: {no_price}")

    # ── Global hard floor/ceiling ──
    if yes_price < MIN_YES_PRICE:
        reasons.append(f"yes_price {yes_price:.3f} below hard floor {MIN_YES_PRICE} (market near-resolved NO)")
    if yes_price > MAX_YES_PRICE:
        reasons.append(f"yes_price {yes_price:.3f} above hard ceiling {MAX_YES_PRICE} (market near-resolved YES)")
    
    # ── BUG FIX: Check NO price too ──
    if no_price < MIN_NO_PRICE:
        reasons.append(f"no_price {no_price:.3f} below hard floor {MIN_NO_PRICE} (market near-resolved YES)")
    if no_price > MAX_NO_PRICE:
        reasons.append(f"no_price {no_price:.3f} above hard ceiling {MAX_NO_PRICE} (market near-resolved NO)")

    # ── Regime-specific bounds ──
    regime_min = regime_params.get('min_price', MIN_YES_PRICE)
    regime_max = regime_params.get('max_price', MAX_YES_PRICE)

    if yes_price < regime_min:
        reasons.append(f"yes_price {yes_price:.3f} below regime min {regime_min}")
    if yes_price > regime_max:
        reasons.append(f"yes_price {yes_price:.3f} above regime max {regime_max}")

    # ── Spread check: yes + no should sum near 1.0 ──
    spread = abs(yes_price + no_price - 1.0)
    if spread > 0.15:
        reasons.append(f"Abnormal spread: yes+no={yes_price+no_price:.3f} (expected ~1.0, diff={spread:.3f})")

    # ── Liquidity ──
    liquidity = market.get('liquidity', market.get('pool', 0))
    if isinstance(liquidity, dict):
        liquidity = sum(liquidity.values())
    if liquidity < MIN_LIQUIDITY:
        reasons.append(f"Liquidity ${liquidity:.2f} below minimum ${MIN_LIQUIDITY}")

    # ── Market status ──
    status_ok, status_msg = check_market_status(market)
    if not status_ok:
        reasons.append(status_msg)

    # ── Side-specific price check ──
    if side == 'YES' and yes_price >= MAX_YES_PRICE:
        reasons.append(f"YES side: price {yes_price:.3f} already near ceiling — no upside")
    if side == 'NO' and no_price >= MAX_NO_PRICE:
        reasons.append(f"NO side: price {no_price:.3f} already near ceiling — no upside")

    if reasons:
        full_reason = "; ".join(reasons)
        logger.warning("Trade REJECTED [%s]: %s", market.get('question', market.get('id', '?')), full_reason)
        return False, full_reason

    return True, "OK"


# ─── 3. Fixed calculate_edge() ───────────────────────────────────────────────

def calculate_edge(
    coin: str,
    yes_price: float,
    no_price:  float,
    velocity:  float,
    regime_params: dict,
    market: Optional[dict] = None,
) -> Optional[dict]:
    """
    Fixed version. Returns trade signal dict or None if no valid edge.

    Changes from buggy version:
      - min_price guard (was missing entirely)
      - max_price sourced from regime_params (not hardcoded 0.60)
      - Global hard floor MIN_YES_PRICE enforced first
      - Optional full pre-trade validation when market dict is provided
    """

    # ── Velocity threshold ──
    thresholds = VELOCITY_THRESHOLDS.get(coin, VELOCITY_THRESHOLDS['DEFAULT'])
    threshold  = thresholds['raw'] * regime_params.get('velocity_mult', 1.0)

    # ── Price bounds from regime ──
    min_price = regime_params.get('min_price', MIN_YES_PRICE)
    max_price = regime_params.get('max_price', MAX_YES_PRICE)

    # ── Hard global floor first (catches 0.015 type entries) ──
    if yes_price < MIN_YES_PRICE:
        logger.debug("SKIP %s: yes_price %.3f below hard floor %.2f", coin, yes_price, MIN_YES_PRICE)
        return None

    if yes_price > MAX_YES_PRICE:
        logger.debug("SKIP %s: yes_price %.3f above hard ceiling %.2f", coin, yes_price, MAX_YES_PRICE)
        return None

    # ── Regime bounds ──
    if yes_price < min_price or yes_price > max_price:
        logger.debug("SKIP %s: yes_price %.3f outside regime [%.2f, %.2f]",
                     coin, yes_price, min_price, max_price)
        return None

    # ── Velocity check ──
    if velocity <= threshold:
        return None

    # ── Optional full market validation ──
    if market is not None:
        ok, reason = validate_trade(market, yes_price, no_price, 'YES', regime_params)
        if not ok:
            logger.warning("SKIP %s: %s", coin, reason)
            return None

    # ── Compute edge ──
    # Edge = how far price can move toward 0.75 equilibrium, scaled by velocity
    edge = velocity * (0.75 - yes_price)
    confidence = min(velocity / (threshold * 2), 1.0)   # 0–1 scale

    if edge <= 0:
        return None

    return {
        'side':       'YES',
        'coin':       coin,
        'yes_price':  yes_price,
        'no_price':   no_price,
        'edge':       round(edge, 4),
        'confidence': round(confidence, 3),
        'velocity':   round(velocity, 4),
        'threshold':  round(threshold, 4),
        'regime':     regime_params.get('label', 'unknown'),
        'max_position_pct': regime_params.get('max_position_pct', 0.03),
    }


# ─── 4. Safe Entry Orchestrator ───────────────────────────────────────────────

def safe_enter_trade(
    coin: str,
    market: dict,
    yes_price: float,
    no_price:  float,
    velocity:  float,
    regime: str,
    portfolio_value: float,
    execute_fn,            # callable(coin, side, size_usd) → order result
) -> Optional[dict]:
    """
    Full safe entry pipeline:
      1. Get regime params
      2. calculate_edge (price + velocity filters)
      3. validate_trade (market status, liquidity, spread)
      4. Size position
      5. Execute

    Args:
        execute_fn: your actual order placement function
    Returns:
        Order result dict, or None if trade was skipped
    """
    regime_params = REGIME_PARAMS.get(regime, REGIME_PARAMS['default'])

    # Step 1: Edge check
    signal = calculate_edge(coin, yes_price, no_price, velocity, regime_params, market)
    if signal is None:
        return None

    # Step 2: Full validation (redundant but belt-and-suspenders)
    ok, reason = validate_trade(market, yes_price, no_price, signal['side'], regime_params)
    if not ok:
        logger.warning("safe_enter_trade blocked: %s", reason)
        return None

    # Step 3: Position sizing (risk-capped)
    max_pct  = regime_params['max_position_pct']
    raw_size = portfolio_value * max_pct * signal['confidence']
    size_usd = round(min(raw_size, portfolio_value * 0.05), 2)  # hard cap 5%

    if size_usd < 1.0:
        logger.info("Position size $%.2f too small, skipping", size_usd)
        return None

    logger.info(
        "ENTER %s %s @ %.3f | edge=%.4f | size=$%.2f | regime=%s",
        signal['side'], coin, yes_price, signal['edge'], size_usd, regime
    )

    return execute_fn(coin, signal['side'], size_usd)


# ─── 5. Quick smoke test ──────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')

    good_market = {
        'question':   'Will BTC close above 70k this week?',
        'resolved':   False,
        'close_time': '2099-12-31T00:00:00Z',
        'liquidity':  500,
    }
    bad_market_resolved = {
        'question':   'Did ETH hit $1k in 2020?',
        'resolved':   True,
        'close_time': '2020-01-01T00:00:00Z',
        'liquidity':  10,
    }

    tests = [
        # (label,             market,              yes,   no,    velocity)
        ("GOOD entry",        good_market,         0.45,  0.55,  0.08),
        ("BAD: price 0.015",  good_market,         0.015, 0.985, 0.50),  # ← the bug
        ("BAD: price 0.90",   good_market,         0.90,  0.10,  0.50),
        ("BAD: resolved",     bad_market_resolved, 0.45,  0.55,  0.50),
        ("BAD: low velocity", good_market,         0.45,  0.55,  0.001),
    ]

    regime_params = REGIME_PARAMS['default']

    print("\n=== calculate_edge() tests ===")
    for label, mkt, yp, np_, vel in tests:
        result = calculate_edge('BTC', yp, np_, vel, regime_params, mkt)
        status = f"SIGNAL edge={result['edge']}" if result else "BLOCKED"
        print(f"  {label:30s} → {status}")
