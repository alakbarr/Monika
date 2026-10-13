# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/base.py
# Description: Base mixin typing and helpers for PerAssetRunner
# ==============================================================================

import asyncio
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock

if TYPE_CHECKING:
    from monika.infrastructure.database.models import AssetAnalysis


def _get_asyncio():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "asyncio"):
        return pas.asyncio
    return asyncio


def _get_clock():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "clock"):
        return pas.clock
    return clock


class _RunnerMixinBase:
    """Base mixin defining typed attributes and cross-mixin methods for PerAssetRunner."""

    settings: Dict[str, Any]
    mt5_client: Optional[object]
    context_builder: Any
    specialist_pipeline: Any
    verifiers: Any
    _specialist_weights_cache: Dict[str, Any]
    primary_client: Any
    session_trigger_client: Any
    secondary_client: Any
    _haiku_client: Optional[Any]
    asset_universe: List[str]
    always_open_assets: Set[str]
    run_parallel: bool
    _last_analysis_time: Dict[str, datetime]
    _min_reanalysis_minutes: int
    consent_callback: Optional[Callable[..., Any]]
    is_fallback_always_approved: Optional[Callable[[], bool]]
    _skip_preflight: bool
    _last_threshold_reason: str
    verification_ledger: Any
    tool_executor: Any

    async def _fetch_stage1_confidence(self, session: AsyncSession) -> float: ...

    async def _log(self, session: AsyncSession, description: str, category: str = "analysis") -> None: ...

    async def _recover_missing_analysis(
        self,
        session: AsyncSession,
        symbol: str,
        user_message: str,
        result: dict,
        active_client: Any,
        system_prompt: Any,
        dynamic_tools: list,
        start_time: datetime,
    ) -> Optional[Any]: ...

    async def _post_process_analysis_verifications(
        self,
        session: AsyncSession,
        symbol: str,
        analysis: Optional[Any],
        decision: str,
        confidence: float,
        raw_bundle_data: Any,
        active_client: Any,
        effective_threshold: Any,
        specialist_biases: dict[str, str],
        specialist_confidence: dict[str, str],
        specialist_trust: dict[str, float],
    ) -> Tuple[str, float]: ...

    async def _run_prescreen(self, session: AsyncSession, symbol: str) -> Tuple[bool, str]: ...

    async def run_one(
        self,
        session: AsyncSession,
        symbol: str,
        extra_context: Optional[str] = None,
        skip_cooldown: bool = False,
        is_secondary: bool = False,
        bypass_prescreen: bool = False,
        use_session_trigger_client: bool = False,
        stage1_confidence: float | None = None,
    ) -> dict: ...

    async def run_all(
        self,
        session_factory: Any,
        symbols: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        per_symbol_contexts: Optional[dict] = None,
        is_secondary: bool = False,
        use_session_trigger_client: bool = False,
        skip_cooldown: bool = False,
        user_market_intel: Optional[list] = None,
    ) -> dict[str, dict]: ...

    # Methods provided by ContextBuilderMixin
    async def _check_brief_freshness_and_quality(
        self, session: AsyncSession, symbol: str, start_time: datetime
    ) -> Tuple[Optional[dict], Optional[Any], List[Tuple[str, str]]]: ...

    async def _compute_ssvp_coherence(
        self, session: AsyncSession, symbol: str, brief_check: Any
    ) -> Optional[str]: ...

    async def _fetch_stage2_bundle(
        self, session: AsyncSession, symbol: str, cot_code: str
    ) -> Tuple[Optional[str], dict, bool, str]: ...

    def _compose_stage2_system_prompt(
        self,
        symbol: str,
        cot_code: Optional[str],
        effective_threshold: int,
        tool_order_guidance: str,
        detected_regime: Optional[str] = None,
    ) -> tuple[tuple[str, str] | str, Optional[dict]]: ...

    def _build_user_message(self, symbol: str) -> str: ...
    def _build_trimmed_user_message(self, symbol: str) -> str: ...

    async def _build_stage2_context_blocks(
        self,
        session: AsyncSession,
        symbol: str,
        brief_check: Optional[Any],
        start_time: datetime,
        extra_context: Optional[str],
        stage1_confidence: Optional[float],
        coherence_injection: str,
    ) -> list[tuple[str, str]]: ...

    async def _fetch_precomputed_data(self, session: AsyncSession, symbol: str) -> str: ...

    # Methods provided by VerifiersMixin
    async def _check_minimum_data_quality(
        self, session: AsyncSession, symbol: str
    ) -> Tuple[bool, str]: ...

    async def _check_data_coherence_for_analysis(
        self, session: AsyncSession, symbol: str
    ) -> Tuple[bool, str]: ...

    async def _verify_data_currency(
        self, session: AsyncSession, symbol: str
    ) -> Tuple[bool, str]: ...

    async def _get_symbol_sl_streak(
        self, session: AsyncSession, symbol: str
    ) -> int: ...

    async def _run_second_opinion_check(
        self, session: AsyncSession, symbol: str, analysis: Any
    ) -> dict: ...

    # Methods provided by SpecialistPipelineMixin
    async def _execute_specialist_debate_pipeline(
        self, session: AsyncSession, symbol: str, raw_bundle_data: Any
    ) -> Tuple[str, Dict[str, str], Dict[str, str], Dict[str, float]]: ...
