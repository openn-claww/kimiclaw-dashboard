#!/usr/bin/env python3
"""
Telegram Alpha Monitor via RSS
Monitors Telegram channels using RSSHub feeds
Reports signals containing keywords: polymarket, prediction, bet, alpha, signal, pump, airdrop
"""

import os
import sys
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
import requests

# Add workspace to path for imports
sys.path.insert(0, '/root/.openclaw/workspace')

# RSSHub instances to try (in order of preference)
RSSHub_INSTANCES = [
    "https://rsshub.rssforever.com",
    "https://rsshub.pseudoyu.com",
    "https://rsshub.app",
]

# Channels to monitor
CHANNELS = [
    {'name': 'Polymarket News', 'username': 'PolymarketNews', 'active': True},
    {'name': 'Whale Alert', 'username': 'whale_alert', 'active': True},
    {'name': 'Crypto Signals', 'username': 'cryptosignals', 'active': True},
    {'name': 'DeFi Pulse', 'username': 'defipulse', 'active': True},
    {'name': 'NFT Alpha', 'username': 'nftalpha', 'active': True},
]

# Keywords to search for
KEYWORDS = [
    'polymarket', 'prediction', 'bet', 'alpha', 'signal', 
    'pump', 'airdrop', 'moon', 'buy', 'sell', 'whitelist', 
    'mint', 'nft', 'defi', 'crypto', 'trading'
]

# State file to track seen messages
STATE_FILE = Path('/root/.openclaw/workspace/.telegram_monitor_state.json')

def load_state():
    """Load previously seen message IDs"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'seen_ids': [], 'last_check': None}

def save_state(state):
    """Save seen message IDs"""
    state['last_check'] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def fetch_rss_feed(username, instance):
    """Fetch RSS feed for a Telegram channel"""
    url = f"{instance}/telegram/channel/{username}"
    try:
        resp = requests.get(url, timeout=20, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; RSS reader)'
        })
        if resp.status_code == 200 and '<?xml' in resp.text:
            return resp.text
    except Exception as e:
        pass
    return None

def parse_rss(xml_content):
    """Parse RSS XML and extract items"""
    items = []
    try:
        root = ET.fromstring(xml_content)
        # Handle RSS 2.0 and Atom
        for item in root.findall('.//item'):
            title = item.find('title')
            desc = item.find('description')
            link = item.find('link')
            pub_date = item.find('pubDate')
            guid = item.find('guid')
            
            items.append({
                'title': title.text if title is not None else '',
                'description': desc.text if desc is not None else '',
                'link': link.text if link is not None else '',
                'pub_date': pub_date.text if pub_date is not None else '',
                'guid': guid.text if guid is not None else ''
            })
    except Exception as e:
        pass
    return items

def contains_keywords(text, keywords):
    """Check if text contains any of the keywords (case insensitive)"""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
    return found

def clean_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ''
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    # Normalize whitespace
    text = ' '.join(text.split())
    return text[:500]  # Limit length

def check_channel(channel, state):
    """Check a single channel for new alpha signals"""
    signals = []
    username = channel['username']
    
    # Try each RSSHub instance
    xml_content = None
    for instance in RSSHub_INSTANCES:
        xml_content = fetch_rss_feed(username, instance)
        if xml_content:
            break
    
    if not xml_content:
        return [], f"Could not fetch feed for @{username}"
    
    items = parse_rss(xml_content)
    
    for item in items:
        msg_id = item['guid'] or item['link']
        
        # Skip already seen messages
        if msg_id in state['seen_ids']:
            continue
        
        # Add to seen
        state['seen_ids'].append(msg_id)
        # Keep only last 1000 IDs to prevent bloat
        state['seen_ids'] = state['seen_ids'][-1000:]
        
        # Check for keywords
        full_text = f"{item['title']} {item['description']}"
        found_keywords = contains_keywords(full_text, KEYWORDS)
        
        if found_keywords:
            signals.append({
                'channel': channel['name'],
                'channel_username': username,
                'title': clean_html(item['title']),
                'content': clean_html(item['description']),
                'link': item['link'],
                'pub_date': item['pub_date'],
                'keywords_found': found_keywords
            })
    
    return signals, None

def format_signal(signal):
    """Format a signal for display"""
    lines = [
        f"🚨 ALPHA SIGNAL from {signal['channel']}",
        f"📌 Keywords: {', '.join(signal['keywords_found'])}",
        f"📝 {signal['title']}",
    ]
    if signal['content']:
        content = signal['content'][:300]
        if len(signal['content']) > 300:
            content += "..."
        lines.append(f"💬 {content}")
    lines.append(f"🔗 {signal['link']}")
    if signal['pub_date']:
        lines.append(f"🕐 {signal['pub_date']}")
    lines.append("-" * 50)
    return "\n".join(lines)

def main():
    """Main monitoring function"""
    state = load_state()
    all_signals = []
    errors = []
    
    print(f"🔍 Telegram Alpha Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    for channel in CHANNELS:
        if not channel.get('active', True):
            continue
        
        signals, error = check_channel(channel, state)
        
        if error:
            errors.append(f"@{channel['username']}: {error}")
        
        if signals:
            all_signals.extend(signals)
            for sig in signals:
                print(format_signal(sig))
                print()
    
    # Save state
    save_state(state)
    
    # Summary
    print("=" * 60)
    print(f"📊 Summary: {len(all_signals)} signals found from {len(CHANNELS)} channels")
    
    if errors:
        print(f"⚠️  Errors: {len(errors)}")
        for err in errors:
            print(f"   - {err}")
    
    # Return signals for further processing
    return all_signals

if __name__ == "__main__":
    signals = main()
    # Exit with count for cron monitoring
    sys.exit(len(signals))
