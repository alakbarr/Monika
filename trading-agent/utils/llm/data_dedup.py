"""
Generation-tracked deduplication for repeated market data fetches.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.DataDedup")


class DataFetchDeduplicator:
    """
    Tracks market data query results within an analysis cycle.
    Returns lightweight stubs for redundant queries whose data has not changed,
    while automatically invalidating on context compaction to preserve reasoning grounds.
    """

    DEDUP_CANDIDATE_TOOLS = frozenset({
        "get_price_history",
        "get_technical_indicators",
        "get_atr",
        "get_open_positions",
        "get_account_info",
        "get_dxy",
        "get_vix",
    })

    def __init__(self):
        self._cache: Dict[str, Tuple[str, int]] = {}  # key -> (content_hash, generation)
        self._generation: int = 1

    def _make_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        try:
            serialized_args = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            serialized_args = str(args)
        args_hash = hashlib.md5(serialized_args.encode("utf-8")).hexdigest()[:8]
        return f"{tool_name}:{args_hash}"

    def check_and_record(self, tool_name: str, args: Dict[str, Any], result_str: str) -> Optional[str]:
        """
        If result_str is identical to a prior call with same args in the current generation,
        returns a deduplication notice. Otherwise records and returns None.
        """
        if tool_name not in self.DEDUP_CANDIDATE_TOOLS:
            return None

        if not result_str or len(result_str) < 50:
            return None

        key = self._make_key(tool_name, args)
        content_hash = hashlib.md5(result_str.encode("utf-8")).hexdigest()[:12]

        if key in self._cache:
            prev_hash, prev_gen = self._cache[key]
            if prev_hash == content_hash and prev_gen == self._generation:
                return f"[Data unchanged since previous fetch in this cycle (gen {self._generation}). Refer to earlier tool observation.]"

        self._cache[key] = (content_hash, self._generation)
        return None

    def invalidate_on_compaction(self) -> None:
        """Increments generation counter and clears cached results after context compaction."""
        self._generation += 1
        self._cache.clear()
        logger.debug(f"[DataDedup] Cache invalidated for context compaction (generation={self._generation}).")
