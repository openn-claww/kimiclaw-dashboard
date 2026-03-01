#!/usr/bin/env python3
"""
Twitter Jugaad Scanner - Alternative via Browser Automation
Scans crypto Twitter accounts for alpha signals using browser
"""

import subprocess
import json
import re
from datetime import datetime

# Accounts to monitor
ACCOUNTS = [
    "CryptoCobain",
    "zhusu", 
    "crypto_birb",
    "IncomeSharks",
    "CryptoCapo_",
    "Polymarket"
]

# Keywords to search for
KEYWORDS = [
    "polymarket",
    "prediction market",
    "prediction markets", 
    "crypto signal",
    "crypto signals",
    "trading alpha",
    "alpha",
    "long",
    "short",
    "bullish",
    "bearish"
]

def fetch_twitter_via_nitter_rss(username):
    """Try to fetch tweets via Nitter RSS feeds (sometimes works when main site is blocked)"""
    import urllib.request
    import xml.etree.ElementTree as ET
    
    nitter_instances = [
        "https://nitter.net",
        "https://nitter.it",
        "https://nitter.cz",
        "https://nitter.privacydev.net",
        "https://nitter.space",
    ]
    
    for instance in nitter_instances:
        try:
            rss_url = f"{instance}/{username}/rss"
            req = urllib.request.Request(
                rss_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                root = ET.fromstring(content)
                
                tweets = []
                for item in root.findall('.//item'):
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    
                    if title is not None:
                        tweets.append({
                            'text': title.text,
                            'link': link.text if link is not None else '',
                            'date': pub_date.text if pub_date is not None else ''
                        })
                return tweets
        except Exception as e:
            continue
    
    return None

def check_keywords(text):
    """Check if text contains any keywords"""
    text_lower = text.lower()
    matches = []
    for keyword in KEYWORDS:
        if keyword.lower() in text_lower:
            matches.append(keyword)
    return matches

def main():
    print("=" * 70)
    print("TWITTER JUGAAD - CRYPTO ALPHA SCANNER (RSS Mode)")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print()
    
    all_findings = []
    
    for account in ACCOUNTS:
        print(f"📱 Checking @{account}...", end=" ")
        tweets = fetch_twitter_via_nitter_rss(account)
        
        if tweets is None:
            print("❌ Failed (all instances blocked)")
            continue
        
        print(f"✅ {len(tweets)} tweets fetched")
        
        for tweet in tweets[:5]:  # Check last 5 tweets
            matches = check_keywords(tweet['text'])
            if matches:
                all_findings.append({
                    'account': account,
                    'tweet': tweet['text'],
                    'link': tweet['link'],
                    'date': tweet['date'],
                    'keywords': matches
                })
    
    print()
    print("=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)
    print()
    
    if not all_findings:
        print("🔍 No tweets matching keywords found in recent posts.")
        print()
        print("Note: Nitter RSS feeds may be rate-limited or blocked.")
        print("Consider manual check at twitter.com for real-time alpha.")
    else:
        for finding in all_findings:
            print(f"🚨 @{finding['account']} - Keywords: {', '.join(finding['keywords'])}")
            print(f"   Tweet: {finding['tweet'][:150]}...")
            print(f"   Link: {finding['link']}")
            print(f"   Date: {finding['date']}")
            print()
    
    # Save to memory
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    summary = {
        'timestamp': timestamp,
        'accounts_checked': len(ACCOUNTS),
        'findings_count': len(all_findings),
        'findings': all_findings
    }
    
    try:
        with open('/root/.openclaw/workspace/memory/twitter_scan_latest.json', 'w') as f:
            json.dump(summary, f, indent=2)
    except:
        pass
    
    return all_findings

if __name__ == "__main__":
    main()
