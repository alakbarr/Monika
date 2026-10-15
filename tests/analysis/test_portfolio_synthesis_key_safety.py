import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch, MagicMock

from monika.application.graph.nodes.risk.portfolio_synthesis import apply_portfolio_synthesis_reduction
from monika.infrastructure.database.models import AssetAnalysis


@pytest.mark.asyncio
async def test_apply_portfolio_synthesis_missing_analysis_id_no_crash(db_session):
    # Setup 1 analysis in DB for GBPUSD
    ana_gbp = AssetAnalysis(
        symbol="GBPUSD",
        decision="BUY",
        confidence=0.8,
        risk_multiplier=1.0,
    )
    db_session.add(ana_gbp)
    await db_session.commit()
    await db_session.refresh(ana_gbp)

    actionable = [
        ("EURUSD", {"decision": "BUY", "confidence": 0.75, "risk_multiplier": 1.0}),  # No analysis_id!
        ("GBPUSD", {"decision": "BUY", "confidence": 0.80, "analysis_id": ana_gbp.id, "risk_multiplier": 1.0}),
        (
            "USDJPY",
            {"decision": "SELL", "confidence": 0.70, "analysis_id": 999999, "risk_multiplier": 1.0},
        ),  # Non-existent ID
    ]

    mock_summary = {
        "recommendation": "reduce",
        "keep": ["EURUSD", "GBPUSD", "USDJPY"],
        "size_adjustments": {
            "EURUSD": 0.5,
            "GBPUSD": 0.7,
            "USDJPY": 0.8,
        },
        "reasoning": "Moderate correlation",
    }

    scheduler = MagicMock()
    scheduler.settings = {}
    state = {"market_regime": "normal"}

    @asynccontextmanager
    async def mock_get_session():
        yield db_session

    with (
        patch(
            "monika.application.graph.nodes.risk.portfolio_synthesis.ai_portfolio_synthesis",
            new=AsyncMock(return_value=mock_summary),
        ),
        patch(
            "monika.infrastructure.database.db.get_session",
            side_effect=mock_get_session,
        ),
    ):
        result_actionable, rejected = await apply_portfolio_synthesis_reduction(actionable, scheduler, state)

    assert len(result_actionable) == 3
    assert len(rejected) == 0

    trade_map = dict(result_actionable)
    # EURUSD (no analysis_id): in-memory multiplier updated to 0.5
    assert trade_map["EURUSD"]["risk_multiplier"] == 0.5

    # GBPUSD (valid analysis_id): in-memory and DB updated to 0.7
    assert trade_map["GBPUSD"]["risk_multiplier"] == 0.7
    await db_session.refresh(ana_gbp)
    assert ana_gbp.risk_multiplier == 0.7

    # USDJPY (non-existent analysis_id): in-memory updated to 0.8 without crashing
    assert trade_map["USDJPY"]["risk_multiplier"] == 0.8
