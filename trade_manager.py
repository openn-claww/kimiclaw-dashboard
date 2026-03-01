"""
trade_manager.py — Trade lifecycle management and automatic settlement.

Solves:
  - Stuck open trades (ETH 15m YES @ 0.025 stuck 5.5h)
  - 404 errors from expired market APIs
  - No PnL recording on resolution
  - Unknown win/loss state after market closes

How to check resolved market outcomes when API returns 404:
  Polymarket's Gamma API keeps market history even after resolution.
  Use /markets/slug/{slug} — it returns the market with resolved=true
  and winner field. If that 404s, fall back to CLOB /prices endpoint
  which shows token prices at 0.00 or 1.00 post-resolution.
"""

import json
import time
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("trade_manager")

# ── Constants ─────────────────────────────────────────────────────────────────
WORKSPACE       = Path("/root/.openclaw/workspace")
TRADES_FILE     = WORKSPACE / "trades_v4.json"
WALLET_FILE     = WORKSPACE / "wallet_v4_production.json"
GAMMA_API       = "https://gamma-api.polymarket.com"
CLOB_API        = "https://clob.polymarket.com"
SETTLE_INTERVAL = 300     # Check open trades every 5 minutes
ALERT_AFTER_MIN = 30      # Alert if trade unresolved after 30 min
MAX_TRADE_AGE_H = 2       # Force-settle check after 2 hours


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Trade:
    trade_id:       str
    coin:           str
    side:           str           # "YES" or "NO"
    timeframe:      str           # "5m" or "15m"
    market_slug:    str
    condition_id:   str
    token_id:       str
    entry_price:    float
    shares:         float
    cost_usdc:      float         # entry_price × shares
    taker_fee:      float         # Fee paid at entry
    entry_time:     float         # Unix timestamp
    window_end:     float         # When market resolves (Unix)

    # Filled on settlement
    status:         str = "open"  # open | won | lost | settled | error
    exit_price:     float = 0.0
    payout_usdc:    float = 0.0
    net_pnl:        float = 0.0
    net_pnl_pct:    float = 0.0
    settled_at:     float = 0.0
    settle_method:  str = ""      # gamma | clob_price | manual

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.entry_time) / 60

    @property
    def is_overdue(self) -> bool:
        return time.time() > self.window_end + 60   # 1 min grace period

    @property
    def needs_alert(self) -> bool:
        return self.is_overdue and self.age_minutes > ALERT_AFTER_MIN

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Trade":
        return cls(**d)


# ── Wallet manager ────────────────────────────────────────────────────────────

class WalletManager:
    def __init__(self):
        self.path = WALLET_FILE
        self._data = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            default = {"balance_usdc": 500.0, "total_pnl": 0.0,
                       "trades_won": 0, "trades_lost": 0}
            self._save(default)
            return default

    def _save(self, data: dict):
        self.path.write_text(json.dumps(data, indent=2))

    @property
    def balance(self) -> float:
        return self._data.get("balance_usdc", 0.0)

    def apply_settlement(self, trade: Trade):
        """Update wallet after trade settles."""
        self._data["balance_usdc"] = round(
            self._data["balance_usdc"] + trade.payout_usdc - trade.cost_usdc, 4
        )
        self._data["total_pnl"] = round(
            self._data.get("total_pnl", 0.0) + trade.net_pnl, 4
        )
        if trade.status == "won":
            self._data["trades_won"] = self._data.get("trades_won", 0) + 1
        else:
            self._data["trades_lost"] = self._data.get("trades_lost", 0) + 1

        self._save(self._data)
        logger.info(
            f"[WALLET] Balance: ${self._data['balance_usdc']:.4f} | "
            f"Total PnL: ${self._data['total_pnl']:+.4f}"
        )


# ── Settlement engine ─────────────────────────────────────────────────────────

def _fetch_json(url: str, timeout: int = 5) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None    # Expected for expired markets
        logger.warning(f"HTTP {e.code} for {url}")
        return None
    except Exception as e:
        logger.warning(f"Fetch failed {url}: {e}")
        return None


