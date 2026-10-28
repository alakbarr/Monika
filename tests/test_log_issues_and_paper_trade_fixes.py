from tests.conftest import create_mock_async_session
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.analysis.schemas.pydantic_schemas import ReevaluationTrigger, SubmitAssetAnalysisSchema
from monika.application.protocol.enhanced_cds import get_cds_thresholds, compute_temporal_cds
from monika.application.analysis.tools.tool_executor import ToolExecutor
from monika.application.scheduler.trigger_checker import TriggerChecker
from monika.infrastructure.database.models import TradeTrigger, PaperTradeRecord, AssetAnalysis, PriceOHLCV
from monika.core.analytics.paper_tracker import PaperTracker


def test_enhanced_cds_new_thresholds():
    """Verify updated CDS thresholds and relaxed temporal max_allowed."""
    thresholds = get_cds_thresholds()
    assert thresholds["sync_trigger"] == 0.50
    assert thresholds["warning"] == 0.35
    assert thresholds["block_buysell"] == 0.65
    assert thresholds["abort_all"] == 0.75


@pytest.mark.asyncio
async def test_compute_temporal_cds_relaxed_age_spread():
    """Verify 4.5 hour age spread yields 0.0 temporal CDS with 6h threshold."""
    mock_session = create_mock_async_session()
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
        type="price_level", detail="Wait until price breaks above 2450.50 for breakout confirmation."
    )
    assert trig_above.type == "price_level"
    assert trig_above.price == 2450.50
    assert trig_above.direction == "above"

    trig_below = ReevaluationTrigger(type="price_level", detail="Re-evaluate when market drops below 1.0850.")
    assert trig_below.type == "price_level"
    assert trig_below.price == 1.0850
    assert trig_below.direction == "below"


def test_reevaluation_trigger_fallback_to_time():
    """Verify ReevaluationTrigger without price info safely falls back to time."""
    trig_generic = ReevaluationTrigger(type="price_level", detail="Re-evaluate when London session structure forms.")
    assert trig_generic.type == "time"


@pytest.mark.asyncio
async def test_tool_executor_symbol_injection():
    """Verify ToolExecutor automatically injects bound symbol if omitted by LLM."""
    mock_session = create_mock_async_session()
    executor = ToolExecutor(mock_session, symbol="XAUUSD")

    # Payload without symbol
    payload_no_symbol = {
        "decision": "wait",
        "confidence": 0.70,
        "rationale": "Testing symbol auto injection without explicit symbol field.",
        "invalidation": "Thesis invalid if price breaks above 2500",
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
        condition_json='{"symbol": "XAUUSD", "detail": "price breaks above 2400.0"}',
    )

    condition = {"symbol": "XAUUSD", "detail": "price breaks above 2400.0"}

    with patch("monika.application.scheduler.trigger_checker.get_session") as mock_get_sess:
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
    mock_session = create_mock_async_session()

    analysis = AssetAnalysis(
        id=101,
        symbol="EURUSD",
        decision="buy",
        stop_loss=1.0800,
        take_profit=1.0900,
        confidence=0.8,
        entry_zone='{"type": "market"}',
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
    from monika.application.scheduler.edge_strategy_runner import EdgeStrategyRunner
    from monika.application.analysis.strategies.base_strategy import EdgeSignal
    from monika.application.analysis.arbitration.signal_arbitrator import ArbitrationResult

    settings = {
        "trading": {
            "edge_strategy": {
                "trend_trailing": {
                    "sl_atr_multiplier": 1.5,
                    "tp_sl_multiplier": 2.5,
                    "use_adr_cap": True,
                    "max_tp_adr_multiple": 1.5,
                }
            },
            "risk": {
                "min_rr_ratio": 1.3,
            },
        }
    }
    runner = EdgeStrategyRunner(settings=settings)
    mock_session = create_mock_async_session()

    sig = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=1.0,
        rationale="TSM test",
        exit_style="trend_trailing",
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
        take_profit=1.3725,
    )

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={})

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", AsyncMock(return_value=0.0020)
        ),
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            AsyncMock(return_value={"adr": 0.0080}),
        ),
        patch(
            "monika.application.analysis.calculators.macro_bias_filter.evaluate_macro_alignment",
            AsyncMock(return_value={"aligned": True, "score": 1.0, "reason": "ok"}),
        ),
        patch(
            "monika.application.analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate",
            AsyncMock(return_value=mock_arb),
        ),
        patch("monika.application.graph.reactive_graph.get_reactive_graph", return_value=mock_graph),
    ):
        await runner._materialize_and_route(mock_session, sig)

        # ATR=0.0020, sl_dist = 0.0020 * 1.5 = 0.0030, tp_dist = 0.0030 * 2.5 = 0.0075
        # Entry=1.3650 -> SL=1.3620, TP=1.3725
        assert sig.stop_loss == 1.3620
        assert sig.take_profit == 1.3725
        rr_ratio = (sig.take_profit - sig.entry_price) / (sig.entry_price - sig.stop_loss)
        assert round(rr_ratio, 2) == 2.50


