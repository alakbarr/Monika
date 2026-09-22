"""
News tool handlers and self-registration.
Handles raw news items, pre-computed news digests, categorized news slices, web search, URL reading, and academic search.
Direct execution without circular trampolines.
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from utils.retry_decorator import retryable
from database.models import NewsItem, NewsDigest, NewsDigestSlice
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.News")


def _get_session(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, settings


async def handle_get_news_items(args: dict, **ctx) -> dict:
    session, _ = _get_session(args, ctx)
    hours_back = int(args.get("hours_back", 24))
    limit = int(args.get("limit", 20))
    currency = args.get("currency")
    min_impact = args.get("min_impact")

    if not session:
        return {"items": [], "status": "no_session"}

    cutoff = clock.now() - timedelta(hours=hours_back)
    query = select(NewsItem).where(NewsItem.published_at >= cutoff)
    if currency:
        query = query.where(NewsItem.currency_tags.like(f"%{currency.upper()}%"))
    if min_impact:
        query = query.where(NewsItem.impact >= min_impact)
    query = query.order_by(NewsItem.published_at.desc()).limit(limit)

    rows = (await session.execute(query)).scalars().all()
    return {
        "count": len(rows),
        "hours_back": hours_back,
        "items": [
            {
                "id": r.id,
                "headline": r.title,
                "title": r.title,
                "summary": r.summary,
                "source": r.source,
                "published_at": r.published_at.isoformat() if r.published_at is not None else None,
                "sentiment_score": getattr(r, "sentiment_score", None),
                "impact": getattr(r, "impact", None),
            }
            for r in rows
        ],
    }


def _wrap_untrusted_digest(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("</untrusted_external_content>", "").replace("<untrusted_external_content>", "")
    return f"<untrusted_external_content>{cleaned}</untrusted_external_content>"


async def handle_get_news_digest(args: dict, **ctx) -> dict:
    session, settings = _get_session(args, ctx)
    if not session:
        return {"status": "no_session", "digest": None, "error": "Database session unavailable"}

    hours_back = int(args.get("hours_back", 12))
    assembled_digest = None

    # 1. Priority 1: Modern rolling slices via DigestSliceGenerator
    try:
        from analysis.prefetch.digest_slice_generator import DigestSliceGenerator
        generator = DigestSliceGenerator(settings)
        assembled_digest = await generator.assemble_12h_digest(session, hours_back=hours_back)
    except Exception as e:
        logger.debug(f"[NewsTools] Slice assembly failed (falling back to legacy digest): {e}")

    # 2. Priority 2: Direct query on NewsDigest table using generated_at
    digest_row = (await session.execute(
        select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1)
    )).scalar_one_or_none()

    if not assembled_digest and not digest_row:
        return {
            "status": "empty",
            "error": "No news digest available. Use get_news_items() instead.",
            "message": "No news digest available",
            "digest": None,
            "digest_text": "",
            "generated_at": None,
            "age_hours": None,
            "macro_narrative": "",
            "currency_impacts": {},
            "key_themes": [],
            "overall_sentiment": "neutral",
        }

    # Calculate age safely
    now = clock.now()
    gen_at = getattr(digest_row, "generated_at", None) if digest_row else now
    if isinstance(gen_at, datetime):
        if gen_at.tzinfo is None and now.tzinfo is not None:
            gen_at = gen_at.replace(tzinfo=timezone.utc)
        elif gen_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age_hours = (now - gen_at).total_seconds() / 3600
    else:
        age_hours = 0.0

    staleness_warning = ""
    if isinstance(age_hours, (int, float)):
        if age_hours > 6:
            staleness_warning = (
                f"\n\n⚠️ STALE DIGEST WARNING: This digest is {age_hours:.1f}h old. "
                f"Significant market events may have occurred since generation. "
                f"MANDATORY: Call get_news_items(hours_back=3) to check for recent developments "
                f"before finalizing currency biases."
            )
        elif age_hours > 3:
            staleness_warning = (
                f"\n\nℹ️ Digest is {age_hours:.1f}h old. "
                f"Consider supplementing with get_news_items for very recent news."
            )

    raw_text = str(assembled_digest or (getattr(digest_row, "digest_text", "") or ""))
    wrapped_digest = _wrap_untrusted_digest(raw_text)
    gen_at_str = gen_at.isoformat() if isinstance(gen_at, datetime) else str(gen_at or "")

    # Extract currency impacts and macro narrative from latest NewsDigestSlice or metadata
    currency_impacts: Dict[str, Any] = {}
    macro_narrative = ""
    key_themes = []
    overall_sentiment = "neutral"

    try:
        slice_row = (await session.execute(
            select(NewsDigestSlice).order_by(NewsDigestSlice.generated_at.desc()).limit(1)
        )).scalar_one_or_none()
        if slice_row:
            if slice_row.currency_sections:
                try:
                    currency_impacts = json.loads(slice_row.currency_sections)
                except Exception:
                    pass
            if slice_row.metadata_json:
                try:
                    meta = json.loads(slice_row.metadata_json)
                    key_themes = meta.get("dominant_themes", [])
                    if not key_themes and "theme_counts" in meta:
                        key_themes = list(meta.get("theme_counts", {}).keys())
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[NewsTools] Failed extracting slice metadata: {e}")

    # Fallback to extracting from metadata block if present in raw_text
    if not key_themes and "```digest_metadata" in raw_text:
        try:
            start = raw_text.index("```digest_metadata") + len("```digest_metadata")
            end = raw_text.index("```", start)
            meta_block = json.loads(raw_text[start:end].strip())
            key_themes = meta_block.get("market_snapshot", {}).get("dominant_themes", [])
        except Exception:
            pass

    if not macro_narrative and raw_text:
        macro_narrative = raw_text[:500].strip()

    return {
        "status": "success",
        "digest_id": getattr(digest_row, "id", None),
        "generated_at": gen_at_str,
        "created_at": gen_at_str,  # Backward compatibility alias
        "age_hours": round(age_hours, 1) if isinstance(age_hours, (int, float)) else 0.0,
        "staleness_warning": staleness_warning,
        "period_hours": hours_back if assembled_digest else getattr(digest_row, "period_hours", hours_back),
        "items_processed": getattr(digest_row, "items_processed", None),
        "digest_source": "rolling_slices" if assembled_digest else "legacy_digest",
        "digest": wrapped_digest + staleness_warning,
        "digest_text": wrapped_digest,
        "overall_sentiment": overall_sentiment,
        "macro_narrative": macro_narrative,
        "key_themes": key_themes,
        "currency_impacts": currency_impacts,
    }


async def handle_get_digest_slices(args: dict, **ctx) -> dict:
    digest_res = await handle_get_news_digest(args, **ctx)
    slice_name = args.get("slice_name", "").upper()
    if digest_res.get("status") != "success":
        return digest_res

    currency_impacts = digest_res.get("currency_impacts", {})
    if slice_name and slice_name in currency_impacts:
        return {
            "status": "success",
            "slice_name": slice_name,
            "data": currency_impacts[slice_name],
            "macro_narrative": digest_res.get("macro_narrative", ""),
            "generated_at": digest_res.get("generated_at"),
            "staleness_warning": digest_res.get("staleness_warning", ""),
        }

    # If specific currency requested but not in impacts dict, search in narrative
    if slice_name and slice_name != "ALL":
        digest_text = digest_res.get("digest_text", "")
        if slice_name in digest_text:
            return {
                "status": "success",
                "slice_name": slice_name,
                "data": {"found_in_narrative": True, "excerpt": digest_text[:1000]},
                "macro_narrative": digest_res.get("macro_narrative", ""),
            }

    return {
        "status": "success",
        "slice_name": slice_name or "ALL",
        "data": currency_impacts,
        "macro_narrative": digest_res.get("macro_narrative", ""),
        "generated_at": digest_res.get("generated_at"),
    }


@retryable(max_retries=2, base_delay=0.5)
async def _execute_web_search(search_service: Any, **kwargs) -> dict:
    return await search_service.search(**kwargs)


@retryable(max_retries=2, base_delay=0.5)
async def _execute_read_url(reader: Any, url: str) -> dict:
    return await reader.read_url(url)


@retryable(max_retries=2, base_delay=0.5)
async def _execute_search_academic(client: Any, query: str, max_results: int) -> dict:
    return await client.search_papers(query=query, max_results=max_results)


async def handle_web_search(args: dict, **ctx) -> dict:
    _, settings = _get_session(args, ctx)
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "Missing required parameter 'query' for web_search"}

    topic = str(args.get("topic", "finance")).strip().lower()
    search_depth = str(args.get("search_depth", "advanced")).strip().lower()
    time_range = str(args.get("time_range", "day")).strip().lower()
    try:
        max_results = int(args.get("max_results", 5))
    except (ValueError, TypeError):
        max_results = 5

    try:
        from data_sources.web_search import get_web_search_service
        search_service = get_web_search_service(settings)
        result = await _execute_web_search(
            search_service,
            query=query,
            topic=topic,
            search_depth=search_depth,
            time_range=time_range,
            max_results=max_results,
        )
        if result and "status" not in result:
            result["status"] = "success"
        return result
    except Exception as e:
        logger.debug(f"Web search error: {e}")
        return {"status": "error", "query": query, "error": str(e)}


async def handle_read_url(args: dict, **ctx) -> dict:
    url = str(args.get("url", "")).strip()
    if not url:
        return {"error": "Missing required parameter 'url' for read_url"}

    try:
        max_chars = int(args.get("max_chars", 12000))
    except (ValueError, TypeError):
        max_chars = 12000

    try:
        from data_sources.web_reader import WebReader
        reader = WebReader(max_chars=max_chars)
        result = await _execute_read_url(reader, url)
        return result
    except Exception as e:
        logger.debug(f"Read URL error: {e}")
        return {"success": False, "url": url, "error": str(e)}


async def handle_search_academic(args: dict, **ctx) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "Missing required parameter 'query' for search_academic"}

    try:
        max_results = int(args.get("max_results", 5))
    except (ValueError, TypeError):
        max_results = 5

    try:
        from data_sources.academic_search import AcademicSearchClient
        client = AcademicSearchClient()
        result = await _execute_search_academic(client, query, max_results)
        return result
    except Exception as e:
        logger.debug(f"Search academic error: {e}")
        return {"success": False, "query": query, "papers": [], "error": str(e)}


def register_news_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_news_items",
            description="Fetch recent filtered financial news items.",
            parameters={"type": "object", "properties": {"hours_back": {"type": "integer"}, "limit": {"type": "integer"}, "currency": {"type": "string"}}},
            handler=handle_get_news_items,
            toolset="news",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_news_digest",
            description="Fetch the latest pre-computed LLM news digest.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_news_digest,
            toolset="news",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_digest_slices",
            description="Fetch specific asset or macro slice from latest news digest.",
            parameters={"type": "object", "properties": {"slice_name": {"type": "string"}}},
            handler=handle_get_digest_slices,
            toolset="news",
            requires_db=True,
        ),
        ToolDefinition(
            name="web_search",
            description="Perform real-time targeted financial web search.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}, "topic": {"type": "string"}, "max_results": {"type": "integer"}}},
            handler=handle_web_search,
            toolset="news",
            requires_db=False,
        ),
        ToolDefinition(
            name="read_url",
            description="Read full clean text content from a web URL.",
            parameters={"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}}},
            handler=handle_read_url,
            toolset="news",
            requires_db=False,
        ),
        ToolDefinition(
            name="search_academic",
            description="Search quantitative trading and macro research papers on arXiv.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
            handler=handle_search_academic,
            toolset="news",
            requires_db=False,
        ),
    ]
    for t in tools:
        registry.register(t)


register_news_tools()
