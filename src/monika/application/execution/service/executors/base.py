# ==============================================================================
# File: application/execution/service/executors/base.py
# ==============================================================================

"""
Shared base typing and utilities for modular order executor mixins.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from monika.application.execution.service.base import _ExecutionServiceMixinBase

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")

__all__ = ["_ExecutionServiceMixinBase", "logger"]
