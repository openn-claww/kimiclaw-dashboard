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

def test_grok_model(model_name, api_key):
    """Test a specific Grok model"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello and confirm this model works"}
        ],
        "temperature": 0.5,
        "max_tokens": 50
    }
    
    try:
        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"success": True, "response": content}
        else:
            return {"success": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def test_all_models():
    """Test all available Grok models"""
    
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("No API key found")
        return
    
    models = [
        "grok-beta",
        "grok-2-latest", 
        "grok-2",
        "grok-1",
        "grok-4-1-fast-reasoning"
    ]
    
    print("="*70)
    print("TESTING ALL GROK MODELS")
    print("="*70)
    
    for model in models:
        print(f"\nTesting: {model}")
        result = test_grok_model(model, api_key)
        
        if result["success"]:
            print(f"  ✅ SUCCESS: {result['response'][:50]}...")
        else:
            print(f"  ❌ FAILED: {result['error']}")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    test_all_models()
