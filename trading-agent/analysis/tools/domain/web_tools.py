# ==============================================================================
# File: analysis/tools/domain/web_tools.py
# ==============================================================================

"""
Web Research, Universal Search & Content Distillation Tools for Monika.
Enables real-time macroeconomic news discovery, central bank statement fetching,
and institutional research ingestion with automatic token protection and disk spill.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry
from data_sources.web_search import WebSearchService
from data_sources.web_reader import WebReader
from utils.content_distiller import ContentDistiller

logger = logging.getLogger("TradingAgent.Tools.WebTools")

_web_search_service = WebSearchService()
_web_reader = WebReader()
_content_distiller = ContentDistiller()


class WebSearchInput(BaseModel):
    """Input parameters for performing a web search."""
    query: str = Field(
        ...,
        description="Search query terms (e.g. 'Federal Reserve interest rate decision March 2026', 'ECB press conference summary')."
    )
    max_results: Optional[int] = Field(
        5,
        description="Maximum number of search results to return (default 5, max 10)."
    )


class WebFetchInput(BaseModel):
    """Input parameters for fetching and extracting clean text from a web URL."""
    url: str = Field(
        ...,
        description="The HTTP or HTTPS URL to fetch and distill."
    )
    max_chars: Optional[int] = Field(
        16000,
        description="Character limit for the extracted text (excess will be spilled to disk with a retrieval pointer)."
    )


@unified_tool_registry.register(
    name="web_search",
    category="RESEARCH",
    input_model=WebSearchInput,
)
async def handle_web_search(
    params: WebSearchInput,
    context: Optional[Any] = None,
) -> str:
    """Performs web search across financial and general sources with multi-provider failover."""
    results = await _web_search_service.search(
        query=params.query,
        max_results=min(params.max_results or 5, 10),
    )
    return json.dumps(results, indent=2)


@unified_tool_registry.register(
    name="web_fetch",
    category="RESEARCH",
    input_model=WebFetchInput,
)
async def handle_web_fetch(
    params: WebFetchInput,
    context: Optional[Any] = None,
) -> str:
    """Fetches clean text from a web page with SSRF security checks and token distillation."""
    page_res = await _web_reader.read_url(params.url)
    if not page_res.get("success"):
        return f"Failed to fetch '{params.url}': {page_res.get('error', 'Unknown error')}"

    raw_content = page_res.get("content", "")
    title = page_res.get("title", "")

    # Distill content and defuse binaries
    distilled = _content_distiller.distill(
        raw_text=raw_content,
        title=title,
        url=params.url,
        budget=params.max_chars,
    )

    return f"# {title or params.url}\n\n{distilled['distilled_text']}"
