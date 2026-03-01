# sentiment_overlay.py - Fear & Greed sentiment filter
import time
import urllib.request
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ── Sentiment Zones ───────────────────────────────────────────────────────────
class SentimentZone(Enum):
    EXTREME_FEAR  = "extreme_fear"   # 0–20
    FEAR          = "fear"           # 21–40
    NEUTRAL       = "neutral"        # 41–60
    GREED         = "greed"          # 61–80
    EXTREME_GREED = "extreme_greed"  # 81–100

ZONE_RANGES = {
    SentimentZone.EXTREME_FEAR:  (0,  20),
    SentimentZone.FEAR:          (21, 40),
    SentimentZone.NEUTRAL:       (41, 60),
    SentimentZone.GREED:         (61, 80),
    SentimentZone.EXTREME_GREED: (81, 100),
}

# Signal Rules per Zone
ZONE_RULES = {
    SentimentZone.EXTREME_FEAR:  {"YES": 1.5,  "NO": None},
    SentimentZone.FEAR:          {"YES": 1.0,  "NO": 0.5 },
    SentimentZone.NEUTRAL:       {"YES": 1.0,  "NO": 1.0 },
    SentimentZone.GREED:         {"YES": 0.5,  "NO": 1.0 },
    SentimentZone.EXTREME_GREED: {"YES": None, "NO": 1.5 },
}

FNG_API_URL    = "https://api.alternative.me/fng/?limit=1"
CACHE_SECONDS  = 3600
REQUEST_TIMEOUT = 5

@dataclass
class FearGreedCache:
    value: int = 50
    zone: SentimentZone = SentimentZone.NEUTRAL
    label: str = "Neutral"
    fetched_at: float = 0.0
    fetch_failures: int = 0
    last_error: Optional[str] = None

_cache = FearGreedCache()

def get_fear_greed(force_refresh: bool = False) -> FearGreedCache:
    """Returns cached sentiment. Hits API only when stale."""
    global _cache
    
    age = time.time() - _cache.fetched_at
    if not force_refresh and age < CACHE_SECONDS:
        return _cache
    
    try:
        with urllib.request.urlopen(FNG_API_URL, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())["data"][0]
        
        value = int(data["value"])
        label = data["value_classification"]
        
        _cache.value = value
        _cache.zone = _score_to_zone(value)
        _cache.label = label
        _cache.fetched_at = time.time()
        _cache.fetch_failures = 0
        _cache.last_error = None
        
        print(f"[SENTIMENT] Updated: {value}/100 — {label} ({_cache.zone.value})")
    
    except Exception as e:
        _cache.fetch_failures += 1
        _cache.last_error = str(e)
        print(f"[SENTIMENT] Fetch failed (#{_cache.fetch_failures}): {e}. Using last known: {_cache.value}")
    
    return _cache

def _score_to_zone(score: int) -> SentimentZone:
    for zone, (lo, hi) in ZONE_RANGES.items():
        if lo <= score <= hi:
            return zone
    return SentimentZone.NEUTRAL

@dataclass
class SentimentVerdict:
    allowed: bool
    size_multiplier: float
    zone: SentimentZone
    fng_value: int
    signal_side: str
    reason: str

def evaluate_signal(side: str, fng: Optional[FearGreedCache] = None) -> SentimentVerdict:
    """Evaluate if sentiment allows the trade signal."""
    if fng is None:
        fng = get_fear_greed()
    
    rules = ZONE_RULES[fng.zone]
    multiplier = rules.get(side)
    allowed = multiplier is not None
    
    if allowed:
        if multiplier > 1.0:
            reason = f"{fng.zone.value} ({fng.value}) — {side} high conviction ({multiplier}x)"
        elif multiplier == 1.0:
            reason = f"{fng.zone.value} ({fng.value}) — neutral, normal {side}"
        else:
            reason = f"{fng.zone.value} ({fng.value}) — {side} against sentiment ({multiplier}x)"
    else:
        reason = f"BLOCKED — {fng.zone.value} ({fng.value}) only allows {'YES' if side == 'NO' else 'NO'}"
    
    return SentimentVerdict(
        allowed=allowed,
        size_multiplier=multiplier or 0.0,
        zone=fng.zone,
        fng_value=fng.value,
        signal_side=side,
        reason=reason,
    )

def calculate_position_size(base_size: float, side: str, fng: Optional[FearGreedCache] = None) -> tuple[float, SentimentVerdict]:
    """Calculate final position size based on sentiment."""
    if fng is None:
        fng = get_fear_greed()
    
    verdict = evaluate_signal(side, fng)
    final_size = round(base_size * verdict.size_multiplier, 4) if verdict.allowed else 0.0
    
    return final_size, verdict
