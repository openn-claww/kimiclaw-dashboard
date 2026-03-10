#!/usr/bin/env python3
"""Discord notifier for bot trades - called via subprocess to avoid blocking"""
import os, sys, json, requests

WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
if not WEBHOOK_URL:
    sys.exit(0)

try:
    trade = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    
    market = trade.get('market', 'Unknown')
    side = trade.get('side', '?')
    amount = trade.get('amount', 0)
    price = trade.get('entry_price', 0)
    edge = trade.get('edge_pct', 0)
    win_prob = trade.get('win_probability', 50)
    reasoning = trade.get('reasoning', '')
    tx_hash = trade.get('tx_hash', '')
    is_warmup = trade.get('is_warmup', False)
    
    color = 0x00ff00 if side == 'YES' else 0xff0000
    warmup_badge = "🔰 WARMUP " if is_warmup else ""
    
    embed = {
        "title": f"{warmup_badge}🎯 Trade Executed: {market}",
        "color": color,
        "fields": [
            {"name": "Side", "value": side, "inline": True},
            {"name": "Amount", "value": f"${amount:.2f}", "inline": True},
            {"name": "Entry Price", "value": f"${price:.3f}", "inline": True},
            {"name": "Edge", "value": f"{edge:.2f}%", "inline": True},
            {"name": "Win Probability", "value": f"{win_prob:.1f}%", "inline": True},
            {"name": "TX Hash", "value": tx_hash[:20] + "..." if tx_hash else "Pending", "inline": False},
            {"name": "Reasoning", "value": reasoning[:500] if reasoning else "Arbitrage signal", "inline": False}
        ],
        "timestamp": trade.get('timestamp_utc', ''),
        "footer": {"text": "PolyARB Bot v6"}
    }
    
    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
except Exception as e:
    print(f"Discord notify error: {e}")
    sys.exit(1)
