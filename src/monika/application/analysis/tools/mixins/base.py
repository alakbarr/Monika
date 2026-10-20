# ==============================================================================
# File: application/analysis/tools/mixins/base.py
# ==============================================================================

"""
Base typing infrastructure and shared logger for ToolExecutor mixins.
Provides static attribute and cross-mixin declarations during type checking.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.ToolExecutor")

FACTOR_POINT_MAP = {
    "fundamental_bias": 2,
    "dxy_confirms": 1,
    "d1_trend": 2,
    "rsi_neutral": 1,
    "near_fvg": 2,
    "near_order_block": 2,
    "in_ote_zone": 1,
    "near_sr_zone": 1,
    "breakout_expansion": 2,
    "volume_expansion": 2,
    "trend_continuation": 2,
    "momentum_expansion": 1,
    "cot_aligned": 1,
    "vix_ok": 1,
    "liquidity_sweep_confirmed": 2,
    "microstructure_ok": 1,
    "microstructure_confirmed": 1,
    "historical_pattern_consensus": 1,
    "pattern_consensus": 1,
    "session_prime": 1,  # modifier tambahan, bukan bagian base-14
    "post_event_entry": 0,  # informational tag, tidak menambah skor
    "quant_strategy_edge": 1,
    "rr_ratio_bonus": 1,
    "adr_target_bonus": 1,
}
FACTOR_CONSISTENCY_TOLERANCE = 1
FACTORS_WITH_VARIABLE_WEIGHT = {"cot_aligned"}


class _ToolExecutorMixinBase:
    """Type-checking base class for ToolExecutor mixins."""

    if TYPE_CHECKING:
        session: AsyncSession
        settings: Dict[str, Any]
        submit_attempts: int
        called_tools: Set[str]
        prefetch_satisfied_tools: Set[str]
        monotonic_restrictions: Set[str]
        model_name: Optional[str]
        symbol: Optional[str]
        _submitted_analysis_id: Optional[int]
        _submitted_brief_id: Optional[int]
        _pending_charts: Dict[str, Any]
        _pending_files: List[Dict[str, Any]]
        verification_ledger: Optional[Any]
        is_admin: bool
        deduplicator: Optional[Any]
        _session_lock: asyncio.Lock
        registry: Optional[Any]
        execution_handlers: Any
        position_handlers: Any
        macro_handlers: Any
        sentiment_handlers: Any
        technical_handlers: Any

        @property
        def effective_called_tools(self) -> Set[str]: ...
        def _resolve_symbol(self, inp: dict) -> Optional[str]: ...
        def add_pending_file(
            self,
            file_path: str,
            filename: Optional[str] = None,
            data: Optional[Any] = None,
            caption: Optional[str] = None,
        ) -> None: ...
        def pop_pending_files(self) -> list[tuple[str, Any]]: ...
        async def _get_cached_tool_result(self, tool_name: str, tool_input: dict) -> Optional[dict]: ...
        async def _save_tool_cache(self, tool_name: str, tool_input: dict, result: Any) -> None: ...
        async def _cleanup_stale_caches(self) -> None: ...
        async def _get_effective_factor_point_map(self) -> dict: ...
        async def _get_dynamic_atr_fallback(self, symbol: str) -> Optional[float]: ...
        async def _validate_tp_structural_target(
            self,
            symbol: str,
            direction: str,
            tp_price: Optional[float],
            atr: Optional[float],
            adr_ctx: Optional[dict] = None,
        ) -> list[str]: ...
        @staticmethod
        def _classify_validation_errors(errs: list[str]) -> str: ...
        async def _validate_smc_entry_proximity(
            self,
            symbol: str,
            entry_price: float,
            direction: str,
            stop_loss: float,
            atr: float,
            confluence_factors: Optional[list[str]] = None,
        ) -> list[str]: ...
        async def execute(self, tool_name: str, tool_input: dict) -> Any: ...


__all__ = [
    "_ToolExecutorMixinBase",
    "logger",
    "FACTOR_POINT_MAP",
    "FACTOR_CONSISTENCY_TOLERANCE",
    "FACTORS_WITH_VARIABLE_WEIGHT",
]
