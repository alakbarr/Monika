# ==============================================================================
# File: analysis/stages/per_asset/runner.py
# Description: Modular facade orchestrator for Stage 2 Per-Asset analysis
# ==============================================================================

import asyncio
import logging
import sys
from datetime import datetime
from typing import Any, Callable, Optional

import monika.core.primitives.clock as clock
from monika.application.analysis.stages.per_asset.context_builder import (
    ContextBuilder,
    ContextBuilderMixin,
)
from monika.application.analysis.stages.per_asset.runner_mixins import (
    BatchOrchestratorMixin,
    PostProcessVerificationMixin,
    PrescreenMixin,
    RecoveryMixin,
    SingleAssetAnalysisMixin,
)
from monika.application.analysis.stages.per_asset.specialist_pipeline import (
    SpecialistPipeline,
    SpecialistPipelineMixin,
)
from monika.application.analysis.stages.per_asset.verifiers import (
    VerifierService,
    VerifiersMixin,
)
from monika.infrastructure.providers.llm_factory import create_client, get_client_for_task

logger = logging.getLogger("TradingAgent.PerAssetStage")


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


class PerAssetRunner(
    ContextBuilderMixin,
    SpecialistPipelineMixin,
    VerifiersMixin,
    PrescreenMixin,
    RecoveryMixin,
    PostProcessVerificationMixin,
    SingleAssetAnalysisMixin,
    BatchOrchestratorMixin,
):
    """Eksekutor utama Tahap 2 yang mengorkestrasi analisis seluruh aset."""

    def __init__(self, settings: dict, mt5_client: Optional[object] = None) -> None:
        """
        Args:
            settings: Dictionary pengaturan lengkap.
            mt5_client: Optional MT5 client instance for preflight quote checks and execution.
        """
        self.settings = settings
        self.mt5_client = mt5_client
        # Composition over Inheritance (H-1)
        self.context_builder = ContextBuilder(settings)
        self.specialist_pipeline = SpecialistPipeline(settings, runner=self)
        self.verifiers = VerifierService(settings, runner=self)

        self._specialist_weights_cache: dict[str, Any] = {"weights": None, "ts": None}
        analysis_cfg = settings.get("analysis", {}) or settings.get("claude", {})

        # Batas turn tool dikurangi karena data sudah dibundel (pre-bundled)
        _stage2_tool_turns = analysis_cfg.get("stage2_max_tool_turns", 8)

        self.primary_client = get_client_for_task("stage2_per_asset_primary", settings)
        self.session_trigger_client = get_client_for_task("stage2_session_trigger", settings)

        try:
            self.secondary_client = get_client_for_task("stage2_per_asset_secondary", settings)
        except Exception:
            self.secondary_client = self.primary_client

        # Pre-screener opsional (Haiku)
        prescreen_task = settings.get("llm", {}).get("task_roles", {}).get("stage2_prescreen", {})
        prescreen_model = prescreen_task.get("primary", "")
        try:
            self._haiku_client = get_client_for_task("stage2_prescreen", settings) if prescreen_model else None
        except Exception:
            self._haiku_client = None
        trading_cfg = settings.get("trading", {})
        self.asset_universe: list[str] = trading_cfg.get("asset_universe", ["XAUUSD", "EURUSD"])
        self.always_open_assets = set(trading_cfg.get("24_7_assets", ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]))
        self.run_parallel: bool = trading_cfg.get("parallel_asset_analysis", False)

        self._last_analysis_time: dict[str, datetime] = {}
        self._min_reanalysis_minutes: int = int(trading_cfg.get("schedule", {}).get("min_reanalysis_minutes", 30))
        self.consent_callback: Optional[Callable[..., Any]] = None
        self.is_fallback_always_approved: Optional[Callable[[], bool]] = None


__all__ = [
    "PerAssetRunner",
    "_get_asyncio",
    "_get_clock",
    "create_client",
    "get_client_for_task",
]