def check_settlement_via_gamma(slug: str) -> Optional[dict]:
    """
    Primary settlement method: Gamma API keeps history even after resolution.
    Returns {"resolved": bool, "winner": "YES"|"NO"|None, "resolution_time": float}
    """
    # Try events endpoint first (more complete data)
    data = _fetch_json(f"{GAMMA_API}/events/slug/{slug}")
    if data:
        markets = data.get("markets", [{}])
        if markets:
            m = markets[0]
            resolved = m.get("resolved", False) or m.get("closed", False)
            winner   = m.get("winner")         # "YES" or "NO" or None
            end_date = m.get("endDate", "")
            return {"resolved": resolved, "winner": winner, "end_date": end_date}

    # Fall back to /markets endpoint
    data = _fetch_json(f"{GAMMA_API}/markets?slug={slug}&limit=1")
    if data and isinstance(data, list) and data:
        m = data[0]
        resolved = m.get("resolved", False) or m.get("closed", False)
        winner   = m.get("winner")
        return {"resolved": resolved, "winner": winner, "end_date": m.get("endDate")}

    return None


def check_settlement_via_clob_price(token_id: str) -> Optional[str]:
    """
    Fallback settlement: After resolution, CLOB token prices become 0.00 or 1.00.
    Price = 1.00 → this outcome WON
    Price = 0.00 → this outcome LOST
    Returns "won", "lost", or None if still live.
    """
    data = _fetch_json(f"{CLOB_API}/price?token_id={token_id}&side=buy")
    if not data:
        return None

    price = float(data.get("price", 0.5))
    if price >= 0.99:
        return "won"
    if price <= 0.01:
        return "lost"
    return None   # Still live, price between 0.01 and 0.99


def settle_trade(trade: Trade) -> bool:
    """
    Attempt to settle one trade. Updates trade in place.
    Returns True if settlement was determined.

    Resolution priority:
      1. Gamma API (has winner field, most reliable)
      2. CLOB price (0.00/1.00 post-resolution)
      3. Time-based: if window_end > 2h ago, mark as needs_manual_review
    """
    if trade.status != "open":
        return True   # Already settled

    # Method 1: Gamma API
    gamma_result = check_settlement_via_gamma(trade.market_slug)
    if gamma_result and gamma_result["resolved"] and gamma_result["winner"]:
        winner = gamma_result["winner"]
        trade.settle_method = "gamma"
        _apply_resolution(trade, winner)
        return True

    # Method 2: CLOB price
    clob_result = check_settlement_via_clob_price(trade.token_id)
    if clob_result:
        trade.settle_method = "clob_price"
        _apply_resolution(trade, "YES" if clob_result == "won" else "NO")
        return True

    # Method 3: Force-settle very old trades
    age_hours = trade.age_minutes / 60
    if age_hours > MAX_TRADE_AGE_H and trade.is_overdue:
        logger.error(
            f"[SETTLEMENT] Trade {trade.trade_id} is {age_hours:.1f}h old "
            f"and unresolvable via API — marking as needs_manual_review"
        )
        trade.status       = "error"
        trade.settle_method = "timeout_error"
        trade.settled_at    = time.time()
        return True

    return False   # Still unresolved, retry later


def _apply_resolution(trade: Trade, winning_side: str):
    """Calculate PnL and mark trade status given which side won."""
    our_side_won = (trade.side == winning_side)

    trade.status     = "won" if our_side_won else "lost"
    trade.settled_at  = time.time()

    if our_side_won:
        # Winner: shares pay $1.00 each
        trade.exit_price  = 1.0
        trade.payout_usdc = trade.shares * 1.0
    else:
        # Loser: shares pay $0.00
        trade.exit_price  = 0.0
        trade.payout_usdc = 0.0

    trade.net_pnl     = round(trade.payout_usdc - trade.cost_usdc - trade.taker_fee, 4)
    trade.net_pnl_pct = round(trade.net_pnl / trade.cost_usdc * 100, 2) if trade.cost_usdc else 0.0

    logger.info(
        f"[SETTLEMENT] {trade.trade_id} → {trade.status.upper()} | "
        f"Payout: ${trade.payout_usdc:.4f} | "
        f"Net PnL: ${trade.net_pnl:+.4f} ({trade.net_pnl_pct:+.1f}%) | "
        f"Method: {trade.settle_method}"
    )


# ── Trade store ───────────────────────────────────────────────────────────────

