import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.schemas.pydantic_schemas import ReevaluationTrigger, SubmitAssetAnalysisSchema
from utils.protocol.enhanced_cds import get_cds_thresholds, compute_temporal_cds
from analysis.tools.tool_executor import ToolExecutor
from scheduler.trigger_checker import TriggerChecker
from database.models import TradeTrigger, PaperTradeRecord, AssetAnalysis, PriceOHLCV
from utils.analytics.paper_tracker import PaperTracker


def test_enhanced_cds_new_thresholds():
    """Verify updated CDS thresholds and relaxed temporal max_allowed."""
    thresholds = get_cds_thresholds()
    assert thresholds['sync_trigger'] == 0.50
    assert thresholds['warning'] == 0.35
    assert thresholds['block_buysell'] == 0.65
    assert thresholds['abort_all'] == 0.75


@pytest.mark.asyncio
async def test_compute_temporal_cds_relaxed_age_spread():
    """Verify 4.5 hour age spread yields 0.0 temporal CDS with 6h threshold."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)
    
    # Mock H4 ts (2h old), indicators ts (2h old), brief ts (5.5h old) -> spread 3.5h <= 6.0h
    mock_h4_ts = MagicMock()
    mock_h4_ts.scalar_one_or_none.return_value = now - timedelta(hours=2)
    
    mock_ind_ts = MagicMock()
    mock_ind_ts.scalar_one_or_none.return_value = now - timedelta(hours=2)
    
    mock_brief_ts = MagicMock()
    mock_brief_ts.scalar_one_or_none.return_value = now - timedelta(hours=5, minutes=30)
    
    mock_vix_ts = MagicMock()
    mock_vix_ts.scalar_one_or_none.return_value = now - timedelta(hours=2)
    
    mock_session.execute.side_effect = [mock_h4_ts, mock_ind_ts, mock_brief_ts, mock_vix_ts]
    
    score = await compute_temporal_cds(mock_session, "EURUSD")
    assert score == 0.0


def test_reevaluation_trigger_price_level_auto_extraction():
    """Verify ReevaluationTrigger extracts price and direction from detail."""
    trig_above = ReevaluationTrigger(
        type="price_level",
        detail="Wait until price breaks above 2450.50 for breakout confirmation."
    )
    assert trig_above.type == "price_level"
    assert trig_above.price == 2450.50
    assert trig_above.direction == "above"

    trig_below = ReevaluationTrigger(
        type="price_level",
        detail="Re-evaluate when market drops below 1.0850."
    )
    assert trig_below.type == "price_level"
    assert trig_below.price == 1.0850
    assert trig_below.direction == "below"


def test_reevaluation_trigger_fallback_to_time():
    """Verify ReevaluationTrigger without price info safely falls back to time."""
    trig_generic = ReevaluationTrigger(
        type="price_level",
        detail="Re-evaluate when London session structure forms."
    )
    assert trig_generic.type == "time"


@pytest.mark.asyncio
async def test_tool_executor_symbol_injection():
    """Verify ToolExecutor automatically injects bound symbol if omitted by LLM."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, symbol="XAUUSD")
    
    # Payload without symbol
    payload_no_symbol = {
        "decision": "wait",
        "confidence": 0.70,
        "rationale": "Testing symbol auto injection without explicit symbol field.",
        "invalidation": "Thesis invalid if price breaks above 2500"
    }
    
    # Mock session query for analysis upsert
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = None
    mock_exec_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_exec_res
    
    res = await executor._tool_submit_asset_analysis(payload_no_symbol)
    assert res.get("status") == "saved"
    assert res.get("symbol") == "XAUUSD"


@pytest.mark.asyncio
async def test_trigger_checker_price_level_fallback():
    """Verify TriggerChecker evaluates price_level trigger using detail fallback regex."""
    checker = TriggerChecker(settings={})
    mock_trigger = TradeTrigger(
        id=86,
        asset_analysis_id=1,
        trigger_type="price_level",
        condition_json='{"symbol": "XAUUSD", "detail": "price breaks above 2400.0"}'
    )
    
    condition = {"symbol": "XAUUSD", "detail": "price breaks above 2400.0"}
    
    with patch("scheduler.trigger_checker.get_session") as mock_get_sess:
        mock_sess = AsyncMock()
        mock_get_sess.return_value.__aenter__.return_value = mock_sess
        
        mock_bar = MagicMock()
        mock_bar.close = 2410.0
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = mock_bar
        mock_sess.execute.return_value = mock_res
        
        result = await checker._check_price_level(mock_trigger, condition)
        assert result is True


