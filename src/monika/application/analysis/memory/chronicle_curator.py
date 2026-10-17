"""
==============================================================================
File: analysis/memory/chronicle_curator.py
==============================================================================

Cognitive Memory Consolidation & Promotion Engine.
Task Role: macro_chronicle_curator

Responsibilities:
1. Evaluates matured tactical events (> 30 days old) in market_chronicle.
2. Compares against existing permanent structural regimes and milestones.
3. Uses LLM reasoning to determine:
   - MERGE: Enrich an existing permanent regime (no new row).
   - CREATE_NEW: Promote to an independent, novel permanent milestone (source_news_id = NULL).
   - RETIRE: Discard transitory micro-noise.
4. Ensures 0% amnesia gap across multi-year trading history while keeping the database
   compact, high-density, and cleanly bounded.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.infrastructure.database.models import MarketChronicle
from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.ChronicleCurator")

CURATOR_SYSTEM_PROMPT = """You are the Senior Quantitative Macro Historian & Regime Architect for Monika algorithmic trading system.
Your mission is to perform weekly cognitive macroeconomic memory consolidation, ensuring Monika retains permanent, high-density, institutional-grade memory across years without memory gaps (anti-amnesia) and without redundant clutter.

DECISION PROTOCOL:
You are provided with:
1. [PERMANENT GROUND TRUTH REGIMES & MILESTONES]: Existing permanent macro memory entries in the database.
2. [MATURED TACTICAL EVENTS (> 30 DAYS OLD)]: Tactical breaking news flashes that have concluded their active market cycle.

For each group/theme in the matured events, analyze causal macro drivers and output ONE of three actions:
1. MERGE (Dilebur): If the matured events represent ongoing development, escalation, or nuance of an EXISTING permanent regime (e.g., additional maritime drone strikes in Strait of Hormuz, continuation of Warsh higher-for-longer guidance, or tariff litigation), MERGE them into that target regime. Provide an enriched, comprehensive updated narrative. DO NOT create duplicate rows.
2. CREATE_NEW (Buat Point Baru): If the matured events represent a genuinely NOVEL macroeconomic paradigm shift, systemic crisis, or historic turning point with independent significance (e.g., unexpected sovereign debt default, major global peace treaty, emergency central bank reversal, or new banking collapse), CREATE A NEW permanent milestone.
3. RETIRE (Pensiunkan): If the event was transitory daily noise or routine economic chatter (e.g., weekly inventory fluctuation, fleeting spokesperson jawboning) that left no lasting macroeconomic structural imprint, mark it for retirement.

