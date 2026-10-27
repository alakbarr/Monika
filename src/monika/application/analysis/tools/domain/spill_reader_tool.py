"""
File: analysis/tools/domain/spill_reader_tool.py
Domain tool handler allowing the AI agent to read back spilled context or observations
from PostgreSQL context_spill_blobs or disk spill cache on demand.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.tools.base_handler import ToolHandler
from monika.application.analysis.tools.registry import register_tool
from monika.application.analysis.tools.unified_registry import unified_tool_registry
from monika.infrastructure.database.models import ContextSpillBlob

logger = logging.getLogger("TradingAgent.Tools.SpillReader")


class RetrieveSpilledContextInput(BaseModel):
    """Input schema for retrieve_spilled_context tool."""

    blob_id: Optional[str] = Field(
        default=None,
        description="The pointer or ID of the spilled blob (e.g. 'spill_a1b2c3d4e5f6' or 'db://spill/spill_a1b2c3d4e5f6').",
    )
    storage_key: Optional[str] = Field(
        default=None,
        description="Backward-compatible alias for blob_id.",
    )
    offset: int = Field(0, ge=0, description="Character offset to start reading from for pagination.")
    max_chars: int = Field(4000, ge=100, le=15000, description="Maximum number of characters to retrieve in one call.")
    grep_pattern: Optional[str] = Field(
        default=None,
        description="Optional regex or substring pattern to search lines within the spilled content.",
    )
    line_offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional starting line index (0-based) for line pagination.",
    )
    line_limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
        description="Optional maximum number of lines to retrieve when using line pagination (1-500).",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_id_present(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("blob_id") and not data.get("storage_key"):
                raise ValueError("Either 'blob_id' or 'storage_key' must be provided.")
        return data


async def handle_retrieve_spilled_context(
    args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs: Any
) -> Dict[str, Any]:
    """
    Retrieves spilled content from PostgreSQL or disk spill caches.
    """
    raw_blob_id = str(args.get("blob_id") or args.get("storage_key") or "").strip()
    if not raw_blob_id:
        return {"error": "Missing required argument 'blob_id'"}

    clean_id = raw_blob_id.replace("db://spill/", "").strip()
    offset = max(0, int(args.get("offset", 0) or 0))
    max_chars = min(15000, max(100, int(args.get("max_chars", 4000) or 4000)))
    grep_pattern = args.get("grep_pattern")
    line_offset = args.get("line_offset")
    line_limit = args.get("line_limit")

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
        from monika.core.paths import DATA_DIR

        possible_dirs = [
            DATA_DIR / "spill",
            DATA_DIR / "cache" / "spillover",
            DATA_DIR / "tool_spill",
            DATA_DIR / "tool_results",
            Path("data/spill"),
            Path("data/cache/spillover"),
            Path("data/tool_spill"),
            Path("data/tool_results"),
        ]

        name_id = os.path.basename(clean_id)
        stem_id = os.path.splitext(name_id)[0]
        p_obj = Path(clean_id)

        if p_obj.exists() and p_obj.is_file():
            try:
                with open(p_obj, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                source = f"disk:{name_id}"
            except Exception as disk_err:
                logger.debug(f"[SpillReader] Direct disk read failed for {p_obj}: {disk_err}")

        if content is None:
            for pdir in possible_dirs:
                if not pdir.exists():
                    continue
                # Try exact match or file containing blob_id / stem
                for f in pdir.iterdir():
                    if (
                        clean_id in f.name
                        or name_id in f.name
                        or stem_id in f.name
                        or f.name == clean_id
                        or f.name == name_id
                        or f.stem == stem_id
                    ):
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

    # Grep filtering
    if grep_pattern:
        import re

        pattern_str = str(grep_pattern)
        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern_str), re.IGNORECASE)

        all_lines = content.splitlines()
        matching_line_indices = [i for i, line in enumerate(all_lines) if regex.search(line)]

        included_lines: Dict[int, str] = {}
        for idx in matching_line_indices:
            start_i = max(0, idx - 2)
            end_i = min(len(all_lines), idx + 3)
            for ci in range(start_i, end_i):
                included_lines[ci] = all_lines[ci]

        formatted_blocks: List[str] = []
        for line_idx in sorted(included_lines.keys()):
            marker = ">" if line_idx in matching_line_indices else " "
            formatted_blocks.append(f"{marker} {line_idx + 1:5d} | {included_lines[line_idx]}")

        res_text = "\n".join(formatted_blocks)
        return {
            "success": True,
            "blob_id": clean_id,
            "source": source,
            "grep_pattern": pattern_str,
            "match_count": len(matching_line_indices),
            "total_lines": len(all_lines),
            "content": res_text,
        }

    # Line pagination
    if line_offset is not None or line_limit is not None:
        l_offset = max(0, int(line_offset or 0))
        l_limit = min(500, max(1, int(line_limit or 100)))
        all_lines = content.splitlines()
        total_lines = len(all_lines)
        slice_lines = all_lines[l_offset : l_offset + l_limit]
        has_more_lines = (l_offset + len(slice_lines)) < total_lines

        formatted_slice = [f"  {l_offset + i + 1:5d} | {l}" for i, l in enumerate(slice_lines)]
        res_text = "\n".join(formatted_slice)
        return {
            "success": True,
            "blob_id": clean_id,
            "source": source,
            "line_offset": l_offset,
            "line_limit": l_limit,
            "returned_lines": len(slice_lines),
            "total_lines": total_lines,
            "has_more": has_more_lines,
            "next_line_offset": (l_offset + len(slice_lines)) if has_more_lines else None,
            "content": res_text,
        }

    # Default character slicing
    total_len = len(content)
    slice_data = content[offset : offset + max_chars]
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


@register_tool(
    "retrieve_spilled_context",
    aliases=["read_spilled_blob", "get_spilled_context"],
    category="SYSTEM",
    parallel_safe=True,
)
class RetrieveSpilledContextHandler(ToolHandler):
    name = "retrieve_spilled_context"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_retrieve_spilled_context(args, session=session, executor=executor, **kwargs)


# Register with unified_tool_registry
@unified_tool_registry.register(
    name="retrieve_spilled_context", category="SYSTEM", input_model=RetrieveSpilledContextInput
)
async def unified_retrieve_spilled_context(
    args: RetrieveSpilledContextInput,
    context: Any = None,
    session: Any = None,
    executor: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Retrieve spilled tool observation or context from PostgreSQL context_spill_blobs or disk."""
    effective_session = session or getattr(context, "session", None) or getattr(executor, "session", None)
    effective_exec = executor or context
    return await handle_retrieve_spilled_context(
        args.model_dump(), session=effective_session, executor=effective_exec, **kwargs
    )