class TradeManager:
    """
    Manages full trade lifecycle: open → settled → archived.
    Persists all state to disk — survives crashes.
    """

    def __init__(self):
        self.trades_file = TRADES_FILE
        self.wallet      = WalletManager()
        self.trades: dict[str, Trade] = {}
        self._load()

    def _load(self):
        try:
            raw = json.loads(self.trades_file.read_text())
            self.trades = {k: Trade.from_dict(v) for k, v in raw.items()}
            open_count = sum(1 for t in self.trades.values() if t.status == "open")
            logger.info(
                f"[TRADE MANAGER] Loaded {len(self.trades)} trades "
                f"({open_count} open)"
            )
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("[TRADE MANAGER] No existing trades file, starting fresh")

    def _save(self):
        self.trades_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self.trades.items()}, indent=2)
        )

    def open_trade(self, trade: Trade):
        """Record a new trade entry."""
        self.trades[trade.trade_id] = trade
        self._save()
        logger.info(
            f"[TRADE OPEN] {trade.trade_id} | "
            f"{trade.coin} {trade.side} {trade.timeframe} | "
            f"Price: {trade.entry_price:.3f} | "
            f"Cost: ${trade.cost_usdc:.4f} | "
            f"Window ends: {datetime.fromtimestamp(trade.window_end, tz=timezone.utc).strftime('%H:%M:%S')} UTC"
        )

    def settle_all_open(self) -> dict:
        """
        Check all open trades for settlement.
        Call this every SETTLE_INTERVAL seconds.
        Returns summary of settlements.
        """
        open_trades = [t for t in self.trades.values() if t.status == "open"]
        summary = {"checked": len(open_trades), "settled": 0, "alerted": 0}

        for trade in open_trades:
            if not trade.is_overdue:
                continue   # Window not closed yet

            if trade.needs_alert:
                logger.warning(
                    f"[ALERT] Trade {trade.trade_id} unresolved after "
                    f"{trade.age_minutes:.0f} min!"
                )
                summary["alerted"] += 1

            settled = settle_trade(trade)
            if settled:
                self.wallet.apply_settlement(trade)
                self._save()
                summary["settled"] += 1

        return summary

    def get_open_trades(self) -> list[Trade]:
        return [t for t in self.trades.values() if t.status == "open"]

    def get_summary(self) -> dict:
        all_t   = list(self.trades.values())
        settled = [t for t in all_t if t.status in ("won", "lost")]
        wins    = [t for t in settled if t.status == "won"]

        return {
            "total":      len(all_t),
            "open":       len(self.get_open_trades()),
            "settled":    len(settled),
            "wins":       len(wins),
            "losses":     len(settled) - len(wins),
            "win_rate":   len(wins) / max(len(settled), 1),
            "total_pnl":  sum(t.net_pnl for t in settled),
            "balance":    self.wallet.balance,
        }

    def print_open_trades(self):
        open_t = self.get_open_trades()
        if not open_t:
            print("No open trades.")
            return
        print(f"\n{'─'*70}")
        print(f"{'ID':<20} {'Coin':<6} {'Side':<5} {'TF':<5} {'Price':<8} "
              f"{'Cost':<8} {'Age':>8} {'Status'}")
        print(f"{'─'*70}")
        for t in open_t:
            overdue = "⚠ OVERDUE" if t.is_overdue else ""
            print(
                f"{t.trade_id:<20} {t.coin:<6} {t.side:<5} {t.timeframe:<5} "
                f"{t.entry_price:<8.3f} ${t.cost_usdc:<7.4f} "
                f"{t.age_minutes:>6.0f}m  {overdue}"
            )
        print(f"{'─'*70}\n")


# ── CLI settlement tool (settle.sh backend) ───────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="Trade Manager")
    parser.add_argument("action",
                        choices=["status", "settle", "list", "check-slug"])
    parser.add_argument("--slug", help="Market slug to check directly")
    args = parser.parse_args()

    tm = TradeManager()

    if args.action == "status":
        s = tm.get_summary()
        print(f"\n{'='*40}")
        print(f"  TRADE SUMMARY")
        print(f"{'='*40}")
        print(f"  Balance:   ${s['balance']:.4f} USDC")
        print(f"  Total PnL: ${s['total_pnl']:+.4f}")
        print(f"  Win Rate:  {s['win_rate']:.0%} ({s['wins']}W / {s['losses']}L)")
        print(f"  Open:      {s['open']} trade(s)")
        print(f"{'='*40}\n")

    elif args.action == "settle":
        print("Checking all open trades for settlement...")
        result = tm.settle_all_open()
        print(f"Checked: {result['checked']} | "
              f"Settled: {result['settled']} | "
              f"Alerts: {result['alerted']}")

    elif args.action == "list":
        tm.print_open_trades()

    elif args.action == "check-slug" and args.slug:
        print(f"Checking slug: {args.slug}")
        result = check_settlement_via_gamma(args.slug)
        print(f"Gamma result:  {result}")

        # Also try CLOB for common token_id patterns
        print("(Pass token_id to check CLOB price directly)")
