#!/usr/bin/env python3
"""
Social Media Strategy Monitor
Scans Twitter and Reddit for new Polymarket/trading strategies
Reports findings to user BEFORE applying
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class StrategyFind:
    source: str  # twitter, reddit
    author: str
    content: str
    url: str
    engagement: int  # likes, upvotes
    strategy_type: str  # arbitrage, hedging, technical, etc.
    confidence: int  # 1-10 based on engagement/author credibility
    timestamp: datetime
    requires_review: bool = True  # Always True - never auto-apply

class SocialMonitor:
    """Monitor social media for trading strategies"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.twitter_bearer = os.getenv('TWITTER_BEARER_TOKEN', '')
        self.reddit_client_id = os.getenv('REDDIT_CLIENT_ID', '')
        self.reddit_secret = os.getenv('REDDIT_SECRET', '')
        
        # Keywords to track
        self.keywords = [
            'polymarket strategy',
            'prediction market',
            'arbitrage crypto',
            'weather trading',
            'short term trading',
            '15 minute strategy',
            'btc up down strategy',
            'polymarket edge',
            'market making crypto'
        ]
        
        # Trusted accounts to prioritize
        self.trusted_twitter = [
            'Polymarket',
            'ChainstackHQ',
            'VoltAgent'
        ]
        
        # Subreddits to monitor
        self.subreddits = [
            'Polymarket',
            'CryptoCurrency',
            'algotrading',
            'wallstreetbets'
        ]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def search_twitter(self) -> List[StrategyFind]:
        """Search Twitter for strategy discussions"""
        finds = []
        
        if not self.twitter_bearer:
            print("⚠️  Twitter API not configured (need TWITTER_BEARER_TOKEN)")
            return finds
        
        headers = {"Authorization": f"Bearer {self.twitter_bearer}"}
        
        for keyword in self.keywords[:3]:  # Limit to avoid rate limits
            try:
                url = f"https://api.twitter.com/2/tweets/search/recent"
                params = {
                    "query": f"{keyword} -is:retweet lang:en",
                    "max_results": 10,
                    "tweet.fields": "public_metrics,created_at,author_id"
                }
                
                async with self.session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for tweet in data.get('data', []):
                            metrics = tweet.get('public_metrics', {})
                            engagement = metrics.get('like_count', 0) + metrics.get('retweet_count', 0)
                            
                            finds.append(StrategyFind(
                                source='twitter',
                                author=tweet.get('author_id', 'unknown'),
                                content=tweet.get('text', '')[:200],
                                url=f"https://twitter.com/i/web/status/{tweet.get('id')}",
                                engagement=engagement,
                                strategy_type=self._classify_strategy(tweet.get('text', '')),
                                confidence=min(10, engagement // 10),
                                timestamp=datetime.now()
                            ))
            except Exception as e:
                print(f"Twitter search error: {e}")
        
        return finds
    
    async def search_reddit(self) -> List[StrategyFind]:
        """Search Reddit for strategy discussions"""
        finds = []
        
        for subreddit in self.subreddits[:2]:  # Limit to avoid rate limits
            try:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    "q": "strategy OR edge OR arbitrage",
                    "sort": "new",
                    "limit": 5
                }
                headers = {"User-Agent": "PolyClawBot/1.0"}
                
                async with self.session.get(url, params=params, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        posts = data.get('data', {}).get('children', [])
                        
                        for post in posts:
                            p = post.get('data', {})
                            engagement = p.get('score', 0) + p.get('num_comments', 0)
                            
                            finds.append(StrategyFind(
                                source='reddit',
                                author=p.get('author', 'unknown'),
                                content=p.get('title', '')[:200],
                                url=f"https://reddit.com{p.get('permalink', '')}",
                                engagement=engagement,
                                strategy_type=self._classify_strategy(p.get('title', '') + p.get('selftext', '')),
                                confidence=min(10, engagement // 5),
                                timestamp=datetime.now()
                            ))
            except Exception as e:
                print(f"Reddit search error: {e}")
        
        return finds
    
    def _classify_strategy(self, text: str) -> str:
        """Classify the type of strategy"""
        text_lower = text.lower()
        
        if 'arbitrage' in text_lower:
            return 'arbitrage'
        elif 'hedge' in text_lower or 'hedging' in text_lower:
            return 'hedging'
        elif 'weather' in text_lower:
            return 'weather_trading'
        elif '15 min' in text_lower or '15min' in text_lower:
            return 'short_term'
        elif 'technical' in text_lower or 'chart' in text_lower:
            return 'technical_analysis'
        elif 'bot' in text_lower or 'automated' in text_lower:
            return 'automation'
        else:
            return 'general'
    
    async def run_scan(self) -> Dict:
        """Full social media scan"""
        print("🔍 Scanning social media for trading strategies...")
        
        twitter_finds = await self.search_twitter()
        reddit_finds = await self.search_reddit()
        
        all_finds = twitter_finds + reddit_finds
        
        # Sort by confidence
        all_finds.sort(key=lambda x: x.confidence, reverse=True)
        
        # Filter high-confidence finds (>= 6)
        high_confidence = [f for f in all_finds if f.confidence >= 6]
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_found": len(all_finds),
            "high_confidence": len(high_confidence),
            "twitter_count": len(twitter_finds),
            "reddit_count": len(reddit_finds),
            "finds": [
                {
                    "source": f.source,
                    "author": f.author,
                    "content": f.content,
                    "url": f.url,
                    "engagement": f.engagement,
                    "strategy_type": f.strategy_type,
                    "confidence": f.confidence,
                    "requires_review": True  # Always require user approval
                }
                for f in high_confidence[:5]  # Top 5 only
            ]
        }

def generate_report(scan_results: Dict) -> str:
    """Generate user-friendly report"""
    if scan_results['high_confidence'] == 0:
        return f"""
🌐 Social Media Strategy Scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}

No high-confidence strategies found in this scan.

Checked:
- Twitter (Polymarket, trading keywords)
- Reddit (r/Polymarket, r/CryptoCurrency, r/algotrading)

Next scan: In 6 hours
"""
    
    report = f"""
🌐 Social Media Strategy Scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}

⚠️  FOUND {scan_results['high_confidence']} STRATEGIES REQUIRING REVIEW

These strategies were found but NOT applied. Review before using:

"""
    
    for i, find in enumerate(scan_results['finds'], 1):
        report += f"""
{i}. [{find['strategy_type'].upper()}] from {find['source']}
   Author: {find['author']}
   Engagement: {find['engagement']} | Confidence: {find['confidence']}/10
   Content: {find['content'][:100]}...
   🔗 {find['url']}
   
   ⚠️  STATUS: PENDING YOUR REVIEW
   Reply "APPLY STRATEGY {i}" to implement
   Reply "SKIP" to ignore

"""
    
    report += """
📝 NOTES:
- All strategies require your explicit approval
- I will NEVER auto-apply social media strategies
- Review engagement and credibility before applying
- Consider paper trading first

Next scan: In 6 hours
"""
    
    return report

async def main():
    async with SocialMonitor() as monitor:
        results = await monitor.run_scan()
        report = generate_report(results)
        print(report)
        
        # Save to file for cron job to pick up
        with open('/root/.openclaw/workspace/social_scan_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

if __name__ == "__main__":
    asyncio.run(main())
