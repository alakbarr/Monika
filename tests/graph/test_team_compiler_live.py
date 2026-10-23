import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.graph.team_compiler import (
    TeamCompiler,
    resolve_desk_for_symbol,
)


def test_resolve_desk_for_symbol():
    """Verify symbol routing to specialized desk YAML presets."""
    assert resolve_desk_for_symbol("BTCUSD") == "crypto_trading_desk"
    assert resolve_desk_for_symbol("ETHUSD") == "crypto_trading_desk"
    assert resolve_desk_for_symbol("XAUUSD") == "gold_commodity_desk"
    assert resolve_desk_for_symbol("XAGUSD") == "gold_commodity_desk"
    assert resolve_desk_for_symbol("EURUSD") == "macro_rates_fx_desk"
    assert resolve_desk_for_symbol("USDJPY") == "macro_rates_fx_desk"
    # Unmatched asset falls back to investment_committee
    assert resolve_desk_for_symbol("UNKNOWN_SYMBOL") == "investment_committee"


def test_team_compiler_loads_all_presets():
    """Verify all 4 desk presets are well-formed and load without error."""
    desks = TeamCompiler.list_available_desks()
    assert "crypto_trading_desk" in desks
    assert "gold_commodity_desk" in desks
    assert "macro_rates_fx_desk" in desks
    assert "investment_committee" in desks

    for d in desks:
        cfg = TeamCompiler.load_desk_config(d)
        assert cfg is not None
        assert len(cfg.roles) >= 3
        assert cfg.consensus_protocol


@pytest.mark.asyncio
async def test_execute_desk_swarm_consensus():
    """Verify concurrent desk swarm execution aggregates convictions and handles veto."""
    mock_llm_resp = (
        '{"role_id": "r1", "role_name": "Test Role", "stance": "bullish", "conviction": 0.85, '
        '"key_factors": ["High funding"], "risk_veto": false, "veto_reason": null, "rationale": "Bullish thesis"}'
    )

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(return_value=mock_llm_resp)

    with patch("monika.application.graph.team_compiler.get_client_for_task", return_value=mock_client):
        res = await TeamCompiler.execute_desk_swarm(
            desk_id="crypto_trading_desk",
            symbol="BTCUSD",
            fact_sheet={"entry_price": 65000, "confluence_score": 8},
            settings={},
        )
        assert res["desk_id"] == "crypto_trading_desk"
        assert res["bull_count"] == 4
        assert res["bear_count"] == 0
        assert res["avg_conviction"] == 0.85
        assert res["risk_veto"] is False


@pytest.mark.asyncio
async def test_execute_desk_swarm_risk_veto_enforced():
    """Verify that a role risk veto sets risk_veto=True across the desk consensus."""
    mock_veto_resp = (
        '{"role_id": "crypto_risk_manager", "role_name": "Risk Manager", "stance": "bearish", '
        '"conviction": 0.95, "key_factors": ["Liquidation cluster"], "risk_veto": true, '
        '"veto_reason": "High liquidation volatility risk", "rationale": "Veto active"}'
    )

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(return_value=mock_veto_resp)

    with patch("monika.application.graph.team_compiler.get_client_for_task", return_value=mock_client):
        res = await TeamCompiler.execute_desk_swarm(
            desk_id="crypto_trading_desk",
            symbol="BTCUSD",
            fact_sheet={"entry_price": 65000},
            settings={},
        )
        assert res["risk_veto"] is True
        assert len(res["veto_reasons"]) > 0
        assert "liquidation" in res["veto_reasons"][0].lower()
