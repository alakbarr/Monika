# ==============================================================================
# File: tests/risk/test_risk_rule_pipeline.py
# ==============================================================================

import pytest
from unittest.mock import MagicMock, AsyncMock

from risk.position_sizing import SizingResult
from risk.risk_rule_plugin import (
    IRiskRulePlugin,
    IDynamicSizingPlugin,
    ModularRiskRegistry,
    RiskRuleVerdict,
)
from harness.contract import PluginMetadata, PluginCategory, PluginOrigin
from risk.risk_gate import RiskGate, RiskVerdict


class AllowedSymbolsRule(IRiskRulePlugin):
    def __init__(self, allowed: list[str]):
        super().__init__()
        self.metadata = PluginMetadata(
            id="allowed_symbols_rule",
            name="Allowed Symbols Rule",
            category=PluginCategory.RISK_RULE,
            origin=PluginOrigin.BUILTIN,
        )
        self.allowed = allowed

    async def validate_pre_order(
        self,
        session,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        account_equity: float = None,
        **kwargs,
    ) -> RiskRuleVerdict:
        if symbol in self.allowed:
            return RiskRuleVerdict(rule_id="allowed_symbols_rule", passed=True)
        return RiskRuleVerdict(
            rule_id="allowed_symbols_rule",
            passed=False,
            rejection_reason=f"Symbol {symbol} is not permitted by AllowedSymbolsRule.",
        )


class HalfRiskSizingPlugin(IDynamicSizingPlugin):
    def __init__(self):
        super().__init__()
        self.metadata = PluginMetadata(
            id="half_risk_sizing",
            name="Half Risk Sizing",
            category=PluginCategory.DYNAMIC_SIZING,
            origin=PluginOrigin.BUILTIN,
        )

    async def adjust_sizing(
        self,
        session,
        symbol: str,
        base_lots: float,
        account_equity: float,
        **kwargs,
    ) -> float:
        return base_lots * 0.5


@pytest.mark.asyncio
async def test_modular_risk_registry_rules():
    registry = ModularRiskRegistry()
    rule = AllowedSymbolsRule(allowed=["EURUSD", "GBPUSD"])
    registry.register_rule(rule)

    session = AsyncMock()
    sizing = MagicMock()
    sizing.recommended_lots = 0.1

    # Allowed symbol
    passed, p_list, f_list, reasons = await registry.evaluate_modular_rules(
        session=session,
        symbol="EURUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
    )
    assert passed is True
    assert "allowed_symbols_rule" in p_list
    assert len(f_list) == 0

    # Disallowed symbol
    passed, p_list, f_list, reasons = await registry.evaluate_modular_rules(
        session=session,
        symbol="BTCUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
    )
    assert passed is False
    assert "allowed_symbols_rule" in f_list
    assert any("not permitted" in r for r in reasons)


@pytest.mark.asyncio
async def test_dynamic_sizing_plugin():
    registry = ModularRiskRegistry()
    plugin = HalfRiskSizingPlugin()
    registry.register_sizing_plugin(plugin)

    session = AsyncMock()
    lots = await registry.apply_dynamic_sizing(
        session=session,
        symbol="EURUSD",
        base_lots=1.0,
        account_equity=10000.0,
    )
    assert lots == 0.5


@pytest.mark.asyncio
async def test_risk_gate_integration_with_modular_rule():
    settings = {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
                "correlation_limit": 3,
                "news_window_minutes": 15,
            }
        },
        "paper_trading": {"initial_balance": 10000.0},
    }
    risk_gate = RiskGate(settings)

    # Register rule rejecting CADJPY
    rule = AllowedSymbolsRule(allowed=["EURUSD"])
    risk_gate.modular_risk_registry.register_rule(rule)

    # Mock all internal checks to return (True, "") so only modular rule fails
    async def mock_pass(*args, **kwargs):
        return True, ""

    risk_gate._check_daily_trade_count = AsyncMock(side_effect=mock_pass)
    risk_gate._check_daily_drawdown = AsyncMock(side_effect=mock_pass)
    risk_gate._check_concurrent_positions = AsyncMock(side_effect=mock_pass)
    risk_gate._check_symbol_position = AsyncMock(side_effect=mock_pass)
    risk_gate._check_lot_size = AsyncMock(side_effect=mock_pass)
    risk_gate._check_news_window = AsyncMock(side_effect=mock_pass)
    risk_gate._check_correlation_heat = AsyncMock(side_effect=mock_pass)
    risk_gate._check_manual_pause = AsyncMock(side_effect=mock_pass)
    risk_gate._check_schmitt_regime = AsyncMock(side_effect=mock_pass)
    risk_gate._check_vpin_toxicity = AsyncMock(side_effect=mock_pass)
    risk_gate._log_verdict = AsyncMock()

    session = AsyncMock()
    sizing = SizingResult(
        symbol="CADJPY",
        direction="buy",
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=1.0,
        sl_distance_pips=100.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
    )

    verdict = await risk_gate.evaluate(
        session=session,
        symbol="CADJPY",
        direction="buy",
        sizing=sizing,
        is_backtest=True,
    )

    assert verdict.approved is False
    assert "allowed_symbols_rule" in verdict.checks_failed
    assert any("not permitted" in r for r in verdict.rejection_reasons)
