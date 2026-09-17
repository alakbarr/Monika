import pytest
from utils.llm.deferred_dispatcher import (
    DeferredLLMDispatcher,
    DeferredRequest,
    DispatchMode,
)


def test_should_defer_candidates():
    dispatcher = DeferredLLMDispatcher()

    # Batch candidates must return True
    assert dispatcher.should_defer("alpha_discovery") is True
    assert dispatcher.should_defer("strategy_synthesis") is True
    assert dispatcher.should_defer("playbook_compiler") is True
    assert dispatcher.should_defer("skill_curation") is True
    assert dispatcher.should_defer("what_if_analysis") is True
    assert dispatcher.should_defer("daily_report") is True

    # Realtime critical trading tasks must return False
    assert dispatcher.should_defer("execution") is False
    assert dispatcher.should_defer("risk_gate") is False
    assert dispatcher.should_defer("trailing_stop") is False
    assert dispatcher.should_defer("flash_crash_detector") is False
    assert dispatcher.should_defer("per_asset_analysis") is False


def test_enqueue_and_queue_management():
    dispatcher = DeferredLLMDispatcher()
    dispatcher.clear_queue()

    req1 = DeferredRequest(
        task_name="alpha_discovery",
        model="claude-3-7-sonnet",
        messages=[{"role": "user", "content": "Formulate alpha hypothesis"}],
    )
    req_id = dispatcher.enqueue(req1)

    assert req_id == req1.request_id
    assert dispatcher.get_queue_size() == 1
    assert dispatcher.get_pending_requests()[0].task_name == "alpha_discovery"


def test_estimate_batch_savings():
    dispatcher = DeferredLLMDispatcher()
    # 1M input tokens + 200k output tokens on claude-3-7-sonnet
    # Real-time: (1M * $3) + (0.2M * $15) = $3 + $3 = $6.00
    # Batch (50% discount): $3.00
    savings = dispatcher.estimate_batch_savings(
        input_tokens=1_000_000,
        output_tokens=200_000,
        model="claude-3-7-sonnet",
    )
    assert savings == 3.0
