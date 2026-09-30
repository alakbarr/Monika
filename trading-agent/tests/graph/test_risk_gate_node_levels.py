import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from database.models import AssetAnalysis
from graph.nodes.risk_gate_node import _safe_num, risk_gate_node


def test_safe_num():
    assert _safe_num(123.45) == 123.45
    assert _safe_num(" $1,234.56 ") == 1234.56
    assert _safe_num("€83,729.50") == 83729.5
    assert _safe_num(None, default=10.0) == 10.0
    assert _safe_num("invalid", default=0.0) == 0.0
    assert _safe_num(float("nan"), default=5.0) == 5.0
    assert _safe_num(float("inf"), default=5.0) == 5.0


@pytest.mark.asyncio
async def test_quant_promoted_trade_synthesizes_levels():
    """Verify that when quant promotes a trade with missing SL/TP, valid levels are generated."""
    sym = "BTCUSD"
    state = {
        "summary": {},
        "actionable_trades": [],
        "asset_analyses": {
            sym: {
                "decision": "wait",
                "confidence": 0.4,
                "analysis_id": 999,
                "entry_price": 83000.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            }
        }
    }

    scheduler = MagicMock()
    scheduler.settings = {"trading": {"risk": {"max_usd_exposure": 3}}}
    scheduler.mt5 = None

    # Mock quant signal with sell decision but None levels
    mock_quant_signal = MagicMock()
    mock_quant_signal.valid = True
    mock_quant_signal.direction = "sell"
    mock_quant_signal.confidence = 0.8
    mock_quant_signal.strategy_id = "alpha_btc_test"
    mock_quant_signal.meta = {"strategy_id": "alpha_btc_test"}

    # Mock arbitration result promoting quant
    mock_arb_res = MagicMock()
    mock_arb_res.decision = "sell"
    mock_arb_res.confidence = 0.8
    mock_arb_res.risk_multiplier = 1.0
    mock_arb_res.selected_source = "quant"
    mock_arb_res.entry_price = None
    mock_arb_res.stop_loss = None
    mock_arb_res.take_profit = None
    mock_arb_res.meta = {"strategy_id": "alpha_btc_test"}

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    mock_db_res = MagicMock()
    mock_db_res.scalar_one_or_none.return_value = 83000.0
    mock_session.execute.return_value = mock_db_res

    with patch("database.db.get_session") as mock_get_sess, \
         patch("analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate", new=AsyncMock(return_value=mock_arb_res)), \
         patch("analysis.strategies.registry.StrategyRegistry.evaluate_all", new=AsyncMock(return_value=[mock_quant_signal])), \
         patch("analysis.strategies.decay_monitor.get_strategy_decay_monitor") as mock_decay, \
         patch("analysis.calculators.regime_classifier.classify_market_regime", new=AsyncMock(return_value={"regime": "trending"})), \
         patch("risk.risk_gate.RiskGate") as mock_rg_class, \
         patch("analysis.validators.precommit_gate.TradePreCommitGate.verify_precommit", new=AsyncMock(return_value=(True, []))):

        mock_get_sess.return_value.__aenter__.return_value = mock_session
        mock_decay.return_value.is_live_ready.return_value = True

        mock_rg_inst = MagicMock()
        mock_rg_verdict = MagicMock(approved=True, rejection_reasons=[])
        mock_rg_inst.evaluate_proposal = AsyncMock(return_value=mock_rg_verdict)
        mock_rg_class.return_value = mock_rg_inst
        scheduler.risk_gate = mock_rg_inst

        res = await risk_gate_node(state, config={"configurable": {"scheduler": scheduler}})

        # The trade should be actionable and approved
        assert "portfolio_synthesis_approved" in res["summary"]
        assert sym in res["summary"]["portfolio_synthesis_approved"]

        # Verify the trade has valid SELL geometry: SL > entry and TP < entry
        trade_data = state["asset_analyses"][sym]
        assert trade_data["decision"] == "sell"
        assert trade_data["stop_loss"] > trade_data["entry_price"]
        assert 0 < trade_data["take_profit"] < trade_data["entry_price"]


@pytest.mark.asyncio
async def test_risk_gate_node_persists_to_asset_analysis_without_setter_error():
    """Verify that persisting arbitrated levels to an existing AssetAnalysis DB object updates entry_price without AttributeError."""
    sym = "BTCUSD"
    ana_record = AssetAnalysis(
        id=101,
        symbol=sym,
        decision="wait",
        confidence=0.5,
        risk_multiplier=1.0,
        entry_zone='{"price": 82000.0}',
    )

    state = {
        "summary": {},
        "actionable_trades": [],
        "asset_analyses": {
            sym: {
                "decision": "wait",
                "confidence": 0.4,
                "analysis_id": 101,
                "entry_price": 83000.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            }
        },
    }

    scheduler = MagicMock()
    scheduler.settings = {"trading": {"risk": {"max_usd_exposure": 3}}}
    scheduler.mt5 = None

    mock_quant_signal = MagicMock(valid=True, direction="buy", confidence=0.85, strategy_id="alpha_btc_1", meta={"strategy_id": "alpha_btc_1"})
    mock_arb_res = MagicMock(
        decision="buy",
        confidence=0.85,
        risk_multiplier=1.2,
        selected_source="quant",
        entry_price=83000.0,
        stop_loss=82000.0,
        take_profit=85000.0,
        meta={"strategy_id": "alpha_btc_1"},
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=ana_record)
    mock_session.commit = AsyncMock()

    mock_db_res = MagicMock()
    mock_db_res.scalar_one_or_none.return_value = 83000.0
    mock_session.execute.return_value = mock_db_res

    with patch("database.db.get_session") as mock_get_sess, \
         patch("analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate", new=AsyncMock(return_value=mock_arb_res)), \
         patch("analysis.strategies.registry.StrategyRegistry.evaluate_all", new=AsyncMock(return_value=[mock_quant_signal])), \
         patch("analysis.strategies.decay_monitor.get_strategy_decay_monitor") as mock_decay, \
         patch("analysis.calculators.regime_classifier.classify_market_regime", new=AsyncMock(return_value={"regime": "trending"})), \
         patch("risk.risk_gate.RiskGate") as mock_rg_class, \
         patch("analysis.validators.precommit_gate.TradePreCommitGate.verify_precommit", new=AsyncMock(return_value=(True, []))):

        mock_get_sess.return_value.__aenter__.return_value = mock_session
        mock_decay.return_value.is_live_ready.return_value = True

        mock_rg_inst = MagicMock()
        mock_rg_verdict = MagicMock(approved=True, rejection_reasons=[])
        mock_rg_inst.evaluate_proposal = AsyncMock(return_value=mock_rg_verdict)
        mock_rg_class.return_value = mock_rg_inst
        scheduler.risk_gate = mock_rg_inst

        res = await risk_gate_node(state, config={"configurable": {"scheduler": scheduler}})

        assert "portfolio_synthesis_approved" in res["summary"]
        assert ana_record.decision == "buy"
        assert ana_record.confidence == 0.85
        assert ana_record.entry_price == 83000.0
        assert ana_record.stop_loss == 82000.0
        assert ana_record.take_profit == 85000.0
        assert mock_session.commit.called

