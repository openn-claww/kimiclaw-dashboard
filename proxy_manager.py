"""
proxy_manager.py — IP Rotation for CLOB [FIX-1]

Handles rotating residential proxies for Polymarket CLOB API access.
Falls back to direct connection if no proxies configured.
"""

import os
import time
import random
import requests
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
import logging

log = logging.getLogger('proxy_manager')


@dataclass
class ProxyEntry:
    """Single proxy with health tracking."""
    url: str
    successes: int = 0
    failures: int = 0
    last_blocked: Optional[datetime] = None
    cooldown_seconds: int = 120
    
    def is_available(self) -> bool:
        """Check if proxy is off cooldown."""
        if self.last_blocked is None:
            return True
        elapsed = (datetime.now() - self.last_blocked).total_seconds()
        return elapsed > self.cooldown_seconds
    
    def mark_success(self):
        """Record successful request."""
        self.successes += 1
    
    def mark_failure(self, blocked: bool = False):
        """Record failed request."""
        self.failures += 1
        if blocked:
            self.last_blocked = datetime.now()
            log.warning(f"Proxy blocked, cooling down: {self.url[:30]}...")


class ProxyManager:
    """Manages rotating proxy pool for CLOB requests."""
    
    def __init__(self):
        self.proxies: List[ProxyEntry] = []
        self.current_index: int = 0
        self._load_proxies()
        
    def _load_proxies(self):
        """Load proxies from env vars in priority order."""
        proxy_urls = []
        
        # Priority 1: PROXY_LIST (comma-separated)
        proxy_list = os.getenv("PROXY_LIST", "")
        if proxy_list:
            proxy_urls.extend([u.strip() for u in proxy_list.split(",") if u.strip()])
        
        # Priority 2: PROXY_URL (single proxy)
        proxy_url = os.getenv("PROXY_URL", "")
        if proxy_url:
            proxy_urls.append(proxy_url)
        
        # Priority 3: HTTPS_PROXY (standard env var)
        https_proxy = os.getenv("HTTPS_PROXY", "")
        if https_proxy:
            proxy_urls.append(https_proxy)
        
        # Create entries
        for url in proxy_urls:
            if url not in [p.url for p in self.proxies]:  # Dedupe
                self.proxies.append(ProxyEntry(url=url))
        
        if self.proxies:
            log.info(f"Loaded {len(self.proxies)} proxy(s)")
        else:
            log.info("No proxies configured, using direct connection")
    
    def get_next_proxy(self) -> Optional[ProxyEntry]:
        """Get next available proxy in rotation."""
        if not self.proxies:
            return None
        
        # Try each proxy starting from current index
        for i in range(len(self.proxies)):
            idx = (self.current_index + i) % len(self.proxies)
            proxy = self.proxies[idx]
            if proxy.is_available():
                self.current_index = (idx + 1) % len(self.proxies)
                return proxy
        
        # All proxies on cooldown, reset and try first
        log.warning("All proxies on cooldown, resetting")
        for p in self.proxies:
            p.last_blocked = None
        
        return self.proxies[0] if self.proxies else None
    
    def request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 5,
        backoff: float = 1.0,
        **kwargs
    ) -> Tuple[Optional[requests.Response], str]:
        """
        Make HTTP request with proxy rotation on failures.
        
        Returns: (response, proxy_used)
        """
        last_exception = None
        
        for attempt in range(max_retries):
            proxy = self.get_next_proxy()
            proxy_url = proxy.url if proxy else "direct"
            proxies = {"https": proxy_url} if proxy else None
            
            try:
                log.debug(f"Request attempt {attempt + 1}/{max_retries} via {proxy_url[:40]}...")
                
                response = requests.request(
                    method=method,
                    url=url,
                    proxies=proxies,
                    timeout=10,
                    **kwargs
                )
                
                # Check for blocking
                if response.status_code in (429, 403):
                    log.warning(f"Proxy blocked (HTTP {response.status_code}): {proxy_url[:40]}...")
                    if proxy:
                        proxy.mark_failure(blocked=True)
                    # Retry with next proxy
                    time.sleep(backoff * (2 ** attempt))
                    continue
                
                # Success
                if proxy:
                    proxy.mark_success()
                return response, proxy_url
                
            except requests.exceptions.Timeout:
                log.warning(f"Proxy timeout: {proxy_url[:40]}...")
                last_exception = "timeout"
                if proxy:
                    proxy.mark_failure()
                    
            except requests.exceptions.ProxyError as e:
                log.warning(f"Proxy error: {e}")
                last_exception = "proxy_error"
                if proxy:
                    proxy.mark_failure()
                    
            except Exception as e:
                log.warning(f"Request error: {e}")
                last_exception = str(e)
            
            # Backoff before retry
            time.sleep(backoff * (2 ** attempt))
        
        # All retries exhausted
        log.error(f"All {max_retries} retries exhausted. Last error: {last_exception}")
        return None, "failed"
    
    def check_clob_health(self, test_url: str = "https://clob.polymarket.com/health") -> Dict:
        """
        [FIX-2] Check CLOB API health through all proxies.
        
        Returns: {
            "reachable": bool,
            "blocked": bool,
            "latency_ms": float,
            "proxy_used": str,
            "error": str
        }
        """
        start = time.time()
        proxy = self.get_next_proxy()
        proxy_url = proxy.url if proxy else "direct"
        proxies = {"https": proxy_url} if proxy else None
        
        try:
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=5
            )
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                if proxy:
                    proxy.mark_success()
                return {
                    "reachable": True,
                    "blocked": False,
                    "latency_ms": latency,
                    "proxy_used": proxy_url,
                    "error": None
                }
            elif response.status_code in (429, 403):
                if proxy:
                    proxy.mark_failure(blocked=True)
                return {
                    "reachable": False,
                    "blocked": True,
                    "latency_ms": latency,
                    "proxy_used": proxy_url,
                    "error": f"Blocked (HTTP {response.status_code})"
                }
            else:
                return {
                    "reachable": False,
                    "blocked": False,
                    "latency_ms": latency,
                    "proxy_used": proxy_url,
                    "error": f"HTTP {response.status_code}"
                }
                
        except Exception as e:
            return {
                "reachable": False,
                "blocked": False,
                "latency_ms": None,
                "proxy_used": proxy_url,
                "error": str(e)
            }
    
    def get_status(self) -> Dict:
        """Get current proxy pool status."""
        return {
            "total_proxies": len(self.proxies),
            "available": sum(1 for p in self.proxies if p.is_available()),
            "on_cooldown": sum(1 for p in self.proxies if not p.is_available()),
            "total_successes": sum(p.successes for p in self.proxies),
            "total_failures": sum(p.failures for p in self.proxies),
            "proxies": [
                {
                    "url": p.url[:40] + "...",
                    "available": p.is_available(),
                    "successes": p.successes,
                    "failures": p.failures
                }
                for p in self.proxies
            ]
        }


# Convenience functions for direct use
def get_proxy_manager() -> ProxyManager:
    """Get singleton proxy manager instance."""
    if not hasattr(get_proxy_manager, "_instance"):
        get_proxy_manager._instance = ProxyManager()
    return get_proxy_manager._instance


def request_with_proxy(method: str, url: str, **kwargs) -> Optional[requests.Response]:
    """Make request with automatic proxy rotation."""
    pm = get_proxy_manager()
    response, _ = pm.request_with_retry(method, url, **kwargs)
    return response
