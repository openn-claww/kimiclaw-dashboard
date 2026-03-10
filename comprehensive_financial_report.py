#!/usr/bin/env python3
"""
comprehensive_financial_report.py - Generate detailed trading report
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List
import json

@dataclass
class Transaction:
    date: str
    market: str
    market_id: str
    side: str
    invested: float
    entry_price: float
    exit_price: float
    gross_return: float
    fees: float
    net_pnl: float
    status: str
    notes: str

# All transactions from trading journal
# Fees: Polymarket charges 2% on the entry amount (invested amount)
FEE_RATE = 0.02

transactions = [
    # Date, Market, ID, Side, Invested, Entry, Exit, Gross, Fees, Net, Status, Notes
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.42, 1.00, 1.38, 0.02, 1.36, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.53, 1.00, 0.89, 0.02, 0.87, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.62, 1.00, 0.61, 0.02, 0.59, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.68, 1.00, 0.47, 0.02, 0.45, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.715, 1.00, 0.40, 0.02, 0.38, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.76, 1.00, 0.32, 0.02, 0.30, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC >$66K Feb 19", "N/A", "YES", 1.00, 0.92, 1.00, 0.09, 0.02, 0.07, "WIN", "Resolved YES"),
    Transaction("2026-02-19", "BTC dip $55K Feb 28", "1303400", "NO", 1.00, 0.89, 1.00, 1.00, 0.02, 0.98, "WIN", "BTC did NOT dip"),
    Transaction("2026-02-19", "BTC $75K Feb 28", "1345641", "NO", 1.00, 0.845, 1.00, 1.00, 0.02, 0.98, "WIN", "BTC did NOT reach $75K"),
    Transaction("2026-02-19", "Iran strike Feb 20", "Iran Feb 20", "NO", 1.00, 0.93, 1.00, 0.07, 0.02, 0.05, "WIN", "No strike occurred"),
    Transaction("2026-02-19", "Jesus return 2027", "703258", "NO", 2.00, 0.97, 0.9625, -0.01, 0.04, -0.05, "OPEN", "Long-term hold - Dec 31, 2026"),
    Transaction("2026-02-19", "Iran strike Feb 21", "1386650", "YES", 0.50, 0.075, 0.00, -0.50, 0.01, -0.51, "LOSS", "Resolved NO"),
    Transaction("2026-02-19", "Iran strike Feb 28", "1198423", "YES", 1.00, 0.235, 1.00, 0.77, 0.02, 0.75, "WIN", "Resolved NO - returned even money"),
    Transaction("2026-02-19", "Warriors game", "1385457", "YES", 8.00, 0.665, 0.00, -8.00, 0.16, -8.16, "LOSS", "Warriors won but position lost?"),
    Transaction("2026-02-19", "BTC down prediction", "1401343", "YES", 5.00, 0.31, 0.00, -5.00, 0.10, -5.10, "LOSS", "BTC went DOWN - wrong side"),
    Transaction("2026-02-19", "BTC down prediction", "1402947", "YES", 2.90, 0.0225, 0.00, -2.90, 0.06, -2.96, "LOSS", "BTC went DOWN - wrong side"),
    Transaction("2026-02-19", "BTC range", "1382242", "NO", 5.00, 0.61, 0.00, -5.00, 0.10, -5.10, "LOSS", "BTC was in range"),
    Transaction("2026-02-19", "BTC below $68K", "1382273", "YES", 5.00, 0.60, 0.00, -5.00, 0.10, -5.10, "LOSS", "BTC below $68K"),
    Transaction("2026-02-22", "Spurs vs Pistons", "1388774", "YES", 4.50, 0.47, 1.00, 2.39, 0.09, 2.30, "WIN", "Spurs won 114-103"),
    Transaction("2026-02-22", "Blazers vs Suns", "1385475", "YES", 4.50, 0.47, 1.00, 2.39, 0.09, 2.30, "WIN", "Blazers won"),
]

# Calculate summary statistics
total_invested = sum(t.invested for t in transactions)
total_gross_pnl = sum(t.gross_return for t in transactions)
total_fees = sum(t.fees for t in transactions)
total_net_pnl = sum(t.net_pnl for t in transactions)

wins = [t for t in transactions if t.status == "WIN"]
losses = [t for t in transactions if t.status == "LOSS"]
open_positions = [t for t in transactions if t.status == "OPEN"]

gross_wins = sum(t.gross_return for t in wins)
gross_losses = sum(t.gross_return for t in losses)
net_wins = sum(t.net_pnl for t in wins)
net_losses = sum(t.net_pnl for t in losses)

# Starting capital (need to estimate based on current balance)
# Current balance is $11.03 after all redemptions
# So starting capital = current + total invested - total returned
# But we need to calculate more carefully

# From the data, let's trace the balance
# Ending balance = $11.03 (stated in journal)
# This is after all redemptions and current open position

# Calculate returns from resolved positions
resolved = [t for t in transactions if t.status in ["WIN", "LOSS"]]
total_resolved_invested = sum(t.invested for t in resolved)
total_resolved_returned = sum(t.invested + t.gross_return for t in resolved)

# Open position value
open_invested = sum(t.invested for t in open_positions)
open_current_value = sum(t.invested + t.gross_return for t in open_positions)

# Estimate starting capital
# Ending balance = Starting + Net PnL from resolved + Current value of open
# $11.03 = Starting + total_net_pnl_from_resolved + open_current_value
# But this doesn't include the open position which is still held

# Actually, current balance of $11.03 is USDC.e after redemptions
# It doesn't include the value of open position #703258

# Let's recalculate:
# The open position (Jesus return 2027) was bought for $2 at $0.97
# Current price is $0.9625, so current value = $2 * (0.9625/0.97) = $1.985
# Or simply: invested + gross_return = $2 + (-$0.01) = $1.99

open_position_value = open_positions[0].invested + open_positions[0].gross_return if open_positions else 0
total_account_value = 11.03 + open_position_value

# Starting capital = total resolved invested (since that's what was put in)
# But some of those trades made money, some lost
# Let's calculate based on net flow

# Actually, let's look at this differently
# Total amount ever invested = $51.30
# Total fees paid = $1.03
# Current liquid balance = $11.03
# Current open position value = $1.99
# Total returned from wins = sum of (invested + gross_return) for wins
# Total lost from losses = sum of invested for losses (since they go to 0)

print("=" * 100)
print("                     COMPREHENSIVE FINANCIAL REPORT")
print("                     Polymarket Trading - Feb 19 to Mar 8, 2026")
print("=" * 100)
print()

print("SECTION 1: COMPLETE TRANSACTION LEDGER")
print("-" * 100)
print(f"{'Date':<12} {'Market':<25} {'Side':<6} {'Invested':>10} {'Entry':>8} {'Exit':>8} {'Gross P&L':>10} {'Fees':>8} {'Net P&L':>10} {'Status':<8}")
print("-" * 100)

running_balance = 0
for t in transactions:
    print(f"{t.date:<12} {t.market:<25} {t.side:<6} ${t.invested:>9.2f} ${t.entry_price:>7.3f} ${t.exit_price:>7.3f} ${t.gross_return:>9.2f} ${t.fees:>7.2f} ${t.net_pnl:>9.2f} {t.status:<8}")

print("-" * 100)
print()

print("SECTION 2: SUMMARY STATISTICS")
print("-" * 100)
print(f"Total Transactions:           {len(transactions)}")
print(f"Winning Trades:               {len(wins)}")
print(f"Losing Trades:                {len(losses)}")
print(f"Open Positions:               {len(open_positions)}")
print(f"Win Rate:                     {len(wins)/(len(wins)+len(losses))*100:.1f}%")
print()
print(f"Total Capital Invested:       ${total_invested:,.2f}")
print(f"Total Fees Paid (2%):         ${total_fees:,.2f}")
print()
print(f"Gross Profit (Wins):          ${gross_wins:,.2f}")
print(f"Gross Loss (Losses):          ${gross_losses:,.2f}")
print(f"Gross P&L:                    ${total_gross_pnl:,.2f}")
print()
print(f"Net Profit (after fees):      ${net_wins:,.2f}")
print(f"Net Loss (after fees):        ${net_losses:,.2f}")
print(f"NET P&L:                      ${total_net_pnl:,.2f}")
print()

print("SECTION 3: ACCOUNT BALANCE RECONCILIATION")
print("-" * 100)

# Calculate starting capital
# We know ending liquid balance is $11.03
# We know the open position is worth ~$1.99
# Total account value = $13.02

# Net P&L from all transactions = -$10.40
# So starting capital = ending value - net pnl = $13.02 - (-$10.40) = $23.42

# But let's verify: sum of all invested = $51.30
# This seems like multiple redeployments of capital

# Actually, the $11.03 is the CURRENT balance after redemptions
# The starting capital would be different

# Let's calculate based on actual flows:
# Money in: Sum of all invested amounts (each trade)
# Money out: Redemptions from wins

# For wins: you get back invested + gross_return
# For losses: you get back $0

# Let's trace it properly
total_wins_returned = sum(t.invested + t.gross_return for t in wins)
total_losses_invested = sum(t.invested for t in losses)

# If we started with X, and invested in all these trades:
# Current liquid = Starting - total_invested + total_wins_returned
# $11.03 = Starting - $51.30 + $19.18
# Starting = $11.03 + $51.30 - $19.18 = $43.15

starting_capital_estimate = 11.03 + total_invested - total_wins_returned

print(f"Estimated Starting Capital:   ${starting_capital_estimate:,.2f}")
print(f"Total Invested (all trades):  ${total_invested:,.2f}")
print(f"Returned from Wins:           ${total_wins_returned:,.2f}")
print(f"Lost from Losses:             ${total_losses_invested:,.2f}")
print()
print(f"Current Liquid Balance:       $11.03 (USDC.e)")
print(f"Open Position Value:          ${open_position_value:,.2f} (Market #703258)")
print(f"TOTAL ACCOUNT VALUE:          ${11.03 + open_position_value:,.2f}")
print()
print(f"Total Return:                 ${total_net_pnl:,.2f} ({total_net_pnl/starting_capital_estimate*100:.1f}%)")
print()

print("SECTION 4: TRADE BREAKDOWN BY CATEGORY")
print("-" * 100)

# Group by type
btc_trades = [t for t in transactions if "BTC" in t.market]
sports_trades = [t for t in transactions if any(x in t.market for x in ["Spurs", "Blazers", "Warriors"])]
iran_trades = [t for t in transactions if "Iran" in t.market]
other_trades = [t for t in transactions if t not in btc_trades + sports_trades + iran_trades]

categories = [
    ("BTC/Crypto", btc_trades),
    ("Sports", sports_trades),
    ("Geopolitical (Iran)", iran_trades),
    ("Other", other_trades),
]

for name, trades in categories:
    if trades:
        cat_invested = sum(t.invested for t in trades)
        cat_gross = sum(t.gross_return for t in trades)
        cat_net = sum(t.net_pnl for t in trades)
        cat_wins = len([t for t in trades if t.status == "WIN"])
        cat_losses = len([t for t in trades if t.status == "LOSS"])
        print(f"{name:<20} Trades: {len(trades):>2}  Wins: {cat_wins:>2}  Losses: {cat_losses:>2}  Invested: ${cat_invested:>7.2f}  Net P&L: ${cat_net:>7.2f}")

print()

print("SECTION 5: INDIVIDUAL WINNERS & LOSERS")
print("-" * 100)
print("TOP 5 WINNERS:")
sorted_wins = sorted(wins, key=lambda x: x.net_pnl, reverse=True)[:5]
for i, t in enumerate(sorted_wins, 1):
    print(f"  {i}. {t.market} ({t.side}): +${t.net_pnl:.2f} net")

print()
print("TOP 5 LOSERS:")
sorted_losses = sorted(losses, key=lambda x: x.net_pnl)[:5]
for i, t in enumerate(sorted_losses, 1):
    print(f"  {i}. {t.market} ({t.side}): ${t.net_pnl:.2f} net")

print()

print("SECTION 6: KEY METRICS")
print("-" * 100)
avg_win = net_wins / len(wins) if wins else 0
avg_loss = net_losses / len(losses) if losses else 0
profit_factor = abs(gross_wins / gross_losses) if gross_losses != 0 else float('inf')

print(f"Average Win:                  ${avg_win:.2f}")
print(f"Average Loss:                 ${avg_loss:.2f}")
print(f"Profit Factor:                {profit_factor:.2f}")
print(f"Largest Single Win:           ${max(t.net_pnl for t in wins):.2f}")
print(f"Largest Single Loss:          ${min(t.net_pnl for t in losses):.2f}")
print()

print("=" * 100)
print("END OF REPORT")
print("=" * 100)

# Save to file
report_data = {
    "generated_at": datetime.now().isoformat(),
    "period": "2026-02-19 to 2026-03-08",
    "summary": {
        "total_transactions": len(transactions),
        "wins": len(wins),
        "losses": len(losses),
        "open_positions": len(open_positions),
        "win_rate": len(wins)/(len(wins)+len(losses))*100,
        "total_invested": total_invested,
        "total_fees": total_fees,
        "gross_pnl": total_gross_pnl,
        "net_pnl": total_net_pnl,
        "starting_capital_estimate": starting_capital_estimate,
        "current_liquid_balance": 11.03,
        "open_position_value": open_position_value,
        "total_account_value": 11.03 + open_position_value,
        "total_return_pct": total_net_pnl/starting_capital_estimate*100,
    },
    "transactions": [
        {
            "date": t.date,
            "market": t.market,
            "market_id": t.market_id,
            "side": t.side,
            "invested": t.invested,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "gross_return": t.gross_return,
            "fees": t.fees,
            "net_pnl": t.net_pnl,
            "status": t.status,
            "notes": t.notes
        }
        for t in transactions
    ]
}

with open('/root/.openclaw/workspace/financial_report.json', 'w') as f:
    json.dump(report_data, f, indent=2)

print()
print("Report saved to: financial_report.json")
