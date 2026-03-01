# orderbook.py - Order book analysis module
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time
import urllib.request
import json

# Configuration
POLYMARKET_CLOB = "https://clob.polymarket.com"
MAX_SPREAD_PCT = 0.02
BULLISH_DEPTH_RATIO = 1.5
BEARISH_DEPTH_RATIO = 0.67
WALL_THRESHOLD = 0.10
STALE_BOOK_SECONDS = 10
CACHE_TTL_SECONDS = 5
REQUEST_TIMEOUT = 3

class BookPressure(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

@dataclass
class OrderLevel:
    price: float
    size: float

@dataclass
class OrderBook:
    market_id: str
    bids: list
    asks: list
    fetched_at: float = field(default_factory=time.time)
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    spread_pct: float = 0.0
    total_bid_size: float = 0.0
    total_ask_size: float = 0.0
    depth_ratio: float = 1.0
    pressure: BookPressure = BookPressure.NEUTRAL
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at
    
    @property
    def is_stale(self) -> bool:
        return self.age_seconds > STALE_BOOK_SECONDS

@dataclass
class WallInfo:
    detected: bool
    side: str
    price: float
    size: float
    pct_of_book: float
    is_blocking: bool = False

@dataclass
class BookVerdict:
    allowed: bool
    spread_pct: float
    depth_ratio: float
    pressure: BookPressure
    bid_wall: Optional[WallInfo]
    ask_wall: Optional[WallInfo]
    block_reason: Optional[str]
    fetched_at: float
    confidence: float

_book_cache: dict[str, OrderBook] = {}

def get_order_book(market_id: str, force_refresh: bool = False) -> Optional[OrderBook]:
    """Fetch order book with caching."""
    cached = _book_cache.get(market_id)
    
    if not force_refresh and cached and cached.age_seconds < CACHE_TTL_SECONDS:
        return cached
    
    try:
        url = f"{POLYMARKET_CLOB}/markets/{market_id}/orderbook"
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
            raw = json.loads(resp.read())
        
        book = _parse_book(market_id, raw)
        _book_cache[market_id] = book
        return book
    
    except Exception as e:
        print(f"[BOOK] Fetch failed for {market_id}: {e}")
        return cached

def _parse_book(market_id: str, raw: dict) -> OrderBook:
    """Parse API response into OrderBook."""
    def _to_levels(entries: list) -> list[OrderLevel]:
        levels = []
        for e in entries:
            try:
                levels.append(OrderLevel(float(e["price"]), float(e["size"])))
            except (KeyError, ValueError):
                continue
        return levels
    
    bids = sorted(_to_levels(raw.get("bids", [])), key=lambda x: x.price, reverse=True)
    asks = sorted(_to_levels(raw.get("asks", [])), key=lambda x: x.price)
    
    book = OrderBook(market_id=market_id, bids=bids, asks=asks)
    
    if bids and asks:
        book.best_bid = bids[0].price
        book.best_ask = asks[0].price
        book.mid_price = (book.best_bid + book.best_ask) / 2
        book.spread_pct = (book.best_ask - book.best_bid) / book.mid_price if book.mid_price > 0 else 1.0
    
    book.total_bid_size = sum(l.size for l in bids)
    book.total_ask_size = sum(l.size for l in asks)
    
    if book.total_ask_size > 0:
        book.depth_ratio = book.total_bid_size / book.total_ask_size
    
    if book.depth_ratio >= BULLISH_DEPTH_RATIO:
        book.pressure = BookPressure.BULLISH
    elif book.depth_ratio <= BEARISH_DEPTH_RATIO:
        book.pressure = BookPressure.BEARISH
    else:
        book.pressure = BookPressure.NEUTRAL
    
    return book

def detect_walls(book: OrderBook) -> tuple[Optional[WallInfo], Optional[WallInfo]]:
    """Detect large walls in order book."""
    total_liquidity = book.total_bid_size + book.total_ask_size
    if total_liquidity == 0:
        return None, None
    
    def _find_wall(levels: list, side: str) -> Optional[WallInfo]:
        if not levels:
            return None
        largest = max(levels, key=lambda x: x.size)
        pct = largest.size / total_liquidity
        if pct >= WALL_THRESHOLD:
            return WallInfo(
                detected=True, side=side, price=largest.price,
                size=largest.size, pct_of_book=pct
            )
        return None
    
    bid_wall = _find_wall(book.bids, "bid")
    ask_wall = _find_wall(book.asks, "ask")
    return bid_wall, ask_wall

def analyze_book(market_id: str, trade_side: str) -> BookVerdict:
    """Main entry point - analyze order book before trade."""
    def _block(reason: str, book: Optional[OrderBook] = None) -> BookVerdict:
        return BookVerdict(
            allowed=False, spread_pct=book.spread_pct if book else 1.0,
            depth_ratio=book.depth_ratio if book else 1.0,
            pressure=book.pressure if book else BookPressure.NEUTRAL,
            bid_wall=None, ask_wall=None, block_reason=reason,
            fetched_at=book.fetched_at if book else 0.0, confidence=0.0
        )
    
    book = get_order_book(market_id)
    if book is None:
        return _block("order book unavailable")
    if book.is_stale:
        return _block(f"order book stale ({book.age_seconds:.0f}s old)", book)
    if not book.bids or not book.asks:
        return _block("empty order book", book)
    
    # Check spread
    if book.spread_pct > MAX_SPREAD_PCT:
        return _block(f"spread {book.spread_pct:.2%} > max {MAX_SPREAD_PCT:.2%}", book)
    
    # Check walls
    bid_wall, ask_wall = detect_walls(book)
    if ask_wall and trade_side == "YES":
        ask_wall.is_blocking = True
        return _block(f"ask wall at {ask_wall.price:.3f} blocking YES", book)
    if bid_wall and trade_side == "NO":
        bid_wall.is_blocking = True
        return _block(f"bid wall at {bid_wall.price:.3f} blocking NO", book)
    
    # Check depth pressure
    pressure_blocks = (
        (trade_side == "YES" and book.pressure == BookPressure.BEARISH) or
        (trade_side == "NO" and book.pressure == BookPressure.BULLISH)
    )
    if pressure_blocks:
        return _block(f"depth ratio {book.depth_ratio:.2f} opposes {trade_side}", book)
    
    # Calculate confidence
    spread_score = max(0.0, 1.0 - (book.spread_pct / MAX_SPREAD_PCT))
    depth_score = 1.0 if (
        (trade_side == "YES" and book.pressure == BookPressure.BULLISH) or
        (trade_side == "NO" and book.pressure == BookPressure.BEARISH)
    ) else 0.5
    wall_penalty = 0.15 if (bid_wall or ask_wall) else 0.0
    confidence = max(0.0, (spread_score * 0.5 + depth_score * 0.5) - wall_penalty)
    
    return BookVerdict(
        allowed=True, spread_pct=book.spread_pct, depth_ratio=book.depth_ratio,
        pressure=book.pressure, bid_wall=bid_wall, ask_wall=ask_wall,
        block_reason=None, fetched_at=book.fetched_at, confidence=confidence
    )
