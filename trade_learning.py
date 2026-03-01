#!/usr/bin/env python3
"""
Trade Learning System
Logs lessons from every win/loss to avoid repeating mistakes
"""

import json
import time
from datetime import datetime

LESSONS_FILE = "/root/.openclaw/workspace/trading_lessons.json"

def load_lessons():
    try:
        with open(LESSONS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_lessons(lessons):
    with open(LESSONS_FILE, 'w') as f:
        json.dump(lessons, f, indent=2)

def add_lesson(trade_result, market, side, entry_price, exit_price, amount, reason):
    """Add lesson from trade"""
    lessons = load_lessons()
    
    lesson = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market': market,
        'result': trade_result,  # WON or LOST
        'side': side,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'amount': amount,
        'profit_loss': (exit_price - entry_price) * amount,
        'reason': reason,
        'lesson': extract_lesson(trade_result, entry_price, reason)
    }
    
    lessons.append(lesson)
    save_lessons(lessons)
    
    print(f"Lesson logged: {lesson['lesson']}")

def extract_lesson(result, entry_price, reason):
    """Extract key lesson from trade"""
    if result == 'WON':
        if entry_price < 0.5:
            return "Buying cheap (\u003c0.5) works - continue"
        else:
            return "Even expensive entries can win with strong edge"
    else:
        if entry_price > 0.7:
            return "Avoid expensive entries (\u003e0.7) - low upside"
        elif 'momentum' in reason.lower() and '0.06%' in reason:
            return "NEVER trade on 0.06% moves - it's noise"
        else:
            return "Review data quality - insufficient edge"

def get_lessons_for_market(market_type):
    """Get relevant lessons for market type"""
    lessons = load_lessons()
    relevant = [l for l in lessons if market_type.lower() in l.get('market', '').lower()]
    return relevant[-3:]  # Last 3 lessons

if __name__ == "__main__":
    # Example: Log lesson from Feb 23 win
    add_lesson(
        trade_result='WON',
        market='BTC >$66K Feb 23',
        side='YES',
        entry_price=0.61,
        exit_price=1.0,
        amount=20,
        reason='BTC at $66,309 above threshold, undervalued at $0.61'
    )
    
    print("\\nAll lessons:")
    for l in load_lessons():
        print(f"- {l['lesson']}")
