# ==============================================================================
# File: data_sources/web_search.py
# ==============================================================================

"""
Web Search Service with Multi-Key Rotation, Failover, and In-Memory TTL Cache.

Mendukung:
1. Tavily Finance Search API dengan rotasi multi-kunci (TRAVILY_API_KEYS / TAVILY_API_KEYS)
   dan automatic failover/retry pada HTTP 429 / 401 / 403.
2. Brave Search API fallback jika pool kunci Tavily habis.
3. DuckDuckGo HTML parser fallback via aiohttp jika semua API keys tidak tersedia/gagal.
4. In-memory TTL cache (default 15 menit).
"""

import asyncio
import hashlib
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, unquote

import aiohttp
from bs4 import BeautifulSoup

import utils.clock as clock

logger = logging.getLogger("TradingAgent.WebSearch")


class WebSearchService:
    """Service pencarian web asinkron dengan rotasi kunci dan multi-tier fallback."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        search_cfg = self.settings.get("search", {})

        # 1. Parse Tavily keys pool
        def _is_valid_val(val: Any) -> bool:
            if not val:
                return False
            s = str(val).strip()
            return bool(s and not s.startswith("${"))

        candidates = [
            os.getenv("TRAVILY_API_KEYS"),
            os.getenv("TAVILY_API_KEYS"),
            os.getenv("TAVILY_API_KEY"),
            search_cfg.get("tavily_api_keys"),
            search_cfg.get("tavily_api_key"),
        ]

        self._tavily_keys: List[str] = []
        for candidate in candidates:
            if not _is_valid_val(candidate):
                continue
            if isinstance(candidate, str):
                for k in re.split(r"[,;\n\s]+", candidate.strip()):
                    k_clean = k.strip()
                    if _is_valid_val(k_clean) and k_clean not in self._tavily_keys:
                        self._tavily_keys.append(k_clean)
            elif isinstance(candidate, (list, tuple)):
                for k in candidate:
                    k_clean = str(k).strip()
                    if _is_valid_val(k_clean) and k_clean not in self._tavily_keys:
                        self._tavily_keys.append(k_clean)
            if self._tavily_keys:
                break

        self._current_key_index = 0
        self._lock = asyncio.Lock()

        # 2. Brave API Key
        brave_candidates = [
            os.getenv("BRAVE_SEARCH_API_KEY"),
            os.getenv("BRAVE_API_KEY"),
            search_cfg.get("brave_api_key"),
        ]
        self.brave_api_key = ""
        for b_cand in brave_candidates:
            if _is_valid_val(b_cand):
                self.brave_api_key = str(b_cand).strip()
                break

        # 3. Cache TTL & LRU Max Size
        ttl_min = search_cfg.get("cache_ttl_minutes", 15)
        try:
            self.cache_ttl = timedelta(minutes=float(ttl_min))
        except (ValueError, TypeError):
            self.cache_ttl = timedelta(minutes=15)

        self._max_cache_size = int(search_cfg.get("max_cache_size", 500))
        self._cache: OrderedDict[str, tuple[datetime, dict]] = OrderedDict()
        self.default_provider = search_cfg.get("default_provider", "tavily")

    @property
    def tavily_keys(self) -> List[str]:
        return list(self._tavily_keys)

    @tavily_keys.setter
    def tavily_keys(self, keys: List[str]):
        self._tavily_keys = list(keys)

    def _get_next_tavily_key(self) -> Optional[str]:
        if not self._tavily_keys:
            return None
        key = self._tavily_keys[self._current_key_index % len(self._tavily_keys)]
        self._current_key_index = (self._current_key_index + 1) % len(self._tavily_keys)
        return key

    @property
    def key_count(self) -> int:
        return len(self._tavily_keys)

    def _get_cache_key(self, query: str, topic: str, time_range: str, max_results: int) -> str:
        raw = f"{query.strip().lower()}_{topic}_{time_range}_{max_results}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _put_cache(self, key: str, val: tuple[datetime, dict]) -> None:
        self._cache[key] = val
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

    async def search(
        self,
        query: str,
        topic: str = "finance",
        search_depth: str = "advanced",
        time_range: str = "day",
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Lakukan pencarian web dengan query yang diberikan.
        Mengembalikan dict hasil terstruktur dengan fallback berjenjang.
        """
        if not query or not query.strip():
            return {
                "query": "",
                "provider": "none",
                "answer": "",
                "results": [],
                "cached": False,
            }

        cache_key = self._get_cache_key(query, topic, time_range, max_results)

        # Check Cache
        async with self._lock:
            if cache_key in self._cache:
                cached_at, cached_result = self._cache[cache_key]
                if clock.now() - cached_at < self.cache_ttl:
                    logger.debug(f"[WebSearch] Cache hit for query: {query[:50]}")
                    self._cache.move_to_end(cache_key)
                    res = dict(cached_result)
                    res["cached"] = True
                    return res
                else:
                    del self._cache[cache_key]

        # Tier 1: Tavily API with multi-key round-robin rotation
        if self._tavily_keys:
            tavily_res = await self._search_tavily_with_rotation(
                query=query,
                topic=topic,
                search_depth=search_depth,
                time_range=time_range,
                max_results=max_results,
            )
            if tavily_res and tavily_res.get("results"):
                tavily_res["cached"] = False
                async with self._lock:
                    self._put_cache(cache_key, (clock.now(), tavily_res))
                return tavily_res

        # Tier 2: Brave Search API Fallback
        if self.brave_api_key:
            logger.info(f"[WebSearch] Attempting Brave Search fallback for: {query[:50]}")
            brave_res = await self._search_brave(query=query, max_results=max_results)
            if brave_res and brave_res.get("results"):
                brave_res["cached"] = False
                async with self._lock:
                    self._put_cache(cache_key, (clock.now(), brave_res))
                return brave_res

        # Tier 3: DuckDuckGo HTML Fallback
        logger.info(f"[WebSearch] Attempting DuckDuckGo HTML fallback for: {query[:50]}")
        ddg_res = await self._search_duckduckgo(query=query, max_results=max_results)
        ddg_res["cached"] = False
        async with self._lock:
            self._put_cache(cache_key, (clock.now(), ddg_res))
        return ddg_res

    async def _search_tavily_with_rotation(
        self,
        query: str,
        topic: str,
        search_depth: str,
        time_range: str,
        max_results: int,
    ) -> Optional[Dict[str, Any]]:
        """Mengeksekusi request Tavily dengan failover rotasi kunci jika kena 429 atau 401/403."""
        total_keys = len(self._tavily_keys)
        if total_keys == 0:
            return None

        endpoint = "https://api.tavily.com/search"

        async with self._lock:
            start_idx = self._current_key_index

        for attempt in range(total_keys):
            key_idx = (start_idx + attempt) % total_keys
            api_key = self._tavily_keys[key_idx]

            payload = {
                "api_key": api_key,
                "query": query,
                "topic": topic if topic in ("finance", "general") else "finance",
                "search_depth": search_depth if search_depth in ("basic", "advanced") else "advanced",
                "time_range": time_range if time_range in ("day", "week", "month", "year") else "day",
                "max_results": max(1, min(max_results, 10)),
                "include_answer": True,
                "include_raw_content": False,
            }

            try:
                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(endpoint, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = []
                            for item in data.get("results", []):
                                results.append({
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                    "content": item.get("content", ""),
                                    "score": item.get("score"),
                                    "published_date": item.get("published_date"),
                                })
                            # Rotate pointer forward on success for load-balancing
                            async with self._lock:
                                self._current_key_index = (key_idx + 1) % total_keys

                            return {
                                "query": query,
                                "provider": "tavily",
                                "source": "tavily",
                                "answer": data.get("answer", ""),
                                "results": results,
                                "total_results": len(results),
                            }
                        elif resp.status in (429, 401, 403):
                            logger.warning(
                                f"[WebSearch] Tavily key idx={key_idx} failed (HTTP {resp.status}). "
                                f"Rotating to next key..."
                            )
                            async with self._lock:
                                self._current_key_index = (key_idx + 1) % total_keys
                            continue
                        else:
                            text_err = await resp.text()
                            logger.warning(f"[WebSearch] Tavily request failed with HTTP {resp.status}: {text_err[:100]}")
                            async with self._lock:
                                self._current_key_index = (key_idx + 1) % total_keys
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[WebSearch] Exception connecting to Tavily (key idx={key_idx}): {e}")
                async with self._lock:
                    self._current_key_index = (key_idx + 1) % total_keys
                continue

        logger.error("[WebSearch] All Tavily API keys exhausted or rate-limited.")
        return None

    async def _search_brave(self, query: str, max_results: int = 5) -> Optional[Dict[str, Any]]:
        """Fallback pencarian via Brave Search API."""
        if not self.brave_api_key:
            return None

        endpoint = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.brave_api_key,
        }
        params = {
            "q": query,
            "count": max(1, min(max_results, 10)),
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        web_results = data.get("web", {}).get("results", [])
                        results = []
                        for item in web_results:
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "content": item.get("description", ""),
                                "score": None,
                                "published_date": item.get("page_age"),
                            })
                        return {
                            "query": query,
                            "provider": "brave",
                            "source": "brave",
                            "answer": "",
                            "results": results,
                            "total_results": len(results),
                        }
                    else:
                        logger.warning(f"[WebSearch] Brave Search returned HTTP {resp.status}")
                        return None
        except Exception as e:
            logger.warning(f"[WebSearch] Brave Search request failed: {e}")
            return None

    async def _search_duckduckgo(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Fallback web scraping dari DuckDuckGo HTML via aiohttp & bs4."""
        endpoint = "https://html.duckduckgo.com/html/"
        data_payload = {"q": query}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        results = []
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import unquote
            import re

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, data=data_payload, headers=headers) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        soup = BeautifulSoup(html_text, "html.parser")
                        result_blocks = soup.find_all("div", class_="result")

                        for block in result_blocks:
                            if len(results) >= max_results:
                                break
                            title_elem = block.find("a", class_="result__a")
                            snippet_elem = block.find("a", class_="result__snippet")
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                raw_href = title_elem.get("href")
                                raw_link = str(raw_href[0] if isinstance(raw_href, list) else (raw_href or ""))
                                actual_url = raw_link
                                if "uddg=" in raw_link:
                                    match = re.search(r"uddg=([^&]+)", raw_link)
                                    if match:
                                        actual_url = unquote(match.group(1))

                                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                                results.append({
                                    "title": title,
                                    "url": actual_url,
                                    "content": snippet,
                                    "score": None,
                                    "published_date": None,
                                })
        except Exception as e:
            logger.warning(f"[WebSearch] DuckDuckGo fallback scraping failed: {e}")

        return {
            "query": query,
            "provider": "duckduckgo",
            "source": "duckduckgo",
            "answer": "",
            "results": results,
            "total_results": len(results),
        }


_global_web_search_service: Optional[WebSearchService] = None

def get_web_search_service(settings: Optional[dict] = None) -> WebSearchService:
    global _global_web_search_service
    if _global_web_search_service is None:
        _global_web_search_service = WebSearchService(settings=settings)
    return _global_web_search_service
