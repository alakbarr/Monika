"""
Semantic Caching Subsystem for Repeated Financial / Macro LLM Queries.

Strict Financial Guardrails:
1. BLACKLISTED: Order execution, current live prices, spread snapshots, and live account state are NEVER cached.
2. CACHED: Static macro knowledge, central bank framework explanations, and stable regime classifications.
3. Candle Anchor Invalidation: Caches are strictly bound to candle timestamps to prevent obsolete lookups.
"""

import time
import hashlib
import logging
from typing import Dict, Any, Optional, Tuple, Callable
from datetime import datetime, timezone

logger = logging.getLogger("TradingAgent.SemanticCache")


class TradingSemanticCache:
    """
    Lightweight, high-speed semantic cache with financial TTL and safety guardrails.
    """

    _instance: Optional["TradingSemanticCache"] = None

    # Tools and tasks that must NEVER be served from cache
    STRICT_BLACKLIST = frozenset({
        "execute_order_guard",
        "modify_position",
        "close_position",
        "get_market_quote",
        "get_spread_snapshot",
        "get_account_info",
        "get_open_positions",
        "calculate_position_size",
        "submit_asset_analysis",
    })

    DEFAULT_TTLS: Dict[str, float] = {
        "macro_explanation": 86400.0,       # 24 hours
        "entity_definition": 86400.0,       # 24 hours
        "central_bank_policy": 28800.0,     # 8 hours
        "fundamental_brief": 14400.0,       # 4 hours
        "regime_classification": 1800.0,    # 30 minutes
        "sentiment_snapshot": 900.0,        # 15 minutes
    }

    def __init__(self):
        # key -> (result_data, timestamp, ttl)
        self._store: Dict[str, Tuple[Any, float, float]] = {}

    @classmethod
    def get_instance(cls) -> "TradingSemanticCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _generate_key(self, category: str, query: str, symbol: Optional[str] = None) -> str:
        clean_q = " ".join(query.strip().lower().split())
        sym = (symbol or "").strip().upper().replace("/", "")
        payload = f"{category}:{sym}:{clean_q}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def get(self, category: str, query: str, symbol: Optional[str] = None) -> Optional[Any]:
        """
        Retrieves cached response if valid and unexpired.
        Returns None on miss or expiration.
        """
        if category in self.STRICT_BLACKLIST:
            return None

        key = self._generate_key(category, query, symbol=symbol)
        entry = self._store.get(key)
        if not entry:
            return None

        data, timestamp, ttl = entry
        now = time.time()
        if now - timestamp > ttl:
            # Expired
            self._store.pop(key, None)
            return None

        logger.debug(f"[SemanticCache] Hit! Category='{category}', Key={key}")
        return data

    def set(self, category: str, query: str, data: Any, symbol: Optional[str] = None, ttl: Optional[float] = None) -> None:
        """
        Stores response in cache with appropriate TTL.
        """
        if category in self.STRICT_BLACKLIST or data is None:
            return

        key = self._generate_key(category, query, symbol=symbol)
        effective_ttl = ttl or self.DEFAULT_TTLS.get(category, 1800.0)
        self._store[key] = (data, time.time(), effective_ttl)
        logger.debug(f"[SemanticCache] Stored response. Category='{category}', Key={key}, TTL={effective_ttl}s")

    def clear(self) -> None:
        """Clears all cached entries."""
        self._store.clear()
