"""
PostgreSQL Context Spill Subsystem.

Spills oversized tool payloads (>2,000 tokens) into the PostgreSQL `context_spill_blobs` table,
leaving only an exact, decisive state receipt and pointer in the active context window.
Prevents O(N) context window degradation and saves thousands of tokens per large tool call.
"""

import uuid
import logging
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ContextSpillBlob
from utils.llm.prompt_compressor import estimate_tokens
from utils.llm.context_compaction import ContextCompactionEngine

logger = logging.getLogger("TradingAgent.PostgresSpillSubsystem")


class PostgresSpillSubsystem:
    """
    Manages spilling oversized tool outputs to PostgreSQL and retrieving them on demand.
    """

    DEFAULT_SPILL_THRESHOLD: int = 2000

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        compaction_cfg = self.settings.get("context_compaction", {})
        self.spill_threshold: int = int(
            compaction_cfg.get("spill_threshold_tokens", self.DEFAULT_SPILL_THRESHOLD)
        )
        self.compactor = ContextCompactionEngine(settings=self.settings)

    async def maybe_spill(
        self,
        session: AsyncSession,
        tool_name: str,
        output: str,
        cycle_id: Optional[str] = None
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
            spill_record = ContextSpillBlob(
                blob_id=blob_id,
                cycle_id=str(cycle_id) if cycle_id else "unassigned",
                tool_name=tool_name,
                token_count=tokens,
                payload_text=output
            )
            session.add(spill_record)
            await session.flush()

            state_summary = self.compactor._extract_decisive_state(tool_name, output)
            logger.info(
                f"[Spill] Spilled {tool_name} ({tokens} tok) to DB pointer 'db://spill/{blob_id}'. "
                f"State summary preserved."
            )

            return (
                f"[Observation Receipt: {tool_name} {state_summary}. "
                f"Full payload ({tokens} tokens) spilled to PostgreSQL pointer 'db://spill/{blob_id}'. "
                f"Use read_spilled_blob(blob_id='{blob_id}') if granular slice needed.]"
            )
        except Exception as e:
            logger.warning(f"Failed to spill tool output to DB ({e}); returning original output.")
            return output

    async def retrieve_spill(
        self,
        session: AsyncSession,
        blob_id: str,
        offset: int = 0,
        max_chars: int = 4000
    ) -> Optional[str]:
        """
        Retrieves a spilled blob from PostgreSQL by its blob_id, with optional slicing.
        """
        clean_id = blob_id.replace("db://spill/", "").strip()
        stmt = select(ContextSpillBlob.payload_text).where(ContextSpillBlob.blob_id == clean_id)
        res = await session.execute(stmt)
        payload = res.scalar_one_or_none()

        if payload is None:
            return None

        if offset > 0 or max_chars < len(payload):
            return payload[offset:offset + max_chars]
        return payload
