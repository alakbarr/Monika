"""
Compatibility facade shim for legacy schemas.py.
Re-exports from canonical monika.core.config.schemas.
"""

from __future__ import annotations

import monika.core.config.schemas as _canonical

from monika.core.config.schemas import (
    BenchmarkCandidateConfig,
    BenchmarkConfig,
    BenchmarkTierConfig,
    EvalsConfig,
    ExecutionConfig,
    HarnessConfig,
    IndicatorsConfig,
    LLMConfig,
    PaperTradingConfig,
    RiskConfig,
    SchedulerConfig,
    SubscriptableConfig,
    TaskRoleConfig,
    TradingAgentConfig,
    TradingConfig,
    UIConfig,
)

__all__ = ['BenchmarkCandidateConfig', 'BenchmarkConfig', 'BenchmarkTierConfig', 'EvalsConfig', 'ExecutionConfig', 'HarnessConfig', 'IndicatorsConfig', 'LLMConfig', 'PaperTradingConfig', 'RiskConfig', 'SchedulerConfig', 'SubscriptableConfig', 'TaskRoleConfig', 'TradingAgentConfig', 'TradingConfig', 'UIConfig']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
