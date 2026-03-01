#!/usr/bin/env python3
"""
Reddit Alpha Scanner - Free social media monitoring
"""

import os
import json
import requests
from datetime import datetime

class RedditScanner:
    def __init__(self):
        # Free Reddit API (no key needed for read-only)
        self.base_url = "https://www.reddit.com"
        self.headers = {'User-Agent': 'PolymarketBot/1.0'}
        
        # Subreddits to monitor
        self.subreddits = [
            'cryptocurrency',
            'polymarket',
            'wallstreetbets',
            'defi',
            'ethfinance',
            'bitcoin'
        ]
    
    def scan_subreddit(self, subreddit):
        """Scan a subreddit for hot posts"""
        try:
            url = f"{self.base_url}/r/{subreddit}/hot.json?limit=10"
            resp = requests.get(url, headers=self.headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                posts = []
                
                for post in data['data']['children']:
                    p = post['data']
                    posts.append({
                        'title': p['title'],
                        'score': p['score'],
                        'comments': p['num_comments'],
                        'url': f"https://reddit.com{p['permalink']}"
                    })
                
                return posts
        except Exception as e:
            print(f"Error scanning r/{subreddit}: {e}")
        
        return []
    
    def find_alpha(self):
        """Find potential trading signals"""
        print("="*70)
        print("REDDIT ALPHA SCANNER")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*70)
        
        keywords = ['polymarket', 'prediction', 'bet', 'crypto', 'bitcoin', 'eth', 'airdrop']
        all_signals = []
        
        for subreddit in self.subreddits:
            print(f"\nScanning r/{subreddit}...")
            posts = self.scan_subreddit(subreddit)
            
            for post in posts:
                title_lower = post['title'].lower()
                if any(k in title_lower for k in keywords):
                    if post['score'] > 10:  # Popular posts only
                        print(f"  🎯 {post['title'][:60]}...")
                        print(f"     Score: {post['score']} | Comments: {post['comments']}")
                        all_signals.append({
                            'source': f'r/{subreddit}',
                            'title': post['title'],
                            'score': post['score'],
                            'url': post['url']
                        })
        
        print(f"\n{'='*70}")
        print(f"Found {len(all_signals)} potential signals")
        print("="*70)
        
        return all_signals

def main():
    scanner = RedditScanner()
    signals = scanner.find_alpha()

if __name__ == "__main__":
    main()
