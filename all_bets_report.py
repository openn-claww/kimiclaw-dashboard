#!/usr/bin/env python3
"""Generate all-bets report for Discord"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "positions.db"

def get_all_positions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, market_slug, side, entry_price, size, entry_time, status, condition_id
        FROM positions
        ORDER BY entry_time DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def format_report():
    positions = get_all_positions()
    
    if not positions:
        return "📊 **ALL BETS TRACKER**\n\nNo bets found in database."
    
    lines = ["📊 **ALL BETS TRACKER**", f"🗓️ Report Time: Sunday, March 1st, 2026 — 5:32 AM (Asia/Shanghai)", ""]
    lines.append(f"📈 **Total Bets: {len(positions)} | Open: {len([p for p in positions if p['status']=='open'])} | Closed: {len([p for p in positions if p['status']=='closed'])}**")
    lines.append("")
    
    total_wagered = 0
    total_expected = 0
    
    for idx, p in enumerate(positions, 1):
        market = p['market_slug']
        side = p['side']
        entry_price = p['entry_price']
        size = p['size']
        status = p['status'].upper()
        condition_id = p['condition_id']
        
        # Amount wagered = size * entry_price
        amount_wagered = size * entry_price
        total_wagered += amount_wagered
        
        # Expected return calculation:
        # If YES wins: payout = size (you get $1 per share)
        # If NO wins: payout = size (you get $1 per share)
        # Expected return = size (potential payout) if open
        expected_return = size if status == "OPEN" else 0
        total_expected += expected_return
        
        # Format market name nicely
        if "btc-updown-5m" in market:
            market_display = f"BTC Up/Down 5m"
        elif "btc-updown-15m" in market:
            market_display = f"BTC Up/Down 15m"
        else:
            market_display = market
        
        # Extract timestamp from ID for display
        parts = p['id'].split('-')
        if len(parts) >= 4:
            ts = parts[-2] if parts[-1] in ['YES', 'NO'] else parts[-1]
            try:
                from datetime import datetime
                dt = datetime.fromtimestamp(int(ts))
                time_str = dt.strftime("%m/%d %H:%M")
            except:
                time_str = ""
        else:
            time_str = ""
        
        # Transaction link (Polygonscan)
        tx_link = f"https://polygonscan.com/tx/{condition_id}" if condition_id else "N/A"
        
        line = f"📊 **BET #{idx}** | Market: {market_display} ({time_str}) | Side: {side} | Amount: ${amount_wagered:.2f} | Status: {status} | Expected: ${expected_return:.2f} | Tx: <{tx_link}>"
        lines.append(line)
    
    lines.append("")
    lines.append(f"💰 **Total Wagered: ${total_wagered:.2f}**")
    lines.append(f"💵 **Total Expected Returns (if all win): ${total_expected:.2f}**")
    lines.append(f"📊 **Potential Profit: ${total_expected - total_wagered:.2f}**")
    
    return "\n".join(lines)

if __name__ == "__main__":
    print(format_report())
