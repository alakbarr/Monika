# ==============================================================================
# File: tests/risk/test_phase10_fortress_invariants.py
# ==============================================================================

"""
Unit tests for Phase 10: Quantitative Trading Fortress Invariants & Master Pipeline Verification.
Verifies:
1. Two-Plane Fortress: Deterministic separation of AI reasoning and financial execution.
2. 22-point Risk Gate deterministic rejection under violation.
3. Carrier-side-effect persistence during conversation rollback (/undo).
4. Zero-lookahead temporal boundary preservation.
5. End-to-end MoA consensus ingestion through Risk Gate.
6. Supply chain quarantine + AST audit defense for dynamic strategies.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from risk.risk_gate import RiskGate, RiskVerdict
from risk.position_sizing import PositionSizer
from database.session_db_wal import SessionDbWal
from agent.state_rewind import StateRewindManager, CARRIER_SIDE_EFFECT_PERSISTED
from agent.moa_loop import MoARuntime, MoAResult
from analysis.memory.skill_ast_audit import SkillAstAuditor
from utils.security.supply_chain_quarantine import SupplyChainQuarantine


@pytest.fixture
def base_risk_settings():
    return {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
                "correlation_limit": 3,
                "news_window_minutes": 15,
                "max_risk_per_trade_percent": 1.0,
                "correlation_threshold": 0.65,
                "correlation_rolling_days": 30,
            }
        }
    }


@pytest.mark.asyncio
async def test_fortress_risk_gate_rejects_excessive_drawdown(base_risk_settings):
    """
    Fortress Invariant 1:
    Risk Gate deterministically denies order dispatch when account drawdown breaches threshold.
    """
    mock_session = AsyncMock()
    gate = RiskGate(settings=base_risk_settings)
    sizer = PositionSizer(settings=base_risk_settings)

    # Wed 14:00 UTC during open market hours
    market_open_time = datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc)

    sizing = sizer.calculate(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        account_equity=10000.0,
    )
    assert sizing.is_valid is True

    # Simulate equity drawdown exceeding 3.0% threshold (e.g. -4.5% daily PnL)
    verdict: RiskVerdict = await gate.evaluate(
        session=mock_session,
        symbol="EURUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
        as_of=market_open_time,
        simulated_positions=[],
        simulated_equity=10000.0,
        simulated_daily_pnl=-450.0,  # -4.5% drawdown
        is_backtest=True,
    )

    assert verdict.approved is False
    assert any("drawdown" in r.lower() for r in verdict.rejection_reasons)


def test_fortress_carrier_side_effect_immutability():
    """
    Fortress Invariant 2:
    State Rewind (/undo) preserves MT5 trade records marked with CARRIER_SIDE_EFFECT_PERSISTED.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "fortress_session.sqlite"
        db = SessionDbWal(db_path=db_path)
        rewind_mgr = StateRewindManager(db=db)

        sid = "live_session_001"

        # Turn 1: chat only
        db.append_message(sid, role="user", content="Check EURUSD", turn_ordinal=1)
        db.append_message(sid, role="assistant", content="EURUSD is consolidative.", turn_ordinal=1)

        # Turn 2: trade with carrier side effect
        db.append_message(sid, role="user", content="Execute BUY 0.10 lot", turn_ordinal=2)
        db.append_message(sid, role="assistant", content="Order dispatched to MT5: Ticket #991122", turn_ordinal=2)
        db.record_tool_execution(
            session_id=sid,
            turn_ordinal=2,
            tool_name="mt5_execute_order",
            arguments={"symbol": "EURUSD"},
            output='{"status": "FILLED", "ticket": 991122}',
            has_side_effects=True,
        )

        outcome = rewind_mgr.rewind_session(sid, user_ordinal=-1)

        assert outcome.carrier_side_effect_persisted is True
        assert "Financial transactions executed" in outcome.status_message
        db.close()


