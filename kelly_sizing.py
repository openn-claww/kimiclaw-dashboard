"""
kelly_sizing.py
Kelly Criterion Position Sizing for Polymarket Binary Markets

FORMULA:
  Kelly fraction = (p * b - q) / b
  Where:
    p = true win probability
    q = 1 - p (loss probability)
    b = net odds (profit per $1 risked)
      YES at price P: b = (1 - P) / P  (e.g., P=0.025 → b=39)
      NO  at price P: b = P / (1 - P)

USAGE:
  from kelly_sizing import kelly_position_size, KellySizer

  # Simple function call
  dollars = kelly_position_size(bankroll=500, entry_price=0.025,
                                 estimated_edge_pct=0.03, side='YES')

  # Full sizer with logging
  sizer = KellySizer(bankroll=500)
  rec = sizer.recommend(entry_price=0.40, estimated_edge_pct=0.03)
  print(rec)
"""

from dataclasses import dataclass
from typing import Optional


# ─── CONFIG ──────────────────────────────────────────────────────────────────

POLYMARKET_FEE = 0.02       # Fee reduces effective net odds
MAX_STAKE_PCT  = 0.05       # Hard cap: never risk more than 5% of bankroll
MIN_STAKE      = 1.00       # Minimum trade size in dollars
KELLY_FRACTION = 0.5        # Use half-Kelly by default (reduces variance significantly)


# ─── CORE KELLY FUNCTIONS ────────────────────────────────────────────────────

def net_odds(entry_price: float, side: str) -> float:
    """
    Net odds = profit per $1 staked if you win (before fee).
    After fee, effective odds are slightly lower.

    YES at 0.025: win $39 for every $1 staked (gross), net $38.22 after 2% fee
    NO  at 0.025: win $0.0256 for every $1 staked — terrible bet
    """
    if side == 'YES':
        gross_odds = (1 - entry_price) / entry_price
    else:  # NO
        gross_odds = entry_price / (1 - entry_price)

    # Reduce odds by fee (fee is charged on winnings)
    effective_odds = gross_odds * (1 - POLYMARKET_FEE)
    return effective_odds


def full_kelly(p_win: float, odds: float) -> float:
    """
    Full Kelly fraction of bankroll to bet.

    Returns a value in [0, 1]. Negative means no edge (don't bet).
    Never bet negative Kelly — it means the market has better info than you.
    """
    q = 1 - p_win
    kelly = (p_win * odds - q) / odds
    return max(kelly, 0.0)


def half_kelly(p_win: float, odds: float) -> float:
    """
    Half-Kelly: half the full Kelly fraction.

    Gives up ~25% of expected growth rate but cuts variance by ~75%.
    Strongly recommended for real trading — full Kelly leads to brutal drawdowns.
    """
    return full_kelly(p_win, odds) * KELLY_FRACTION


# ─── POSITION SIZE CALCULATOR ────────────────────────────────────────────────

def kelly_position_size(
    bankroll:          float,
    entry_price:       float,
    estimated_edge_pct: float,
    side:              str  = 'YES',
    use_half_kelly:    bool = True,
    max_pct:           float = MAX_STAKE_PCT,
    min_dollars:       float = MIN_STAKE,
) -> float:
    """
    Returns the dollar amount to stake on this trade.

    Args:
        bankroll:           Current account balance
        entry_price:        Market price (0.0 to 1.0)
        estimated_edge_pct: Your estimated edge over market (e.g., 0.03 = 3%)
        side:               'YES' or 'NO'
        use_half_kelly:     If True, use 50% of full Kelly (recommended)
        max_pct:            Hard cap as fraction of bankroll
        min_dollars:        Minimum trade size (return 0 if below this)

    Returns:
        Dollar amount to stake (0.0 if no positive edge)
    """
    # Input validation
    if not (0.0 < entry_price < 1.0):
        raise ValueError(f"entry_price must be between 0 and 1, got {entry_price}")
    if estimated_edge_pct < 0:
        return 0.0  # No edge, don't bet
    if bankroll <= 0:
        return 0.0

    # True win probability = market price + your edge
    if side == 'YES':
        p_win = min(entry_price + estimated_edge_pct, 0.99)
    else:  # NO
        p_win = min((1 - entry_price) + estimated_edge_pct, 0.99)

    odds = net_odds(entry_price, side)

    # Calculate Kelly fraction
    if use_half_kelly:
        fraction = half_kelly(p_win, odds)
    else:
        fraction = full_kelly(p_win, odds)

    # Apply hard cap
    fraction = min(fraction, max_pct)

    # Convert to dollars
    stake = bankroll * fraction

    # Enforce minimum
    if stake < min_dollars:
        return 0.0

    return round(stake, 2)


# ─── DATACLASS FOR FULL RECOMMENDATION ──────────────────────────────────────

@dataclass
class SizingRecommendation:
    entry_price:       float
    side:              str
    estimated_edge:    float
    true_prob:         float
    net_odds:          float
    full_kelly_pct:    float
    half_kelly_pct:    float
    recommended_pct:   float     # After caps
    recommended_dollars: float
    bankroll:          float
    notes:             str = ""

    def __str__(self):
        lines = [
            f"─── Kelly Sizing Recommendation ──────────────",
            f"  Entry Price:      {self.entry_price:.4f} ({self.side})",
            f"  Estimated Edge:   {self.estimated_edge:+.2%}",
            f"  True Prob:        {self.true_prob:.2%}",
            f"  Net Odds:         {self.net_odds:.2f}x",
            f"  Full Kelly:       {self.full_kelly_pct:.2%} of bankroll",
            f"  Half Kelly:       {self.half_kelly_pct:.2%} of bankroll",
            f"  → Recommended:    {self.recommended_pct:.2%}  (${self.recommended_dollars:.2f})",
            f"  Bankroll:         ${self.bankroll:.2f}",
        ]
        if self.notes:
            lines.append(f"  ⚠ Note: {self.notes}")
        lines.append(f"──────────────────────────────────────────────")
        return "\n".join(lines)