def test_invalidation_direction_schema_no_ambiguity():
    """Verify invalidation_direction schema does not contain type: [string, null] alongside enum."""
    from monika.application.analysis.schemas import get_tool_schema
    from monika.application.analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema

    schema = get_tool_schema(SubmitAssetAnalysisSchema)
    inv = schema["properties"]["invalidation_direction"]
    assert inv["type"] == "string"
    assert inv["enum"] == ["above", "below"]


def test_reevaluation_trigger_auto_fallback_buy_and_wait():
    """Verify SubmitAssetAnalysisSchema auto-fills reevaluation_trigger if omitted."""
    payload_buy = {
        "symbol": "EURUSD",
        "decision": "buy",
        "confidence": 0.8,
        "rationale": "Strong rejection at H4 FVG",
        "entry_condition": {"type": "market", "detail": "Market entry"},
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "invalidation": "Thesis invalid below 1.0790",
        "invalidation_price": 1.0790,
        "invalidation_direction": "below",
        "confluence_score": 8,
        "priced_in_score": 3,
    }
    validated_buy = SubmitAssetAnalysisSchema.model_validate(payload_buy)
    assert validated_buy.reevaluation_trigger is not None
    assert validated_buy.reevaluation_trigger.price == 1.0790

    payload_wait = {
        "symbol": "EURUSD",
        "decision": "wait",
        "confidence": 0.5,
        "rationale": "Waiting for confirmation",
        "invalidation": "Invalid above 1.1000",
    }
    validated_wait = SubmitAssetAnalysisSchema.model_validate(payload_wait)
    assert validated_wait.reevaluation_trigger is not None
    assert validated_wait.reevaluation_trigger.type == "time"


def test_confluence_factors_microstructure_and_pattern_recognized():
    """Verify microstructure and pattern confluence factors are accepted."""
    from monika.application.analysis.tools.executor import FACTOR_POINT_MAP
    from monika.application.agent.harness.tool_repair import coerce_tool_arguments

    assert "microstructure_ok" in FACTOR_POINT_MAP
    assert "historical_pattern_consensus" in FACTOR_POINT_MAP

    pdef = {"properties": {"confluence_factors": {"type": "array"}}}
    repaired = coerce_tool_arguments({"confluence_factors": ["order_flow", "pattern_similarity"]}, pdef)
    assert "microstructure_ok" in repaired["confluence_factors"]
    assert "historical_pattern_consensus" in repaired["confluence_factors"]


@pytest.mark.asyncio
async def test_submit_asset_analysis_priced_in_override_dict_serialization(db_session):
    """Verify submit_asset_analysis serializes dictionary priced_in_override_justification to JSON text."""
    import json
    from sqlalchemy import select

    executor = ToolExecutor(session=db_session, symbol="XTIUSD")
    executor.called_tools.add("get_price_history")
    executor.called_tools.add("get_technical_indicators")

    override_dict = {
        "override_reason": "Not applicable: no directional trade is being submitted, no priced-in override requested.",
        "why_stage1_wrong": "Not applicable",
        "post_event_evidence": "Not applicable",
    }
    payload = {
        "symbol": "XTIUSD",
        "decision": "wait",
        "confidence": 0.86,
        "entry_condition": {"type": "market", "price": 99.61, "detail": "No entry inside H4 FVG"},
        "invalidation": "WAIT thesis invalidated by H4 CHOCH",
        "reevaluation_trigger": {
            "type": "price_level",
            "detail": "Re-evaluate BUY after H4 bullish MSS",
            "price": 100.3333,
            "direction": "above",
            "symbol": "XTIUSD",
        },
        "rationale": "WAIT. XTIUSD ground truth: 99.61, priced-in score is 8/10.",
        "priced_in_score": 8,
        "priced_in_override_justification": override_dict,
        "confluence_score": 0,
        "playbook_id": "xtiusd_s_vwap_dev10_asian_playbook",
    }

    res = await executor.execute("submit_asset_analysis", payload)
    assert res.get("status") == "saved", f"Expected saved status, got: {res}"
    analysis_id = res.get("analysis_id")
    assert analysis_id is not None

    saved_row = (await db_session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))).scalar_one()
    assert isinstance(saved_row.priced_in_override_justification, str)
    decoded = json.loads(saved_row.priced_in_override_justification)
    assert decoded["override_reason"] == override_dict["override_reason"]
    assert decoded["why_stage1_wrong"] == override_dict["why_stage1_wrong"]
    assert decoded["post_event_evidence"] == override_dict["post_event_evidence"]


