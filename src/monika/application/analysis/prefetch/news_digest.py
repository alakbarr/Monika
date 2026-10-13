# ==============================================================================
# File: application/analysis/prefetch/news_digest.py
# ==============================================================================

"""
Backward-compatible facade for news digest prefetching and processing.

All classes, helpers, and schemas are now modularized under
monika.application.analysis.prefetch.news_digest.
"""

from __future__ import annotations

from monika.application.analysis.prefetch.news_digest import *
from monika.application.analysis.prefetch.news_digest import base as base
from monika.application.analysis.prefetch.news_digest import classification as classification
from monika.application.analysis.prefetch.news_digest import constants as constants
from monika.application.analysis.prefetch.news_digest import generation as generation
from monika.application.analysis.prefetch.news_digest import helpers as helpers
from monika.application.analysis.prefetch.news_digest import macro_context as macro_context
from monika.application.analysis.prefetch.news_digest import processor as processor
from monika.application.analysis.prefetch.news_digest import summaries as summaries
from monika.application.analysis.prefetch.news_digest import verification as verification
