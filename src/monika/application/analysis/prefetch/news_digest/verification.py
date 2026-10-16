# ==============================================================================
# File: application/analysis/prefetch/news_digest/verification.py
# ==============================================================================

"""
Second-pass verification, breaking news cross-checks, calendar corroboration, and metrics tracking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives.clock import ensure_utc
from monika.domain.market.news_impact_keywords import SHOCK_KEYWORDS
from monika.infrastructure.database.models import NewsItem
from monika.application.analysis.prefetch.news_digest.base import (
    _NewsDigestMixinBase,
    logger,
)
from monika.application.analysis.prefetch.news_digest.constants import (
    NEWS_CLASSIFICATION_SCHEMA,
    NON_BREAKING_TITLE_PATTERN,
    _SENTIMENT_SET,
)
from monika.application.analysis.prefetch.news_digest.helpers import (
    _deduplicate_items_by_title,
    _is_zero_based_series,
    _jaccard_title_similarity,
    _keyword_fallback_classify,
    _resolve_item_index,
)

NEWS_ESCALATION_SYSTEM_PROMPT = """You are a senior institutional macro risk and news analyst conducting objective, unanchored news re-verification.
Evaluate each news item against institutional economic criteria (C1-C5):
- C1: Direct Central Bank rate decision, policy statement, or emergency liquidity facility.
- C2: Tier-1 macroeconomic data surprise vs consensus (NFP, CPI, Core PCE, GDP, ISM/PMI).
- C3: Major geopolitical shock, armed conflict escalation, energy embargo, or systemic shipping route disruption.
- C4: Sovereign debt distress, currency peg break, or tier-1 financial institution insolvency.
- C5: Routine commentary, retrospective market recap, or scheduled remarks reaffirming known policy.

Classification hierarchy:
- BREAKING: Fresh (<2h) unscheduled shock or extreme tier-1 data deviation with immediate systemic market disruption.
- HIGH: Significant scheduled release with large surprise or material macro consequence altering asset pricing.
- MEDIUM: Standard economic data in line with expectations, routine policy remarks, or localized development.
- LOW / NONE: Market opinion, technical analysis, retrospective editorial, or single-stock/minor token noise.

