#!/usr/bin/env python3
"""news_feed_compact.py - Streamlined news feed for V6 [NEWS]"""

import os, json, time, logging, threading
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path
import requests

log = logging.getLogger('news_feed')
WORKSPACE = '/root/.openclaw/workspace'

# API Keys - hardcoded with env override
NEWSAPI_KEYS = [
    os.getenv('NEWSAPI_KEY_1', '06dc3ef927d3416aba1b6ece3fb57716'),
    os.getenv('NEWSAPI_KEY_2', '9bd8097226574cd3932fa65081029738'),
    os.getenv('NEWSAPI_KEY_3', 'a7dce4fae15c486c811af014a1094728')
]
GNEWS_KEY = os.getenv('GNEWS_KEY', '01f1ea1cc4375f5a24c0afb3d953e4d4')
CURRENTS_KEY = os.getenv('CURRENTS_KEY', '06dc3ef927d3416aba1b6ece3fb57716')

# Keywords
BULLISH = ['surge','rally','moon','ath','all-time high','breakout','pump','bull run','institutional','etf approval','buy','accumulation','whale buying']
BEARISH = ['crash','dump','bear market','sell-off','liquidation','hack','exploit','sec','ban','whale selling','ponzi','rug pull','bankruptcy']

class NewsFeed:
    """Simple news feed with key rotation."""
    
    def __init__(self):
        self.current_key_idx = 0
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'MasterBotV6/1.0'
        self._cache = {}
        log.info("[NEWS] NewsFeed initialized")

    def get_signal(self, coin='BTC') -> Dict:
        """Get sentiment signal for coin."""
        # Try GNews first (real-time)
        if GNEWS_KEY:
            try:
                return self._fetch_gnews(coin)
            except Exception as e:
                log.debug(f"[NEWS] GNews failed: {e}")
        
        # Fallback to NewsAPI
        return self._fetch_newsapi(coin)
    
    def _fetch_gnews(self, coin: str) -> Dict:
        """Fetch from GNews API."""
        r = self.session.get(
            'https://gnews.io/api/v4/search',
            params={'q': f'{coin} crypto', 'lang': 'en', 'max': 5, 'apikey': GNEWS_KEY},
            timeout=5
        )
        if r.status_code == 200:
            articles = r.json().get('articles', [])
            headlines = [a['title'] for a in articles if a.get('title')]
            return self._analyze(headlines, 'gnews')
        raise Exception(f"GNews HTTP {r.status_code}")
    
    def _fetch_newsapi(self, coin: str) -> Dict:
        """Fetch from NewsAPI with key rotation."""
        for _ in range(len(NEWSAPI_KEYS)):
            key = NEWSAPI_KEYS[self.current_key_idx]
            if not key:
                self.current_key_idx = (self.current_key_idx + 1) % len(NEWSAPI_KEYS)
                continue
                
            r = self.session.get(
                'https://newsapi.org/v2/everything',
                params={'q': f'{coin} cryptocurrency', 'language': 'en', 'sortBy': 'publishedAt', 'pageSize': 5, 'apiKey': key},
                timeout=5
            )
            
            if r.status_code == 200:
                articles = r.json().get('articles', [])
                headlines = [a['title'] for a in articles if a.get('title')]
                return self._analyze(headlines, 'newsapi')
            elif r.status_code == 429:
                log.warning(f"[NEWS] NewsAPI key {self.current_key_idx+1} rate limited")
                self.current_key_idx = (self.current_key_idx + 1) % len(NEWSAPI_KEYS)
            else:
                self.current_key_idx = (self.current_key_idx + 1) % len(NEWSAPI_KEYS)
        
        # All keys exhausted
        return {'sentiment': 'NEUTRAL', 'confidence': 0.0, 'source': 'none', 'keywords': []}
    
    def _analyze(self, headlines: List[str], source: str) -> Dict:
        """Analyze sentiment from headlines."""
        score = 0
        keywords = []
        
        for h in headlines:
            h_lower = h.lower()
            for kw in BULLISH:
                if kw in h_lower:
                    score += 1
                    keywords.append(f'+{kw}')
            for kw in BEARISH:
                if kw in h_lower:
                    score -= 1
                    keywords.append(f'-{kw}')
        
        if score > 0.5:
            sentiment, conf = 'BULLISH', min(score/3, 1.0)
        elif score < -0.5:
            sentiment, conf = 'BEARISH', min(abs(score)/3, 1.0)
        else:
            sentiment, conf = 'NEUTRAL', 0.0
        
        return {
            'sentiment': sentiment,
            'confidence': round(conf, 2),
            'source': source,
            'keywords': list(set(keywords))[:10],
            'headlines': headlines[:3]
        }

def combine_signals(arb_side: str, news: Dict) -> Dict:
    """Combine arb signal with news sentiment."""
    sentiment = news.get('sentiment', 'NEUTRAL')
    conf = news.get('confidence', 0.0)
    
    # Alignment check
    aligned = (arb_side == 'YES' and sentiment == 'BULLISH') or (arb_side == 'NO' and sentiment == 'BEARISH')
    conflict = (arb_side == 'YES' and sentiment == 'BEARISH') or (arb_side == 'NO' and sentiment == 'BULLISH')
    
    if sentiment == 'NEUTRAL':
        return {'execute': True, 'size_mult': 0.5, 'reason': 'neutral_news'}
    
    if aligned:
        return {'execute': True, 'size_mult': min(1.0, 0.7 + conf*0.3), 'reason': f'aligned_{sentiment.lower()}'}
    
    if conflict:
        if conf > 0.8:
            return {'execute': False, 'size_mult': 0.0, 'reason': 'strong_conflict'}
        return {'execute': True, 'size_mult': 0.3, 'reason': 'weak_conflict'}
    
    return {'execute': True, 'size_mult': 0.5, 'reason': 'default'}
