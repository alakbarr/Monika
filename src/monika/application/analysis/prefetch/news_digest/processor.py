# ==============================================================================
# File: application/analysis/prefetch/news_digest/processor.py
# ==============================================================================

"""
Aggregated NewsDigestProcessor combining modular domain mixins.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from monika.infrastructure.providers.llm_factory import get_client_for_task
from monika.application.analysis.prefetch.news_digest.base import (
    _NewsDigestMixinBase,
    logger,
)
from monika.application.analysis.prefetch.news_digest.constants import (
    CLASSIFICATION_FEW_SHOT_EXAMPLES,
)
from monika.application.analysis.prefetch.news_digest.macro_context import MacroContextMixin
from monika.application.analysis.prefetch.news_digest.verification import NewsClassificationVerificationMixin
from monika.application.analysis.prefetch.news_digest.classification import NewsClassificationMixin
from monika.application.analysis.prefetch.news_digest.generation import NewsDigestGenerationMixin


class NewsDigestProcessor(
    MacroContextMixin,
    NewsClassificationVerificationMixin,
    NewsClassificationMixin,
    NewsDigestGenerationMixin,
):
    """Memproses berita untuk disajikan ke tahap analisis."""

    CLASSIFICATION_FEW_SHOT_EXAMPLES = CLASSIFICATION_FEW_SHOT_EXAMPLES

    def __init__(self, settings: dict):
        self.settings = settings
        self._classifier = get_client_for_task("news_classification", settings)
        self._digest_generator = get_client_for_task("news_digest", settings)
        self._macro_synth = get_client_for_task("news_digest_macro_overview", settings)
        self._verifier = get_client_for_task("news_digest_verifier", settings)
        self._classification_verifier = get_client_for_task("news_classification_verifier", settings)
        self._classification_escalation = get_client_for_task("news_classification_escalation", settings)

        # Hybrid Event-Driven 5-Day Macro Context Cache (shared singleton state via MacroContextMixin)
        # Note: Retained as class properties on MacroContextMixin to preserve singleton state across instances.

        # Backward compatibility aliases
        self._flash_lite = self._classifier
        self._flash = self._digest_generator