Evaluate purely on the factual evidence and 5-day macro context. Prioritize objective reasoning before deciding impact."""


class NewsClassificationVerificationMixin(_NewsDigestMixinBase):
    """Mixin providing classification verification, boundary cross-checks, and metrics."""

    def _detect_under_classification_candidates(
        self, batch: list[NewsItem], validated_result: list, calendar_priors: dict
    ) -> list[tuple[dict, NewsItem]]:
        """Symmetric safety net to the existing over-classification downgrade logic.
        Catches items the primary classifier under-rated (e.g. MEDIUM/LOW/NONE) that
        keyword or calendar evidence suggests should actually be HIGH or BREAKING.
        Without this, the system only ever protects against false BREAKING alarms,
        never against missed real ones — an asymmetry that directly contradicts the
        zero-tolerance requirement for this stage."""
        IMPACT_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "BREAKING": 4}
        candidates = []
        is_zb = _is_zero_based_series(validated_result, len(batch))
        for item_result in validated_result:
            if not isinstance(item_result, dict):
                continue
            idx = _resolve_item_index(item_result, batch, is_zero_based=is_zb)
            if idx is None:
                continue
            news_item = batch[idx]
            current_impact = item_result.get("impact", "MEDIUM")
            if IMPACT_RANK.get(current_impact, 0) >= IMPACT_RANK["HIGH"]:
                continue
            text = f"{news_item.title} {news_item.summary or ''}".lower()
            has_shock = any(k in text for k in SHOCK_KEYWORDS)
            calendar_prior = calendar_priors.get(idx + 1)
            calendar_says_high = calendar_prior == "high"
            # Also catch cases where confidence itself was low on a non-HIGH verdict —
            # low confidence in either direction deserves a second look.
            low_confidence = (item_result.get("confidence") or 1.0) < 0.55
            if has_shock or calendar_says_high or (low_confidence and current_impact == "MEDIUM"):
                candidates.append((item_result, news_item))
        return candidates

    async def _reverify_candidates(
        self, session: AsyncSession, candidates: list[tuple[dict, NewsItem]], now_utc: datetime
    ) -> dict:
        """Generalized bidirectional re-verification (replaces the old, one-directional
        _escalate_low_confidence_items — now used for BOTH downgrade and upgrade cases)."""
        if not candidates:
            return {}
        lines = []
        for j, (item_result, news_item) in enumerate(candidates):
            f_utc = ensure_utc(news_item.fetched_at) if news_item.fetched_at else None
            age_min = round((now_utc - f_utc).total_seconds() / 60) if f_utc else "?"
            lines.append(
                f"{j + 1}. [ID #{news_item.id}]\n"
                f"   TITLE: {news_item.title[:200]}\n"
                f"   FULL SUMMARY: {(news_item.summary or '')[:600]}\n"
                f"   TIME-IN-SYSTEM: {age_min} min"
            )
        macro_5d_context = await self._build_5day_macro_context(session, now_utc)
        prompt = (
            f"Re-evaluate each of the following items from SCRATCH, without bias toward any prior verdict. "
            f"Your job is purely to assess objectively based on the institutional criteria (C1-C5), "
            f"the 5-day market context, and the full content below.\n\n"
            f"{macro_5d_context}\n\n"
            f"ITEMS:\n{chr(10).join(lines)}\n\n"
            f'Respond JSON array: [{{"index":1,"reasoning":"...","impact":"HIGH",'
            f'"confidence":0.8,"surprise_magnitude":"none","currencies":["USD"],'
            f'"sentiments":[],"key_data_point":""}}]'
        )
        try:
            result = await self._classification_escalation.classify_json(
                prompt=prompt, system_prompt=NEWS_ESCALATION_SYSTEM_PROMPT, schema=NEWS_CLASSIFICATION_SCHEMA
            )
        except Exception as e:
            logger.warning(f"[NewsClassification] Re-verification failed (non-fatal): {e}")
            return {}
        if not result:
            return {}
        if isinstance(result, dict):
            result = (
                result.get("items")
                or result.get("results")
                or result.get("data")
                or result.get("classifications")
                or [result]
            )
        if not isinstance(result, list):
            return {}
        corrected = {}
        for r in result:
            if not isinstance(r, dict):
                continue
            r_news_id = r.get("news_id")
            matched_item = None
            if r_news_id:
                for _, n_item in candidates:
                    if n_item.id == r_news_id:
                        matched_item = n_item
                        break
            if not matched_item:
                cand_items = [c[1] for c in candidates]
                idx = _resolve_item_index(r, cand_items)
                if idx is not None:
                    matched_item = cand_items[idx]
            if matched_item:
                corrected[matched_item.id] = r
        return corrected

    async def _escalate_low_confidence_items(
        self, session: AsyncSession, low_conf_items: list[tuple[dict, NewsItem]], now_utc: datetime
    ) -> dict:
        """Re-classify items marked HIGH/BREAKING by flash-lite with confidence < 0.6
        (meaning the model was uncertain), using a stronger model + full context (untruncated).
        Returns {news_item_id: corrected_result_dict}."""
        if not low_conf_items:
            return {}
        lines = []
        for j, (item_result, news_item) in enumerate(low_conf_items):
            f_utc = ensure_utc(news_item.fetched_at) if news_item.fetched_at else None
            age_min = round((now_utc - f_utc).total_seconds() / 60) if f_utc else "?"
            lines.append(
                f"{j + 1}. [ID #{news_item.id}]\n"
                f"   TITLE: {news_item.title[:200]}\n"
                f"   FULL SUMMARY: {(news_item.summary or '')[:600]}\n"
                f"   TIME-IN-SYSTEM: {age_min} min"
            )
        prompt = (
            "A fast classifier model marked the following items as borderline or uncertain (<0.6 confidence). "
            "Your job: RE-EVALUATE carefully using institutional criteria (C1-C5) and the FULL summary. "
            "Evaluate from scratch objectively without prior assumptions.\n\n"
            f"ITEMS:\n{chr(10).join(lines)}\n\n"
            'Respond JSON array: [{"index":1,"news_id":123,"reasoning":"...","impact":"HIGH","confidence":0.8,'
            '"surprise_magnitude":"none","currencies":["USD"],"sentiments":[],"key_data_point":""}]'
        )
        try:
            result = await self._classification_escalation.classify_json(
                prompt=prompt, system_prompt=NEWS_ESCALATION_SYSTEM_PROMPT, schema=NEWS_CLASSIFICATION_SCHEMA
            )
        except Exception as e:
            logger.warning(f"[NewsClassification] Escalation re-verify failed (non-fatal, keeping original): {e}")
            return {}
        if not result:
            return {}
        if isinstance(result, dict):
            result = (
                result.get("items")
                or result.get("results")
                or result.get("data")
                or result.get("classifications")
                or [result]
            )
        if not isinstance(result, list):
            return {}
        corrected = {}
        for r in result:
            if not isinstance(r, dict):
                continue
            r_news_id = r.get("news_id")
            matched_item = None
            if r_news_id:
                for _, n_item in low_conf_items:
                    if n_item.id == r_news_id:
                        matched_item = n_item
                        break
            if not matched_item:
                low_items = [n_item for _, n_item in low_conf_items]
                idx = _resolve_item_index(r, low_items)
                if idx is not None:
                    matched_item = low_items[idx]
            if matched_item:
                corrected[matched_item.id] = r
                logger.info(
                    f"[NewsClassification] Escalation resolved '{matched_item.title[:50]}': "
                    f"-> {r.get('impact')} (conf={r.get('confidence', 0):.2f})"
                )
        return corrected

    async def _verify_high_medium_boundary(self, session: AsyncSession, news_items: list[NewsItem]) -> None:
        """
        Second-pass verification khusus untuk boundary HIGH vs MEDIUM.
        Ini boundary paling konsekuensial untuk Stage 1/Stage 2 (per prioritas sistem):
        - HIGH salah diturunkan ke MEDIUM -> Stage 1 under-weight driver yang sebenarnya penting.
        - MEDIUM salah dinaikkan ke HIGH -> Stage 1 over-inflate urgensi makro yang sebenarnya rutin.
        """
        high_items = [n for n in news_items if getattr(n, "impact", None) == "HIGH"]
        medium_items = [n for n in news_items if getattr(n, "impact", None) == "MEDIUM"]
        boundary_candidates = high_items + medium_items
        if len(boundary_candidates) < 3:
            return

        verify_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "target_impact": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "target_impact", "reason"],
            },
        }

        for batch_start in range(0, len(boundary_candidates), 8):
            chunk = boundary_candidates[batch_start : batch_start + 8]
            text = "\n\n".join(
                [
                    f"{j + 1}. [current={item.impact}] {item.title[:150]}\n   {(item.summary or '')[:200]}"
                    for j, item in enumerate(chunk)
                ]
            )
            prompt = f"""You are a senior macro calibration editor for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) trading signals.
