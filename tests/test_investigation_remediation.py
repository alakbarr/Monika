# ==============================================================================
# File: tests/test_investigation_remediation.py
# Monika System Doctor & Runtime Investigation Verification Test Suite
# ==============================================================================

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import warnings

import numpy as np
import pandas as pd
import pytest

from monika.application.analysis.strategies.hypothesis_registry import (
    HypothesisRegistry,
    HypothesisStatus,
    StrategyHypothesis,
)
from monika.core.analytics.chart_generator import (
    generate_candlestick_chart,
    generate_configured_workspace_chart,
)
from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_084 import compute as compute_alpha_084
from monika.infrastructure.llm.rate_limiting.claude_rate_limiter import ClaudeRateLimiter
from monika.infrastructure.llm.spill_subsystem import PostgresSpillSubsystem


# ----------------------------------------------------------------------
# 1. Chart Generator DataFrame Truth Value Fix Verification
# ----------------------------------------------------------------------


def test_chart_generator_accepts_dataframe_input_without_truth_value_error():
    """Verify chart generator functions accept pd.DataFrame without ambiguous truth value error."""
    dates = pd.date_range("2026-01-01", periods=30, freq="4h", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": np.linspace(1.10, 1.12, 30),
            "High": np.linspace(1.11, 1.13, 30),
            "Low": np.linspace(1.09, 1.11, 30),
            "Close": np.linspace(1.10, 1.12, 30),
            "Volume": np.full(30, 1000.0),
        },
        index=dates,
    )

    # Calling with DataFrame previously raised:
    # ValueError: The truth value of a DataFrame is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all().
    buf, path = generate_configured_workspace_chart(
        df,
        symbol="EURUSD",
        timeframe="H4",
        save_to_disk=False,
    )
    assert buf is not None
    assert buf.getvalue().startswith(b"\x89PNG")

    # Also verify standard candlestick chart generator
    buf_candle = generate_candlestick_chart(df, symbol="EURUSD", timeframe="H4")
    assert buf_candle is not None
    assert buf_candle.getvalue().startswith(b"\x89PNG")


# ----------------------------------------------------------------------
# 2. Hypothesis Registry Datetime and Dataclass Serialization Verification
# ----------------------------------------------------------------------


@dataclass
class MockTradeRecord:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    pnl: float


def test_hypothesis_registry_serializes_datetime_and_dataclasses(tmp_path: Path):
    """Verify HypothesisRegistry saves and loads hypotheses with datetime and dataclasses in metrics."""
    storage_file = tmp_path / "hypotheses_test.json"
    registry = HypothesisRegistry(storage_path=storage_file)

    now = datetime(2026, 10, 26, 17, 21, 47, tzinfo=timezone.utc)
    mock_trade = MockTradeRecord(
        symbol="EURUSD",
        entry_time=now,
        exit_time=now + timedelta(hours=2),
        pnl=150.0,
    )

    hyp = registry.register(
        thesis="Breakout on volatility compression",
        signal_definition="close > upper_band and adx > 25",
        target_universe=["EURUSD", "GBPUSD"],
        timeframe="H1",
    )

    # Update with complex metrics containing datetime and dataclass
    registry.update_status(
        hyp.hypothesis_id,
        HypothesisStatus.TESTING,
        metrics={
            "sharpe": 1.85,
            "validation_timestamp": now,
            "validation_date": date(2026, 10, 26),
            "trades": [mock_trade],
        },
    )

    # Must save without: "TypeError: Object of type datetime is not JSON serializable"
    assert storage_file.exists()
    content = storage_file.read_text(encoding="utf-8")
    assert "2026-10-26T17:21:47+00:00" in content
    assert "EURUSD" in content

    # Verify reloading works cleanly
    new_reg = HypothesisRegistry(storage_path=storage_file)
    loaded = new_reg._hypotheses.get(hyp.hypothesis_id)
    assert loaded is not None
    assert loaded.status == HypothesisStatus.TESTING
    assert loaded.metrics["sharpe"] == 1.85


# ----------------------------------------------------------------------
# 3. WorldQuant Alpha 084 Overflow Prevention Verification
# ----------------------------------------------------------------------


