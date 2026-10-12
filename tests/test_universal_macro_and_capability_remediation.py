# ==============================================================================
# File: tests/test_universal_macro_and_capability_remediation.py
# ==============================================================================

"""
Comprehensive Integration & Verification Tests for Universal Macro Architecture,
Central Bank Redline Diffing, and Capability Remediation (Master Plan v3.2.0).
"""

import asyncio
import io
import os
import pytest
import pandas as pd
from datetime import datetime, timezone

from database.db import get_engine, get_session
from database.models import (
    Base,
    EconomicReportDecomposition,
    CentralBankDocument,
    MacroLiquidityCreditMetric,
)
from risk.position_sizing import PositionSizer
from analysis.calculators.universal_macro_analyzer import UniversalMacroAnalyzer
from analysis.calculators.universal_cb_differ import UniversalCentralBankDiffer
from analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer
from analysis.tools.handlers.behavioral_alert_tool import handle_create_behavioral_alert
from analysis.tools.handlers.broker_profile_tool import handle_compare_broker_spread_profiles
from analysis.tools.handlers.trade_intel import handle_export_trades_to_excel, handle_generate_docx_report, handle_generate_pptx_deck
from utils.chart_generator import generate_smc_candlestick_chart
import json
from unittest.mock import MagicMock, AsyncMock


def test_database_models_exist():
    """Verify the 3 universal tables exist in Base metadata."""
    assert "economic_report_decompositions" in Base.metadata.tables
    assert "central_bank_documents" in Base.metadata.tables
    assert "macro_liquidity_credit_metrics" in Base.metadata.tables


def test_cent_account_dual_protection():
    """Verify Cent Account equity normalization and safe lot sizing."""
    ps = PositionSizer({"trading": {"risk": {"is_cent_account": True}}})
    # User passes 10,000 cents (= $100.0 USD)
    res = ps.calculate("EURUSD", "BUY", 1.1000, 1.0950, 1.1100, account_equity=10000.0)
    assert res.is_valid is True
    assert res.account_equity == 100.0  # normalized
    assert res.risk_amount_usd == 1.0   # 1% of $100 = $1.00
    assert res.recommended_lots == 0.01 # minimum safe lot, not blown up


@pytest.mark.asyncio
async def test_universal_macro_analyzer():
    """Verify granular report decomposition and noise attribution."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    cpi_records = [
        EconomicReportDecomposition(report_type="CPI", component_name="Headline CPI", category="headline", value_actual=0.3, value_forecast=0.2, mom_change=0.3, yoy_change=2.9),
        EconomicReportDecomposition(report_type="CPI", component_name="Core CPI", category="core", value_actual=0.2, value_forecast=0.2, mom_change=0.2, yoy_change=3.1),
        EconomicReportDecomposition(report_type="CPI", component_name="Shelter", category="sticky", value_actual=0.35, mom_change=0.35, contribution_bps=12.5),
        EconomicReportDecomposition(report_type="CPI", component_name="Energy", category="transitory", value_actual=1.4, mom_change=1.4, contribution_bps=10.0, is_noise=True),
    ]
    mock_res.scalars.return_value.all.return_value = cpi_records
    mock_session.execute.return_value = mock_res

    analyzer = UniversalMacroAnalyzer(mock_session)
    analyzer.router.ensure_report_available = AsyncMock()

    cpi_res = await analyzer.decompose_report("CPI")
    assert "institutional_verdict" in cpi_res
    assert cpi_res["institutional_verdict"]["classification"] in [
        "TRANSITORY_NOISE_ONLY", "STRUCTURAL_PERSISTENT_SHIFT", "MIXED_IMPACT"
    ]

    g10_res = await analyzer.analyze_g10_macro_divergence("EURUSD")
    assert "relative_macro_score" in g10_res
    assert "fundamental_bias" in g10_res


@pytest.mark.asyncio
async def test_universal_central_bank_differ():
    """Verify redline diffing and hawkish/dovish scoring."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    docs = [
        CentralBankDocument(bank="FED", doc_type="MINUTES", meeting_date=datetime.now(), title="Current FOMC", full_text="Tightening stance. Persistent inflation.", paragraphs_json=json.dumps(["Tightening stance.", "Persistent inflation."]), hawkish_dovish_score=0.4),
        CentralBankDocument(bank="FED", doc_type="MINUTES", meeting_date=datetime.now(), title="Prior FOMC", full_text="Restrictive stance. Disinflation evident.", paragraphs_json=json.dumps(["Restrictive stance.", "Disinflation evident."]), hawkish_dovish_score=0.1),
    ]
    mock_res.scalars.return_value.all.return_value = docs
    mock_session.execute.return_value = mock_res

    differ = UniversalCentralBankDiffer(mock_session)
    differ.router.ensure_cb_document_available = AsyncMock()

    diff_res = await differ.diff_cb_documents("FED", "MINUTES")
    assert "monetary_tone_shift" in diff_res
    assert "delta_score" in diff_res["monetary_tone_shift"]
    assert "redline_modifications" in diff_res
    assert isinstance(diff_res["redline_modifications"]["key_additions"], list)


