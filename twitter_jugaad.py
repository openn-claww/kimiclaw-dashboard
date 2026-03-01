#!/usr/bin/env python3
"""
Twitter Jugaad - Free Twitter monitoring via alternative methods
Scans crypto Twitter accounts for alpha on Polymarket, prediction markets, signals

NOTE: Nitter was discontinued in Feb 2024 when Twitter removed guest access.
This script now uses alternative methods.
"""

import requests
import json
import re
from datetime import datetime
import sys

def scan_twitter_accounts(accounts, keywords, instances):
    """
    Scan Twitter accounts for keywords using available methods.
    
    Returns dict with scan results and status.
    """
    results = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M %Z'),
        'accounts_scanned': accounts,
        'keywords': keywords,
        'matches': [],
        'status': 'incomplete',
        'errors': []
    }
    
    # Try each Nitter instance
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    working_instance = None
    
    # Find a working instance
    for instance in instances:
        try:
            resp = requests.get(instance, headers=headers, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 500:
                # Check if it's actually serving content or just Cloudflare challenge
                if 'timeline' in resp.text.lower() or 'tweet' in resp.text.lower():
                    working_instance = instance
                    break
        except Exception as e:
            results['errors'].append(f"{instance}: {str(e)[:50]}")
            continue
    
    if not working_instance:
        results['status'] = 'failed'
        results['errors'].append("No working Nitter instances found. Nitter was discontinued in Feb 2024.")
        return results
    
    results['working_instance'] = working_instance
    
    # Scan each account
    for account in accounts:
        try:
            url = f"{working_instance}/{account}"
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                results['errors'].append(f"@{account}: HTTP {resp.status_code}")
                continue
            
            html = resp.text.lower()
            
            # Check for Cloudflare protection
            if 'cf-ray' in resp.headers or 'cloudflare' in html or len(resp.text) < 1000:
                results['errors'].append(f"@{account}: Blocked by Cloudflare")
                continue
            
            # Look for keyword matches in the HTML
            for keyword in keywords:
                if keyword.lower() in html:
                    # Try to extract some context
                    idx = html.find(keyword.lower())
                    start = max(0, idx - 100)
                    end = min(len(html), idx + 200)
                    context = html[start:end]
                    # Clean up HTML tags
                    context = re.sub(r'<[^>]+>', ' ', context)
                    context = re.sub(r'\s+', ' ', context).strip()
                    
                    results['matches'].append({
                        'account': account,
                        'keyword': keyword,
                        'context': context[:200] if context else f"Found '{keyword}' in page",
                        'url': url
                    })
                    break  # Only record one match per account per scan
                    
        except Exception as e:
            results['errors'].append(f"@{account}: {str(e)[:50]}")
    
    results['status'] = 'completed'
    return results

def print_report(results):
    """Print formatted scan report"""
    print("="*70)
    print("TWITTER JUGAAD - CRYPTO ALPHA SCANNER")
    print(f"Time: {results['timestamp']}")
    print("="*70)
    
    print(f"\n📡 Instance: {results.get('working_instance', 'None')}")
    print(f"📱 Accounts: {len(results['accounts_scanned'])}")
    print(f"🔍 Keywords: {', '.join(results['keywords'][:5])}...")
    print("-"*70)
    
    if results['errors']:
        print("\n⚠️  Issues encountered:")
        for err in results['errors'][:5]:
            print(f"   - {err}")
    
    if results['matches']:
        print(f"\n🎯 FOUND {len(results['matches'])} MATCHES:\n")
        for i, match in enumerate(results['matches'], 1):
            print(f"[{i}] @{match['account']} - '{match['keyword']}'")
            print(f"    {match['context'][:150]}...")
            print(f"    {match['url']}")
            print()
    else:
        print("\n📝 No keyword matches found.")
        print("   (Nitter has been discontinued - automated access is blocked)")
    
    print("-"*70)
    print(f"Status: {results['status']}")
    print("="*70)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Twitter Jugaad - Crypto Alpha Scanner')
    parser.add_argument('--accounts', nargs='+', default=[
        'CryptoCobain', 'zhusu', 'crypto_birb', 
        'IncomeSharks', 'CryptoCapo_', 'Polymarket'
    ], help='Twitter accounts to monitor')
    parser.add_argument('--keywords', nargs='+', default=[
        'polymarket', 'prediction market', 'prediction markets',
        'crypto signal', 'crypto signals', 'trading alpha'
    ], help='Keywords to search for')
    parser.add_argument('--instances', nargs='+', default=[
        'https://nitter.net', 'https://nitter.it', 'https://nitter.cz',
        'https://nitter.poast.org', 'https://xcancel.com'
    ], help='Nitter instances to try')
    
    args = parser.parse_args()
    
    results = scan_twitter_accounts(args.accounts, args.keywords, args.instances)
    print_report(results)