def test_wq_alpha_084_no_power_overflow_warning():
    """Verify wq_alpha_084 handles extreme price deltas without RuntimeWarning in power/square."""
    dates = pd.date_range("2026-01-01", periods=60, freq="1D")
    symbols = ["BTCUSD", "ETHUSD"]

    # Create prices with large 5-day delta (e.g. BTC swinging by $5,000)
    base_price = 60000.0
    close_vals = np.array([base_price + (i * 200.0) for i in range(60)])
    close_df = pd.DataFrame(
        {"BTCUSD": close_vals, "ETHUSD": close_vals * 0.05},
        index=dates,
    )
    vwap_df = close_df * 1.001

    panel = {"close": close_df, "vwap": vwap_df}

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        out = compute_alpha_084(panel)

        overflow_warnings = [
            w
            for w in recorded_warnings
            if issubclass(w.category, RuntimeWarning) and "overflow" in str(w.message).lower()
        ]
        assert len(overflow_warnings) == 0, f"Encountered unexpected overflow warnings: {overflow_warnings}"

    assert isinstance(out, pd.DataFrame)
    assert out.shape == close_df.shape
    assert not np.isinf(out.to_numpy()).any()


# ----------------------------------------------------------------------
# 4. Claude Rate Limiter Pacing Log Level Verification
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_rate_limiter_pacing_log_level(caplog):
    """Verify routine micro-pacing delays (< 3.0s) log at INFO rather than WARNING."""
    ClaudeRateLimiter._last_session_start = 0.0
    ClaudeRateLimiter._call_times = []
    ClaudeRateLimiter._token_history = []

    # First call acquires immediately
    await ClaudeRateLimiter.acquire_session_slot(model_name="claude-3-7-sonnet")

    # Immediate second call should be paced by MIN_DELAY_BETWEEN_SESSIONS (2.0s)
    with caplog.at_level("INFO"):
        await ClaudeRateLimiter.acquire_session_slot(model_name="claude-3-7-sonnet")

    # Warnings should NOT include micro-delay pacing
    warnings_found = [
        r.message for r in caplog.records if r.levelname == "WARNING" and "Claude rate limiter throttled" in r.message
    ]
    assert len(warnings_found) == 0, f"Expected no WARNING for micro-pacing, found: {warnings_found}"

    info_found = [
        r.message for r in caplog.records if r.levelname == "INFO" and "Claude rate limiter throttled" in r.message
    ]
    assert len(info_found) >= 1


@pytest.mark.asyncio
async def test_claude_rate_limiter_bypasses_non_claude_models():
    """Verify non-Claude models (e.g. DeepSeek, Gemini) are not throttled by ClaudeRateLimiter."""
    ClaudeRateLimiter._last_session_start = time.time()
    original_delay = ClaudeRateLimiter.MIN_DELAY_BETWEEN_SESSIONS
    ClaudeRateLimiter.MIN_DELAY_BETWEEN_SESSIONS = 5.0
    try:
        start = time.monotonic()
        await ClaudeRateLimiter.acquire_session_slot(model_name="deepseek-v4.1-flash-1017")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Non-Claude model should not be throttled, elapsed: {elapsed}s"
    finally:
        ClaudeRateLimiter.MIN_DELAY_BETWEEN_SESSIONS = original_delay


# ----------------------------------------------------------------------
# 5. Spill Subsystem Uses Isolated Database Session
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spill_subsystem_persists_via_isolated_session():
    """Verify maybe_spill creates an isolated session via get_session and does not call add/flush on caller session."""
    subsystem = PostgresSpillSubsystem(settings={"context_compaction": {"spill_threshold_tokens": 50}})

    caller_mock_session = MagicMock()
    isolated_mock_session = AsyncMock()
    isolated_mock_session.add = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = isolated_mock_session
    mock_ctx.__aexit__.return_value = None

    large_payload = "A" * 5000  # Will trigger spill (>50 tokens)

    with patch("monika.infrastructure.database.db.get_session", return_value=mock_ctx):
        receipt = await subsystem.maybe_spill(
            session=caller_mock_session,
            tool_name="web_search",
            output=large_payload,
            cycle_id="test_cycle",
        )

        assert "db://spill/" in receipt
        # Caller session must NOT be mutated or flushed
        caller_mock_session.add.assert_not_called()
        caller_mock_session.flush.assert_not_called()
        # Isolated session must be used and committed
        isolated_mock_session.add.assert_called_once()
        isolated_mock_session.commit.assert_awaited_once()
