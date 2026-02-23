import os
import json
import time
import requests

def get_live_markets():
    try:
        resp = requests.get("https://gamma-api.polymarket.com/markets?active=true&limit=80", timeout=10)
        return resp.json()
    except:
        return []

def ask_grok_for_best_trades(markets_data):
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        return {"opportunities": [], "error": "No API key"}
    
    # Simplify markets data
    simplified = []
    for m in markets_data[:40]:
        try:
            vol = m.get("volume", 0)
            if isinstance(vol, str):
                vol = float(vol.replace('K', '000').replace('M', '000000').replace('$', '').replace(',', ''))
            simplified.append({
                "q": m.get("question", "Unknown")[:80],
                "yes": round(float(m.get("yesAsk", 0)), 2),
                "no": round(float(m.get("noAsk", 0)), 2),
                "vol": round(vol/1000, 0)
            })
        except:
            continue
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "grok-4-1-fast-reasoning",
        "messages": [
            {"role": "system", "content": "You are a professional Polymarket trader with 96% win rate. Return only JSON."},
            {"role": "user", "content": f"""Analyze these markets and return BEST 1-2 opportunities:
{json.dumps(simplified, indent=2)}

Return ONLY this JSON format:
{{
  "opportunities": [
    {{
      "market": "exact question",
      "side": "Yes or No",
      "confidence": 70-100,
      "edge": 6.5-35,
      "reason": "short reason",
      "suggested_bet": 1-5
    }}
  ]
}}"""}
        ],
        "temperature": 0.15,
        "max_tokens": 800
    }
    
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # Extract JSON from response
                try:
                    return json.loads(content)
                except:
                    # Try to find JSON in response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    return {"opportunities": [], "raw": content[:200]}
            else:
                print(f"Attempt {attempt+1}: HTTP {resp.status_code}")
                time.sleep(5)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(5)
    
    return {"opportunities": []}
