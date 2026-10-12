# ==============================================================================
# File: risk/risk_rule_plugin.py
# Description: Backward-compatibility shim for monika.domain.risk.risk_rule_plugin
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.risk_rule_plugin
"""

import sys
import monika.domain.risk.risk_rule_plugin as _canonical

from monika.domain.risk.risk_rule_plugin import (
    IDynamicSizingPlugin,
    IPostTradeInspectionPlugin,
    IRiskRulePlugin,
    ModularRiskRegistry,
    PluginCategory,
    PluginMetadata,
    PluginOrigin,
    RiskRuleVerdict,
    SizingResult,
    TradingPlugin,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "IDynamicSizingPlugin",
    "IPostTradeInspectionPlugin",
    "IRiskRulePlugin",
    "ModularRiskRegistry",
    "PluginCategory",
    "PluginMetadata",
    "PluginOrigin",
    "RiskRuleVerdict",
    "SizingResult",
    "TradingPlugin",
    "logger",
]
