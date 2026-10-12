"""
Dynamic Model Pricing Synchronizer.

Fetches and maintains accurate LLM pricing catalogs with HTTP conditional caching (ETag / If-None-Match).
Eliminates hardcoded, out-of-date pricing tables and ensures institutional token accounting accuracy.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.PricingSync")

API_URL = "https://models.dev/api.json"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "models_dev_cache.json")
CACHE_TTL_SECONDS = 86400  # 24 hours


class ModelsDevSync:
    """Synchronizer for upstream dynamic LLM pricing data."""

    _cached_data: Optional[Dict[str, Any]] = None
    _last_checked: float = 0.0

    @classmethod
    def get_cache_path(cls) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(CACHE_PATH)), exist_ok=True)
        return CACHE_PATH

    @classmethod
    def load_cache(cls) -> Dict[str, Any]:
        """Load locally cached pricing data."""
        if cls._cached_data is not None and (time.time() - cls._last_checked < 300):
            return cls._cached_data

        path = cls.get_cache_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        cls._cached_data = loaded
                        cls._last_checked = time.time()
                        return loaded
            except Exception as e:
                logger.debug(f"[PricingSync] Failed loading cache: {e}")
        return {}

    @classmethod
    def save_cache(cls, data: Dict[str, Any], etag: Optional[str] = None):
        """Persist pricing data and metadata to disk."""
        payload = {
            "_updated_at": time.time(),
            "_etag": etag,
            "models": data,
        }
        cls._cached_data = payload
        cls._last_checked = time.time()
        path = cls.get_cache_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug(f"[PricingSync] Failed saving pricing cache: {e}")

    @classmethod
    async def sync_pricing(cls) -> Dict[str, Any]:
        """
        Conditionally fetch latest pricing using HTTP ETag validation.
        Returns the active models dictionary.
        """
        cached = cls.load_cache()
        updated_at = cached.get("_updated_at", 0)

        # Return existing cache if fresh within TTL
        if cached and (time.time() - updated_at < CACHE_TTL_SECONDS) and cached.get("models"):
            return cached.get("models", {})

        etag = cached.get("_etag")
        headers = {"If-None-Match": etag} if etag else {}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(API_URL, headers=headers)
                if response.status_code == 304:
                    logger.debug("[PricingSync] Pricing data unmodified (304). Reusing cached rates.")
                    cached["_updated_at"] = time.time()
                    return cached.get("models", {})
                if response.status_code == 200:
                    data = response.json()
                    new_etag = response.headers.get("etag")
                    cls.save_cache(data, new_etag)
                    logger.info(f"[PricingSync] Successfully updated pricing for {len(data)} models.")
                    return data
        except Exception as e:
            logger.debug(f"[PricingSync] Pricing network sync skipped: {e}")

        return cached.get("models", {})

    @classmethod
    def get_model_pricing(cls, model_name: str) -> Optional[Dict[str, float]]:
        """
        Lookup pricing rates (USD per 1M tokens) for a given model.
        Returns dict with keys: input, output, cache_read, cache_write (if found).
        """
        cached = cls.load_cache()
        models = cached.get("models", {})
        if not models:
            return None

        # Exact match
        if model_name in models:
            m = models[model_name]
            return {
                "input": float(m.get("input_cost_per_million", m.get("input", 0.0))),
                "output": float(m.get("output_cost_per_million", m.get("output", 0.0))),
                "cache_read": float(m.get("cache_read_cost_per_million", m.get("cache_read", 0.0))),
                "cache_write": float(m.get("cache_write_cost_per_million", m.get("cache_write", 0.0))),
            }

        # Prefix / partial match
        target = model_name.lower()
        for k, m in models.items():
            if k.lower() in target or target in k.lower():
                return {
                    "input": float(m.get("input_cost_per_million", m.get("input", 0.0))),
                    "output": float(m.get("output_cost_per_million", m.get("output", 0.0))),
                    "cache_read": float(m.get("cache_read_cost_per_million", m.get("cache_read", 0.0))),
                    "cache_write": float(m.get("cache_write_cost_per_million", m.get("cache_write", 0.0))),
                }

        return None
