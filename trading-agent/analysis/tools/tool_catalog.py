"""
File: analysis/tools/tool_catalog.py
Hybrid Tool Catalog with Pinned Core Tools and Dynamic BM25 Discovery for Monika.
Maintains 5-7 core tools pinned in prompt for KV-cache preservation while enabling
on-demand discovery and parameter inspection for 40+ specialized quantitative tools.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple

logger = logging.getLogger("TradingAgent.ToolCatalog")


@dataclass
class ToolCatalogEntry:
    name: str
    category: str
    description: str
    parameters_schema: Dict[str, Any]
    is_pinned: bool = False
    tokens: Set[str] = field(default_factory=set)


class HybridToolCatalog:
    """Combines pinned core tools for prompt caching with BM25 on-demand tool discovery."""

    def __init__(self):
        self._entries: Dict[str, ToolCatalogEntry] = {}
        self._pinned_tool_names: Set[str] = set()
        self._corpus_token_freq: Dict[str, int] = {}
        self._total_docs: int = 0
        self._avg_doc_len: float = 0.0

    def register_tool(
        self,
        name: str,
        category: str,
        description: str,
        parameters_schema: Dict[str, Any],
        is_pinned: bool = False,
    ) -> None:
        """Registers a tool into the catalog."""
        tokens = self._tokenize(f"{name} {category} {description}")
        entry = ToolCatalogEntry(
            name=name,
            category=category,
            description=description,
            parameters_schema=parameters_schema,
            is_pinned=is_pinned,
            tokens=tokens,
        )
        self._entries[name] = entry
        if is_pinned:
            self._pinned_tool_names.add(name)
        self._reindex()

    def _tokenize(self, text: str) -> Set[str]:
        words = text.lower().replace("_", " ").replace("-", " ").split()
        return {w for w in words if len(w) > 2}

    def _reindex(self) -> None:
        self._total_docs = len(self._entries)
        if self._total_docs == 0:
            return

        token_counts: Dict[str, int] = {}
        total_len = 0
        for entry in self._entries.values():
            total_len += len(entry.tokens)
            for t in entry.tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

        self._corpus_token_freq = token_counts
        self._avg_doc_len = total_len / max(1, self._total_docs)

    def get_pinned_tools(self) -> List[Dict[str, Any]]:
        """Returns the minimal set of pinned core tools for KV-cache preservation."""
        return [
            {
                "name": entry.name,
                "description": entry.description,
                "parameters": entry.parameters_schema,
            }
            for name, entry in self._entries.items()
            if entry.is_pinned
        ]

    def search_tools(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Searches deferred specialized tools using BM25 scoring."""
        q_tokens = self._tokenize(query)
        if not q_tokens or not self._entries:
            return []

        scores: List[Tuple[float, ToolCatalogEntry]] = []
        k1 = 1.5
        b = 0.75

        for entry in self._entries.values():
            if entry.is_pinned:
                continue  # Pinned tools are already in prompt

            doc_len = len(entry.tokens)
            score = 0.0
            matched_terms = 0

            for qt in q_tokens:
                if qt in entry.tokens:
                    matched_terms += 1
                    doc_freq = self._corpus_token_freq.get(qt, 1)
                    idf = math.log(1.0 + (self._total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
                    tf = 1.0  # Set membership binary TF
                    term_score = idf * (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (doc_len / max(1.0, self._avg_doc_len))))
                    score += term_score

            if matched_terms > 0:
                scores.append((score, entry))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, entry in scores[:top_k]:
            results.append({
                "name": entry.name,
                "category": entry.category,
                "description": entry.description,
                "score": round(score, 3),
            })
        return results

    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Returns complete parameter schema for a specific deferred tool."""
        entry = self._entries.get(tool_name)
        if not entry:
            return None
        return {
            "name": entry.name,
            "category": entry.category,
            "description": entry.description,
            "parameters": entry.parameters_schema,
        }