@pytest.mark.asyncio
async def test_submit_asset_analysis_priced_in_override_idempotent_retry(db_session):
    """Verify idempotent update within same session serializes updated override dictionary."""
    import json
    from sqlalchemy import select

    executor = ToolExecutor(session=db_session, symbol="XBRUSD")
    executor.called_tools.add("get_price_history")
    executor.called_tools.add("get_technical_indicators")

    payload = {
        "symbol": "XBRUSD",
        "decision": "wait",
        "confidence": 0.86,
        "invalidation": "Thesis invalidated above 110.20",
        "rationale": "Initial WAIT rationale",
        "priced_in_score": 8,
        "priced_in_override_justification": {
            "override_reason": "No override requested. Score 8/10 is binding hard block.",
            "why_stage1_wrong": "Initial why wrong assessment",
            "post_event_evidence": "No post-event evidence",
        },
    }

    res1 = await executor.execute("submit_asset_analysis", payload)
    assert res1.get("status") == "saved"
    analysis_id = res1.get("analysis_id")

    # Retry/update in same execution session
    payload_retry = dict(payload)
    payload_retry["confidence"] = 0.90
    payload_retry["priced_in_override_justification"] = {
        "override_reason": "No override requested. Score 8/10 is binding hard block.",
        "why_stage1_wrong": "Updated why wrong assessment on retry",
        "post_event_evidence": "Confirmed no post-event evidence",
    }
    res2 = await executor.execute("submit_asset_analysis", payload_retry)
    assert res2.get("status") == "saved"
    assert res2.get("analysis_id") == analysis_id

    updated_row = (await db_session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))).scalar_one()
    assert isinstance(updated_row.priced_in_override_justification, str)
    decoded = json.loads(updated_row.priced_in_override_justification)
    assert decoded["why_stage1_wrong"] == "Updated why wrong assessment on retry"


@pytest.mark.asyncio
async def test_submit_asset_analysis_priced_in_override_string_and_none_serialization(db_session):
    """Verify submit_asset_analysis handles string, empty dict, and None without failure."""
    from sqlalchemy import select

    executor = ToolExecutor(session=db_session, symbol="EURUSD")
    executor.called_tools.add("get_price_history")
    executor.called_tools.add("get_technical_indicators")

    # Case 1: String justification
    payload_str = {
        "symbol": "EURUSD",
        "decision": "wait",
        "confidence": 0.70,
        "invalidation": "Invalid above 1.1000",
        "rationale": "WAIT rationale",
        "priced_in_score": 8,
        "priced_in_override_justification": "Explicit text justification for market priced in status",
    }
    res_str = await executor.execute("submit_asset_analysis", payload_str)
    assert res_str.get("status") == "saved"
    row_str = (
        await db_session.execute(select(AssetAnalysis).where(AssetAnalysis.id == res_str["analysis_id"]))
    ).scalar_one()
    assert isinstance(row_str.priced_in_override_justification, str)
    assert "Explicit text justification" in row_str.priced_in_override_justification

    # Case 2: None / omitted justification
    executor2 = ToolExecutor(session=db_session, symbol="GBPUSD")
    executor2.called_tools.add("get_price_history")
    executor2.called_tools.add("get_technical_indicators")
    payload_none = {
        "symbol": "GBPUSD",
        "decision": "wait",
        "confidence": 0.60,
        "invalidation": "Invalid below 1.2500",
        "rationale": "WAIT rationale",
        "priced_in_score": 3,
        "priced_in_override_justification": None,
    }
    res_none = await executor2.execute("submit_asset_analysis", payload_none)
    assert res_none.get("status") == "saved"
    row_none = (
        await db_session.execute(select(AssetAnalysis).where(AssetAnalysis.id == res_none["analysis_id"]))
    ).scalar_one()
    assert row_none.priced_in_override_justification is None
