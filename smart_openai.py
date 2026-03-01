import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_live_markets():
    try:
        resp = requests.get("https://gamma-api.polymarket.com/markets?active=true&limit=80", timeout=10)
        return resp.json()
    except:
        return []

def ask_ai_for_best_trades(markets_data):
    # Filter for short-term active markets only
    short_term = []
    for m in markets_data:
        q = m.get('question', '').lower()
        # Check if it's a short-term market
        if any(term in q for term in ['5 min', '15 min', '30 min', '1 hour', 'hourly', 'today', 'feb 22', 'feb 23']):
            # Check if market is still active (not closed)
            if not m.get('closed', False) and m.get('active', True):
                short_term.append({
                    'q': m.get('question', 'Unknown')[:80],
                    'yes': round(float(m.get('yesAsk', 0)), 2),
                    'no': round(float(m.get('noAsk', 0)), 2),
                    'vol': m.get('volume', 0)
                })
    
    if not short_term:
        return {"opportunities": [], "note": "No active short-term markets found"}
    
    prompt = f"""
You are a professional Polymarket trader with 96% win rate.
Focus ONLY on SHORT-TERM markets (resolving within hours).

Current active short-term markets: {json.dumps(short_term[:20], indent=2)}

Return ONLY the BEST 1-2 trading opportunities in this exact JSON format:

{{
  "opportunities": [
    {{
      "market": "full exact market question",
      "side": "Yes or No",
      "confidence": 70-100,
      "edge": 6.5-35,
      "reason": "short powerful reason",
      "suggested_bet": 1-5
    }}
  ]
}}

If no good opportunities, return empty opportunities array.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.15,
        max_tokens=900
    )
    
    try:
        return json.loads(response.choices[0].message.content)
    except:
        return {"opportunities": []}
