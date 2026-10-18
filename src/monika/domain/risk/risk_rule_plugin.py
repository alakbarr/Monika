# ==============================================================================
# File: risk/risk_rule_plugin.py
# ==============================================================================

"""
Risk Rule and Dynamic Sizing Plugin Contracts for Monika Trading Harness.
Provides modular pre-order validation, dynamic sizing adjustments, and post-trade inspection.
Core safety invariants (kill-switch, hard SL, max lot cap, max drawdown <= 5%) remain
hardcoded in RiskGate and cannot be bypassed.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from monika.core.contracts.plugin import PluginCategory, PluginMetadata, PluginOrigin, TradingPlugin
from monika.domain.risk.position_sizing import SizingResult

logger = logging.getLogger("TradingAgent.Risk.Plugin")


@dataclass
class RiskRuleVerdict:
    rule_id: str
    passed: bool
    rejection_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class IRiskRulePlugin(TradingPlugin, ABC):
    """
    Contract for modular pre-trade risk inspection rules.
    Examples: Session trading hours filter, custom volatility bands, sector exposure limits.
    """

    category: PluginCategory = PluginCategory.RISK_RULE

    @abstractmethod
    async def validate_pre_order(
        self,
        session: Any,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        account_equity: float | None = None,
        **kwargs: Any,
    ) -> RiskRuleVerdict:
        """Evaluate pre-order parameters against the custom risk rule."""
        pass


class IDynamicSizingPlugin(TradingPlugin, ABC):
    """
    Contract for dynamic position sizing modifiers.
    Examples: Kelly Criterion adjustment, ATR volatility scaling, Win-streak scaling.
    """

    category: PluginCategory = PluginCategory.DYNAMIC_SIZING

    @abstractmethod
    async def adjust_sizing(
        self,
        session: Any,
        symbol: str,
        base_lots: float,
        account_equity: float,
        **kwargs: Any,
    ) -> float:
        """Adjust proposed lot size within safe boundaries."""
        pass


class IPostTradeInspectionPlugin(TradingPlugin, ABC):
    """
    Contract for post-trade fills and closed position auditing.
    Examples: Slippage anomaly detection, execution latency tracker.
    """

    @abstractmethod
    async def inspect_post_trade(
        self,
        session: Any,
        deal_data: dict[str, Any],
    ) -> None:
        """Process post-trade execution metrics and audit fills."""
        pass


class ModularRiskRegistry:
    """
    Central registry for active modular risk rules and dynamic sizing plugins.
    Integrated into RiskGate to extend validation while preserving core safety invariants.
    """

    _instance: ModularRiskRegistry | None = None

    def __init__(self):
        self._rules: dict[str, IRiskRulePlugin] = {}
        self._sizing_plugins: dict[str, IDynamicSizingPlugin] = {}
        self._post_trade_plugins: dict[str, IPostTradeInspectionPlugin] = {}

    @classmethod
    def get_instance(cls) -> ModularRiskRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_rule(self, plugin: IRiskRulePlugin) -> None:
        rule_id = plugin.metadata.id if hasattr(plugin, "metadata") else type(plugin).__name__
        self._rules[rule_id] = plugin
        logger.info(f"Registered RiskRulePlugin: {rule_id}")

    def unregister_rule(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)
        logger.info(f"Unregistered RiskRulePlugin: {rule_id}")

    def register_sizing_plugin(self, plugin: IDynamicSizingPlugin) -> None:
        plugin_id = plugin.metadata.id if hasattr(plugin, "metadata") else type(plugin).__name__
        self._sizing_plugins[plugin_id] = plugin
        logger.info(f"Registered DynamicSizingPlugin: {plugin_id}")

    def unregister_sizing_plugin(self, plugin_id: str) -> None:
        self._sizing_plugins.pop(plugin_id, None)

    def register_post_trade_plugin(self, plugin: IPostTradeInspectionPlugin) -> None:
        plugin_id = plugin.metadata.id if hasattr(plugin, "metadata") else type(plugin).__name__
        self._post_trade_plugins[plugin_id] = plugin

    def get_rules(self) -> list[IRiskRulePlugin]:
        return [r for r in self._rules.values() if getattr(r, "is_enabled", True)]

    def get_sizing_plugins(self) -> list[IDynamicSizingPlugin]:
        return [s for s in self._sizing_plugins.values() if getattr(s, "is_enabled", True)]

    async def evaluate_modular_rules(
        self,
        session: Any,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        account_equity: float | None = None,
        **kwargs: Any,
    ) -> tuple[bool, list[str], list[str], list[str]]:
        """
        Runs all active modular risk rules.
        Returns: (all_passed, checks_passed, checks_failed, rejection_reasons)
        """
        all_passed = True
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        rejection_reasons: list[str] = []

        for rule in self.get_rules():
            rule_id = rule.metadata.id if hasattr(rule, "metadata") else type(rule).__name__
            try:
                verdict = await rule.validate_pre_order(
                    session=session,
                    symbol=symbol,
                    direction=direction,
                    sizing=sizing,
                    account_equity=account_equity,
                    **kwargs,
                )
                if verdict.passed:
                    checks_passed.append(rule_id)
                else:
                    all_passed = False
                    checks_failed.append(rule_id)
                    if verdict.rejection_reason:
                        rejection_reasons.append(verdict.rejection_reason)
            except Exception as e:
                logger.error(f"Error evaluating RiskRulePlugin [{rule_id}]: {e}", exc_info=True)
                all_passed = False
                checks_failed.append(rule_id)
                rejection_reasons.append(f"Risk rule [{rule_id}] runtime failure (fail-closed): {e}")

        return all_passed, checks_passed, checks_failed, rejection_reasons

    async def apply_dynamic_sizing(
        self,
        session: Any,
        symbol: str,
        base_lots: float,
        account_equity: float,
        max_lot_cap: float = 50.0,
        **kwargs: Any,
    ) -> float:
        """
        Chains active dynamic sizing plugins, strictly capping by max_lot_cap.
        """
        lots = base_lots
        for plugin in self.get_sizing_plugins():
            plugin_id = plugin.metadata.id if hasattr(plugin, "metadata") else type(plugin).__name__
            try:
                adjusted = await plugin.adjust_sizing(
                    session=session,
                    symbol=symbol,
                    base_lots=lots,
                    account_equity=account_equity,
                    **kwargs,
                )
                # Safety clamping: lot size cannot be negative and cannot exceed max_lot_cap
                lots = max(0.01, min(float(adjusted), max_lot_cap))
            except Exception as e:
                logger.warning(f"Dynamic sizing plugin [{plugin_id}] failed: {e}. Keeping lots={lots}")

        return round(lots, 2)