CRITICAL INVARIANTS:
- Narratives must be authoritative, dense, 2-3 sentences explaining the overarching theme, fundamental transmission mechanism, and asset price impact.
- Avoid low-quality squawk style. Write in professional financial English.
- Be selective: Aim for high signal-to-noise ratio.
"""


class ActionDecision(str, Enum):
    MERGE = "merge"
    CREATE_NEW = "create_new"
    RETIRE = "retire"


class CuratedMilestoneProposal(BaseModel):
    action: ActionDecision = Field(..., description="Action: merge into existing, create_new milestone, or retire")
    target_existing_chronicle_id: Optional[int] = Field(None, description="Existing chronicle ID if action is merge")
    event_date: str = Field(..., description="ISO-8601 UTC timestamp of the peak event")
    category: str = Field(..., description="policy_change | geopolitical | data_shock | regime_shift | institutional")
    headline: str = Field(..., description="Authoritative, concise, executive headline (<= 180 chars)")
    narrative: str = Field(..., description="Deep analytical macro narrative explaining causality (2-3 sentences)")
    currencies_affected: str = Field(..., description="Comma-separated assets/currencies (e.g. USD,XAUUSD,EUR)")
    severity: str = Field(default="high", description="high or critical")
    is_ongoing: bool = Field(
        default=False, description="True if condition is an active structural reality, False if resolved"
    )
    rationale: str = Field(..., description="Detailed macroeconomic rationale for the decision")


class WeeklyConsolidationOutput(BaseModel):
    proposals: List[CuratedMilestoneProposal]
    processed_tactical_ids: List[int]
    synthesis_summary: str


class ChronicleCurator:
    """Agentic Curator for weekly macro memory consolidation."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        try:
            self._client = get_client_for_task("macro_chronicle_curator", self.settings)
        except Exception as e:
            logger.warning(f"[ChronicleCurator] Failed to load macro_chronicle_curator client: {e}")
            self._client = None

    async def consolidate_matured_tactical_events(self, session: AsyncSession, force: bool = False) -> Dict[str, Any]:
        """
        Executes weekly cognitive consolidation on Monday mornings:
        1. Selects tactical entries older than 30 days (source_news_id IS NOT NULL).
        2. Compares against permanent structural regimes (source_news_id IS NULL).
        3. Uses LLM to decide MERGE vs CREATE_NEW vs RETIRE.
        4. Commits consolidated entries and cleans up processed tactical micro-events.
        """
        now = clock.now()

        # Guard: Run only on Monday morning (weekday == 0) unless forced
        if not force and now.weekday() != 0:
            return {"status": "skipped", "reason": "Weekly consolidation scheduled only for Monday morning."}

        # 1. Fetch tactical news older than 30 days
        cutoff_date = now - timedelta(days=30)
        tactical_stmt = (
            select(MarketChronicle)
            .where(
                MarketChronicle.source_news_id.isnot(None),
                MarketChronicle.event_date <= cutoff_date,
            )
            .order_by(MarketChronicle.event_date.asc())
        )
        tactical_res = await session.execute(tactical_stmt)
        tactical_events = tactical_res.scalars().all()

        if not tactical_events:
            logger.info("[ChronicleCurator] No matured tactical events (> 30 days) to consolidate.")
            return {"status": "noop", "matured_count": 0}

        # 2. Fetch permanent structural regimes & milestones
        permanent_stmt = (
            select(MarketChronicle)
            .where(MarketChronicle.source_news_id.is_(None))
            .order_by(MarketChronicle.is_ongoing.desc(), MarketChronicle.event_date.desc())
        )
        permanent_res = await session.execute(permanent_stmt)
        permanent_regimes = permanent_res.scalars().all()

        logger.info(
            f"[ChronicleCurator] Found {len(tactical_events)} matured tactical events and "
            f"{len(permanent_regimes)} permanent ground truth regimes. Initiating consolidation..."
        )

        # 3. Call LLM for cognitive consolidation
        decision = await self._run_llm_synthesis(permanent_regimes, tactical_events)

        # 4. Fallback if LLM is unavailable or unparseable
        if not decision:
            logger.warning("[ChronicleCurator] LLM synthesis returned empty. Using deterministic fallback.")
            decision = self._deterministic_fallback_synthesis(permanent_regimes, tactical_events)

        # 5. Apply decisions atomically
        applied_stats = await self._apply_consolidation_decisions(session, decision, tactical_events)
        return {"status": "success", "stats": applied_stats}

    async def _run_llm_synthesis(
        self, permanent_regimes: Sequence[MarketChronicle], tactical_events: Sequence[MarketChronicle]
    ) -> Optional[WeeklyConsolidationOutput]:
        """Calls macro_chronicle_curator task role with structured prompt."""
        if not self._client:
            return None

        perm_text_lines = []
        for r in permanent_regimes:
            status = "ACTIVE ONGOING" if r.is_ongoing else "RESOLVED HISTORICAL"
            perm_text_lines.append(
                f"- ID [{r.id}] [{r.category.upper()}] [{status}] (Date: {r.event_date.strftime('%Y-%m-%d')}): {r.headline}\n"
                f"  Narrative: {r.narrative or ''}"
            )
        permanent_context = "\n".join(perm_text_lines)

        tactical_lines = []
        for t in tactical_events[:60]:  # Limit batch to top 60 items per prompt
            tactical_lines.append(
                f"- ID [{t.id}] (Date: {t.event_date.strftime('%Y-%m-%d')}) [{t.category}] [{t.severity}]: {t.headline}\n"
                f"  Context: {(t.narrative or t.headline)[:200]}"
            )
        tactical_context = "\n".join(tactical_lines)

        user_prompt = f"""[PERMANENT GROUND TRUTH REGIMES & MILESTONES (Current Database)]:
{permanent_context}

[MATURED TACTICAL EVENTS TO CONSOLIDATE (> 30 DAYS OLD)]:
{tactical_context}

TASK:
Analyze the matured tactical events against the permanent regimes.
Synthesize and produce a structured consolidation decision adhering to the Decision Directives:
- Which events should be MERGED into existing permanent regimes (enriching their narrative)?
- Which events represent NOVEL, independent milestones that should be CREATED as new permanent milestones?
- Which events are redundant daily noise that should simply be RETIRED?

Return your response in valid JSON matching the WeeklyConsolidationOutput schema.
"""

        try:
            resp = await self._client.generate(
                prompt=user_prompt,
                system=CURATOR_SYSTEM_PROMPT,
                response_format={"type": "json_object"},
            )
            raw_text = getattr(resp, "text", "") or str(resp)

            # Parse JSON
            # Extract JSON block if surrounded by markdown code fences
            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines).strip()

            parsed = json.loads(cleaned_text)
            return WeeklyConsolidationOutput.model_validate(parsed)
        except Exception as e:
            logger.warning(f"[ChronicleCurator] LLM synthesis generation/parsing failed: {e}")
            return None

    def _deterministic_fallback_synthesis(
        self, permanent_regimes: Sequence[MarketChronicle], tactical_events: Sequence[MarketChronicle]
    ) -> WeeklyConsolidationOutput:
        """Deterministic safety net ensuring zero crash in offline mode."""
        from collections import defaultdict

        monthly_groups = defaultdict(list)
        for t in tactical_events:
            ym = t.event_date.strftime("%Y-%m")
            monthly_groups[ym].append(t)

        proposals: List[CuratedMilestoneProposal] = []
        processed_ids = [t.id for t in tactical_events]

        for ym, items in monthly_groups.items():
            critical_items = [it for it in items if it.severity == "critical"]
            top_item = critical_items[0] if critical_items else items[0]

            # Check if this top_item category matches an active permanent regime
            matching_regime = None
            for r in permanent_regimes:
                if r.is_ongoing and r.category == top_item.category:
                    matching_regime = r
                    break

            if matching_regime:
                # Merge into existing regime
                enriched_narrative = (
                    f"{matching_regime.narrative or ''} | Synthesis update ({ym}): "
                    f"Reflected ongoing developments including {top_item.headline[:100]}."
                )[:600]
                proposals.append(
                    CuratedMilestoneProposal(
                        action=ActionDecision.MERGE,
                        target_existing_chronicle_id=matching_regime.id,
                        event_date=top_item.event_date.isoformat(),
                        category=matching_regime.category,
                        headline=matching_regime.headline,
                        narrative=enriched_narrative,
                        currencies_affected=matching_regime.currencies_affected or "MACRO",
                        severity=matching_regime.severity,
                        is_ongoing=True,
                        rationale=f"Deterministic fallback: Merged into existing active {matching_regime.category} regime.",
                    )
                )
            else:
                # Create as new monthly consolidated milestone
                headlines_sample = " | ".join(dict.fromkeys(it.headline[:70] for it in items[:3]))
                proposals.append(
                    CuratedMilestoneProposal(
                        action=ActionDecision.CREATE_NEW,
                        target_existing_chronicle_id=None,
                        event_date=top_item.event_date.isoformat(),
                        category=top_item.category,
                        headline=f"Macro Synthesis ({ym}): {top_item.headline[:120]}",
                        narrative=f"Historical milestone for {ym}. Core catalysts: {headlines_sample}.",
                        currencies_affected=top_item.currencies_affected or "MACRO",
                        severity=top_item.severity,
                        is_ongoing=False,
                        rationale="Deterministic fallback: Promoted representative monthly milestone.",
                    )
                )

        return WeeklyConsolidationOutput(
            proposals=proposals,
            processed_tactical_ids=processed_ids,
            synthesis_summary=f"Deterministic fallback processed {len(tactical_events)} items into {len(proposals)} proposals.",
        )

    async def _apply_consolidation_decisions(
        self,
        session: AsyncSession,
        decision: WeeklyConsolidationOutput,
        tactical_events: Sequence[MarketChronicle],
    ) -> Dict[str, int]:
        """Applies the consolidation decisions to the database transactionally."""
        merged_count = 0
        created_count = 0
        retired_count = 0
        now = clock.now()

        for prop in decision.proposals:
            if prop.action == ActionDecision.MERGE and prop.target_existing_chronicle_id:
                # Update existing regime
                regime = await session.get(MarketChronicle, prop.target_existing_chronicle_id)
                if regime:
                    if prop.headline and len(prop.headline) > 10:
                        regime.headline = prop.headline[:300]
                    regime.narrative = prop.narrative
                    regime.is_ongoing = prop.is_ongoing
                    if not prop.is_ongoing and not regime.resolved_at:
                        regime.resolved_at = now
                    merged_count += 1
            elif prop.action == ActionDecision.CREATE_NEW:
                # Promote to permanent milestone
                try:
                    dt_str = prop.event_date
                    if dt_str.endswith("Z"):
                        dt_str = dt_str[:-1] + "+00:00"
                    ev_date = datetime.fromisoformat(dt_str)
                except Exception:
                    ev_date = now - timedelta(days=31)

                new_entry = MarketChronicle(
                    event_date=ev_date,
                    category=prop.category,
                    headline=prop.headline[:300],
                    narrative=prop.narrative,
                    currencies_affected=prop.currencies_affected or "MACRO",
                    severity=prop.severity,
                    source_news_id=None,  # Permanent seed marker
                    is_ongoing=prop.is_ongoing,
                    resolved_at=None if prop.is_ongoing else ev_date,
                    created_at=now,
                )
                session.add(new_entry)
                created_count += 1

        # Delete processed tactical items from market_chronicle
        ids_to_retire = list(set(decision.processed_tactical_ids or [t.id for t in tactical_events]))
        if ids_to_retire:
            del_stmt = delete(MarketChronicle).where(MarketChronicle.id.in_(ids_to_retire))
            await session.execute(del_stmt)
            retired_count = len(ids_to_retire)

        await session.commit()
        logger.info(
            f"[ChronicleCurator] Consolidation complete: {merged_count} merged, "
            f"{created_count} new milestones promoted, {retired_count} tactical items retired."
        )
        return {
            "merged": merged_count,
            "created": created_count,
            "retired": retired_count,
        }
