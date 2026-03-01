#!/usr/bin/env python3
"""
Reddit Monitor with VPN/Proxy workaround
"""

import os
import json
import time
import requests
from datetime import datetime

class RedditMonitor:
    def __init__(self):
        self.subreddits = [
            'cryptocurrency',
            'polymarket', 
            'wallstreetbets',
            'defi',
            'ethfinance',
            'bitcoin'
        ]
        
        # Try multiple Reddit instances
        self.endpoints = [
            'https://www.reddit.com',
            'https://old.reddit.com',
            'https://i.reddit.com'
        ]
    
    def fetch_with_retry(self, url, headers, max_retries=3):
        """Fetch with retry and different user agents"""
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        
        for attempt in range(max_retries):
            try:
                headers['User-Agent'] = user_agents[attempt % len(user_agents)]
                resp = requests.get(url, headers=headers, timeout=15)
                
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:  # Rate limited
                    time.sleep(5 * (attempt + 1))
                else:
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(3)
        
        return None
    
    def scan_subreddit(self, subreddit):
        """Scan a subreddit"""
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        resp = self.fetch_with_retry(url, headers)
        
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                posts = []
                
                for post in data['data']['children']:
                    p = post['data']
                    posts.append({
                        'title': p['title'],
                        'score': p['score'],
                        'upvote_ratio': p.get('upvote_ratio', 0),
                        'url': f"https://reddit.com{p['permalink']}"
                    })
                return posts
            except:
                pass
        
        return []
    
    def find_signals(self):
        """Find trading signals"""
        print(f"[{datetime.now().strftime('%H:%M')}] Scanning Reddit...")
        
        keywords = ['polymarket', 'prediction', 'bet', 'crypto', 'bitcoin', 'eth']
        signals = []
        
        for sub in self.subreddits:
            posts = self.scan_subreddit(sub)
            for post in posts:
                title_lower = post['title'].lower()
                if any(k in title_lower for k in keywords):
                    if post['score'] > 20 and post.get('upvote_ratio', 0) > 0.7:
                        signals.append({
                            'sub': sub,
                            'title': post['title'][:70],
                            'score': post['score'],
                            'url': post['url']
                        })
        
        return signals

def main():
    monitor = RedditMonitor()
    signals = monitor.find_signals()
    
    if signals:
        print(f"\n🎯 Found {len(signals)} signals:")
        for s in signals:
            print(f"  r/{s['sub']}: {s['title']}... ({s['score']} upvotes)")
    else:
        print("  No high-confidence signals found")

if __name__ == "__main__":
    main()
