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
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Dict, List, Union

from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

from analysis.stages.per_asset.context_builder import (
    SYMBOL_TO_COT,
    SYSTEM_PROMPT_STATIC,
    SYSTEM_PROMPT_TEMPLATE,
    SPECIALIST_PROMPTS,
    _flatten_system_prompt,
    _render_specialist_prompt,
    ContextBuilderMixin,
)
from analysis.stages.per_asset.specialist_pipeline import SpecialistPipelineMixin
from analysis.stages.per_asset.verifiers import (
    VerifiersMixin,
    _get_symbol_sl_streak,
)
from analysis.stages.per_asset.runner import PerAssetRunner

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
