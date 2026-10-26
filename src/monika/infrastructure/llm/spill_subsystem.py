"""
PostgreSQL Context Spill Subsystem.

Spills oversized tool payloads (>2,000 tokens) into the PostgreSQL `context_spill_blobs` table,
leaving only an exact, decisive state receipt and pointer in the active context window.
Prevents O(N) context window degradation and saves thousands of tokens per large tool call.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import ContextSpillBlob
from monika.infrastructure.llm.context_compaction import ContextCompactionEngine
from monika.infrastructure.llm.prompt_compressor import estimate_tokens

logger = logging.getLogger("TradingAgent.PostgresSpillSubsystem")


def _format_head_tail_preview(text: str, head_budget: int = 500, tail_budget: int = 500) -> str:
    """Format 50/50 head-tail preview aligned on line boundaries where possible."""
    if len(text) <= head_budget + tail_budget:
        return text

    head_raw = text[:head_budget]
    tail_raw = text[-tail_budget:]

    last_nl = head_raw.rfind("\n")
    if last_nl > head_budget // 2:
        head = head_raw[:last_nl]
    else:
        head = head_raw

    first_nl = tail_raw.find("\n")
    if 0 <= first_nl < tail_budget // 2:
        tail = tail_raw[first_nl + 1 :]
    else:
        tail = tail_raw

    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n...[Omitted {omitted} chars]...\n{tail}"


class PostgresSpillSubsystem:
    """
    Manages spilling oversized tool outputs to PostgreSQL and retrieving them on demand.
    """

    DEFAULT_SPILL_THRESHOLD: int = 2000

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        compaction_cfg = self.settings.get("context_compaction", {})
        self.spill_threshold: int = int(compaction_cfg.get("spill_threshold_tokens", self.DEFAULT_SPILL_THRESHOLD))
        self.compactor = ContextCompactionEngine(settings=self.settings)

    async def maybe_spill(
        self, session: AsyncSession, tool_name: str, output: str, cycle_id: Optional[str] = None
    ) -> str:
        """
        Evaluates output token size. If exceeding threshold, spills to DB and returns
        a compact state receipt with pointer URI.
        """
        if not output or not isinstance(output, str):
            return output or ""

        tokens = estimate_tokens(output)
        if tokens <= self.spill_threshold:
            return output

        # Protected decision tools are never spilled
        if tool_name in ("submit_asset_analysis", "submit_fundamental_brief"):
            return output

        blob_id = f"spill_{uuid.uuid4().hex[:12]}"
        try:
            from monika.infrastructure.database.db import get_session

            async with get_session() as spill_session:
                spill_record = ContextSpillBlob(
                    blob_id=blob_id,
                    cycle_id=str(cycle_id) if cycle_id else "unassigned",
                    tool_name=tool_name,
                    token_count=tokens,
                    payload_text=output,
                )
                spill_session.add(spill_record)
                await spill_session.commit()

            state_summary = self.compactor._extract_decisive_state(tool_name, output)
            logger.info(
                f"[Spill] Spilled {tool_name} ({tokens} tok) to DB pointer 'db://spill/{blob_id}'. "
                f"State summary preserved."
            )

            preview = _format_head_tail_preview(output, 500, 500)
            return (
                f"[Observation Receipt: {tool_name} {state_summary}. "
                f"Preview:\n{preview}\n"
                f"Full payload ({tokens} tokens) spilled to PostgreSQL pointer 'db://spill/{blob_id}'. "
                f"Use retrieve_spilled_context(blob_id='{blob_id}', offset=0, max_chars=4000, grep_pattern='...') to inspect or search within it.]"
            )
        except Exception as e:
            logger.warning(f"Failed to spill tool output to DB ({e}); returning original output.")
            return output

    async def retrieve_spill(
        self, session: AsyncSession, blob_id: str, offset: int = 0, max_chars: int = 4000
    ) -> Optional[str]:
        """
        Retrieves a spilled blob from PostgreSQL by its blob_id, with optional slicing.
        """
        clean_id = blob_id.replace("db://spill/", "").strip()
        stmt = select(ContextSpillBlob.payload_text).where(ContextSpillBlob.blob_id == clean_id)
        if session is not None:
            lock = getattr(session, "_session_lock", None)
            if lock is not None:
                async with lock:
                    res = await session.execute(stmt)
            else:
                res = await session.execute(stmt)
            payload = res.scalar_one_or_none()
        else:
            from monika.infrastructure.database.db import get_session

            async with get_session() as read_session:
                res = await read_session.execute(stmt)
                payload = res.scalar_one_or_none()

        if payload is None:
            return None

        if offset > 0 or max_chars < len(payload):
            return payload[offset : offset + max_chars]
        return payload
