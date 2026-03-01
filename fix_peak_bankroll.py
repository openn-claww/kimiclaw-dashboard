"""
fix_peak_bankroll.py
One-time repair script for corrupted peak_bankroll in risk_state.json.

Run ONCE with the bot stopped:
    python3 fix_peak_bankroll.py

Reads wallet trade history to calculate the mathematically correct peak,
then writes a repaired risk_state.json.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE      = Path("/root/.openclaw/workspace")
RISK_STATE     = WORKSPACE / "risk_state.json"
WALLET         = WORKSPACE / "wallet_v4_production.json"
RISK_BACKUP    = WORKSPACE / "risk_state.json.backup_before_fix"
STARTING_BANKROLL = 500.0   # Your known starting capital


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def calculate_correct_peak(wallet: dict, starting_bankroll: float) -> dict:
    """
    Walk through trade history chronologically and track the running bankroll.
    Peak = highest value the bankroll ever reached.
    Returns a dict with the reconstructed bankroll curve and correct peak.
    """
    trades = wallet.get("trades", [])

    # Sort by timestamp if available, otherwise assume chronological order
    def trade_time(t):
        ts = t.get("timestamp") or t.get("resolved_at") or t.get("entry_time") or ""
        return ts

    sorted_trades = sorted(trades, key=trade_time)

    running_balance = starting_bankroll
    peak            = starting_bankroll
    history         = [{"event": "start", "balance": running_balance, "peak": peak}]

    for trade in sorted_trades:
        # Try various field names your wallet might use
        net_pnl = (
            trade.get("net_pnl")
            or trade.get("pnl")
            or trade.get("profit")
            or 0.0
        )

        # Only count resolved/completed trades
        status = trade.get("status") or trade.get("state") or ""
        if status.lower() in ("open", "pending", "unresolved"):
            continue  # Skip open positions — don't count unrealized PnL

        running_balance += float(net_pnl)
        if running_balance > peak:
            peak = running_balance

        history.append({
            "event":      "trade",
            "market":     trade.get("market_id") or trade.get("slug") or "unknown",
            "net_pnl":    net_pnl,
            "balance":    running_balance,
            "peak":       peak,
        })

    return {
        "calculated_peak":    round(peak, 4),
        "calculated_current": round(running_balance, 4),
        "history":            history,
        "trade_count":        len([h for h in history if h["event"] == "trade"]),
    }


def repair_state(risk_state: dict, correct_peak: float, correct_current: float) -> dict:
    """
    Return a repaired copy of risk_state with validated peak and current.
    Does not modify the original dict.
    """
    repaired = dict(risk_state)

    # Core correction
    repaired["peak_bankroll"]    = correct_peak
    repaired["current_bankroll"] = correct_current

    # Sanity-check other fields while we're here
    if repaired.get("starting_bankroll", 0) <= 0:
        repaired["starting_bankroll"] = STARTING_BANKROLL

    # Lift the halt if it was triggered by the wrong peak
    # Only do this if halted AND halt_reason contains "drawdown" or "Drawdown"
    halt_reason = repaired.get("halt_reason", "")
    if repaired.get("halted") and "drawdown" in halt_reason.lower():
        print(f"  ↳ Lifting drawdown halt (cause: '{halt_reason}') — peak has been corrected")
        repaired["halted"]      = False
        repaired["halt_reason"] = ""
        repaired["halt_until"]  = None

    # Lift pause too if it was drawdown-related
    pause_reason = repaired.get("pause_reason", "")
    if repaired.get("paused") and "drawdown" in pause_reason.lower():
        repaired["paused"]       = False
        repaired["pause_reason"] = ""
        repaired["pause_until"]  = None

    # Add a repair audit entry to events log
    repair_event = {
        "ts":                 datetime.now(timezone.utc).isoformat(),
        "event":              "manual_repair",
        "details":            f"peak_bankroll corrected from {risk_state.get('peak_bankroll')} to {correct_peak}",
        "bankroll":           correct_current,
        "daily_pnl":          repaired.get("daily_pnl", 0.0),
        "drawdown_pct":       round((correct_peak - correct_current) / correct_peak * 100, 2) if correct_peak > 0 else 0.0,
        "consecutive_losses": repaired.get("consecutive_losses", 0),
        "open_positions":     repaired.get("open_positions", 0),
    }
    repaired.setdefault("events", []).append(repair_event)

    return repaired


def main():
    print("=" * 60)
    print("  Risk State Repair — Peak Bankroll Correction")
    print("=" * 60)

    # ── Load current state ────────────────────────────────────────
    if not RISK_STATE.exists():
        print(f"ERROR: {RISK_STATE} not found")
        return

    current_state = load_json(RISK_STATE)
    print(f"\nCurrent (corrupted) state:")
    print(f"  starting_bankroll: ${current_state.get('starting_bankroll', '?')}")
    print(f"  current_bankroll:  ${current_state.get('current_bankroll', '?')}")
    print(f"  peak_bankroll:     ${current_state.get('peak_bankroll', '?')}  ← WRONG")
    print(f"  halted:            {current_state.get('halted', False)}")
    print(f"  halt_reason:       {current_state.get('halt_reason', '')}")

    # ── Calculate correct peak from wallet history ────────────────
    if WALLET.exists():
        wallet = load_json(WALLET)
        print(f"\nWallet file found — reconstructing bankroll from trade history...")
        result = calculate_correct_peak(wallet, STARTING_BANKROLL)

        print(f"\nReconstruction result:")
        for step in result["history"]:
            if step["event"] == "start":
                print(f"  START:  balance=${step['balance']:.2f}  peak=${step['peak']:.2f}")
            else:
                pnl_str = f"+${step['net_pnl']:.2f}" if step['net_pnl'] >= 0 else f"-${abs(step['net_pnl']):.2f}"
                print(f"  TRADE:  {pnl_str:<10}  balance=${step['balance']:.2f}  peak=${step['peak']:.2f}  [{step['market']}]")

        correct_peak    = result["calculated_peak"]
        correct_current = result["calculated_current"]

        # Cross-check against what the state file says current is
        state_current = current_state.get("current_bankroll", 0)
        if abs(correct_current - state_current) > 1.0:
            print(f"\n  ⚠ WARNING: Wallet history gives current=${correct_current:.2f} "
                  f"but state file says ${state_current:.2f}")
            print(f"  Using state file's current_bankroll (${state_current:.2f}) as it may")
            print(f"  include the open BTC position.")
            correct_current = state_current

    else:
        # No wallet file — fall back to: peak = max(starting, current)
        print(f"\nNo wallet file found — using current_bankroll as peak")
        correct_current = current_state.get("current_bankroll", STARTING_BANKROLL)
        correct_peak    = max(STARTING_BANKROLL, correct_current)

    # ── Show what we're about to do ───────────────────────────────
    correct_drawdown = (correct_peak - correct_current) / correct_peak * 100 if correct_peak > 0 else 0
    print(f"\nCorrect values:")
    print(f"  peak_bankroll:  ${correct_peak:.2f}  (was ${current_state.get('peak_bankroll', '?')})")
    print(f"  current:        ${correct_current:.2f}")
    print(f"  drawdown:       {correct_drawdown:.2f}%  (was {((current_state.get('peak_bankroll',0) - current_state.get('current_bankroll',0)) / current_state.get('peak_bankroll',1) * 100):.1f}%)")

    # ── Confirm before writing ────────────────────────────────────
    confirm = input("\nApply this fix? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("Aborted — no changes made.")
        return

    # ── Backup current state ──────────────────────────────────────
    shutil.copy2(RISK_STATE, RISK_BACKUP)
    print(f"\nBackup saved: {RISK_BACKUP}")

    # ── Write repaired state atomically ──────────────────────────
    repaired = repair_state(current_state, correct_peak, correct_current)

    tmp = RISK_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(repaired, indent=2, default=str))
    json.loads(tmp.read_text())  # Validate before replacing
    tmp.replace(RISK_STATE)

    print(f"Repaired state written: {RISK_STATE}")

    # ── Verify ───────────────────────────────────────────────────
    verified = load_json(RISK_STATE)
    print(f"\nVerification — reading back repaired file:")
    print(f"  peak_bankroll:  ${verified['peak_bankroll']:.2f}  ✓")
    print(f"  current:        ${verified['current_bankroll']:.2f}  ✓")
    print(f"  halted:         {verified['halted']}")
    print(f"  halt_reason:    '{verified.get('halt_reason', '')}'")

    final_dd = (verified['peak_bankroll'] - verified['current_bankroll']) / verified['peak_bankroll'] * 100
    print(f"  drawdown:       {final_dd:.2f}%")

    if verified['halted']:
        print(f"\n  ⚠ Bot is still halted for reason: '{verified['halt_reason']}'")
        print(f"  This halt was NOT caused by the peak corruption — investigate separately.")
    else:
        print(f"\n  ✓ Bot is no longer halted. Safe to restart.")

    print(f"\nTo roll back: cp {RISK_BACKUP} {RISK_STATE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
