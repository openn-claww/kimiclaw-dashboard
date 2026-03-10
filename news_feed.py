#!/usr/bin/env python3
"""news_feed.py — Multi-Source News Feed with Key Rotation [NEWS]"""

import os, json, time, logging, threading, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from collections import deque
import requests

log = logging.getLogger('news_feed')
WORKSPACE = '/root/.openclaw/workspace'
QUOTA_FILE = f'{WORKSPACE}/news_quota.json'
SIGNALS_FILE = f'{WORKSPACE}/news_signals.json'

# Config
_NEWSAPI_KEYS = [os.getenv('NEWSAPI_KEY_1',''), os.getenv('NEWSAPI_KEY_2',''), os.getenv('NEWSAPI_KEY_3','')]
_GNEWS_KEY = os.getenv('GNEWS_KEY','')
_CURRENTS_KEY = os.getenv('CURRENTS_KEY','')

NEWS_CHECK_INTERVAL = int(os.getenv('NEWS_CHECK_INTERVAL','120'))
NEWS_GNEWS_HOUR_START = int(os.getenv('NEWS_GNEWS_HOUR_START','8'))
NEWS_GNEWS_HOUR_END = int(os.getenv('NEWS_GNEWS_HOUR_END','20'))
NEWS_SENTIMENT_THRESHOLD = float(os.getenv('NEWS_SENTIMENT_THRESHOLD','0.5'))
NEWS_COMBINE_WITH_ARB = os.getenv('NEWS_COMBINE_WITH_ARB','true').lower() == 'true'

QUOTA_GNEWS_DAILY = 100
QUOTA_NEWSAPI_DAILY = 100
QUOTA_CURRENTS_DAILY = 20
QUOTA_BURST_PER_MIN = 5

RSS_FEEDS = {
    'cointelegraph': 'https://cointelegraph.com/rss',
    'coindesk': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
    'decrypt': 'https://decrypt.co/feed',
}

COIN_QUERIES = {'BTC': 'bitcoin OR BTC price', 'ETH': 'ethereum OR ETH price', 'SOL': 'solana OR SOL', 'XRP': 'XRP OR ripple'}

BULLISH_KEYWORDS = {'surge':1.0,'rally':1.0,'moon':0.9,'ath':1.0,'all-time high':1.0,'breakout':0.9,'pump':0.8,'bull run':0.9,'bullish':0.8,'institutional':0.7,'etf approval':1.0,'buy':0.6,'accumulation':0.7,'whale buying':0.8}
BEARISH_KEYWORDS = {'crash':-1.0,'dump':-0.9,'bear market':-0.9,'bearish':-0.8,'death cross':-0.8,'sell-off':-0.8,'liquidation':-0.9,'hack':-0.9,'exploit':-0.9,'sec':-0.6,'ban':-0.8,'whale selling':-0.8,'ponzi':-0.9,'rug pull':-1.0,'bankruptcy':-0.9}

class KeyManager:
    """[NEWS] Tracks daily quota usage per API key with midnight UTC reset."""
    def __init__(self):
        self._lock = threading.Lock()
        self._quotas: Dict[str, dict] = {}
        self._burst: Dict[str, deque] = {}
        self._load()

    def _default_quota(self, source: str, daily: int) -> dict:
        now = datetime.now(tz=timezone.utc)
        next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return {'source': source, 'used': 0, 'daily_limit': daily, 'reset_at': next_reset.isoformat()}

    def _load(self):
        try:
            with open(QUOTA_FILE) as f:
                self._quotas = json.load(f)
        except:
            self._quotas = {}
        for i, k in enumerate(['gnews','newsapi_0','newsapi_1','newsapi_2','currents']):
            limit = QUOTA_GNEWS_DAILY if i==0 else (QUOTA_CURRENTS_DAILY if i==4 else QUOTA_NEWSAPI_DAILY)
            if k not in self._quotas:
                self._quotas[k] = self._default_quota(k, limit)
            self._burst[k] = deque()
        self._check_resets()
        self._save()

    def _check_resets(self):
        now = datetime.now(tz=timezone.utc)
        for k, q in self._quotas.items():
            try:
                reset_dt = datetime.fromisoformat(q['reset_at'])
                if now >= reset_dt:
                    log.info(f"[NEWS][Quota] Reset {k} (was {q['used']})")
                    q['used'] = 0
                    q['reset_at'] = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
            except: pass

    def _save(self):
        try:
            with open(QUOTA_FILE + '.tmp', 'w') as f:
                json.dump(self._quotas, f)
            Path(QUOTA_FILE + '.tmp').replace(QUOTA_FILE)
        except Exception as e:
            log.debug(f"[NEWS] Save failed: {e}")

    def has_quota(self, source: str) -> bool:
        with self._lock:
            self._check_resets()
            q = self._quotas.get(source, {})
            return q.get('used', 0) < q.get('daily_limit', 0)

    def has_burst_quota(self, source: str) -> bool:
        with self._lock:
            now = time.time()
            dq = self._burst.get(source, deque())
            while dq and now - dq[0] > 60:
                dq.popleft()
            return len(dq) < QUOTA_BURST_PER_MIN

    def consume(self, source: str):
        with self._lock:
            self._check_resets()
            if source in self._quotas:
                self._quotas[source]['used'] += 1
            if source not in self._burst:
                self._burst[source] = deque()
            self._burst[source].append(time.time())
        self._save()

    def remaining(self, source: str) -> int:
        with self._lock:
            q = self._quotas.get(source, {})
            return max(0, q.get('daily_limit', 0) - q.get('used', 0))

    def get_status(self) -> dict:
        with self._lock:
            self._check_resets()
            return {k: {'used': q['used'], 'remaining': max(0, q['daily_limit']-q['used'])} for k, q in self._quotas.items()}