Task: For EACH item, evaluate its true market impact and assign the exact TARGET IMPACT: HIGH, MEDIUM, or LOW.

DECISION CRITERIA:
- HIGH: Direct, immediate market-moving catalysts (official Tier-1/Tier-2 economic data releases, central bank rate/policy shocks with fresh guidance, major Bitcoin ETF/regulatory enforcement, active military/geopolitical disruptions to global oil/trade routes).
- MEDIUM: Routine macro data matching consensus, general opinion/commentary without new policy cues, long-term structural economic analyses that lack immediate price catalysts (e.g., 'Germany economic model is broken', historical summaries, retrospective reviews).
- LOW: Irrelevant noise, spam, minor altcoin/memecoin commentary without broader market relevance.

CRITICAL INSTRUCTION:
Do NOT return action words like PROMOTE/DEMOTE. Simply specify what the item's true final impact SHOULD be: 'HIGH', 'MEDIUM', or 'LOW'.

ITEMS:
{text}

Respond JSON array of objects:
[{{"index": 1, "target_impact": "MEDIUM", "reason": "Structural economic analysis without immediate catalyst"}}]"""
            try:
                is_typesafe = getattr(self._classification_verifier, "provider_name", None) == "typesafe"
                if is_typesafe:
                    from typesafe_sdk import Choice

                    chunk_questions = {}
                    for j, item in enumerate(chunk):
                        chunk_questions[f"item_{j + 1}_impact"] = Choice(
                            instructions=f"Assign target market impact (HIGH, MEDIUM, or LOW) for: {item.title[:100]}",
                            criteria={
                                "HIGH": "Direct, immediate market-moving catalyst",
                                "MEDIUM": "Routine data, general commentary without immediate catalyst",
                                "LOW": "Irrelevant noise, minor commentary without broader market relevance",
                            },
                        )
                    chunk_res = await self._classification_verifier.classify_json(
                        prompt="", state=text, jev_questions=chunk_questions
                    )
                    if chunk_res and isinstance(chunk_res, dict):
                        result = [
                            {
                                "index": j + 1,
                                "target_impact": str(chunk_res.get(f"item_{j + 1}_impact", chunk[j].impact)).upper(),
                                "reason": f"System One classified as {chunk_res.get(f'item_{j + 1}_impact', chunk[j].impact)}",
                            }
                            for j in range(len(chunk))
                        ]
                    else:
                        result = await self._classification_verifier.classify_json(prompt=prompt, schema=verify_schema)
                else:
                    result = await self._classification_verifier.classify_json(prompt=prompt, schema=verify_schema)
                if not result:
                    continue
                if isinstance(result, dict):
                    result = result.get("items") or result.get("verdicts") or result.get("results") or [result]
                if not isinstance(result, list):
                    continue
                is_zb = _is_zero_based_series(result, len(chunk))
                for v in result:
                    if not isinstance(v, dict):
                        continue
                    idx = _resolve_item_index(v, chunk, is_zero_based=is_zb)
                    if idx is None:
                        continue
                    item = chunk[idx]
                    old_impact = item.impact
                    reason = str(v.get("reason", "")).strip()
                    reason_lower = reason.lower()

                    # Resolve intended target_impact (supporting both new target_impact and legacy verdict enum)
                    target = v.get("target_impact") or v.get("impact")
                    if not target:
                        verdict = v.get("verdict", "")
                        if verdict == "PROMOTE_TO_HIGH":
                            target = "HIGH"
                        elif verdict == "DEMOTE_TO_MEDIUM":
                            target = "MEDIUM"
                        elif verdict == "DEMOTE_TO_LOW":
                            target = "LOW"
                        elif verdict == "CONFIRM":
                            target = old_impact

                    target = str(target).upper() if target else old_impact

                    # Contradiction Guard: Reconcile discrepancies between target_impact and semantic reason
                    downgrade_indicators = [
                        "keep medium",
                        "stay medium",
                        "remain medium",
                        "is medium",
                        "not high",
                        "lacks catalyst",
                        "no catalyst",
                        "routine",
                        "opinion only",
                        "not market moving",
                        "historical analysis",
                        "commentary only",
                        "structural without catalyst",
                        "no immediate impact",
                        "limited impact",
                    ]
                    upgrade_indicators = [
                        "must be high",
                        "urgent breaking",
                        "major catalyst",
                        "tier-1 data release",
                        "central bank shock",
                        "major market mover",
                        "critical geopolitics",
                    ]

                    if target == "HIGH" and any(kw in reason_lower for kw in downgrade_indicators):
                        logger.warning(
                            f"[HIGH/MEDIUM Boundary] Contradiction caught & reconciled: Target HIGH overridden to MEDIUM for '{item.title[:50]}' because reason states: '{reason}'"
                        )
                        target = "MEDIUM"
                    elif target == "MEDIUM" and any(kw in reason_lower for kw in upgrade_indicators):
                        logger.warning(
                            f"[HIGH/MEDIUM Boundary] Contradiction caught & reconciled: Target MEDIUM upgraded to HIGH for '{item.title[:50]}' because reason states: '{reason}'"
                        )
                        target = "HIGH"

                    # Apply validated tier change
                    if target != old_impact:
                        item.impact = target
                        if target == "HIGH":
                            logger.info(f"[HIGH/MEDIUM Boundary] Promoted to HIGH: {item.title[:60]} ({reason})")
                        elif target == "MEDIUM":
                            logger.info(f"[HIGH/MEDIUM Boundary] Demoted to MEDIUM: {item.title[:60]} ({reason})")
                        elif target == "LOW":
                            logger.info(f"[HIGH/MEDIUM Boundary] Demoted to LOW: {item.title[:60]} ({reason})")
                await session.commit()
            except Exception as e:
                logger.warning(f"[HIGH/MEDIUM Boundary] verification pass failed (non-fatal): {e}")

    async def _validate_classification_batch(
        self,
        session: AsyncSession,
        result: list | dict,
        batch: list,
        now_utc: datetime,
        seen_breaking_titles: list,
        global_breaking_budget: dict,
        calendar_priors: dict,
    ) -> list:
        """Validate and correct classification results."""
        if not result:
            return []
        if isinstance(result, dict):
            result = (
                result.get("items")
                or result.get("results")
                or result.get("data")
                or result.get("classifications")
                or [result]
            )
        if not isinstance(result, list):
            return []

        validated = []
        breaking_indices = set()
        resolved_batch_indices = set()
        is_zero_based = _is_zero_based_series(result, len(batch))

        for item_result in result:
            if not isinstance(item_result, dict):
                continue
            idx = _resolve_item_index(item_result, batch, is_zero_based=is_zero_based)
            if idx is None or idx in resolved_batch_indices:
                continue
            resolved_batch_indices.add(idx)
            item_result["index"] = idx + 1
            news_item = batch[idx]
            impact = item_result.get("impact", "MEDIUM")
            mag = item_result.get("surprise_magnitude", "none")

            # === NEW: hard calendar-based cap (deterministic, cannot be bypassed by LLM) ===
            calendar_prior = calendar_priors.get(idx + 1)
            if calendar_prior:
                IMPACT_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "BREAKING": 4}
                CALENDAR_CAP = {"high": "BREAKING", "medium": "HIGH", "low": "MEDIUM"}
                cap = CALENDAR_CAP.get(calendar_prior)
                if cap and IMPACT_RANK.get(impact, 0) > IMPACT_RANK.get(cap, 4):
                    item_result["_downgraded_reason"] = f"calendar_impact_rating={calendar_prior} caps at {cap}"
                    impact = cap
                    item_result["impact"] = cap
                # also enforce a FLOOR: don't let LLM under-classify a HIGH-rated calendar event to LOW/NONE
                CALENDAR_FLOOR = {"high": "MEDIUM"}  # conservative floor, avoid over-forcing
                floor = CALENDAR_FLOOR.get(calendar_prior)
                if floor and IMPACT_RANK.get(impact, 0) < IMPACT_RANK.get(floor, 0):
                    item_result["_upgraded_reason"] = f"calendar_impact_rating={calendar_prior} floors at {floor}"
                    impact = floor
                    item_result["impact"] = floor
            # === existing magnitude/confidence/duplicate/budget checks continue unchanged below ===
            title_summary = f"{news_item.title or ''} {news_item.summary or ''}".lower()
            is_non_data_shock = any(w in title_summary for w in SHOCK_KEYWORDS) or any(
                w in title_summary
                for w in (
                    "emergency rate",
                    "rate cut",
                    "rate hike",
                    "war",
                    "invasion",
                    "missile",
                    "sanction",
                    "ban",
                    "default",
                    "halted",
                    "crisis",
                    "tariff",
                    "black swan",
                )
            )

            if impact == "BREAKING" and mag not in ("large", "moderate") and not is_non_data_shock:
                item_result["_downgraded_reason"] = f"magnitude={mag} not large/moderate (non-shock)"
                impact = "HIGH"
                item_result["impact"] = "HIGH"

            # Confidence-based safety downgrade
            confidence = item_result.get("confidence", 1.0)
            DOWNGRADE_MAP = {"BREAKING": "HIGH", "HIGH": "MEDIUM", "MEDIUM": "LOW"}
            if confidence is not None and confidence < 0.6 and impact in DOWNGRADE_MAP:
                downgraded = DOWNGRADE_MAP[impact]
                item_result["_confidence_downgrade"] = f"{impact}->{downgraded} (confidence={confidence:.2f})"
                impact = downgraded
                item_result["impact"] = downgraded

            # Hard validation: BREAKING requires TIME-IN-SYSTEM < 120 minutes
            if impact == "BREAKING" and news_item.fetched_at:
                f_at = ensure_utc(news_item.fetched_at)
                time_in_system = (now_utc - f_at).total_seconds() / 60 if f_at else 0
                if time_in_system > 120:
                    impact = "HIGH"
                    item_result["impact"] = "HIGH"
                    item_result["_downgraded_reason"] = f"time_in_system={time_in_system:.0f}min > 120"

            # Auto-tightening validation
            if impact == "BREAKING":
                from sqlalchemy import select

                from monika.infrastructure.database.models import SystemConfig

                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "news_auto_tighten"))
                ).scalar_one_or_none()
                if cfg and cfg.value == "1":
                    is_shock = any(w in (news_item.title or "").lower() for w in SHOCK_KEYWORDS)
                    if not is_shock:
                        impact = "HIGH"
                        item_result["impact"] = "HIGH"
                        item_result["_downgraded_reason"] = "auto_tightening_active"

            # Cross-batch deduplication for BREAKING themes
            if impact == "BREAKING":
                is_duplicate = await self._is_duplicate_breaking_event(session, news_item, now_utc)
                if is_duplicate:
                    impact = "HIGH"
                    item_result["impact"] = "HIGH"
                    item_result["_downgraded_reason"] = "duplicate_breaking_in_db"
                else:
                    is_similar_to_seen = any(
                        _jaccard_title_similarity(news_item.title or "", seen_title) >= 0.5
                        for seen_title in seen_breaking_titles
                    )
                    if is_similar_to_seen:
                        impact = "HIGH"
                        item_result["impact"] = "HIGH"
                        item_result["_downgraded_reason"] = "cross_batch_dedup_jaccard"
                    else:
                        seen_breaking_titles.append(news_item.title or "")

            if impact == "BREAKING" and NON_BREAKING_TITLE_PATTERN.search(news_item.title or ""):
                # FIX: Demote to HIGH (not MEDIUM) so it still triggers re-analysis if actionable
                impact = "HIGH"
                item_result["impact"] = "HIGH"
                item_result["_downgraded_reason"] = (
                    "non_breaking_title_pattern (bahasa opini/analisis/preview terdeteksi di judul)"
                )

            # Hard validation: BREAKING max 2 per batch
            if impact == "BREAKING":
                if len(breaking_indices) >= 2:
                    impact = "HIGH"
                    item_result["impact"] = "HIGH"
                    item_result["_downgraded_reason"] = "max_breaking_per_batch_exceeded"
                elif global_breaking_budget["count"] >= global_breaking_budget["max"]:
                    impact = "HIGH"
                    item_result["impact"] = "HIGH"
                    item_result["_downgraded_reason"] = "global_breaking_budget_exceeded"
                else:
                    breaking_indices.add(idx)
                    global_breaking_budget["count"] += 1

            # Calendar cross-check
            if impact == "BREAKING":
                has_event = await self._cross_check_breaking_against_calendar(session, news_item, now_utc)
                if not has_event:
                    # Downgrade if no recent calendar event supports this breaking data release
                    # Unless it contains keywords indicative of shock or high confidence from LLM
                    is_shock = any(w in (news_item.title or "").lower() for w in SHOCK_KEYWORDS)
                    conf = float(item_result.get("confidence", 1.0) or 1.0)
                    if not is_shock and conf < 0.70:
                        impact = "HIGH"
                        item_result["impact"] = "HIGH"
                        item_result["_downgraded_reason"] = "no_calendar_event_low_conf"

            # NEW: cross-check magnitude untuk data release (non-data shocks exempt)
            if impact == "BREAKING" and not is_non_data_shock and mag in ("large", "moderate"):
                kdp = item_result.get("key_data_point", "").strip()
                if not kdp:
                    impact = "HIGH"
                    item_result["impact"] = "HIGH"
                    item_result["_downgraded_reason"] = "missing_key_data_point_grounding"
                else:
                    magnitude_ok, mag_reason = await self._cross_check_breaking_surprise_magnitude(
                        session, news_item, now_utc
                    )
                    if not magnitude_ok:
                        impact = "HIGH"
                        item_result["impact"] = "HIGH"
                        item_result["_downgraded_reason"] = f"surprise_magnitude_check: {mag_reason}"

            # Validate impact value
            if impact not in ("BREAKING", "HIGH", "MEDIUM", "LOW", "NONE"):
                impact = "MEDIUM"
                item_result["impact"] = "MEDIUM"

            # Validate currencies
            valid_currencies = {"USD", "EUR", "GBP", "JPY", "AUD", "XAU", "XTI", "BTC", "NON"}
            currencies = [c for c in item_result.get("currencies", []) if c in valid_currencies]
            if not currencies:
                currencies = ["NON"]
            item_result["currencies"] = currencies

            # NEW: validasi sentiment terhadap taksonomi terkontrol
            sentiments = [s for s in item_result.get("sentiments", []) if s in _SENTIMENT_SET]
            item_result["sentiments"] = sentiments

            validated.append(item_result)

        return validated

    async def _is_duplicate_breaking_event(self, session: AsyncSession, news_item, now_utc: datetime) -> bool:
        """Check database for recent BREAKING news on the same theme."""
        from sqlalchemy import select

        from monika.infrastructure.database.models import NewsItem

        check_time = ensure_utc(news_item.fetched_at) or now_utc
        since = check_time - timedelta(hours=4)

        # Get recent breaking news
        stmt = select(NewsItem).where(
            NewsItem.fetched_at >= since, NewsItem.impact == "BREAKING", NewsItem.id != news_item.id
        )
        recent_breaking = (await session.execute(stmt)).scalars().all()

        if not recent_breaking:
            return False

        FINANCIAL_COMMON_WORDS = {
            "market",
            "markets",
            "dollar",
            "rates",
            "report",
            "economic",
            "prices",
            "price",
            "yield",
            "yields",
            "today",
            "ahead",
            "after",
            "since",
            "about",
            "could",
            "would",
            "first",
            "month",
            "years",
            "daily",
            "weekly",
            "update",
        }
        title_lower = (news_item.title or "").lower()
        keywords = set(w for w in title_lower.split() if len(w) > 4 and w not in FINANCIAL_COMMON_WORDS)

        for rb in recent_breaking:
            rb_title = (rb.title or "").lower()
            rb_keywords = set(w for w in rb_title.split() if len(w) > 4 and w not in FINANCIAL_COMMON_WORDS)

            # If they share 4 or more specific significant words, consider it a duplicate event
            overlap = keywords.intersection(rb_keywords)
            if len(overlap) >= 4:
                return True

        return False

    async def _cross_check_breaking_against_calendar(self, session: AsyncSession, news_item, now_utc: datetime) -> bool:
        """Check if there was a HIGH impact calendar event in the last 4 hours."""
        try:
            from sqlalchemy import or_, select

            from monika.infrastructure.database.models import EconomicCalendar

            # Check window: 4 hours before fetched time
            check_time = ensure_utc(news_item.fetched_at) or now_utc
            since = check_time - timedelta(hours=4)

            stmt = (
                select(EconomicCalendar)
                .where(
                    EconomicCalendar.event_time >= since,
                    EconomicCalendar.event_time <= check_time + timedelta(hours=1),
                    or_(
                        EconomicCalendar.impact == "HIGH",
                        EconomicCalendar.impact == "High",
                        EconomicCalendar.impact == "high",
                    ),
                )
                .limit(1)
            )

            event = (await session.execute(stmt)).scalar_one_or_none()
            return event is not None
        except Exception as e:
            logger.debug(f"Calendar cross-check failed (fail-open): {e}")
            return True

    async def _cross_check_breaking_surprise_magnitude(
        self, session: AsyncSession, news_item, now_utc: datetime
    ) -> tuple[bool, str]:
        """Memvalidasi bahwa klasifikasi BREAKING untuk data release didukung oleh surprise_score
        aktual yang tersimpan di EconomicCalendar (bukan sekadar klaim LLM)."""
        try:
            from sqlalchemy import select

            from monika.infrastructure.database.models import EconomicCalendar

            check_time = ensure_utc(news_item.fetched_at) or now_utc
            since = check_time - timedelta(hours=4)
            stmt = (
                select(EconomicCalendar)
                .where(
                    EconomicCalendar.event_time >= since,
                    EconomicCalendar.event_time <= check_time + timedelta(hours=1),
                    EconomicCalendar.impact.in_(["high", "High", "HIGH"]),
                    EconomicCalendar.surprise_score.is_not(None),
                )
                .order_by(EconomicCalendar.event_time.desc())
                .limit(3)
            )
            events = (await session.execute(stmt)).scalars().all()
            if not events:
                return (True, "no_surprise_data_available")  # fail-open, data belum sempat dihitung
            max_abs_surprise = max(abs(e.surprise_score or 0.0) for e in events)
            MIN_SURPRISE_FOR_BREAKING = 15.0  # tinjau ulang periodik via compute_news_classification_calibration

            from monika.application.analysis.calculators.economic_surprise import _parse_numeric

            # Check relative score (>= 15.0) AND indicator-specific absolute thresholds
            has_major_surprise = False
            for e in events:
                if abs(e.surprise_score or 0.0) >= MIN_SURPRISE_FOR_BREAKING:
                    has_major_surprise = True
                    break
                act_v = _parse_numeric(e.actual)
                fc_v = _parse_numeric(e.forecast)
                if act_v is not None and fc_v is not None:
                    name_l = (e.event_name or "").lower()
                    diff = abs(act_v - fc_v)
                    # Interest Rate decision: 15 bps (0.15%)
                    if any(k in name_l for k in ("rate", "fed funds", "refinancing", "cash rate")) and diff >= 0.15:
                        has_major_surprise = True
                        break
                    # CPI / PCE / Inflation: 0.20%
                    if any(k in name_l for k in ("cpi", "pce", "inflation", "ppi")) and diff >= 0.20:
                        has_major_surprise = True
                        break
                    # NFP / Payrolls: 30K
                    if any(k in name_l for k in ("nonfarm", "payroll", "employment change")) and (
                        diff >= 30000 or (diff >= 30.0 and act_v < 1000)
                    ):
                        has_major_surprise = True
                        break
                    # Unemployment Rate: 0.20%
                    if "unemployment" in name_l and diff >= 0.20:
                        has_major_surprise = True
                        break

            if not has_major_surprise:
                return (
                    False,
                    f"surprise_score={max_abs_surprise:.1f} and indicator values below absolute BREAKING thresholds",
                )
            return (True, f"surprise confirms BREAKING magnitude (score={max_abs_surprise:.1f})")
        except Exception as e:
            logger.debug(f"Surprise magnitude cross-check failed (fail-open): {e}")
            return (True, "check_failed_fail_open")

    async def _track_classification_metrics(self, session: AsyncSession, classified_items: list):
        impact_dist = {"BREAKING": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
        for item in classified_items:
            impact = getattr(item, "impact", "NONE") or "NONE"
            impact_dist[impact] = impact_dist.get(impact, 0) + 1
        total = sum(impact_dist.values())
        breaking_pct = impact_dist["BREAKING"] / total * 100 if total > 0 else 0
        if breaking_pct > 20:
            logger.warning(f"[NewsClassification] RATE ANOMALY: {breaking_pct:.0f}% item BREAKING (ambang: 20%).")
            try:
                from monika.core.analytics.news_classification_tracker import compute_news_classification_calibration
                from monika.infrastructure.database.models import SystemConfig

                calib = await compute_news_classification_calibration(session, days_back=3)
                breaking_stats = calib.get("by_impact", {}).get("BREAKING", {})
                match_rate = breaking_stats.get("match_rate_pct", 100)
                sample = breaking_stats.get("total", 0)
                # Hanya auto-tighten kalau ADA bukti outcome bahwa BREAKING beneran sering
                # tidak match pergerakan harga nyata — bukan cuma karena hari ini banyak berita.
                should_tighten = sample < 5 or match_rate < 45
                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "news_auto_tighten"))
                ).scalar_one_or_none()
                new_val = "1" if should_tighten else "0"
                if cfg:
                    cfg.value = new_val
                else:
                    session.add(SystemConfig(key="news_auto_tighten", value=new_val))
                await session.commit()
                logger.warning(
                    f"[NewsClassification] Rate anomaly {'DIKONFIRMASI' if should_tighten else 'DITOLAK'} oleh outcome "
                    f"(3d BREAKING match_rate={match_rate}% dari {sample} sampel). news_auto_tighten={new_val}"
                )
            except Exception as e:
                logger.debug(f"Outcome-corroborated anomaly check gagal, fallback ke rate-only: {e}")
        import json

        from monika.infrastructure.database.models import SystemConfig

        hour_key = f"news_cls_dist_{datetime.now(timezone.utc).strftime('%Y%m%d_%H')}"
        existing = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == hour_key))
        ).scalar_one_or_none()
        if not existing:
            session.add(
                SystemConfig(key=hour_key, value=json.dumps({**impact_dist, "breaking_pct": round(breaking_pct, 1)}))
            )
            await session.commit()
