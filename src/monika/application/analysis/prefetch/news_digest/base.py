# ==============================================================================
# File: application/analysis/prefetch/news_digest/base.py
# ==============================================================================

"""
Shared logging, constants, and typing infrastructure for NewsDigestProcessor mixins.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from monika.infrastructure.database.models import NewsItem

logger = logging.getLogger("TradingAgent.NewsDigest")


class _NewsDigestMixinBase:
    """Type-checking base contract for NewsDigestProcessor modular mixins."""

    if TYPE_CHECKING:
        settings: dict
        _classifier: Any
        _digest_generator: Any
        _macro_synth: Any
        _verifier: Any
        _classification_verifier: Any
        _classification_escalation: Any
        _macro_context_cache: Optional[str]
        _macro_context_cache_time: Optional[datetime]
        _last_known_brief_id: Optional[int]
        _last_known_breaking_id: Optional[int]
        _flash_lite: Any
        _flash: Any
        CLASSIFICATION_FEW_SHOT_EXAMPLES: str

        def invalidate_macro_context_cache(self) -> None: ...
        async def _build_5day_macro_context(self, session: AsyncSession, now_utc: datetime) -> str: ...
        async def _build_7day_macro_grounding_context(self, session: AsyncSession, now_utc: datetime) -> str: ...
        def _detect_under_classification_candidates(
            self, batch: list[NewsItem], validated_result: list, calendar_priors: dict
        ) -> list[tuple[dict, NewsItem]]: ...
        async def _reverify_candidates(
            self, session: AsyncSession, candidates: list[tuple[dict, NewsItem]], now_utc: datetime
        ) -> dict: ...
        async def _escalate_low_confidence_items(
            self, session: AsyncSession, low_conf_items: list[tuple[dict, NewsItem]], now_utc: datetime
        ) -> dict: ...
        async def _get_calendar_impact_priors(
            self, session: AsyncSession, batch: list[NewsItem], now_utc: datetime
        ) -> dict[int, Optional[str]]: ...
        def _is_potentially_relevant(self, title: Optional[str], summary: Optional[str]) -> bool: ...
        async def _verify_high_medium_boundary(self, session: AsyncSession, news_items: list[NewsItem]) -> None: ...
        async def _get_recent_classified_titles(self, session: AsyncSession, hours: int = 12) -> list[str]: ...
        async def classify_unscored_news(self, session: AsyncSession, hours_back: int = 6) -> int: ...
        async def _validate_classification_batch(
            self,
            session: AsyncSession,
            result: list | dict,
            batch: list,
            now_utc: datetime,
            seen_breaking_titles: list,
            global_breaking_budget: dict,
            calendar_priors: dict,
        ) -> list: ...
        async def _is_duplicate_breaking_event(
            self, session: AsyncSession, news_item: Any, now_utc: datetime
        ) -> bool: ...
        async def _cross_check_breaking_against_calendar(
            self, session: AsyncSession, news_item: Any, now_utc: datetime
        ) -> bool: ...
        async def _cross_check_breaking_surprise_magnitude(
            self, session: AsyncSession, news_item: Any, now_utc: datetime
        ) -> tuple[bool, str]: ...
        async def _track_classification_metrics(self, session: AsyncSession, classified_items: list) -> None: ...
        async def _should_use_cache(self, session: AsyncSession, cache_hours: float) -> tuple[bool, Optional[str]]: ...
        def _compute_quick_priced_in(self, news_items: Sequence[NewsItem] | list, theme_counts: dict) -> dict: ...
        async def _build_structured_metadata_dict(
            self, session: AsyncSession, all_significant: Sequence[NewsItem] | list
        ) -> dict: ...
        async def _build_structured_metadata(
            self, session: AsyncSession, all_significant: Sequence[NewsItem] | list
        ) -> str: ...
        def _extract_prior_metadata(self, text: str) -> dict: ...
        def _build_structured_delta(self, curr_meta: dict, prev_meta: dict) -> str: ...
        async def _build_currency_signals_summary(self, grouped_news: dict, target_currencies: list) -> str: ...
        async def create_news_digest(self, session: AsyncSession, hours_back: int = 12) -> Optional[str]: ...
        async def _check_digest_internal_consistency(self, digest_text: str) -> Optional[dict]: ...
        async def _reconcile_digest_contradictions(
            self, digest_text: str, contradictions: list[dict]
        ) -> Optional[str]: ...
        async def _compute_coverage_gaps(self, session: AsyncSession, digest_text: str) -> str: ...
        async def _cleanup_old_digests(self, session: AsyncSession) -> None: ...
        async def get_latest_digest(self, session: AsyncSession, hours_back: int = 12) -> Optional[str]: ...
