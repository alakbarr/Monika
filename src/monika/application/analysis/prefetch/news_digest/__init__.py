# ==============================================================================
# File: application/analysis/prefetch/news_digest/__init__.py
# ==============================================================================

"""
Modular package for news digest preprocessing and aggregation.
"""

from __future__ import annotations

from monika.application.analysis.prefetch.news_digest.base import (
    _NewsDigestMixinBase,
    logger,
)
from monika.application.analysis.prefetch.news_digest.constants import (
    CLASSIFICATION_FEW_SHOT_EXAMPLES,
    DIGEST_CONSISTENCY_SCHEMA,
    NEWS_CLASSIFICATION_SCHEMA,
    NON_BREAKING_TITLE_PATTERN,
    SENTIMENT_TAXONOMY,
    _FINANCIAL_SHORT_TOKENS,
    _NUMERIC_TOKEN_PATTERN,
    _POLARITY_GROUPS,
    _SENTIMENT_SET,
    _STRUCTURAL_NUMBERS,
)
from monika.application.analysis.prefetch.news_digest.helpers import (
    _deduplicate_items_by_title,
    _extract_numeric_claims,
    _flag_ungrounded_numbers,
    _format_news_item_for_prompt,
    _get_polarity_group,
    _is_zero_based_series,
    _jaccard_title_similarity,
    _keyword_fallback_classify,
    _normalize_contradictions,
    _normalize_num_variants,
    _resolve_item_index,
)
from monika.application.analysis.prefetch.news_digest.summaries import (
    generate_deterministic_currency_summary,
    generate_deterministic_macro_summary,
    get_classification_health_report,
)
from monika.application.analysis.prefetch.news_digest.macro_context import MacroContextMixin
from monika.application.analysis.prefetch.news_digest.verification import NewsClassificationVerificationMixin
from monika.application.analysis.prefetch.news_digest.classification import NewsClassificationMixin
from monika.application.analysis.prefetch.news_digest.generation import NewsDigestGenerationMixin
from monika.application.analysis.prefetch.news_digest.processor import NewsDigestProcessor

__all__ = [
    "CLASSIFICATION_FEW_SHOT_EXAMPLES",
    "DIGEST_CONSISTENCY_SCHEMA",
    "MacroContextMixin",
    "NEWS_CLASSIFICATION_SCHEMA",
    "NON_BREAKING_TITLE_PATTERN",
    "NewsClassificationMixin",
    "NewsClassificationVerificationMixin",
    "NewsDigestGenerationMixin",
    "NewsDigestProcessor",
    "SENTIMENT_TAXONOMY",
    "_FINANCIAL_SHORT_TOKENS",
    "_NUMERIC_TOKEN_PATTERN",
    "_NewsDigestMixinBase",
    "_POLARITY_GROUPS",
    "_SENTIMENT_SET",
    "_STRUCTURAL_NUMBERS",
    "_deduplicate_items_by_title",
    "_extract_numeric_claims",
    "_flag_ungrounded_numbers",
    "_format_news_item_for_prompt",
    "_get_polarity_group",
    "_is_zero_based_series",
    "_jaccard_title_similarity",
    "_keyword_fallback_classify",
    "_normalize_contradictions",
    "_normalize_num_variants",
    "_resolve_item_index",
    "generate_deterministic_currency_summary",
    "generate_deterministic_macro_summary",
    "get_classification_health_report",
    "logger",
]
