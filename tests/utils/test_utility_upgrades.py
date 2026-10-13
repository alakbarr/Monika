import pytest
from database.models import CycleEvent
from analysis.tools.base_handler import DisaggregatedToolResult
from utils.analytics.models_dev_sync import ModelsDevSync
from utils.llm.deferred_dispatcher import DeferredLLMDispatcher, DeferredRequest


def test_cycle_event_model():
    event = CycleEvent(
        cycle_id="cycle_20260921_1900",
        sequence=1,
        event_type="macro_bias_assessed",
        payload={"bias": "BULLISH", "confidence": 0.85, "reason": "DXY weakening"}
    )
    assert event.cycle_id == "cycle_20260921_1900"
    assert event.sequence == 1
    assert event.event_type == "macro_bias_assessed"
    assert event.payload["bias"] == "BULLISH"


def test_disaggregated_tool_result():
    res = DisaggregatedToolResult(
        content="ATR14 is 0.0045, Trend is Bullish",
        details={"atr_14": 0.0045, "raw_candles": [{"c": 1.085}, {"c": 1.086}]}
    )
    assert "ATR14 is 0.0045" in res.content
    assert res.details["atr_14"] == 0.0045
    assert len(res.details["raw_candles"]) == 2


def test_models_dev_sync_local_cache():
    sample_data = {
        "claude-3-5-sonnet": {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.30,
            "cache_write": 3.75,
        }
    }
    ModelsDevSync.save_cache(sample_data, etag="sample_etag_123")
    rates = ModelsDevSync.get_model_pricing("claude-3-5-sonnet")
    assert rates is not None
    assert rates["input"] == 3.0
    assert rates["output"] == 15.0
    assert rates["cache_read"] == 0.30


@pytest.mark.asyncio
async def test_deferred_dispatcher_all_7_tasks():
    dispatcher = DeferredLLMDispatcher()
    
    # All 7 target background tasks from user decision
    tasks = [
        "alpha_discovery",
        "strategy_synthesis",
        "playbook_compile",
        "tearsheet_generation",
        "reflection_deep",
        "historical_backtest",
        "sentiment_aggregate"
    ]
    for t in tasks:
        assert dispatcher.should_defer(t) is True, f"Task {t} should be deferrable"

    # Enqueue requests
    for t in tasks:
        req = DeferredRequest(task_name=t, model="gemini-3.5-flash-lite", messages=[{"role": "user", "content": "analyze"}])
        dispatcher.enqueue(req)

    assert dispatcher.get_queue_size() == len(tasks)

    # Batch dispatch
    results = await dispatcher.dispatch_pending_batch()
    assert len(results) == len(tasks)
    assert dispatcher.get_queue_size() == 0
