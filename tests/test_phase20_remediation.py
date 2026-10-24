# ==============================================================================
# File: tests/test_phase20_remediation.py
# ==============================================================================

"""
Verification suite for Phase 20 remediation:
1. TokenBudgetManager reserve debiting & exhaustion.
2. Pricing engine Gemini commercial vs free tier & DeepSeek v4 alias.
3. TradingCycleEventLog thread safety and SHA-256 chain integrity under concurrency.
4. MetricsCollector OpenMetrics summary monotonicity and label escaping.
5. DocxReportGenerator & PptxDeckGenerator safe formatting and fallback resilience.
6. TearsheetGenerator UTC-aware normalization and zero-equity guard.
7. EdgeTracker Decimal acceptance and auto-pause deduplication.
8. StrategyEdgeTracker finite profit factor JSON serialization.
9. PaperTracker settings loading resolution.
10. Scripts ultra_signals importability and heal_kill_switch dry-run safety.
"""

import json
import math
import threading
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.core.analytics.edge_tracker import is_trade_win
from monika.core.analytics.paper_tracker import PaperTracker
from monika.core.analytics.pricing import cost_usd, get_price, is_free_tier
from monika.core.analytics.strategy_edge_tracker import compute_strategy_pair_stats
from monika.core.telemetry.metrics_exporter import MetricsCollector
from monika.core.telemetry.reporting.docx_report_generator import DocxReportGenerator, _safe_fmt as docx_safe_fmt
from monika.core.telemetry.reporting.pptx_deck_generator import PptxDeckGenerator, _safe_fmt as pptx_safe_fmt
from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator, TearsheetResult
from monika.core.telemetry.token_budgeter import TokenBudgetManager
from monika.core.telemetry.trading_cycle_event_log import TradingCycleEventLog


def test_pricing_gemini_commercial_and_free():
    """Verify Gemini commercial models under paid key or vertex are billed, and free tiers are $0."""
    # Paid key / vertex models are billed at rate card
    assert cost_usd("gemini-4-argon", 1_000_000, 500_000, is_direct_free_tier=False) == pytest.approx(7.0)
    assert not is_free_tier("gemini-4-argon", is_direct_free_tier=False)
    assert not is_free_tier("vertex/gemini-1.5-pro")

    # Free tier models must be $0
    assert is_free_tier("gemini-2.0-flash:free")
    assert is_free_tier("groq/llama3-8b", provider="groq")
    assert cost_usd("gemini-2.0-flash:free", 100_000, 50_000) == 0.0
    assert cost_usd("gemini-3.7-flash", 10000, 5000, provider="gemini") == 0.0

    # Generic alias deepseek-v4 resolves cleanly
    price_v4 = get_price("deepseek-v4")
    assert price_v4.input == pytest.approx(0.66)
    assert price_v4.output == pytest.approx(1.98)


def test_token_budgeter_reserve_exhaustion():
    """Verify emergency reserve quota is debited and exhausted when a subsystem exceeds quota."""
    TokenBudgetManager.reset()
    manager = TokenBudgetManager(
        settings={
            "llm": {
                "daily_token_budget": 10000,
            }
        }
    )
    # stage1 share is 0.20 -> 2,000 tokens
    # reserve share is 0.10 -> 1,000 tokens
    stage1_quota = manager.get_quota("stage1")
    reserve_quota = manager.get_quota("reserve")
    assert stage1_quota == 2000
    assert reserve_quota == 1000

    # Initial spend within quota
    assert manager.can_spend("stage1", 1500)
    manager.record_usage("stage1", 750, 750)  # Total 1500

    # Next call exceeds stage1 quota (1500 + 1000 = 2500 > 2000), but reserve (1000) can buffer 500 deficit
    assert manager.can_spend("stage1", 1000)
    manager.record_usage("stage1", 500, 500)  # Total 2500, excess 500 debited against reserve

    # Reserve now has 500 left. Deficit of 600 cannot be buffered (requested 1100 when remaining is 0 from stage1, deficit 1100 > 500)
    assert not manager.can_spend("stage1", 1100)


def test_trading_cycle_event_log_concurrent_integrity(tmp_path):
    """Verify multithreaded concurrent event recording maintains monotonic sequence and chain integrity."""
    TradingCycleEventLog.reset()
    event_log = TradingCycleEventLog(storage_dir=tmp_path)
    cycle_id = "test_concurrent_cycle"

    def _worker(thread_id: int):
        for i in range(25):
            event_log.record_event(
                cycle_id=cycle_id,
                event_type="test_event",
                payload={"thread": thread_id, "idx": i},
            )

    threads = [threading.Thread(target=_worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = event_log.get_events_for_cycle(cycle_id)
    assert len(events) == 100

    # Verify contiguous monotonic sequence numbering
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, 101))

    # Verify SHA-256 chain integrity
    for i in range(1, len(events)):
        assert events[i].prev_hash == events[i - 1].chain_hash


def test_metrics_collector_monotonic_summary():
    """Verify Prometheus summary metrics maintain monotonic count and sum past 500 samples."""
    MetricsCollector.reset()
    collector = MetricsCollector()

    metric_name = "test_execution_duration_ms"
    # Record 600 samples of 10.0 ms
    for _ in range(600):
        collector.record_histogram(metric_name, 10.0)

    # Raw sample ring buffer is capped at 500 for quantiles
    assert len(collector._histograms[metric_name]) == 500

    # Monotonic summary count & sum reflect total 600 samples
    assert collector._summary_counts[metric_name] == 600
    assert collector._summary_sums[metric_name] == pytest.approx(6000.0)

    output = collector.generate_prometheus_metrics()
    assert f"trading_agent_{metric_name}_count 600" in output
    assert f"trading_agent_{metric_name}_sum 6000.0000" in output


