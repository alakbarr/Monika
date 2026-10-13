# ==============================================================================
# File: analysis/tools/handlers/trade_intel.py
# ==============================================================================

"""
Backward-compatible facade for trade intelligence and history tool handlers.

All handler classes and functions are now modularized under
monika.application.analysis.tools.handlers.trade_intel.
"""

from __future__ import annotations

from monika.application.analysis.tools.handlers.trade_intel import *
from monika.application.analysis.tools.handlers.trade_intel import base as base
from monika.application.analysis.tools.handlers.trade_intel import debate as debate
from monika.application.analysis.tools.handlers.trade_intel import operations as operations
from monika.application.analysis.tools.handlers.trade_intel import performance as performance
from monika.application.analysis.tools.handlers.trade_intel import registry as registry
from monika.application.analysis.tools.handlers.trade_intel import reporting as reporting
from monika.application.analysis.tools.handlers.trade_intel import simulation as simulation