# ─── KELLY SIZER CLASS ───────────────────────────────────────────────────────

class KellySizer:
    """
    Stateful Kelly sizer. Tracks bankroll and provides recommendations.

    Usage:
        sizer = KellySizer(bankroll=500.0)
        rec = sizer.recommend(entry_price=0.40, estimated_edge_pct=0.03)
        print(rec)
        sizer.update_bankroll(new_balance=512.50)
    """

    def __init__(
        self,
        bankroll:    float,
        kelly_frac:  float = KELLY_FRACTION,
        max_pct:     float = MAX_STAKE_PCT,
        min_dollars: float = MIN_STAKE,
    ):
        self.bankroll    = bankroll
        self.kelly_frac  = kelly_frac
        self.max_pct     = max_pct
        self.min_dollars = min_dollars

    def update_bankroll(self, new_balance: float):
        self.bankroll = new_balance

    def recommend(
        self,
        entry_price:        float,
        estimated_edge_pct: float,
        side:               str  = 'YES',
    ) -> SizingRecommendation:
        """Full recommendation with diagnostics."""
        notes = []

        if side == 'YES':
            p_win = min(entry_price + estimated_edge_pct, 0.99)
        else:
            p_win = min((1 - entry_price) + estimated_edge_pct, 0.99)

        odds        = net_odds(entry_price, side)
        fk          = full_kelly(p_win, odds)
        hk          = fk * self.kelly_frac
        rec_pct     = min(hk, self.max_pct)

        if fk == 0.0:
            notes.append("No edge detected — Kelly is 0, skipping trade")
            rec_pct = 0.0
        elif fk > self.max_pct * 2:
            notes.append(f"Kelly ({fk:.1%}) far exceeds cap ({self.max_pct:.0%}) — verify edge estimate")
        if entry_price < 0.05 or entry_price > 0.95:
            notes.append("Extreme price — edge estimate uncertainty is high")

        stake = round(self.bankroll * rec_pct, 2)
        if stake < self.min_dollars:
            stake = 0.0
            rec_pct = 0.0
            notes.append(f"Stake below minimum (${self.min_dollars}) — skipping")

        return SizingRecommendation(
            entry_price=entry_price,
            side=side,
            estimated_edge=estimated_edge_pct,
            true_prob=p_win,
            net_odds=odds,
            full_kelly_pct=fk,
            half_kelly_pct=hk,
            recommended_pct=rec_pct,
            recommended_dollars=stake,
            bankroll=self.bankroll,
            notes="; ".join(notes),
        )

    def size_table(self, estimated_edge_pct: float = 0.03):
        """Print a sizing table for various prices at a given edge."""
        print(f"\nSizing Table | Bankroll=${self.bankroll:.0f} | Edge={estimated_edge_pct:.0%} | Half-Kelly capped at {self.max_pct:.0%}")
        print(f"{'Price':>7}  {'Side':>4}  {'TrueP':>6}  {'Odds':>6}  {'FullK':>6}  {'HalfK':>6}  {'Stake$':>7}")
        print(f"{'─'*7}  {'─'*4}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*7}")

        prices = [0.025, 0.05, 0.10, 0.15, 0.25, 0.35, 0.50, 0.65, 0.75, 0.85]
        for price in prices:
            for side in ['YES', 'NO']:
                rec = self.recommend(price, estimated_edge_pct, side)
                print(f"  {price:>5.3f}  {side:>4}  {rec.true_prob:>5.1%}  "
                      f"{rec.net_odds:>5.2f}x  {rec.full_kelly_pct:>5.2%}  "
                      f"{rec.half_kelly_pct:>5.2%}  ${rec.recommended_dollars:>6.2f}")


# ─── MAIN / EXAMPLES ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Kelly Criterion Position Sizing — Polymarket")
    print("=" * 60)

    sizer = KellySizer(bankroll=500.0)

    # Example 1: Your ETH moonshot trade
    print("\n[Example 1] ETH moonshot — Entry 0.025 YES, 3% edge")
    rec = sizer.recommend(entry_price=0.025, estimated_edge_pct=0.03, side='YES')
    print(rec)

    # Example 2: Moderate edge, center price
    print("\n[Example 2] Standard trade — Entry 0.40 YES, 3% edge")
    rec = sizer.recommend(entry_price=0.40, estimated_edge_pct=0.03, side='YES')
    print(rec)

    # Example 3: High edge, edge zone
    print("\n[Example 3] High confidence — Entry 0.20 YES, 8% edge")
    rec = sizer.recommend(entry_price=0.20, estimated_edge_pct=0.08, side='YES')
    print(rec)

    # Example 4: No edge (should return 0)
    print("\n[Example 4] No edge — should return $0")
    rec = sizer.recommend(entry_price=0.50, estimated_edge_pct=0.0, side='YES')
    print(rec)

    # Sizing table
    sizer.size_table(estimated_edge_pct=0.03)

    # Quick function reference
    print("\n" + "=" * 60)
    print("  Quick Function Reference")
    print("=" * 60)
    size = kelly_position_size(
        bankroll=500,
        entry_price=0.025,
        estimated_edge_pct=0.03,
        side='YES'
    )
    print(f"  kelly_position_size(500, 0.025, 0.03, 'YES') = ${size:.2f}")
    size2 = kelly_position_size(500, 0.40, 0.03, 'YES')
    print(f"  kelly_position_size(500, 0.40,  0.03, 'YES') = ${size2:.2f}")
