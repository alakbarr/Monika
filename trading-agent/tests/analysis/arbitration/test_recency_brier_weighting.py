import pytest
from unittest.mock import AsyncMock, MagicMock

from analysis.arbitration.signal_arbitrator import (
    compute_empirical_arbitrator_weights,
    SignalArbitrator,
)
from database.models import PaperTradeRecord, AssetAnalysis


@pytest.mark.asyncio
async def test_brier_recency_decay_favors_recent_performance():
    mock_session = AsyncMock()

    # 20 trades total.
    # index 0..9 (most recent): LLM accurate (conf=0.90, win=1.0), Quant inaccurate (conf=0.20, win=1.0)
    # index 10..19 (older): LLM inaccurate (conf=0.20, win=1.0), Quant accurate (conf=0.90, win=1.0)
    records = []
    for i in range(20):
        rec = MagicMock(spec=PaperTradeRecord)
        rec.status = "closed"
        rec.symbol = "EURUSD"
        rec.decision_source = "concordant"
        rec.exit_reason = "tp_hit"
        rec.pnl_pct = 1.5

        ana = MagicMock(spec=AssetAnalysis)
        ana.source_strategy_id = "strat_momentum"

        if i < 10:  # Recent trades: LLM accurate, Quant inaccurate
            ana.confidence = 0.90
            ana.strategy_confidence = 0.20
        else:       # Older trades: Quant accurate, LLM inaccurate
            ana.confidence = 0.20
            ana.strategy_confidence = 0.90

        records.append((rec, ana))

    mock_exec = MagicMock()
    mock_exec.all.return_value = records
    mock_session.execute.return_value = mock_exec

    # With recency decay (0.90), recent wins give LLM much lower Brier error
    w_q_decay, w_l_decay = await compute_empirical_arbitrator_weights(
        mock_session, default_quant=0.5, default_llm=0.5, decay_factor=0.90
    )
    assert w_l_decay > 0.50
    assert w_q_decay < 0.50

    # With zero decay (1.00), both have 10 wins / 10 losses, weights should be much closer
    w_q_flat, w_l_flat = await compute_empirical_arbitrator_weights(
        mock_session, default_quant=0.5, default_llm=0.5, decay_factor=1.00
    )
    # The recency decay should give LLM a significantly higher weight than flat weighting
    assert w_l_decay > w_l_flat


@pytest.mark.asyncio
async def test_symbol_weight_boost():
    mock_session = AsyncMock()

    # 15 trades: 5 on XAUUSD (LLM won), 10 on other symbols (LLM lost)
    records = []
    for i in range(15):
        rec = MagicMock(spec=PaperTradeRecord)
        rec.status = "closed"
        rec.decision_source = "concordant"
        ana = MagicMock(spec=AssetAnalysis)
        ana.source_strategy_id = "strat_momentum"
        ana.strategy_confidence = 0.65

        if i < 5:
            rec.symbol = "XAUUSD"
            rec.exit_reason = "tp_hit"
            rec.pnl_pct = 2.0
            ana.confidence = 0.85
        else:
            rec.symbol = "USDJPY"
            rec.exit_reason = "sl_hit"
            rec.pnl_pct = -1.0
            ana.confidence = 0.85

        records.append((rec, ana))

    mock_exec = MagicMock()
    mock_exec.all.return_value = records
    mock_session.execute.return_value = mock_exec

    # Calling with symbol="XAUUSD" should boost LLM weight compared to generic call
    w_q_xau, w_l_xau = await compute_empirical_arbitrator_weights(
        mock_session, default_quant=0.5, default_llm=0.5, symbol="XAUUSD"
    )
    w_q_gen, w_l_gen = await compute_empirical_arbitrator_weights(
        mock_session, default_quant=0.5, default_llm=0.5, symbol="USDJPY"
    )
    assert w_l_xau > w_l_gen


@pytest.mark.asyncio
async def test_losing_streak_penalty():
    mock_session = AsyncMock()

    # 12 trades where LLM has 3 consecutive losses most recently
    records = []
    for i in range(12):
        rec = MagicMock(spec=PaperTradeRecord)
        rec.status = "closed"
        rec.symbol = "EURUSD"
        rec.decision_source = "concordant"

        ana = MagicMock(spec=AssetAnalysis)
        ana.source_strategy_id = "strat_trend"
        ana.strategy_confidence = 0.70

        if i < 3:  # Most recent 3 are losses for LLM
            rec.exit_reason = "sl_hit"
            rec.pnl_pct = -1.0
            ana.confidence = 0.85
        else:
            rec.exit_reason = "tp_hit"
            rec.pnl_pct = 1.5
            ana.confidence = 0.85

        records.append((rec, ana))

    mock_exec = MagicMock()
    mock_exec.all.return_value = records
    mock_session.execute.return_value = mock_exec

    w_q, w_l = await compute_empirical_arbitrator_weights(
        mock_session, default_quant=0.5, default_llm=0.5
    )
    # 3 consecutive losses triggers penalty on LLM weight
    assert w_q > w_l