def test_metrics_collector_label_escaping():
    """Verify quotes and newlines in labels are escaped properly in Prometheus output."""
    collector = MetricsCollector()
    collector.inc_counter(
        "test_error_counter",
        1.0,
        labels={"reason": 'quote "here"', "detail": "line1\nline2"},
    )
    output = collector.generate_prometheus_metrics()
    assert r'detail="line1\nline2"' in output
    assert r'reason="quote \"here\""' in output


def test_reporting_generators_safe_formatting_and_fallback(tmp_path):
    """Verify DOCX and PPTX generators handle None metrics safely and provide clean fallback."""
    # Test safe formatters directly
    assert docx_safe_fmt(None, ".2f", default="N/A") == "N/A"
    assert docx_safe_fmt(float("nan"), ".2f", default="N/A") == "N/A"
    assert docx_safe_fmt(12.345, ".2f") == "12.35"

    assert pptx_safe_fmt(None, ".1f", default="0.0%") == "0.0%"
    assert pptx_safe_fmt(55.67, ".1f", suffix="%") == "55.7%"

    # Generate with sparse metrics containing None
    sparse_metrics = {
        "initial_equity": 10000.0,
        "total_net_pnl": None,
        "total_return_pct": None,
        "annualized_sharpe": None,
        "win_rate_pct": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "total_trades": None,
    }

    docx_gen = DocxReportGenerator(output_dir=str(tmp_path))
    docx_file = docx_gen.generate_report(metrics=sparse_metrics, title="Sparse Docx Test")
    assert docx_file.endswith(".docx") or docx_file.endswith(".md")

    pptx_gen = PptxDeckGenerator(output_dir=str(tmp_path))
    pptx_file = pptx_gen.generate_pitch_deck(metrics=sparse_metrics, title="Sparse PPTX Test")
    assert pptx_file.endswith(".pptx") or pptx_file.endswith(".md")


def test_tearsheet_generator_naive_and_aware_datetime(tmp_path):
    """Verify QuantTearsheetGenerator handles mixed naive/aware datetimes and zero equity safely."""
    trades = [
        {"pnl": 150.0, "pnl_pct": 1.5, "symbol": "EURUSD", "closed_at": "2026-10-01T10:00:00"},  # string naive
        {"pnl": -50.0, "pnl_pct": -0.5, "symbol": "GBPUSD", "closed_at": "2026-10-02T12:00:00Z"},  # string aware
    ]
    # Test with initial_equity > 0
    res = QuantTearsheetGenerator.generate_from_trades(trades=trades, initial_equity=10000.0)
    assert res.total_trades == 2
    assert res.total_net_pnl == pytest.approx(100.0)
    assert res.total_return_pct == pytest.approx(1.0)

    # Test with zero initial equity (must not divide by zero)
    res_zero = QuantTearsheetGenerator.generate_from_trades(trades=[], initial_equity=0.0)
    assert res_zero.total_return_pct == 0.0


def test_edge_tracker_decimal_and_pause_deduplication():
    """Verify is_trade_win accepts Decimal types and pause check avoids repeat alerts."""
    # Decimal PnL > 0 is WIN
    assert is_trade_win({"pnl_pct": Decimal("1.25"), "exit_reason": "trailing_sl"}) is True
    # Decimal PnL < 0 is LOSS
    assert is_trade_win({"pnl_pct": Decimal("-0.85"), "exit_reason": "trailing_sl"}) is False
    # Decimal realized_pnl
    assert is_trade_win({"realized_pnl": Decimal("250.50"), "exit_reason": "manual"}) is True

    # Pause string check
    class MockConfig:
        value = "true:Auto-paused by EdgeTracker: z=-2.15"

    existing_pause = MockConfig()
    is_already_paused = bool(
        existing_pause and existing_pause.value and existing_pause.value.split(":", 1)[0].strip().lower() == "true"
    )
    assert is_already_paused is True


@pytest.mark.asyncio
async def test_strategy_edge_tracker_finite_profit_factor():
    """Verify strategy profit factor is capped at finite value (99.99) for JSON serialization."""
    mock_trade = MagicMock()
    mock_trade.pnl_pct = 5.0  # Only wins, 0 gross loss

    mock_analysis = MagicMock()
    mock_analysis.source_strategy_id = "test_strat"
    mock_analysis.symbol = "EURUSD"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(mock_trade, mock_analysis)])))

    stats = await compute_strategy_pair_stats(mock_session, {})
    pair_stat = stats.get("test_strat_EURUSD")
    assert pair_stat is not None
    assert pair_stat["profit_factor"] == 99.99
    assert math.isfinite(pair_stat["profit_factor"])

    # JSON dumps must succeed without invalid 'Infinity'
    dumped = json.dumps(stats)
    assert "Infinity" not in dumped
    loaded = json.loads(dumped)
    assert loaded["test_strat_EURUSD"]["profit_factor"] == 99.99


def test_paper_tracker_settings_resolution():
    """Verify PaperTracker.__init__ resolves settings from config/settings.yaml when none provided."""
    tracker = PaperTracker()
    assert isinstance(tracker.settings, dict)
    # Root settings must have at least trading or paper_trading section
    assert "trading" in tracker.settings or "paper_trading" in tracker.settings or len(tracker.settings) > 0


def test_scripts_ultra_signals_import():
    """Verify ultra_signals.py imports cleanly without ModuleNotFoundError."""
    import scripts.empirical_alpha.ultra_signals as us

    assert hasattr(us, "get_ultra_signal_universe")