@pytest.mark.asyncio
async def test_universal_liquidity_analyzer():
    """Verify Fed Net Liquidity formula and Treasury auction tails."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    liq_records = [
        MacroLiquidityCreditMetric(metric_type="FED_NET_LIQUIDITY", value=5960.0, previous_value=5920.0, change_value=40.0, regime="EXPANSIONARY", record_date=datetime.now()),
        MacroLiquidityCreditMetric(metric_type="TREASURY_AUCTION_10Y", value=4.285, metadata_json=json.dumps({"tail_bps": 1.2, "bid_to_cover": 2.52, "indirect_bidder_pct": 68.0}), record_date=datetime.now()),
        MacroLiquidityCreditMetric(metric_type="ICE_BOFA_HY_OAS", value=320.0, record_date=datetime.now()),
        MacroLiquidityCreditMetric(metric_type="SOFR_RATE", value=5.31, record_date=datetime.now()),
    ]
    mock_res.scalars.return_value.all.return_value = liq_records
    mock_session.execute.return_value = mock_res

    la = UniversalLiquidityAnalyzer(mock_session)
    la.router.ensure_liquidity_and_stress_available = AsyncMock()

    liq = await la.analyze_fed_net_liquidity()
    assert "current_net_liquidity_billions" in liq
    assert liq["current_net_liquidity_billions"] > 0
    assert liq["regime"] in ["EXPANSIONARY", "CONTRACTIONARY"]

    auc = await la.analyze_treasury_auction_demand("10Y")
    assert "tail_basis_points" in auc
    assert "bid_to_cover_ratio" in auc

    stress = await la.analyze_credit_and_funding_stress()
    assert "hy_oas_bps" in stress


@pytest.mark.asyncio
async def test_behavioral_alert_quarantine():
    """Verify psychology alert and trading quarantine cooldown."""
    async with get_session() as session:
        res = await handle_create_behavioral_alert(
            {"alert_type": "REVENGE_TRADING", "action_mode": "QUARANTINE", "quarantine_hours": 2.5},
            session=session,
        )
        assert res["status"] == "success"
        assert res["quarantine_applied"] is True
        assert "quarantine_until" in res


@pytest.mark.asyncio
async def test_broker_spread_profile():
    """Verify ECN vs Standard account spread comparison."""
    res = await handle_compare_broker_spread_profiles({"symbol": "EURUSD"})
    assert res["status"] == "success"
    assert len(res["comparison_results"]) > 0
    assert "recommended_account_type" in res["comparison_results"][0]


def test_chart_generator_with_ob_and_volume_profile():
    """Verify candlestick generator renders with Order Blocks and Volume Profile."""
    sample_ohlcv = [
        {"timestamp": f"2026-09-01T{h:02d}:00:00Z", "open": 1.1000 + h*0.0005, "high": 1.1010 + h*0.0005, "low": 1.0995 + h*0.0005, "close": 1.1008 + h*0.0005, "volume": 1000 + h*50}
        for h in range(20)
    ]
    obs = [{"high": 1.1080, "low": 1.1060, "direction": "bearish"}]
    vp = {"poc": 1.1050, "vah": 1.1080, "val": 1.1020}

    buf, path = generate_smc_candlestick_chart(
        ohlcv_rows=sample_ohlcv,
        symbol="EURUSD",
        timeframe="H1",
        order_blocks=obs,
        volume_profile=vp,
        save_to_disk=False,
    )
    assert buf is not None
    assert buf.getbuffer().nbytes > 1000  # valid image buffer


@pytest.mark.asyncio
async def test_excel_export_executive_kpis():
    """Verify Excel export creates Executive_KPIs sheet."""
    class MockExecutor:
        def __init__(self):
            self.files = []
        def add_pending_file(self, file_path, filename, caption):
            self.files.append(file_path)

    executor = MockExecutor()
    async with get_session() as session:
        res = await handle_export_trades_to_excel(
            {"filename": "test_monika_journal.xlsx"},
            session=session,
            executor=executor,
        )
        # Even if empty or with mock data, check return
        assert res["status"] in ["success", "empty"]
        if res["status"] == "success":
            assert os.path.exists(res["filepath"])
            xl = pd.ExcelFile(res["filepath"])
            assert "Executive_KPIs" in xl.sheet_names
            assert "Trade_Journal" in xl.sheet_names
            os.remove(res["filepath"])
