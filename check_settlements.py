#!/usr/bin/env python3
"""
Settlement Monitor - Checks for resolved markets and calculates P&L
Run this periodically to update actual P&L
"""

import json
import requests
from datetime import datetime

STATE_FILE = "/root/.openclaw/workspace/wallet1_state.json"
TRADES_FILE = "/root/.openclaw/workspace/wallet1_new_trades.json"

def check_settlements():
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    except:
        print("No state file found")
        return
    
    positions = state.get('positions', [])
    balance = state.get('balance', 0)
    
    if not positions:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No open positions")
        return
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(positions)} positions...")
    
    settled = []
    total_pnl = 0
    
    for pos in positions:
        try:
            resp = requests.get(f"https://gamma-api.polymarket.com/markets/slug/{pos['slug']}", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('resolved', False):
                    winner = data.get('winningOutcomeIndex')
                    our_side = 0 if pos['side'] == 'YES' else 1
                    won = (winner == our_side)
                    
                    if won:
                        if pos['side'] == 'YES':
                            payout = pos['amount'] * (1/pos['entry_price']) * 0.95
                        else:
                            payout = pos['amount'] * (1/(1-pos['entry_price'])) * 0.95
                        profit = payout - pos['amount']
                        balance += payout
                        total_pnl += profit
                        print(f"  ✅ WIN: {pos['market']} {pos['side']} | +${profit:.2f}")
                    else:
                        total_pnl -= pos['amount']
                        print(f"  ❌ LOSS: {pos['market']} {pos['side']} | -${pos['amount']:.2f}")
                    
                    settled.append(pos)
        except Exception as e:
            pass
    
    # Remove settled positions
    for s in settled:
        positions.remove(s)
    
    # Update state
    state['balance'] = balance
    state['positions'] = positions
    state['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    
    print(f"\n  Settled: {len(settled)}")
    print(f"  Remaining positions: {len(positions)}")
    print(f"  Session P&L: ${total_pnl:.2f}")
    print(f"  Current balance: ${balance:.2f}")
    print(f"  Original bankroll: $686.93")
    print(f"  Total P&L vs start: ${balance - 686.93:.2f}")

if __name__ == "__main__":
    check_settlements()