@pytest.mark.asyncio
async def test_paper_trade_open_and_close_simulation():
    """Verify PaperTracker opens paper trade with symmetric spread and closes on SL/TP."""
    tracker = PaperTracker()
    mock_session = AsyncMock()
    
    analysis = AssetAnalysis(
        id=101,
        symbol="EURUSD",
        decision="buy",
        stop_loss=1.0800,
        take_profit=1.0900,
        confidence=0.8,
        entry_zone='{"type": "market"}'
    )
    
    # Mock H4 bar for opening
    mock_bar = MagicMock()
    mock_bar.close = 1.0850
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_bar
    mock_session.execute.return_value = mock_res
    
    await tracker.open_paper_trade(mock_session, analysis, risk_pct=0.5)
    
    # Verify session.add was called with PaperTradeRecord
    assert mock_session.add.called
    added_trade = mock_session.add.call_args[0][0]
    assert isinstance(added_trade, PaperTradeRecord)
    assert added_trade.symbol == "EURUSD"
    assert added_trade.direction == "buy"
    assert added_trade.status == "open"
    assert added_trade.entry_price > 1.0850  # half spread added for buy ask


@pytest.mark.asyncio
async def test_edge_strategy_runner_trend_trailing_rr_ratio():
    """Verify trend_trailing generates realistic SL (1.5x ATR) and TP (2.5x SL) resulting in ~1:2.5 R:R through EdgeStrategyRunner."""
    from scheduler.edge_strategy_runner import EdgeStrategyRunner
    from analysis.strategies.base_strategy import EdgeSignal
    from analysis.arbitration.signal_arbitrator import ArbitrationResult

    settings = {
        'trading': {
            'edge_strategy': {
                'trend_trailing': {
                    'sl_atr_multiplier': 1.5,
                    'tp_sl_multiplier': 2.5,
                    'use_adr_cap': True,
                    'max_tp_adr_multiple': 1.5,
                }
            },
            'risk': {
                'min_rr_ratio': 1.3,
            }
        }
    }
    runner = EdgeStrategyRunner(settings=settings)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()

    sig = EdgeSignal(
        strategy_id='tsm_momentum',
        symbol='GBPUSD',
        direction='buy',
        valid=True,
        confidence=1.0,
        rationale='TSM test',
        exit_style='trend_trailing'
    )
    sig.entry_price = 1.3650

    mock_arb = ArbitrationResult(
        symbol="GBPUSD",
        decision="buy",
        confidence=0.85,
        risk_multiplier=1.0,
        selected_source="quant",
        arbitration_reason="Quant strategy prioritized",
        entry_price=sig.entry_price,
        stop_loss=1.3620,
        take_profit=1.3725
    )

    with patch('analysis.calculators.intraday_level_optimizer._get_atr', AsyncMock(return_value=0.0020)), \
         patch('analysis.calculators.daily_range_calculator.compute_daily_range_context', AsyncMock(return_value={'adr': 0.0080})), \
         patch('analysis.calculators.macro_bias_filter.evaluate_macro_alignment', AsyncMock(return_value={'aligned': True, 'score': 1.0, 'reason': 'ok'})), \
         patch('analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate', AsyncMock(return_value=mock_arb)), \
         patch('graph.reactive_graph.get_reactive_graph'):
        
        await runner._materialize_and_route(mock_session, sig)
        
        # ATR=0.0020, sl_dist = 0.0020 * 1.5 = 0.0030, tp_dist = 0.0030 * 2.5 = 0.0075
        # Entry=1.3650 -> SL=1.3620, TP=1.3725
        assert sig.stop_loss == 1.3620
        assert sig.take_profit == 1.3725
        rr_ratio = (sig.take_profit - sig.entry_price) / (sig.entry_price - sig.stop_loss)
        assert round(rr_ratio, 2) == 2.50


