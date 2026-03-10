"""
═══════════════════════════════════════════════════════════════════════════════
CALIBRATED KELLY SIZING SYSTEM v1.0
Replaces hardcoded edge=0.03 with empirically calibrated win rates per price bucket.
═══════════════════════════════════════════════════════════════════════════════

DESIGN ANSWERS (see full rationale in INTEGRATION_GUIDE.md):
  Buckets:        7 buckets (symmetric + dead zone split for clarity)
  Symmetry:       YES — buckets mirror around 0.50 (YES at 0.20 = NO at 0.80)
  Decay half-life: 60 days (Polymarket markets are relatively slow-moving)
  Kelly fraction:  Dynamic — 0.25 (low confidence) to 0.40 (high confidence)
  Min samples:     30 per bucket for full confidence; 10 for reduced sizing
  Payoff ratio:    Actual avg win/loss per bucket; fallback = 1.0 (binary)
  Negative edge:   Skip trade if calibrated Kelly = negative
  Architecture:    New kelly_calibrator.py + minimal patch to edge_tracker.py
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import math
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KellyConfig:
    # ── Bucket tuning ──────────────────────────────────────────────
    # Buckets defined in BUCKET_DEFINITIONS below

    # ── Sample size thresholds ────────────────────────────────────
    MIN_SAMPLES_FULL_CONFIDENCE:    int   = 30   # Full Kelly fraction
    MIN_SAMPLES_PARTIAL_CONFIDENCE: int   = 10   # Reduced fraction
    # Below MIN_SAMPLES_PARTIAL_CONFIDENCE → fallback sizing

    # ── Kelly fraction bounds (dynamically scaled between these) ──
    KELLY_FRACTION_MIN:  float = 0.10   # Minimum (fallback / low confidence)
    KELLY_FRACTION_LOW:  float = 0.20   # Low confidence (10-29 samples)
    KELLY_FRACTION_HIGH: float = 0.40   # Full confidence (30+ samples)

    # ── Fallback when no data ──────────────────────────────────────
    FALLBACK_WIN_PROB:  float = 0.50    # Assume coin flip
    FALLBACK_EDGE:      float = 0.00    # Zero assumed edge
    FALLBACK_MAX_SIZE:  float = 0.02    # 2% of bankroll max when no data

    # ── Time decay ────────────────────────────────────────────────
    DECAY_HALF_LIFE_DAYS: float = 60.0  # Trade weight halves every 60 days

    # ── Position size limits ──────────────────────────────────────
    MAX_POSITION_PCT:   float = 0.10    # Hard cap: 10% of bankroll
    MIN_POSITION_USD:   float = 1.00    # Minimum meaningful size

    # ── Negative edge behaviour ───────────────────────────────────
    SKIP_NEGATIVE_EDGE: bool  = True    # True = skip trades with negative Kelly

    # ── Payoff ratio ──────────────────────────────────────────────
    # For binary YES/NO markets: 1 USDC risked to win ~1 USDC
    # Polymarket prices ARE the payoff: entry 0.30 → win 0.70, lose 0.30
    # We calculate implied_b from entry price when payoff is unknown
    USE_PRICE_IMPLIED_PAYOFF: bool = True  # Recommended for Polymarket

    # ── Storage ───────────────────────────────────────────────────
    CALIBRATION_FILE: str = "/root/.openclaw/workspace/kelly_calibration.json"


# ─────────────────────────────────────────────────────────────────────────────
# BUCKET DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
#
# Polymarket Up-Down prices are probabilities (0-1).
# A YES token at 0.20 means market thinks 20% chance of UP — you think higher.
# A YES token at 0.80 means market thinks 80% chance of UP.
#
# KEY INSIGHT: Price IS the market's implied probability.
# Your "edge" = your estimated win_prob - market_implied_win_prob (token price)
#
# We normalize ALL entries to [0, 0.50] range since:
#   Buying YES at 0.20  ≡  Buying NO at 0.80 (same payoff structure)
#   Both represent "buying the cheap side"
#
# normalized_price = min(entry_price, 1 - entry_price)
#
# This doubles your sample size per bucket and removes YES/NO asymmetry bias.

@dataclass
class BucketDef:
    name:        str
    low:         float   # inclusive lower bound of normalized_price
    high:        float   # exclusive upper bound
    description: str
    trade_hint:  str     # What this bucket means strategically


BUCKET_DEFINITIONS: list[BucketDef] = [
    BucketDef("moonshot",   0.00, 0.05, "Extreme longshot (<5% or >95%)", "High variance; rare wins pay huge"),
    BucketDef("extreme",    0.05, 0.12, "Extreme value (5-12% or 88-95%)",  "Strong edge if you win more than 1/8"),
    BucketDef("deep_value", 0.12, 0.22, "Deep value (12-22% or 78-88%)",    "Core edge zone for contrarian plays"),
    BucketDef("value",      0.22, 0.35, "Value (22-35% or 65-78%)",         "Moderate edge, good volume"),
    BucketDef("slight",     0.35, 0.43, "Slight value (35-43% or 57-65%)",  "Thin edge; reduce size"),
    BucketDef("deadzone",   0.43, 0.50, "Dead zone (43-50%)",               "Avoid — near coin flip"),
    BucketDef("atm",        0.50, 0.501,"At the money (exactly 0.50)",      "Skip — no edge possible"),
]

# Map bucket name → BucketDef
BUCKET_MAP: dict[str, BucketDef] = {b.name: b for b in BUCKET_DEFINITIONS}


def classify_price(entry_price: float) -> tuple[str, float]:
    """
    Returns (bucket_name, normalized_price).
    normalized_price = min(entry_price, 1 - entry_price) → always in [0, 0.50]
    """
    p = max(0.001, min(0.999, entry_price))
    norm = min(p, 1.0 - p)

    for bucket in BUCKET_DEFINITIONS:
        if bucket.low <= norm < bucket.high:
            return bucket.name, norm

    # Fallback for exactly 0.50
    return "atm", 0.50


def price_implied_payoff(entry_price: float) -> float:
    """
    For Polymarket binary markets, the token price IS the cost.
    If you buy YES at price p:
      - Win: gain (1 - p) per token
      - Lose: lose p per token
      - Payoff ratio b = (1 - p) / p

    Example: Buy YES at 0.25 → b = 0.75/0.25 = 3.0
             Buy YES at 0.70 → b = 0.30/0.70 = 0.43
    """
    p = max(0.001, min(0.999, entry_price))
    return (1.0 - p) / p


# ─────────────────────────────────────────────────────────────────────────────
# TRADE RECORD
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    trade_id:      str
    market_id:     str
    coin:          str
    entry_price:   float          # Token price (0-1), e.g. 0.025 or 0.685
    outcome:       str            # 'WIN' or 'LOSS'
    pnl_pct:       float          # Realized P&L as % of stake (e.g. +0.975 or -1.0)
    timestamp_utc: str            # ISO format
    bucket:        str            # Assigned at record time
    norm_price:    float          # normalized_price at time of record
    notes:         str = ""


# ─────────────────────────────────────────────────────────────────────────────
# PER-BUCKET STATISTICS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BucketStats:
    bucket:          str
    raw_n:           int   = 0     # Total unweighted trades
    weighted_wins:   float = 0.0   # Sum of decay-weighted win flags
    weighted_total:  float = 0.0   # Sum of all decay weights
    avg_win_pct:     float = 0.0   # Average P&L% on winning trades (unweighted for stability)
    avg_loss_pct:    float = 0.0   # Average P&L% on losing trades (absolute value)
    win_pct_raw:     float = 0.0   # Raw unweighted win rate (diagnostic)

    @property
    def win_prob(self) -> float:
        """Time-weighted win probability."""
        if self.weighted_total < 0.001:
            return 0.0
        return self.weighted_wins / self.weighted_total

    @property
    def payoff_ratio(self) -> float:
        """
        avg_win_pct / avg_loss_pct.
        Returns 1.0 if insufficient data.
        """
        if self.avg_loss_pct < 0.001 or self.avg_win_pct < 0.001:
            return 1.0
        return self.avg_win_pct / self.avg_loss_pct

    @property
    def confidence_score(self) -> float:
        """
        0.0 → no data
        0.5 → 10+ samples (partial)
        1.0 → 30+ samples (full)
        """
        if self.raw_n < 10:
            return min(0.4, self.raw_n / 25.0)
        if self.raw_n < 30:
            return 0.5 + 0.5 * ((self.raw_n - 10) / 20.0)
        return 1.0

    @property
    def wilson_lower_bound(self) -> float:
        """
        Wilson score lower bound of 95% confidence interval for win_prob.
        Returns conservative lower-bound estimate — use this for Kelly to avoid overconfidence.
        """
        n = self.raw_n
        if n < 5:
            return 0.0
        p = self.win_prob
        z = 1.96  # 95% confidence
        center = (p + z*z / (2*n)) / (1 + z*z / n)
        margin = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)
        return max(0.0, center - margin)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "win_prob":           round(self.win_prob, 4),
            "payoff_ratio":       round(self.payoff_ratio, 4),
            "confidence_score":   round(self.confidence_score, 4),
            "wilson_lower":       round(self.wilson_lower_bound, 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# KELLY FORMULA
# ─────────────────────────────────────────────────────────────────────────────

def full_kelly(win_prob: float, payoff_ratio: float) -> float:
    """
    Standard Kelly Criterion:
      f* = (p * b - q) / b
    where:
      p = win probability
      q = 1 - p (loss probability)
      b = payoff ratio (avg_win / avg_loss)

    Returns fraction of bankroll to bet.
    Negative values indicate negative edge.
    """
    q = 1.0 - win_prob
    if payoff_ratio <= 0:
        return 0.0
    return (win_prob * payoff_ratio - q) / payoff_ratio


def kelly_stake(
    win_prob:      float,
    payoff_ratio:  float,
    bankroll:      float,
    confidence:    float,
    cfg:           KellyConfig,
) -> tuple[float, dict]:
    """
    Returns (stake_in_usd, diagnostic_dict).

    Kelly fraction scales with confidence:
      confidence=0.0 → fraction = KELLY_FRACTION_MIN
      confidence=0.5 → fraction = KELLY_FRACTION_LOW
      confidence=1.0 → fraction = KELLY_FRACTION_HIGH
    """
    diag: dict = {
        "win_prob":      win_prob,
        "payoff_ratio":  payoff_ratio,
        "confidence":    confidence,
        "bankroll":      bankroll,
    }

    f_star = full_kelly(win_prob, payoff_ratio)
    diag["full_kelly_pct"] = round(f_star, 6)

    if f_star <= 0:
        diag["reason"] = "Negative or zero Kelly — skip trade"
        return 0.0, diag

    # Scale Kelly fraction by confidence
    fraction = cfg.KELLY_FRACTION_MIN + (
        cfg.KELLY_FRACTION_HIGH - cfg.KELLY_FRACTION_MIN
    ) * confidence
    diag["kelly_fraction"] = round(fraction, 4)

    raw_pct  = f_star * fraction
    capped   = min(raw_pct, cfg.MAX_POSITION_PCT)
    stake    = bankroll * capped

    diag["raw_pct"]      = round(raw_pct, 6)
    diag["capped_pct"]   = round(capped, 6)
    diag["stake_usd"]    = round(stake, 2)
    diag["cap_applied"]  = raw_pct > cfg.MAX_POSITION_PCT

    if stake < cfg.MIN_POSITION_USD:
        diag["reason"] = f"Stake ${stake:.2f} below minimum ${cfg.MIN_POSITION_USD}"
        return 0.0, diag

    diag["reason"] = "OK"
    return round(stake, 2), diag


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CALIBRATOR CLASS
# ─────────────────────────────────────────────────────────────────────────────

class KellyCalibrator:
    """
    Central class for calibrated Kelly position sizing.

    Typical usage:
        calibrator = KellyCalibrator()
        calibrator.load()

        # Before placing a trade:
        stake, diag = calibrator.get_stake(entry_price=0.25, bankroll=691.55)
        if stake == 0:
            skip_trade(diag['reason'])
        else:
            place_trade(stake)

        # After trade resolves:
        calibrator.record_trade(trade_record)
        calibrator.save()
    """

    def __init__(self, cfg: Optional[KellyConfig] = None):
        self.cfg    = cfg or KellyConfig()
        self._stats: dict[str, BucketStats] = {
            b.name: BucketStats(bucket=b.name) for b in BUCKET_DEFINITIONS
        }
        self._trades: list[TradeRecord] = []

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self):
        data = {
            "version":      "1.0",
            "saved_utc":    datetime.now(timezone.utc).isoformat(),
            "config":       asdict(self.cfg),
            "trades":       [asdict(t) for t in self._trades],
            "stats":        {k: v.to_dict() for k, v in self._stats.items()},
        }
        with open(self.cfg.CALIBRATION_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"[KellyCalibrator] Saved {len(self._trades)} trades.")

    def load(self) -> bool:
        path = Path(self.cfg.CALIBRATION_FILE)
        if not path.exists():
            logger.info("[KellyCalibrator] No calibration file found. Starting fresh.")
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            self._trades = [TradeRecord(**t) for t in data.get("trades", [])]
            self._recompute_all_stats()
            logger.info(f"[KellyCalibrator] Loaded {len(self._trades)} historical trades.")
            return True
        except Exception as e:
            logger.error(f"[KellyCalibrator] Load failed: {e}")
            return False

    # ── Core Public API ────────────────────────────────────────────────────────

    def get_stake(
        self,
        entry_price: float,
        bankroll:    float,
        coin:        str = "",
        market_id:   str = "",
    ) -> tuple[float, dict]:
        """
        Main entry point. Returns (stake_usd, diagnostics).
        stake_usd = 0.0 means: skip this trade.
        """
        bucket_name, norm_price = classify_price(entry_price)
        stats = self._stats[bucket_name]
        bucket_def = BUCKET_MAP[bucket_name]

        diag = {
            "entry_price":   entry_price,
            "norm_price":    norm_price,
            "bucket":        bucket_name,
            "bucket_desc":   bucket_def.description,
            "raw_n":         stats.raw_n,
            "coin":          coin,
        }

        # Dead zone / ATM — always skip
        if bucket_name in ("deadzone", "atm"):
            diag["reason"] = f"Dead zone ({bucket_def.description}) — no edge"
            return 0.0, diag

        # ── Determine win probability to use ──────────────────────────────────

        if stats.raw_n >= self.cfg.MIN_SAMPLES_PARTIAL_CONFIDENCE:
            # Use Wilson lower bound for conservatism
            win_prob   = stats.wilson_lower_bound
            confidence = stats.confidence_score
            diag["win_prob_source"] = "calibrated_wilson_lower"
        else:
            # Fallback: use price-implied win prob with conservative damping
            # "The market is probably right" assumption
            win_prob   = norm_price * 1.05  # Assume you have 5% edge over market
            confidence = self.cfg.MIN_SAMPLES_PARTIAL_CONFIDENCE * 0.0 if stats.raw_n == 0 else (
                stats.raw_n / self.cfg.MIN_SAMPLES_PARTIAL_CONFIDENCE * self.cfg.KELLY_FRACTION_MIN
            )
            confidence = min(0.3, confidence)
            diag["win_prob_source"] = "fallback_price_implied"

            # Cap fallback size
            stake = min(bankroll * self.cfg.FALLBACK_MAX_SIZE, 10.0)
            diag["win_prob"]   = round(win_prob, 4)
            diag["confidence"] = round(confidence, 4)
            diag["stake_usd"]  = round(stake, 2)
            diag["reason"]     = f"Insufficient data (n={stats.raw_n} < {self.cfg.MIN_SAMPLES_PARTIAL_CONFIDENCE}); fallback size"
            return round(stake, 2), diag

        diag["win_prob"]     = round(win_prob, 4)
        diag["confidence"]   = round(confidence, 4)
        diag["raw_win_prob"] = round(stats.win_prob, 4)

        # ── Determine payoff ratio ─────────────────────────────────────────────

        if self.cfg.USE_PRICE_IMPLIED_PAYOFF:
            payoff_ratio = price_implied_payoff(entry_price)
            diag["payoff_source"] = "price_implied"
        elif stats.payoff_ratio > 0.01:
            payoff_ratio = stats.payoff_ratio
            diag["payoff_source"] = "historical_avg"
        else:
            payoff_ratio = price_implied_payoff(entry_price)
            diag["payoff_source"] = "price_implied_fallback"

        diag["payoff_ratio"] = round(payoff_ratio, 4)

        # ── Calculate Kelly stake ──────────────────────────────────────────────

        stake, kelly_diag = kelly_stake(win_prob, payoff_ratio, bankroll, confidence, self.cfg)
        diag.update(kelly_diag)

        if stake == 0.0 and self.cfg.SKIP_NEGATIVE_EDGE:
            return 0.0, diag

        return stake, diag

    def record_trade(self, trade: TradeRecord):
        """
        Add a completed trade to history and recompute bucket stats.
        Call this after every trade resolution.
        """
        # Ensure bucket is set
        if not trade.bucket:
            trade.bucket, trade.norm_price = classify_price(trade.entry_price)

        self._trades.append(trade)
        self._recompute_bucket_stats(trade.bucket)
        logger.info(
            f"[KellyCalibrator] Recorded {trade.trade_id} | "
            f"bucket={trade.bucket} | outcome={trade.outcome} | "
            f"pnl={trade.pnl_pct:+.3f}"
        )

    def get_stats_summary(self) -> dict:
        """Returns human-readable stats for all buckets."""
        return {
            name: {
                "n":             s.raw_n,
                "win_rate_raw":  f"{s.win_prob:.1%}",
                "wilson_lower":  f"{s.wilson_lower_bound:.1%}",
                "payoff_ratio":  f"{s.payoff_ratio:.3f}",
                "confidence":    f"{s.confidence_score:.1%}",
                "full_kelly":    f"{full_kelly(s.win_prob, s.payoff_ratio):.4f}",
                "bucket_desc":   BUCKET_MAP[name].description,
            }
            for name, s in self._stats.items()
            if s.raw_n > 0
        }

    # ── Stat Computation ───────────────────────────────────────────────────────

    def _recompute_all_stats(self):
        for bucket_name in self._stats:
            self._recompute_bucket_stats(bucket_name)

    def _recompute_bucket_stats(self, bucket_name: str):
        now_ts = time.time()
        half_life_secs = self.cfg.DECAY_HALF_LIFE_DAYS * 86400.0

        bucket_trades = [
            t for t in self._trades if t.bucket == bucket_name
        ]

        if not bucket_trades:
            self._stats[bucket_name] = BucketStats(bucket=bucket_name)
            return

        weighted_wins  = 0.0
        weighted_total = 0.0
        win_pnls       = []
        loss_pnls      = []
        wins_raw       = 0

        for t in bucket_trades:
            try:
                trade_ts = datetime.fromisoformat(
                    t.timestamp_utc.replace("Z", "+00:00")
                ).timestamp()
            except Exception:
                trade_ts = now_ts  # Treat as current if unparseable

            age_secs = max(0.0, now_ts - trade_ts)
            weight   = math.exp(-age_secs * math.log(2) / half_life_secs)

            if t.outcome == "WIN":
                weighted_wins += weight
                win_pnls.append(abs(t.pnl_pct))
                wins_raw += 1
            else:
                loss_pnls.append(abs(t.pnl_pct))

            weighted_total += weight

        avg_win  = sum(win_pnls)  / len(win_pnls)  if win_pnls  else 0.0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 1.0  # Avoid div/0
        win_pct_raw = wins_raw / len(bucket_trades)

        self._stats[bucket_name] = BucketStats(
            bucket         = bucket_name,
            raw_n          = len(bucket_trades),
            weighted_wins  = weighted_wins,
            weighted_total = weighted_total,
            avg_win_pct    = avg_win,
            avg_loss_pct   = avg_loss,
            win_pct_raw    = win_pct_raw,
        )

    # ── Backtest / Import ──────────────────────────────────────────────────────

    def import_from_trades_json(
        self,
        trades_json_path: str,
        field_map: Optional[dict] = None,
    ) -> int:
        """
        Import existing trades from your trades_v4_production.json file.

        Default field_map assumes your trade dicts have:
          {
            "id":           str,
            "market_id":    str,
            "coin":         str,
            "entry_price":  float,   ← token price (0-1)
            "outcome":      "WIN" or "LOSS",
            "pnl_pct":      float,   ← e.g. +0.975 for win at 0.025, -1.0 for full loss
            "timestamp":    str,     ← ISO or Unix
          }

        Override with field_map if your keys differ:
          field_map = {"entry_price": "token_price", "outcome": "result"}
        """
        fm = {
            "id":          "id",
            "market_id":   "market_id",
            "coin":        "coin",
            "entry_price": "entry_price",
            "outcome":     "outcome",
            "pnl_pct":     "pnl_pct",
            "timestamp":   "timestamp",
        }
        if field_map:
            fm.update(field_map)

        try:
            with open(trades_json_path) as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"[Import] Cannot load {trades_json_path}: {e}")
            return 0

        # Support both list and dict-of-trades formats
        if isinstance(raw, dict):
            trade_list = list(raw.values())
        else:
            trade_list = raw

        imported = 0
        for item in trade_list:
            try:
                ts_raw = item.get(fm["timestamp"], "")
                # Handle Unix timestamp
                if isinstance(ts_raw, (int, float)):
                    ts_str = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
                else:
                    ts_str = str(ts_raw)

                ep = float(item.get(fm["entry_price"], 0))
                if ep <= 0 or ep >= 1:
                    continue

                outcome_raw = str(item.get(fm["outcome"], "")).upper()
                if outcome_raw not in ("WIN", "LOSS"):
                    # Try common alternates
                    outcome_map = {"YES": "WIN", "NO": "LOSS", "1": "WIN", "0": "LOSS",
                                   "TRUE": "WIN", "FALSE": "LOSS"}
                    outcome_raw = outcome_map.get(outcome_raw, "")
                if not outcome_raw:
                    continue

                bucket, norm = classify_price(ep)

                t = TradeRecord(
                    trade_id      = str(item.get(fm["id"], f"import_{imported}")),
                    market_id     = str(item.get(fm["market_id"], "")),
                    coin          = str(item.get(fm["coin"], "")),
                    entry_price   = ep,
                    outcome       = outcome_raw,
                    pnl_pct       = float(item.get(fm["pnl_pct"], 0.0)),
                    timestamp_utc = ts_str,
                    bucket        = bucket,
                    norm_price    = norm,
                )
                self._trades.append(t)
                imported += 1
            except Exception as e:
                logger.warning(f"[Import] Skipped trade: {e}")

        self._recompute_all_stats()
        logger.info(f"[Import] Imported {imported} trades from {trades_json_path}")
        return imported


# ─────────────────────────────────────────────────────────────────────────────
# BACKTESTER
# ─────────────────────────────────────────────────────────────────────────────

class KellyBacktester:
    """
    Walk-forward backtest: calibrates on past N trades, sizes next M trades.
    Avoids lookahead / overfitting.

    Usage:
        bt = KellyBacktester(trades_list)
        results = bt.run(warmup_trades=30, starting_bankroll=691.55)
        bt.print_report(results)
    """

    def __init__(self, trades: list[TradeRecord], cfg: Optional[KellyConfig] = None):
        self.trades = sorted(trades, key=lambda t: t.timestamp_utc)
        self.cfg    = cfg or KellyConfig()

    def run(
        self,
        warmup_trades:     int   = 30,
        starting_bankroll: float = 691.55,
    ) -> dict:
        """
        Returns backtest result dict with equity curve, per-trade detail.
        """
        bankroll   = starting_bankroll
        equity     = [bankroll]
        trade_log  = []
        cal        = KellyCalibrator(self.cfg)

        for i, trade in enumerate(self.trades):
            bucket, norm = classify_price(trade.entry_price)

            if i < warmup_trades:
                # Warmup phase: record trades but size at minimum
                stake  = bankroll * self.cfg.FALLBACK_MAX_SIZE
                source = "warmup_flat"
            else:
                # Live phase: use calibrated sizing
                stake, diag = cal.get_stake(trade.entry_price, bankroll, trade.coin)
                source = diag.get("win_prob_source", "calibrated")
                if stake == 0.0:
                    # Skipped trade — treat as 0 P&L
                    cal.record_trade(trade)
                    trade_log.append({
                        "i":        i,
                        "trade_id": trade.trade_id,
                        "bucket":   bucket,
                        "outcome":  trade.outcome,
                        "stake":    0.0,
                        "pnl":      0.0,
                        "bankroll": bankroll,
                        "skipped":  True,
                        "source":   source,
                    })
                    continue

            # Apply outcome
            if trade.outcome == "WIN":
                pnl = stake * trade.pnl_pct if trade.pnl_pct != 0 else stake * price_implied_payoff(trade.entry_price)
            else:
                pnl = -stake

            bankroll += pnl
            bankroll  = max(0.01, bankroll)  # Ruin floor
            equity.append(bankroll)

            cal.record_trade(trade)

            trade_log.append({
                "i":        i,
                "trade_id": trade.trade_id,
                "entry":    trade.entry_price,
                "bucket":   bucket,
                "outcome":  trade.outcome,
                "stake":    round(stake, 2),
                "pnl":      round(pnl, 2),
                "bankroll": round(bankroll, 2),
                "skipped":  False,
                "source":   source,
            })

        # Summary stats
        total_trades  = len(self.trades)
        skipped       = sum(1 for t in trade_log if t.get("skipped"))
        wins          = sum(1 for t in trade_log if not t.get("skipped") and t["outcome"] == "WIN")
        losses        = sum(1 for t in trade_log if not t.get("skipped") and t["outcome"] == "LOSS")
        total_pnl     = bankroll - starting_bankroll
        max_bankroll  = max(equity)
        drawdown_pts  = [max(equity[:i+1]) - equity[i] for i in range(len(equity))]
        max_drawdown  = max(drawdown_pts) if drawdown_pts else 0.0

        return {
            "starting_bankroll": starting_bankroll,
            "ending_bankroll":   round(bankroll, 2),
            "total_pnl":         round(total_pnl, 2),
            "total_pnl_pct":     round(total_pnl / starting_bankroll * 100, 2),
            "total_trades":      total_trades,
            "skipped_trades":    skipped,
            "wins":              wins,
            "losses":            losses,
            "win_rate":          round(wins / max(1, wins + losses), 4),
            "max_bankroll":      round(max_bankroll, 2),
            "max_drawdown_usd":  round(max_drawdown, 2),
            "equity_curve":      equity,
            "trade_log":         trade_log,
            "warmup_trades":     warmup_trades,
        }

    def print_report(self, results: dict):
        print(f"\n{'═'*60}")
        print(f"  KELLY CALIBRATION BACKTEST REPORT")
        print(f"{'═'*60}")
        print(f"  Warmup trades:   {results['warmup_trades']}")
        print(f"  Total trades:    {results['total_trades']}")
        print(f"  Skipped trades:  {results['skipped_trades']} (negative edge)")
        print(f"  Win rate:        {results['win_rate']:.1%}")
        print(f"{'─'*60}")
        print(f"  Starting:        ${results['starting_bankroll']:.2f}")
        print(f"  Ending:          ${results['ending_bankroll']:.2f}")
        print(f"  Total P&L:       ${results['total_pnl']:+.2f} ({results['total_pnl_pct']:+.1f}%)")
        print(f"  Max bankroll:    ${results['max_bankroll']:.2f}")
        print(f"  Max drawdown:    ${results['max_drawdown_usd']:.2f}")
        print(f"{'─'*60}")

        # Per-bucket breakdown
        bucket_stats: dict[str, dict] = {}
        for t in results["trade_log"]:
            b = t["bucket"]
            if b not in bucket_stats:
                bucket_stats[b] = {"n": 0, "wins": 0, "total_pnl": 0.0, "skipped": 0}
            if t.get("skipped"):
                bucket_stats[b]["skipped"] += 1
            else:
                bucket_stats[b]["n"]    += 1
                bucket_stats[b]["wins"] += 1 if t["outcome"] == "WIN" else 0
                bucket_stats[b]["total_pnl"] += t["pnl"]

        print(f"  {'Bucket':<12} {'N':>5} {'WR':>7} {'P&L':>10} {'Skipped':>8}")
        print(f"  {'─'*12} {'─'*5} {'─'*7} {'─'*10} {'─'*8}")
        for b, s in sorted(bucket_stats.items(), key=lambda x: x[0]):
            wr = s["wins"] / s["n"] if s["n"] > 0 else 0
            print(f"  {b:<12} {s['n']:>5} {wr:>7.1%} {s['total_pnl']:>+10.2f} {s['skipped']:>8}")
        print(f"{'═'*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTIC UTILITY
# ─────────────────────────────────────────────────────────────────────────────

def print_calibration_status(cal: KellyCalibrator):
    """Print current calibration state — run standalone for quick check."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total   = len(cal._trades)

    print(f"\n{'═'*65}")
    print(f"  KELLY CALIBRATION STATUS — {now_str}")
    print(f"  Total trades in history: {total}")
    print(f"{'─'*65}")
    print(f"  {'Bucket':<12} {'N':>4} {'WinProb':>9} {'Wilson↓':>9} {'Payoff':>8} {'f*':>8} {'Conf':>7}")
    print(f"  {'─'*12} {'─'*4} {'─'*9} {'─'*9} {'─'*8} {'─'*8} {'─'*7}")

    for b_def in BUCKET_DEFINITIONS:
        s = cal._stats[b_def.name]
        if s.raw_n == 0:
            print(f"  {b_def.name:<12} {'0':>4}  {'—':>9} {'—':>9} {'—':>8} {'—':>8} {'—':>7}")
            continue
        fstar = full_kelly(s.wilson_lower_bound, s.payoff_ratio)
        print(
            f"  {b_def.name:<12} {s.raw_n:>4}  "
            f"{s.win_prob:>8.1%}  {s.wilson_lower_bound:>8.1%}  "
            f"{s.payoff_ratio:>7.3f}  {fstar:>7.4f}  {s.confidence_score:>6.1%}"
        )

    print(f"{'─'*65}")
    print(f"  Wilson lower bound is used for Kelly (conservative)")
    print(f"  f* = full Kelly fraction (multiply by 0.10–0.40 for actual size)")
    print(f"{'═'*65}\n")


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cal = KellyCalibrator()

    # Simulate your 2 existing trades
    from datetime import timezone

    cal.record_trade(TradeRecord(
        trade_id="eth_yes_1",
        market_id="eth-updown-15m-test1",
        coin="ETH",
        entry_price=0.025,   # YES at 2.5 cents
        outcome="WIN",
        pnl_pct=0.975,       # Won (1 - 0.025) / 0.025 = 39x — or as pct of token: +0.975
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        bucket="",
        norm_price=0.0,
    ))

    cal.record_trade(TradeRecord(
        trade_id="btc_yes_2",
        market_id="btc-updown-15m-test2",
        coin="BTC",
        entry_price=0.685,   # YES at 68.5 cents
        outcome="WIN",
        pnl_pct=0.315,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        bucket="",
        norm_price=0.0,
    ))

    print_calibration_status(cal)

    # Show stake recommendations at various price points
    bankroll = 691.55
    print(f"\n  STAKE RECOMMENDATIONS (bankroll=${bankroll})")
    print(f"  {'Entry':>7}  {'Bucket':<12}  {'Stake':>8}  {'Reason'}")
    print(f"  {'─'*7}  {'─'*12}  {'─'*8}  {'─'*30}")
    for ep in [0.02, 0.05, 0.15, 0.25, 0.35, 0.47, 0.50, 0.65, 0.80, 0.95]:
        stake, diag = cal.get_stake(ep, bankroll)
        print(f"  {ep:>7.3f}  {diag['bucket']:<12}  ${stake:>7.2f}  {diag['reason']}")
    print()
