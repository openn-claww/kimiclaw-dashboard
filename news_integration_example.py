#!/usr/bin/env python3
"""
News API Integration Example for Master Bot
Fetches crypto news and generates sentiment signals.
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class NewsFeed:
    """Crypto news feed for trading signals."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.base_url = "https://newsapi.org/v2"
        self.last_check = datetime.now() - timedelta(minutes=5)
        self.cache = []
    
    def fetch_crypto_news(self) -> List[Dict]:
        """Fetch latest crypto news."""
        if not self.api_key:
            print("⚠️ No NEWSAPI_KEY set - using free tier limitations")
            return []
        
        try:
            url = f"{self.base_url}/everything"
            params = {
                "q": "bitcoin OR btc OR ethereum OR eth",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": self.api_key,
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])
                
                # Filter to last 5 minutes only
                recent = []
                for article in articles:
                    pub_time = datetime.fromisoformat(
                        article["publishedAt"].replace("Z", "+00:00")
                    )
                    if pub_time > self.last_check:
                        recent.append(article)
                
                self.last_check = datetime.now()
                self.cache = recent
                return recent
            else:
                print(f"NewsAPI error: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Failed to fetch news: {e}")
            return []
    
    def analyze_sentiment(self, title: str) -> Dict:
        """Simple keyword-based sentiment analysis."""
        title_lower = title.lower()
        
        # Bullish keywords
        bullish = [
            "surge", "rally", "bull", "moon", " ATH", "all time high",
            "adoption", "institutional", "etf approval", "pump", "breakout",
            "support", "buy", "accumulation", "whale buying"
        ]
        
        # Bearish keywords
        bearish = [
            "crash", "dump", "bear", "death cross", "sell-off", "liquidation",
            "hack", "exploit", "sec", "ban", "regulation", "rejection",
            "resistance", "sell", "distribution", "whale selling"
        ]
        
        bull_score = sum(1 for word in bullish if word in title_lower)
        bear_score = sum(1 for word in bearish if word in title_lower)
        
        if bull_score > bear_score:
            return {"sentiment": "BULLISH", "score": min(bull_score * 0.3, 1.0)}
        elif bear_score > bull_score:
            return {"sentiment": "BEARISH", "score": min(bear_score * 0.3, 1.0)}
        else:
            return {"sentiment": "NEUTRAL", "score": 0.0}
    
    def get_trading_signal(self) -> Optional[Dict]:
        """Generate trading signal from latest news."""
        news = self.fetch_crypto_news()
        
        if not news:
            return None
        
        # Aggregate sentiment
        total_bull = 0
        total_bear = 0
        
        for article in news:
            sentiment = self.analyze_sentiment(article["title"])
            if sentiment["sentiment"] == "BULLISH":
                total_bull += sentiment["score"]
            elif sentiment["sentiment"] == "BEARISH":
                total_bear += sentiment["score"]
        
        # Generate signal if strong bias
        if total_bull > total_bear * 2 and total_bull > 1.0:
            return {
                "action": "BUY_YES",
                "confidence": min(total_bull / 3, 1.0),
                "reason": f"News sentiment: {total_bull:.1f} bullish vs {total_bear:.1f} bearish",
                "articles": len(news)
            }
        elif total_bear > total_bull * 2 and total_bear > 1.0:
            return {
                "action": "BUY_NO",
                "confidence": min(total_bear / 3, 1.0),
                "reason": f"News sentiment: {total_bear:.1f} bearish vs {total_bull:.1f} bullish",
                "articles": len(news)
            }
        
        return None

# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("NEWS API INTEGRATION TEST")
    print("=" * 70)
    
    # Get free API key from: https://newsapi.org/register
    feed = NewsFeed()
    
    print("\nFetching crypto news...")
    news = feed.fetch_crypto_news()
    
    if news:
        print(f"\nFound {len(news)} recent articles:")
        for article in news[:5]:
            sentiment = feed.analyze_sentiment(article["title"])
            emoji = "🟢" if sentiment["sentiment"] == "BULLISH" else "🔴" if sentiment["sentiment"] == "BEARISH" else "⚪"
            print(f"\n{emoji} {article['title'][:80]}...")
            print(f"   Sentiment: {sentiment['sentiment']} ({sentiment['score']:.2f})")
            print(f"   Source: {article['source']['name']}")
        
        signal = feed.get_trading_signal()
        if signal:
            print(f"\n📊 TRADING SIGNAL:")
            print(f"   Action: {signal['action']}")
            print(f"   Confidence: {signal['confidence']:.1%}")
            print(f"   Reason: {signal['reason']}")
        else:
            print("\n📊 No strong signal from news")
    else:
        print("\n⚠️ No news fetched - check API key")
    
    print("\n" + "=" * 70)
    print("To use in production:")
    print("1. Get free API key from newsapi.org")
    print("2. Set export NEWSAPI_KEY='your_key'")
    print("3. Call feed.get_trading_signal() every 30 seconds")
    print("=" * 70)
