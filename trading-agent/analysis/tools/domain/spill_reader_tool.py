"""
File: analysis/tools/domain/spill_reader_tool.py
Domain tool handler allowing the AI agent to read back spilled context or observations
from PostgreSQL context_spill_blobs or disk spill cache on demand.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ContextSpillBlob
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.SpillReader")


class RetrieveSpilledContextInput(BaseModel):
    """Input schema for retrieve_spilled_context tool."""
    blob_id: str = Field(
        ...,
        description="The pointer or ID of the spilled blob (e.g. 'spill_a1b2c3d4e5f6' or 'db://spill/spill_a1b2c3d4e5f6')."
    )
    offset: int = Field(
        0,
        ge=0,
        description="Character offset to start reading from for pagination."
    )
    max_chars: int = Field(
        4000,
        ge=100,
        le=15000,
        description="Maximum number of characters to retrieve in one call."
    )


async def handle_retrieve_spilled_context(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Retrieves spilled content from PostgreSQL or disk spill caches.
    """
    raw_blob_id = str(args.get("blob_id", "")).strip()
    if not raw_blob_id:
        return {"error": "Missing required argument 'blob_id'"}

    clean_id = raw_blob_id.replace("db://spill/", "").strip()
    offset = max(0, int(args.get("offset", 0) or 0))
    max_chars = min(15000, max(100, int(args.get("max_chars", 4000) or 4000)))

    content: Optional[str] = None
    source = "unknown"

    # 1. Check PostgreSQL context_spill_blobs
    effective_session = session or getattr(executor, "session", None)
    if effective_session is not None:
        try:
            stmt = select(ContextSpillBlob.payload_text).where(ContextSpillBlob.blob_id == clean_id)
            res = await effective_session.execute(stmt)
            content = res.scalar_one_or_none()
            if content is not None:
                source = "postgres"
        except Exception as db_err:
            logger.debug(f"[SpillReader] PostgreSQL lookup failed for {clean_id}: {db_err}")

    # 2. If not found in DB, check disk cache
    if content is None:
        possible_dirs = [
            Path("data/cache/spillover"),
            Path("data/tool_spill"),
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "cache" / "spillover",
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "tool_spill",
        ]
        for pdir in possible_dirs:
            if not pdir.exists():
                continue
            # Try exact match or file containing blob_id
            for f in pdir.iterdir():
                if clean_id in f.name:
                    try:
                        with open(f, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                        source = f"disk:{f.name}"
                        break
                    except Exception as disk_err:
                        logger.debug(f"[SpillReader] Disk read failed for {f}: {disk_err}")
            if content is not None:
                break

    if content is None:
        return {
            "success": False,
            "blob_id": clean_id,
            "error": f"Spilled context '{clean_id}' not found in database or disk caches.",
        }

    total_len = len(content)
    slice_data = content[offset: offset + max_chars]
    has_more = (offset + len(slice_data)) < total_len

    return {
        "success": True,
        "blob_id": clean_id,
        "source": source,
        "offset": offset,
        "length": len(slice_data),
        "total_chars": total_len,
        "has_more": has_more,
        "next_offset": (offset + len(slice_data)) if has_more else None,
        "content": slice_data,
    }


@register_tool("retrieve_spilled_context", aliases=["read_spilled_blob", "get_spilled_context"], category="SYSTEM", parallel_safe=True)
class RetrieveSpilledContextHandler(ToolHandler):
    name = "retrieve_spilled_context"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_retrieve_spilled_context(args, session=session, executor=executor, **kwargs)


# Register with unified_tool_registry
@unified_tool_registry.register(
    name="retrieve_spilled_context",
    category="SYSTEM",
    input_model=RetrieveSpilledContextInput
)
async def unified_retrieve_spilled_context(args: RetrieveSpilledContextInput, context: Any = None) -> Dict[str, Any]:
    """Retrieve spilled tool observation or context from PostgreSQL context_spill_blobs or disk."""
    session = getattr(context, "session", None) if context else None
    return await handle_retrieve_spilled_context(args.model_dump(), session=session, executor=context)
