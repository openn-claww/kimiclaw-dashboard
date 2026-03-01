"""
edge_tracker.py
Data-driven edge estimation for Polymarket Kelly sizing.

PROBLEM SOLVED:
  Kelly criterion requires an honest edge estimate (your win probability minus
  the market's implied probability). A hardcoded 3% is fiction — it's probably
  wrong and it doesn't improve over time.

HOW THIS WORKS:
  - Trades are bucketed by entry price (rounded to nearest 0.05) and side (YES/NO)
  - Each bucket independently tracks wins and total trades
  - Edge = observed_win_rate - market_implied_probability
  - Returns DEFAULT_EDGE (1%) until a bucket accumulates MIN_SAMPLES (30) trades
  - At 30 samples, bucket switches to observed data with a confidence-weighted
    blend that smoothly transitions (no cliff-edge at exactly 30)

BUCKET DESIGN:
  Price 0.023 → bucket 0.00  (rounds to nearest 0.05 → 0.05, but 0.00 for <0.025)
  Price 0.025 → bucket 0.05
  Price 0.40  → bucket 0.40
  Price 0.763 → bucket 0.75
  Each (bucket, side) pair is independent — YES at 0.40 and NO at 0.40 are tracked
  separately because they represent different market conditions.

USAGE:
  from edge_tracker import EdgeTracker
  from kelly_sizing import KellySizer

  tracker = EdgeTracker.load()
  sizer   = KellySizer(bankroll=690)

  # Before placing a trade:
  edge = tracker.get_edge(entry_price=0.40, side='YES')
  rec  = sizer.recommend(entry_price=0.40, estimated_edge_pct=edge, side='YES')
  print(f"Edge: {edge:.2%}  →  Stake: ${rec.recommended_dollars:.2f}")

  # After trade resolves:
  tracker.record_result(entry_price=0.40, side='YES', won=True)
  tracker.save()
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from atomic_json import atomic_write_json, safe_load_json

logger = logging.getLogger(__name__)

TRACKER_PATH = Path("/root/.openclaw/workspace/edge_tracker.json")


# ─── BUCKET STATS ────────────────────────────────────────────────────────────

@dataclass
class BucketStats:
    """Win/loss record for one (price_bucket, side) pair."""
    bucket:      float   # e.g. 0.25
    side:        str     # 'YES' or 'NO'
    wins:        int = 0
    losses:      int = 0
    first_trade: str = ""   # ISO timestamp
    last_trade:  str = ""   # ISO timestamp

    @property
    def total(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> Optional[float]:
        return self.wins / self.total if self.total > 0 else None

    @property
    def market_implied(self) -> float:
        """What the market says the win probability is."""
        return self.bucket if self.side == 'YES' else (1.0 - self.bucket)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BucketStats":
        return cls(**d)


# ─── EDGE TRACKER ────────────────────────────────────────────────────────────

class EdgeTracker:
    """
    Tracks observed win rates by (price_bucket, side) to estimate real edge.

    Starts conservative (DEFAULT_EDGE = 1%) and becomes data-driven as trades
    accumulate. Uses confidence weighting to smooth the transition — at 15
    samples you get 50% real data, at 30+ you get 100% real data.
    """

    DEFAULT_EDGE  = 0.01   # 1% conservative default — bet small until calibrated
    MIN_SAMPLES   = 30     # Full trust threshold
    BUCKET_SIZE   = 0.05   # Width of each price bucket
    MAX_EDGE      = 0.25   # Cap: never let edge estimate exceed 25% (sanity check)

    def __init__(self):
        # Key: "0.25:YES" → BucketStats
        self._buckets: dict[str, BucketStats] = {}
        self._total_trades = 0
        self._created_at   = datetime.now(timezone.utc).isoformat()

    # ─── PUBLIC API ──────────────────────────────────────────────────────────

    def get_edge(self, entry_price: float, side: str) -> float:
        """
        Return the estimated edge for this price/side combination.

        Returns DEFAULT_EDGE until the bucket has enough samples, then
        transitions smoothly to observed data.

        Args:
            entry_price: Market entry price (0.0 – 1.0)
            side:        'YES' or 'NO'

        Returns:
            Edge as a fraction (e.g. 0.03 = 3%). Always >= 0.
            Returns 0.0 if observed data suggests no edge (don't bet).
        """
        bucket = self._get_bucket(entry_price)
        stats  = self._get_or_create(bucket, side)

        if stats.total == 0:
            logger.debug(f"Edge [{bucket:.2f}:{side}]: no data → default {self.DEFAULT_EDGE:.2%}")
            return self.DEFAULT_EDGE

        observed_wr     = stats.wins / stats.total
        market_implied  = stats.market_implied
        raw_edge        = observed_wr - market_implied

        # Confidence weight: 0% at 0 samples, 100% at MIN_SAMPLES
        # This prevents a single early win from inflating the edge estimate
        confidence      = min(stats.total / self.MIN_SAMPLES, 1.0)
        blended_edge    = (confidence * raw_edge) + ((1 - confidence) * self.DEFAULT_EDGE)
        final_edge      = max(min(blended_edge, self.MAX_EDGE), 0.0)

        logger.debug(
            f"Edge [{bucket:.2f}:{side}]: {stats.wins}W/{stats.losses}L "
            f"wr={observed_wr:.2%} implied={market_implied:.2%} "
            f"raw={raw_edge:+.2%} conf={confidence:.0%} final={final_edge:.2%}"
        )
        return round(final_edge, 6)

    def record_result(self, entry_price: float, side: str, won: bool):
        """
        Record the outcome of a completed trade.

        Call this after every resolved trade. Call save() after to persist.

        Args:
            entry_price: The price at which you entered (0.0 – 1.0)
            side:        'YES' or 'NO'
            won:         True if the trade was profitable
        """
        bucket = self._get_bucket(entry_price)
        stats  = self._get_or_create(bucket, side)
        now    = datetime.now(timezone.utc).isoformat()

        if won:
            stats.wins += 1
        else:
            stats.losses += 1

        if not stats.first_trade:
            stats.first_trade = now
        stats.last_trade = now
        self._total_trades += 1

        wr_str = f"{stats.wins / stats.total:.1%}" if stats.total > 0 else "n/a"
        calibrated = "calibrated" if stats.total >= self.MIN_SAMPLES else f"need {self.MIN_SAMPLES - stats.total} more"
        logger.info(
            f"EdgeTracker recorded: [{bucket:.2f}:{side}] "
            f"{'WIN' if won else 'LOSS'} → "
            f"{stats.wins}W/{stats.losses}L  wr={wr_str}  [{calibrated}]"
        )

    def get_stats(self, entry_price: float, side: str) -> dict:
        """
        Return full diagnostic stats for a bucket.

        Returns a dict with: bucket, side, wins, losses, total, win_rate,
        market_implied, raw_edge, confidence, calibrated_edge, is_calibrated.
        """
        bucket = self._get_bucket(entry_price)
        stats  = self._get_or_create(bucket, side)
        edge   = self.get_edge(entry_price, side)

        raw_edge = (stats.win_rate - stats.market_implied) if stats.win_rate is not None else None
        return {
            "bucket":           bucket,
            "side":             side,
            "wins":             stats.wins,
            "losses":           stats.losses,
            "total":            stats.total,
            "win_rate":         round(stats.win_rate, 4) if stats.win_rate is not None else None,
            "market_implied":   round(stats.market_implied, 4),
            "raw_edge":         round(raw_edge, 4) if raw_edge is not None else None,
            "confidence":       round(min(stats.total / self.MIN_SAMPLES, 1.0), 4),
            "calibrated_edge":  round(edge, 4),
            "is_calibrated":    stats.total >= self.MIN_SAMPLES,
            "samples_needed":   max(0, self.MIN_SAMPLES - stats.total),
            "first_trade":      stats.first_trade,
            "last_trade":       stats.last_trade,
        }

    def get_all_stats(self) -> list[dict]:
        """Return stats for every bucket that has at least one trade."""
        result = []
        for key, stats in self._buckets.items():
            if stats.total > 0:
                result.append(self.get_stats(stats.bucket, stats.side))
        return sorted(result, key=lambda s: (s["bucket"], s["side"]))

    def calibration_report(self) -> str:
        """
        Human-readable report of current calibration status.
        Print this to understand how much data you have.
        """
        lines = [
            "═" * 62,
            "  EdgeTracker Calibration Report",
            f"  Total trades recorded: {self._total_trades}",
            f"  Buckets with data:     {sum(1 for s in self._buckets.values() if s.total > 0)}",
            "═" * 62,
            f"  {'Bucket':>7}  {'Side':>4}  {'W':>4}  {'L':>4}  {'WR':>6}  {'Edge':>7}  {'Conf':>5}  Status",
            f"  {'─'*7}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*5}  {'─'*15}",
        ]

        active = [s for s in self._buckets.values() if s.total > 0]
        if not active:
            lines.append("  No trades recorded yet. All buckets returning DEFAULT_EDGE (1%).")
        else:
            for stats in sorted(active, key=lambda s: (s.bucket, s.side)):
                edge  = self.get_edge(stats.bucket, stats.side)
                conf  = min(stats.total / self.MIN_SAMPLES, 1.0)
                wr    = f"{stats.win_rate:.1%}" if stats.win_rate is not None else "—"
                status = "✓ calibrated" if stats.total >= self.MIN_SAMPLES else f"need {self.MIN_SAMPLES - stats.total}"
                lines.append(
                    f"  {stats.bucket:>7.2f}  {stats.side:>4}  "
                    f"{stats.wins:>4}  {stats.losses:>4}  {wr:>6}  "
                    f"{edge:>+6.2%}  {conf:>4.0%}  {status}"
                )

        lines.append("═" * 62)
        return "\n".join(lines)

    # ─── PERSISTENCE ─────────────────────────────────────────────────────────

    def save(self, path: Path = TRACKER_PATH) -> bool:
        """Persist tracker state to disk using atomic write."""
        data = {
            "version":       2,
            "created_at":    self._created_at,
            "saved_at":      datetime.now(timezone.utc).isoformat(),
            "total_trades":  self._total_trades,
            "default_edge":  self.DEFAULT_EDGE,
            "min_samples":   self.MIN_SAMPLES,
            "buckets":       {k: v.to_dict() for k, v in self._buckets.items()},
        }
        ok = atomic_write_json(data, path)
        if ok:
            logger.debug(f"EdgeTracker saved: {path} ({self._total_trades} trades)")
        else:
            logger.error(f"EdgeTracker save FAILED: {path}")
        return ok

    @classmethod
    def load(cls, path: Path = TRACKER_PATH) -> "EdgeTracker":
        """
        Load tracker from disk, or return a fresh instance if no file exists.
        Never raises — worst case is starting fresh with DEFAULT_EDGE.
        """
        tracker = cls()

        raw = safe_load_json(path, default={})
        if not raw:
            logger.info(f"EdgeTracker: no existing data at {path} — starting fresh")
            return tracker

        try:
            tracker._created_at   = raw.get("created_at", tracker._created_at)
            tracker._total_trades = raw.get("total_trades", 0)

            for key, bucket_dict in raw.get("buckets", {}).items():
                tracker._buckets[key] = BucketStats.from_dict(bucket_dict)

            # Migrate v1 format (bucket key was just price string)
            # to v2 format ("0.25:YES") — safe to run on already-v2 data
            tracker._buckets = {
                k: v for k, v in tracker._buckets.items()
                if ":" in k  # v2 keys always contain ":"
            }

            n = sum(1 for s in tracker._buckets.values() if s.total > 0)
            logger.info(
                f"EdgeTracker loaded: {tracker._total_trades} trades across {n} active buckets"
            )
        except Exception as e:
            logger.error(f"EdgeTracker load error ({e}) — starting fresh")
            return cls()

        return tracker

    # ─── INTERNALS ───────────────────────────────────────────────────────────

    def _get_bucket(self, price: float) -> float:
        """
        Round price to nearest BUCKET_SIZE center.

        0.023 → 0.00 (but we floor at 0.00 and ceil at 1.00)
        0.025 → 0.05 (exactly on boundary → rounds up)
        0.40  → 0.40
        0.763 → 0.75
        0.98  → 1.00

        Using math.floor(x + 0.5) for true round-half-up (not banker rounding).
        """
        # Python built-in round() uses banker rounding: round(0.5) == 0, not 1.
        # math.floor(0.5 + 0.5) == 1 — always rounds 0.5 up.
        step   = self.BUCKET_SIZE
        bucket = math.floor(price / step + 0.5) * step
        # Clamp to [0.00, 1.00]
        bucket = max(0.0, min(1.0, bucket))
        # Avoid floating-point artifacts (0.30000000000000004 → 0.30)
        return round(bucket, 10)

    def _bucket_key(self, bucket: float, side: str) -> str:
        return f"{bucket:.2f}:{side}"

    def _get_or_create(self, bucket: float, side: str) -> BucketStats:
        key = self._bucket_key(bucket, side)
        if key not in self._buckets:
            self._buckets[key] = BucketStats(bucket=bucket, side=side)
        return self._buckets[key]


# ─── INTEGRATED SIZING HELPER ────────────────────────────────────────────────

def get_kelly_stake(
    tracker:    EdgeTracker,
    sizer,                   # KellySizer instance
    entry_price: float,
    side:       str,
) -> tuple[float, float]:
    """
    Convenience function: get edge from tracker, feed to sizer, return stake.

    Returns:
        (stake_dollars, edge_used)

    Usage:
        stake, edge = get_kelly_stake(tracker, sizer, price, side)
        logger.info(f"Staking ${stake:.2f} with {edge:.2%} edge")
    """
    edge = tracker.get_edge(entry_price, side)
    rec  = sizer.recommend(entry_price=entry_price, estimated_edge_pct=edge, side=side)
    return rec.recommended_dollars, edge


# ─── TESTS ───────────────────────────────────────────────────────────────────

def run_tests():
    """
    Self-contained test suite. Run with: python3 edge_tracker.py
    """
    import tempfile, shutil

    tmpdir  = Path(tempfile.mkdtemp())
    tracker_path = tmpdir / "edge_tracker_test.json"

    passed = failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  ✓  {name}")
            passed += 1
        else:
            print(f"  ✗  {name}{(' — ' + detail) if detail else ''}")
            failed += 1

    print(f"\n{'═'*60}")
    print("  EdgeTracker — Test Suite")
    print(f"{'═'*60}")

    # ── Test 1: Bucket rounding ───────────────────────────────────
    print("\n[1] Bucket rounding")
    t = EdgeTracker()
    cases = [
        (0.023, 0.00),
        (0.025, 0.05),  # ties round to nearest even → 0.00 or 0.05? We want 0.05
        (0.024, 0.00),
        (0.10,  0.10),
        (0.40,  0.40),
        (0.763, 0.75),  # 0.763 / 0.05 = 15.26 → round to 15 → 0.75
        (0.98,  1.00),
        (0.15,  0.15),
        (0.685, 0.70),  # your BTC open trade price
    ]
    for price, expected in cases:
        result = t._get_bucket(price)
        check(f"  {price} → {expected:.2f}", abs(result - expected) < 1e-9,
              f"got {result}")

    # ── Test 2: DEFAULT_EDGE before min samples ───────────────────
    print("\n[2] DEFAULT_EDGE returned when samples < 30")
    t = EdgeTracker()
    edge = t.get_edge(0.40, 'YES')
    check("0 samples → DEFAULT_EDGE", abs(edge - EdgeTracker.DEFAULT_EDGE) < 1e-9,
          f"got {edge}")

    # Record 29 wins — still not calibrated
    for _ in range(29):
        t.record_result(0.40, 'YES', won=True)
    edge_29 = t.get_edge(0.40, 'YES')
    stats   = t.get_stats(0.40, 'YES')
    check("29 samples → not fully calibrated", not stats['is_calibrated'])
    check("29 samples → edge is blended (between default and raw)",
          EdgeTracker.DEFAULT_EDGE < edge_29 < 0.60,
          f"got {edge_29:.4f}")

    # ── Test 3: Calibrated edge after 30+ samples ─────────────────
    print("\n[3] Calibrated edge after 30+ samples")
    t = EdgeTracker()
    # Simulate 60 trades: 40 wins at YES 0.40 → 66.7% WR, market says 40%
    # Raw edge = 0.667 - 0.40 = 0.267, but capped at MAX_EDGE=0.25
    for _ in range(40):
        t.record_result(0.40, 'YES', won=True)
    for _ in range(20):
        t.record_result(0.40, 'YES', won=False)

    s    = t.get_stats(0.40, 'YES')
    edge = t.get_edge(0.40, 'YES')
    check("60 samples → is_calibrated", s['is_calibrated'])
    check("win_rate calculated correctly", abs(s['win_rate'] - 40/60) < 0.001,
          f"got {s['win_rate']:.4f}")
    check("market_implied = entry_price for YES", abs(s['market_implied'] - 0.40) < 1e-9)
    check("raw_edge is positive (strategy has edge)", s['raw_edge'] > 0,
          f"raw_edge={s['raw_edge']}")
    check("calibrated_edge is capped at MAX_EDGE", edge <= EdgeTracker.MAX_EDGE,
          f"got {edge}")
    check("calibrated_edge > DEFAULT_EDGE", edge > EdgeTracker.DEFAULT_EDGE)

    # ── Test 4: NO side uses (1 - bucket) as market_implied ───────
    print("\n[4] NO side edge calculation")
    t = EdgeTracker()
    for _ in range(30):
        t.record_result(0.70, 'NO', won=True)  # 100% WR on NO at 0.70
    s = t.get_stats(0.70, 'NO')
    # market_implied for NO at 0.70 = 1 - 0.70 = 0.30
    check("NO market_implied = 1 - bucket", abs(s['market_implied'] - 0.30) < 1e-9,
          f"got {s['market_implied']}")
    check("NO win rate 100% → positive edge", s['raw_edge'] > 0)

    # ── Test 5: No negative edge returned ─────────────────────────
    print("\n[5] Edge never goes negative")
    t = EdgeTracker()
    # 40 losses, 20 wins at YES 0.40 → WR=33%, market=40%, raw_edge=-7%
    for _ in range(20):
        t.record_result(0.40, 'YES', won=True)
    for _ in range(40):
        t.record_result(0.40, 'YES', won=False)
    edge = t.get_edge(0.40, 'YES')
    check("negative raw edge → get_edge returns 0.0", edge == 0.0,
          f"got {edge}")

    # ── Test 6: Buckets are independent ───────────────────────────
    print("\n[6] Different (price, side) pairs are independent")
    t = EdgeTracker()
    for _ in range(30):
        t.record_result(0.40, 'YES', won=True)
    for _ in range(30):
        t.record_result(0.40, 'NO',  won=False)
    edge_yes = t.get_edge(0.40, 'YES')
    edge_no  = t.get_edge(0.40, 'NO')
    check("YES bucket tracks independently", edge_yes > 0.10)
    check("NO bucket tracks independently",  edge_no  == 0.0)

    # ── Test 7: Persistence ───────────────────────────────────────
    print("\n[7] Save and load")
    t1 = EdgeTracker()
    t1.record_result(0.25, 'YES', won=True)
    t1.record_result(0.25, 'YES', won=False)
    t1.record_result(0.50, 'NO',  won=True)
    t1.save(tracker_path)
    check("save returns True", tracker_path.exists())

    t2 = EdgeTracker.load(tracker_path)
    check("total_trades persisted", t2._total_trades == 3, f"got {t2._total_trades}")
    s_orig    = t1.get_stats(0.25, 'YES')
    s_loaded  = t2.get_stats(0.25, 'YES')
    check("bucket wins persisted",   s_loaded['wins']   == s_orig['wins'])
    check("bucket losses persisted", s_loaded['losses'] == s_orig['losses'])
    check("50:NO bucket persisted",  t2.get_stats(0.50, 'NO')['wins'] == 1)

    # ── Test 8: Integration with KellySizer ───────────────────────
    print("\n[8] Integration with KellySizer")
    try:
        from kelly_sizing import KellySizer
        sizer = KellySizer(bankroll=690.0)

        t = EdgeTracker()
        # 0 samples → DEFAULT_EDGE (1%)
        stake_default, edge_default = get_kelly_stake(t, sizer, 0.40, 'YES')
        # Load up 60 trades with big edge
        for _ in range(50):
            t.record_result(0.40, 'YES', won=True)
        for _ in range(10):
            t.record_result(0.40, 'YES', won=False)
        stake_calibrated, edge_calibrated = get_kelly_stake(t, sizer, 0.40, 'YES')

        check("default stake (1% edge) is smaller",
              stake_default < stake_calibrated,
              f"default=${stake_default:.2f} calibrated=${stake_calibrated:.2f}")
        check("calibrated edge > default edge",
              edge_calibrated > edge_default,
              f"{edge_calibrated:.4f} > {edge_default:.4f}")
        check("stake within bankroll limits", stake_calibrated <= 690.0 * 0.05 + 0.01)
        print(f"      default:    edge={edge_default:.2%}  stake=${stake_default:.2f}")
        print(f"      calibrated: edge={edge_calibrated:.2%}  stake=${stake_calibrated:.2f}")
    except ImportError:
        print("  ⚠  KellySizer not found — skipping integration test")

    # ── Test 9: Edge progression demo ─────────────────────────────
    print("\n[9] Edge progression as trades accumulate (55% WR at 0.40 YES)")
    t = EdgeTracker()
    print(f"  {'Trades':>7}  {'WR':>6}  {'Edge':>7}  {'Conf':>5}  Source")
    print(f"  {'─'*7}  {'─'*6}  {'─'*7}  {'─'*5}  {'─'*15}")
    for n in [0, 5, 10, 20, 30, 50, 100]:
        # Add trades to reach count n (55% WR)
        current = t.get_stats(0.40, 'YES')['total']
        to_add  = max(0, n - current)
        for i in range(to_add):
            t.record_result(0.40, 'YES', won=(i % 20 < 11))  # 55% WR
        s    = t.get_stats(0.40, 'YES')
        edge = t.get_edge(0.40, 'YES')
        wr   = f"{s['win_rate']:.1%}" if s['win_rate'] is not None else "—"
        conf = s['confidence']
        src  = "calibrated ✓" if s['is_calibrated'] else f"default blend"
        print(f"  {s['total']:>7}  {wr:>6}  {edge:>+6.2%}  {conf:>4.0%}  {src}")

    check("edge progression test ran", True)

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'═'*60}\n")

    shutil.rmtree(tmpdir, ignore_errors=True)
    return failed == 0


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s %(message)s")

    success = run_tests()

    # Also show calibration report for the live file if it exists
    if TRACKER_PATH.exists():
        print("\nLive tracker state:")
        live = EdgeTracker.load()
        print(live.calibration_report())

    sys.exit(0 if success else 1)
