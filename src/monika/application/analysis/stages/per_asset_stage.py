# ==============================================================================
# File: analysis/stages/per_asset_stage.py
# ==============================================================================

"""
Tahap Analisis Per-Aset (Tahap 2) - Backward-Compatible Facade.

Refactored into modular components under `analysis/stages/per_asset/`:
- `runner.py`: PerAssetRunner orchestrating all asset analyses.
- `context_builder.py`: ContextBuilderMixin for prompt and data bundle formatting.
- `specialist_pipeline.py`: SpecialistPipelineMixin for specialist debate pipeline.
- `verifiers.py`: VerifiersMixin for data quality, currency, and SSVP coherence.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.stages.per_asset.context_builder import (
    SPECIALIST_PROMPTS,
    SYMBOL_TO_COT,
    SYSTEM_PROMPT_STATIC,
    SYSTEM_PROMPT_TEMPLATE,
    ContextBuilderMixin,
    _flatten_system_prompt,
    _render_specialist_prompt,
)
from monika.application.analysis.stages.per_asset.runner import PerAssetRunner
from monika.application.analysis.stages.per_asset.specialist_pipeline import SpecialistPipelineMixin
from monika.application.analysis.stages.per_asset.verifiers import (
    VerifiersMixin,
    _get_symbol_sl_streak,
)

logger = logging.getLogger("TradingAgent.PerAssetStage")


class PerAssetStage(PerAssetRunner):
    """
    Eksekutor Tahap 2: Menghasilkan keputusan trading (BUY/SELL/WAIT) per aset.
    Backward-compatible facade wrapping modular PerAssetRunner.
    """

    pass


__all__ = [
    "PerAssetStage",
    "PerAssetRunner",
    "ContextBuilderMixin",
    "SpecialistPipelineMixin",
    "VerifiersMixin",
    "SYMBOL_TO_COT",
    "SYSTEM_PROMPT_STATIC",
    "SYSTEM_PROMPT_TEMPLATE",
    "SPECIALIST_PROMPTS",
    "_flatten_system_prompt",
    "_render_specialist_prompt",
    "_get_symbol_sl_streak",
    "clock",
    "asyncio",
]