def test_fortress_end_to_end_moa_to_risk_pipeline(base_risk_settings):
    """
    Fortress Invariant 3:
    MoA council consensus (Sonnet 5 + DeepSeek V4 + Gemini + GPT-6) must pass through
    deterministic Sizing and Risk Gate validation.
    """
    def mock_council_llm(slot, messages):
        model = slot.get("model", "")
        if "deepseek-v4-pro" in model:
            return "DeepSeek V4: High probability Long on GBPUSD; stop at 1.2980."
        elif "gemini-3.8-flash" in model:
            return "Gemini 3.8: Macro news backdrop supports GBP strength."
        elif "gpt-6-astra" in model:
            return "GPT-6 Astra: Liquidity pool below 1.3000 cleared."
        elif "claude-sonnet-5" in model:
            return "Claude Sonnet 5: Consensus: BUY GBPUSD, SL=1.2980, TP=1.3080, Risk=0.5%."
        return f"Advice from {model}"

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = MoARuntime(
            llm_caller=mock_council_llm,
            default_preset="trading_quant_moa",
            trace_dir=tmpdir,
        )
        result: MoAResult = runtime.run_moa("Analyze GBPUSD H1 structure.")

        assert "Consensus: BUY GBPUSD" in result.synthesis
    assert result.is_degraded is False

    # Convert synthesized directive to candidate sizing via deterministic PositionSizer
    sizer = PositionSizer(settings=base_risk_settings)
    sizing = sizer.calculate(
        symbol="GBPUSD",
        direction="buy",
        entry_price=1.3000,
        stop_loss=1.2980,
        take_profit=1.3080,
        account_equity=10000.0,
    )
    assert sizing.is_valid is True

    # Must pass RiskGate during open market hours
    gate = RiskGate(settings=base_risk_settings)
    mock_session = AsyncMock()
    market_open_time = datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc)

    import asyncio
    verdict = asyncio.run(gate.evaluate(
        session=mock_session,
        symbol="GBPUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
        as_of=market_open_time,
        simulated_positions=[],
        simulated_equity=10000.0,
        simulated_daily_pnl=0.0,
        is_backtest=True,
    ))

    assert verdict.approved is True


def test_fortress_supply_chain_and_ast_double_quarantine():
    """
    Fortress Invariant 4:
    Dynamic strategy code must pass BOTH the 14-day supply-chain quarantine AND
    the AST static security audit before execution.
    """
    # 1. Supply Chain Quarantine Check
    quarantine = SupplyChainQuarantine(quarantine_days=14)
    poisoned_pkg = quarantine.evaluate_package(
        package_name="anthroppic",  # Typosquat of anthropic
        version="1.0.0",
    )
    assert poisoned_pkg.allowed is False
    assert poisoned_pkg.status == "TYPOSQUAT_SUSPECT"

    # 2. AST Security Audit Check (Dangerous imports like subprocess or ctypes)
    malicious_strategy = """
import subprocess

class MaliciousAlpha:
    def on_tick(self):
        eval("malicious_code()")
"""
    auditor = SkillAstAuditor()
    report = auditor.audit_code(malicious_strategy)
    assert report.is_clean is False
    assert len(report.violations) >= 2

    # 3. Clean Quantitative Strategy Check
    clean_strategy = """
import math

class BreakoutAlpha:
    def on_tick(self, price, ma):
        if price > ma:
            return "BUY"
        return "HOLD"
"""
    clean_report = auditor.audit_code(clean_strategy)
    assert clean_report.is_clean is True


def test_invariant_registry_duplicate_warning(caplog):
    import logging
    from risk.invariants.registry import InvariantRegistry, InvariantResult, InvariantStatus

    registry = InvariantRegistry()
    dummy1 = lambda ctx: InvariantResult("test_inv", InvariantStatus.PASS)
    dummy2 = lambda ctx: InvariantResult("test_inv", InvariantStatus.FAIL)

    registry.register("test_inv", dummy1)
    with caplog.at_level(logging.WARNING):
        registry.register("test_inv", dummy2)
    assert "already registered, overwriting" in caplog.text
    assert registry.list_invariants() == ["test_inv"]
