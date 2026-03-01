"""
settle_stuck_trade.py — One-shot script to settle the stuck ETH 15m YES trade.

Handles ALL wallet formats your bot might use:
  - wallet_v4_production.json (new format)
  - memory/trades.json (old format)
  - memory/wallet.json (alternate format)
  - Any JSON with "open_trades", "positions", or "trades" keys

Run: python3 settle_stuck_trade.py
  → Finds all open trades across all files
  → Queries Polymarket for resolution
  → Updates wallet with PnL
  → Prints settlement report
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path("/root/.openclaw/workspace")

# All possible locations for trade/wallet data
SEARCH_PATHS = [
    WORKSPACE / "wallet_v4_production.json",
    WORKSPACE / "memory" / "trades.json",
    WORKSPACE / "memory" / "wallet.json",
    WORKSPACE / "trades_v4.json",
    WORKSPACE / "wallet.json",
    WORKSPACE / "memory" / "memory.json",
]

GAMMA  = "https://gamma-api.polymarket.com"
CLOB   = "https://clob.polymarket.com"


# ── Universal wallet reader ───────────────────────────────────────────────────

def load_all_wallet_data() -> dict:
    """
    Reads ALL known wallet/trade files and merges them.
    Returns unified structure regardless of source format.
    """
    result = {
        "balance":     None,
        "open_trades": [],
        "all_trades":  [],
        "sources":     [],
    }

    for path in SEARCH_PATHS:
        if not path.exists():
            continue

        try:
            raw = json.loads(path.read_text())
            print(f"  Found: {path} ({path.stat().st_size} bytes)")
            result["sources"].append(str(path))

            # Format 1: {balance_usdc, open_trades: [...]}
            if "balance_usdc" in raw:
                result["balance"] = raw["balance_usdc"]
                print(f"    Balance: ${result['balance']:.4f}")

            # Format 2: {positions: {market_id: {...}}}
            if "positions" in raw:
                for market_id, pos in raw["positions"].items():
                    trade = _normalize_position(market_id, pos)
                    if trade:
                        result["open_trades"].append(trade)
                        print(f"    Position: {trade['coin']} {trade['side']} @ {trade['entry_price']:.3f}")

            # Format 3: {open_trades: [...]}
            if "open_trades" in raw:
                for t in raw["open_trades"]:
                    trade = _normalize_trade(t)
                    if trade:
                        result["open_trades"].append(trade)
                        print(f"    Open trade: {trade['coin']} {trade['side']} @ {trade['entry_price']:.3f}")

            # Format 4: {trades: [...]} or {trades: {id: {...}}}
            if "trades" in raw:
                trades = raw["trades"]
                if isinstance(trades, list):
                    items = trades
                elif isinstance(trades, dict):
                    items = list(trades.values())
                else:
                    items = []
                for t in items:
                    trade = _normalize_trade(t)
                    if trade:
                        result["all_trades"].append(trade)
                        if trade.get("status", "open") == "open":
                            result["open_trades"].append(trade)

            # Format 5: flat dict with trade fields directly
            if "entry_price" in raw and "side" in raw:
                trade = _normalize_trade(raw)
                if trade:
                    result["open_trades"].append(trade)
                    print(f"    Direct trade: {trade['coin']} {trade['side']} @ {trade['entry_price']:.3f}")

            # Format 6: wallet_v4 with in-wallet open trade record
            if "last_trade" in raw:
                t = raw["last_trade"]
                if isinstance(t, dict) and t.get("status") == "open":
                    trade = _normalize_trade(t)
                    if trade:
                        result["open_trades"].append(trade)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  Warning: Could not parse {path}: {e}")

    # Deduplicate by entry_price + side + coin
    seen = set()
    unique = []
    for t in result["open_trades"]:
        key = (t.get("coin"), t.get("side"), t.get("entry_price"), t.get("timeframe"))
        if key not in seen:
            seen.add(key)
            unique.append(t)
    result["open_trades"] = unique

    return result


def _normalize_trade(raw: dict) -> dict:
    """Normalize any trade dict format to standard structure."""
    if not isinstance(raw, dict):
        return None

    # Try to extract coin
    coin = (raw.get("coin") or raw.get("asset") or raw.get("market", "")
            .upper().replace("USDT", "").replace("-USD", "")[:3] or "UNK").upper()

    # Side
    side = raw.get("side") or raw.get("direction") or raw.get("outcome") or "YES"
    side = side.upper()

    entry_price = float(raw.get("entry_price") or raw.get("price") or
                        raw.get("yes_price") or 0)
    if entry_price == 0:
        return None

    return {
        "coin":         coin,
        "side":         side,
        "entry_price":  entry_price,
        "shares":       float(raw.get("shares") or raw.get("amount") or raw.get("size") or 0),
        "cost_usdc":    float(raw.get("cost_usdc") or raw.get("cost") or
                              raw.get("amount_usdc") or entry_price * float(raw.get("shares", 1))),
        "timeframe":    raw.get("timeframe") or raw.get("tf") or "15m",
        "market_slug":  raw.get("market_slug") or raw.get("slug") or raw.get("market") or "",
        "condition_id": raw.get("condition_id") or raw.get("conditionId") or "",
        "token_id":     raw.get("token_id") or raw.get("yes_token_id") or raw.get("tokenId") or "",
        "entry_time":   float(raw.get("entry_time") or raw.get("timestamp") or
                              raw.get("created_at") or 0),
        "window_end":   float(raw.get("window_end") or raw.get("end_time") or
                              raw.get("expiry") or 0),
        "status":       raw.get("status") or "open",
        "_raw":         raw,   # Keep original for wallet update
    }


def _normalize_position(market_id: str, pos: dict) -> dict:
    """Normalize Polymarket CLOB position format."""
    if not isinstance(pos, dict):
        return None

    # Derive coin from market_id or slug
    market_id_lower = market_id.lower()
    coin = "BTC" if "btc" in market_id_lower else \
           "ETH" if "eth" in market_id_lower else \
           "SOL" if "sol" in market_id_lower else "UNK"

    side = "YES" if pos.get("outcome", "").upper() == "YES" else "NO"

    return {
        "coin":         coin,
        "side":         side,
        "entry_price":  float(pos.get("avg_price") or pos.get("price") or 0),
        "shares":       float(pos.get("size") or pos.get("shares") or 0),
        "cost_usdc":    float(pos.get("value") or pos.get("cost") or 0),
        "timeframe":    "15m" if "15m" in market_id_lower else "5m",
        "market_slug":  market_id,
        "condition_id": pos.get("condition_id") or market_id,
        "token_id":     pos.get("token_id") or "",
        "entry_time":   float(pos.get("entry_time") or pos.get("timestamp") or 0),
        "window_end":   0,
        "status":       "open",
        "_raw":         pos,
    }


# ── Settlement engine ─────────────────────────────────────────────────────────

def fetch(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_url": url}
    except Exception as e:
        return {"_error": str(e), "_url": url}


def resolve_trade(trade: dict) -> dict:
    """
    Query Polymarket to determine if trade won or lost.
    Returns {"status": "won"|"lost"|"unknown", "method": str, "detail": dict}
    """
    coin      = trade["coin"].lower()
    timeframe = trade.get("timeframe", "15m")
    slug      = trade.get("market_slug", "")

    # Strategy: try multiple API approaches
    attempts = []

    # Attempt 1: Direct slug lookup (if we have it)
    if slug and not slug.startswith("_"):
        result = fetch(f"{GAMMA}/events/slug/{slug}")
        attempts.append(("gamma_slug", result))
        if "markets" in result:
            m = result["markets"][0] if result["markets"] else {}
            if m.get("resolved") or m.get("closed"):
                winner = m.get("winner")
                if winner:
                    won = (winner.upper() == trade["side"].upper())
                    return {"status": "won" if won else "lost",
                            "method": "gamma_slug",
                            "winner": winner,
                            "detail": m}

    # Attempt 2: CLOB price check (1.00 = won, 0.00 = lost)
    token_id = trade.get("token_id", "")
    if token_id:
        result = fetch(f"{CLOB}/price?token_id={token_id}&side=buy")
        attempts.append(("clob_price", result))
        price = float(result.get("price", 0.5)) if "price" in result else 0.5
        if price >= 0.99:
            return {"status": "won", "method": "clob_price", "price": price, "detail": result}
        if price <= 0.01:
            return {"status": "lost", "method": "clob_price", "price": price, "detail": result}

    # Attempt 3: Search by coin+timeframe prefix for recent markets
    for ts_offset in range(-5, 6):
        # The ETH trade at 16:54 UTC on Feb 28 → window_end around 17:09 UTC
        # Try a range of 15-minute windows around that time
        entry_ts = trade.get("entry_time", 0)
        if entry_ts:
            interval = 900 if timeframe == "15m" else 300
            window_start = (int(entry_ts) // interval) * interval + (ts_offset * interval)
            candidate_slug = f"{coin}-updown-{timeframe}-{window_start}"
            result = fetch(f"{GAMMA}/events/slug/{candidate_slug}")
            attempts.append((f"gamma_ts_scan_{ts_offset}", result))
            if "markets" in result:
                m = result["markets"][0] if result["markets"] else {}
                if m.get("resolved") or m.get("closed"):
                    winner = m.get("winner")
                    if winner:
                        won = (winner.upper() == trade["side"].upper())
                        return {"status": "won" if won else "lost",
                                "method": f"gamma_ts_scan (offset={ts_offset})",
                                "winner": winner,
                                "slug": candidate_slug,
                                "detail": m}

    return {"status": "unknown", "method": "all_failed",
            "attempts": len(attempts),
            "last_errors": [a[1].get("_error") for a in attempts if "_error" in a[1]]}


# ── Main settlement flow ──────────────────────────────────────────────────────

def run_settlement():
    print("\n" + "═"*60)
    print("  STUCK TRADE SETTLEMENT")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("═"*60)

    # Step 1: Find all open trades
    print("\n[1] Scanning for open trades...")
    wallet_data = load_all_wallet_data()

    if not wallet_data["sources"]:
        print("  ERROR: No wallet/trade files found in workspace!")
        print("  Checked:")
        for p in SEARCH_PATHS:
            print(f"    {p}")
        return

    open_trades = wallet_data["open_trades"]
    print(f"\n  Found {len(open_trades)} open trade(s)")

    if not open_trades:
        print("  No open trades to settle.")
        print("\n  If you know the trade details, enter them manually:")
        print("  Edit this script and add to MANUAL_TRADES below")
        return

    # Step 2: Settle each trade
    print("\n[2] Resolving trades with Polymarket API...")
    settlements = []

    for i, trade in enumerate(open_trades):
        print(f"\n  Trade {i+1}: {trade['coin']} {trade['side']} {trade['timeframe']} "
              f"@ {trade['entry_price']:.3f}")
        print(f"    Slug: {trade.get('market_slug', 'unknown')}")
        print(f"    Entry time: {datetime.fromtimestamp(trade['entry_time'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if trade['entry_time'] else 'unknown'}")

        resolution = resolve_trade(trade)
        print(f"    Resolution: {resolution['status'].upper()} (method: {resolution['method']})")

        if resolution["status"] in ("won", "lost"):
            won      = resolution["status"] == "won"
            payout   = trade["shares"] if won else 0.0
            net_pnl  = payout - trade["cost_usdc"]
            pnl_pct  = (net_pnl / trade["cost_usdc"] * 100) if trade["cost_usdc"] else 0

            print(f"    {'✅ WON' if won else '❌ LOST'}")
            print(f"    Cost:   ${trade['cost_usdc']:.4f}")
            print(f"    Payout: ${payout:.4f}")
            print(f"    PnL:    ${net_pnl:+.4f} ({pnl_pct:+.1f}%)")

            settlements.append({
                "trade":      trade,
                "resolution": resolution,
                "won":        won,
                "payout":     payout,
                "net_pnl":    net_pnl,
                "pnl_pct":    pnl_pct,
            })
        else:
            print(f"    ⚠ Could not determine outcome. Market may still be live or data unavailable.")
            print(f"    Attempts: {resolution.get('attempts', 0)}")

    # Step 3: Update wallet files
    if settlements:
        print(f"\n[3] Updating wallet files...")
        total_pnl = sum(s["net_pnl"] for s in settlements)

        for path in SEARCH_PATHS:
            if path.exists():
                try:
                    raw = json.loads(path.read_text())
                    modified = False

                    # Update balance
                    if "balance_usdc" in raw:
                        old_bal = raw["balance_usdc"]
                        raw["balance_usdc"] = round(old_bal + total_pnl, 4)
                        raw["total_pnl"] = round(raw.get("total_pnl", 0) + total_pnl, 4)
                        wins   = sum(1 for s in settlements if s["won"])
                        losses = sum(1 for s in settlements if not s["won"])
                        raw["trades_won"]  = raw.get("trades_won", 0) + wins
                        raw["trades_lost"] = raw.get("trades_lost", 0) + losses

                        # Clear open trades if field exists
                        if "open_trades" in raw:
                            raw["open_trades"] = []
                        if "positions" in raw:
                            raw["positions"] = {}

                        path.write_text(json.dumps(raw, indent=2))
                        print(f"  Updated: {path}")
                        print(f"    Balance: ${old_bal:.4f} → ${raw['balance_usdc']:.4f}")
                        modified = True

                except Exception as e:
                    print(f"  Warning: Could not update {path}: {e}")

        # Write settlements to the canonical trade file
        canonical = WORKSPACE / "trades_v4.json"
        existing  = {}
        try:
            existing = json.loads(canonical.read_text()) if canonical.exists() else {}
        except Exception:
            pass

        for s in settlements:
            trade_id = f"{s['trade']['coin']}_{s['trade']['side']}_{int(s['trade']['entry_time'])}"
            existing[trade_id] = {
                **s["trade"],
                "status":      "won" if s["won"] else "lost",
                "payout_usdc": s["payout"],
                "net_pnl":     s["net_pnl"],
                "net_pnl_pct": s["pnl_pct"],
                "settled_at":  time.time(),
                "settle_method": s["resolution"]["method"],
            }
            existing[trade_id].pop("_raw", None)

        canonical.write_text(json.dumps(existing, indent=2))
        print(f"  Wrote settlement record: {canonical}")

    # Step 4: Summary
    print(f"\n{'═'*60}")
    print(f"  SETTLEMENT SUMMARY")
    print(f"{'═'*60}")
    print(f"  Trades found:   {len(open_trades)}")
    print(f"  Settled:        {len(settlements)}")
    print(f"  Unknown/live:   {len(open_trades) - len(settlements)}")
    if settlements:
        total_pnl = sum(s["net_pnl"] for s in settlements)
        wins      = sum(1 for s in settlements if s["won"])
        print(f"  Wins/Losses:    {wins}W / {len(settlements)-wins}L")
        print(f"  Total PnL:      ${total_pnl:+.4f}")
    print(f"{'═'*60}\n")


# ── Manual override for known stuck trade ────────────────────────────────────
# If the auto-scanner can't find your trade, fill this in:
MANUAL_TRADE = {
    "enabled":      False,   # Set to True to use this
    "coin":         "ETH",
    "side":         "YES",
    "timeframe":    "15m",
    "entry_price":  0.025,
    "shares":       0.0,     # Fill in: how many shares you bought
    "cost_usdc":    0.0,     # Fill in: total USDC spent
    "entry_time":   0,       # Fill in: Unix timestamp of entry (16:54 UTC Feb 28)
    "market_slug":  "",      # Fill in if you have it: e.g. eth-updown-15m-1740758040
    "token_id":     "",      # Fill in if you have it
}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true",
                        help="Use MANUAL_TRADE override")
    args = parser.parse_args()

    if args.manual and MANUAL_TRADE["enabled"]:
        from trade_manager import TradeManager, Trade, settle_trade
        print("Using manual trade override...")
        # Feed into settlement directly
        trade = _normalize_trade(MANUAL_TRADE)
        resolution = resolve_trade(trade)
        print(f"Resolution: {resolution}")
    else:
        run_settlement()
