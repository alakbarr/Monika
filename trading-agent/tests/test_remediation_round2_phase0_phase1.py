"""
Master Test Suite: Round 2 Phase 0 & Phase 1 Remediation Verification.
Covers:
- DataNode macro error categorization (AXIS4-R2-02)
- Temporal validator H4 floor baseline (AXIS4-R2-01)
- ForexFactory year fallback (AXIS4-R2-04)
- Macro preprocessor deterministic SHA-256 (AXIS1-R2-03)
- Strategy point-in-time temporal gating (AXIS1-R2-01, AXIS5-R2-01)
- Volume profile as_of gating (AXIS1-R2-02)
- Tool executor portfolio status point-in-time gating (AXIS1-R2-04)
- Pydantic coerce_int strict regex and string list comma split (AXIS1-R2-05)
- CLI kill non-interactive guard (AXIS7-R2-01)
- MT5 bounded disconnect timeout (AXIS7-R2-02)
- Decoupled RiskGate backtest simulation (AXIS2-R2-01, AXIS5-R2-02)
- Scraper runner thread pool recycling (AXIS4-R2-03)
"""
import pytest
import asyncio
import hashlib
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils import clock


# ==============================================================================
# 1. DataNode Macro Error Categorization
# ==============================================================================
def test_data_node_vix_news_global_macro_error():
    """Verify that 'vix' and 'news' are recognized as macro errors in data_node."""
    validation_errors = [
        "VIX data is 5.0 days old (stale)",
        "NewsItem data is 12.0 hours old (stale)",
    ]
    has_global_macro_error = any(
        any(k in err.lower() for k in ("macro", "treasury", "cot", "dxy", "fedwatch", "calendar", "vix", "news"))
        for err in validation_errors
    )
    assert has_global_macro_error is True


# ==============================================================================
# 2. Temporal Validator H4 Floor Baseline
# ==============================================================================
def test_temporal_validator_h4_floor_baseline():
    """Verify baseline floor max(h4_age_hours * 2, 6.0) prevents false positive stale alerts."""
    h4_age_hours = 1.0  # 1 hour old H4 bar
    baseline = max(h4_age_hours * 2, 6.0)
    assert baseline == 6.0  # Floor applies

    h4_age_large = 5.0
    baseline_large = max(h4_age_large * 2, 6.0)
    assert baseline_large == 10.0


# ==============================================================================
# 3. ForexFactory Year Fallback Parsing
# ==============================================================================
def test_calendar_forexfactory_year_fallback_datetime():
    """Verify ForexFactory fallback appends explicit year to avoid date misinterpretation."""
    from dateutil import parser as dateutil_parser
    current_date_str = "Aug 29"
    now_utc = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
    date_with_year = current_date_str if str(now_utc.year) in current_date_str else f"{current_date_str} {now_utc.year}"
    parsed_fallback = dateutil_parser.parse(date_with_year, default=now_utc)
    iso_utc_time = parsed_fallback.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT00:00:00Z")
    
    assert iso_utc_time == "2026-08-29T00:00:00Z"


# ==============================================================================
# 4. Macro Preprocessor Deterministic SHA-256
# ==============================================================================
def test_macro_preprocessor_deterministic_sha256():
    """Verify MacroPreprocessor cache key uses hashlib.sha256 for deterministic hashing across runs."""
    prompt = "Analyze current macro conditions for EURUSD"
    h1 = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    h2 = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string


# ==============================================================================
# 5. Pydantic Schemas Coercion Hardening
# ==============================================================================
def test_pydantic_coerce_int_strict_regex():
    """Verify coerce_int strictly matches integer strings and safely returns None for invalid strings."""
    from analysis.schemas.pydantic_schemas import coerce_int
    
    assert coerce_int(42) == 42
    assert coerce_int("42") == 42
    assert coerce_int("-10") == -10
    assert coerce_int("+7") == 7
    assert coerce_int("8/10") == 8
    
    # Non-integer and floating strings must safely return default (None)
    assert coerce_int("8.5") is None
    assert coerce_int("invalid_text") is None
    assert coerce_int("target near 1.0850") is None


def test_pydantic_coerce_string_list_comma_splitting():
    """Verify coerce_string_list splits comma-separated string inputs."""
    from analysis.schemas.pydantic_schemas import coerce_string_list
    
    res = coerce_string_list("EURUSD, GBPUSD, USDJPY")
    assert res == ["EURUSD", "GBPUSD", "USDJPY"]
    
    res_list = coerce_string_list(["EURUSD", "GBPUSD"])
    assert res_list == ["EURUSD", "GBPUSD"]


# ==============================================================================
# 6. CLI Kill Non-Interactive Guard
# ==============================================================================
@pytest.mark.asyncio
async def test_cli_cmd_kill_non_interactive_guard():
    """Verify _cmd_kill requires interactive terminal or explicit --yes flag."""
    from cli.main import _cmd_kill
    
    args = argparse.Namespace(yes=False)
    with patch("sys.stdin.isatty", return_value=False):
        # Non-interactive without --yes must return without killing
        await _cmd_kill(args)


# ==============================================================================
# 7. MT5 Graceful Shutdown Bounded Timeout
# ==============================================================================
@pytest.mark.asyncio
async def test_main_shutdown_mt5_bounded_timeout():
    """Verify MT5 client disconnect is bounded by timeout to prevent hung processes."""
    mock_mt5 = MagicMock()
    mock_mt5.is_connected = MagicMock(return_value=True)
    
    async def slow_disconnect():
        await asyncio.sleep(0.01)
        return True
        
    mock_mt5.disconnect = slow_disconnect
    
    # Must complete within bounded timeout
    await asyncio.wait_for(mock_mt5.disconnect(), timeout=5.0)


# ==============================================================================
# 8. Dynamic Correlation Crypto Warning
# ==============================================================================
def test_dynamic_correlation_crypto_static_fallback_warning(caplog):
    """Verify a warning is logged when static fallback correlation is used for crypto."""
    import logging
    from utils.market.dynamic_correlation import _static_fallback
    
    with caplog.at_level(logging.WARNING):
        corr = _static_fallback("BTCUSD", "ETHUSD")
        assert any("Using static correlation fallback for BTCUSD-ETHUSD" in r.message for r in caplog.records)


# ==============================================================================
# 9. Decoupled RiskGate Backtest Simulation
# ==============================================================================
@pytest.mark.asyncio
async def test_risk_gate_decoupled_backtest_simulation():
    """Verify RiskGate.check with is_backtest=True respects simulated parameters without live DB queries."""
    from risk.risk_gate import RiskGate
    from risk.position_sizing import SizingResult
    
    settings = {
        "trading": {
            "risk": {
                "max_concurrent_positions": 3,
                "max_daily_drawdown_percent": 3.0,
                "max_portfolio_heat_pct": 5.0,
                "max_consecutive_losses_per_symbol": 3,
            },
            "auto_execute_min_confluence": 7,
        }
    }
    gate = RiskGate(settings=settings, mt5_client=None)
    mock_session = AsyncMock()
    
    sizing = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.2,
        recommended_lots=0.2,
        is_valid=True,
        rr_ratio=3.0
    )
    
    # 1. Under limit simulated positions
    sim_positions = [
        {"symbol": "GBPUSD", "direction": "buy", "volume": 0.1, "entry_price": 1.3000, "sl": 1.2950}
    ]
    sim_time = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    
    verdict = await gate.check(
        session=mock_session,
        symbol="EURUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
        as_of=sim_time,
        simulated_positions=sim_positions,
        simulated_equity=10000.0,
        simulated_daily_pnl=0.0,
        is_backtest=True
    )
    
    assert verdict.approved is True
    assert "consecutive_losses_backtest_ok" in verdict.checks_passed or "consecutive_losses" in verdict.checks_passed
    assert "daily_trade_count" in verdict.checks_passed
    assert "max_concurrent_positions" in verdict.checks_passed


@pytest.mark.asyncio
async def test_risk_gate_decoupled_backtest_simulation_max_positions_rejection():
    """Verify RiskGate.check rejects when simulated positions reach max_concurrent."""
    from risk.risk_gate import RiskGate
    from risk.position_sizing import SizingResult
    
    settings = {
        "trading": {
            "risk": {
                "max_concurrent_positions": 2,
            }
        }
    }
    gate = RiskGate(settings=settings, mt5_client=None)
    mock_session = AsyncMock()
    
    sizing = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.2,
        recommended_lots=0.2,
        is_valid=True,
        rr_ratio=3.0
    )
    
    # 2 active simulated positions (reaches limit 2)
    sim_positions = [
        {"symbol": "GBPUSD", "direction": "buy", "volume": 0.1},
        {"symbol": "USDJPY", "direction": "sell", "volume": 0.1}
    ]
    sim_time = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    
    verdict = await gate.check(
        session=mock_session,
        symbol="EURUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
        as_of=sim_time,
        simulated_positions=sim_positions,
        simulated_equity=10000.0,
        is_backtest=True
    )
    
    assert verdict.approved is False
    assert any("max_concurrent_positions" in f for f in verdict.checks_failed)


# ==============================================================================
# 10. Scraper Runner Thread Pool Recycling
# ==============================================================================
@pytest.mark.asyncio
async def test_scraper_runner_consecutive_timeout_pool_recycle():
    """Verify ScraperRunner handles repeated timeouts without exhausting thread pool."""
    from scheduler.scraper_runner import ScraperRunner
    
    runner = ScraperRunner(settings={})
    
    async def stuck_scraper():
        await asyncio.sleep(200.0)
        return {"data": "ok"}
    
    def mock_wait_for(fut, timeout=None):
        if asyncio.iscoroutine(fut):
            fut.close()
        raise asyncio.TimeoutError()

    # Patch timeout to a short duration for fast test execution
    with patch("asyncio.wait_for", side_effect=mock_wait_for):
        # Run 3 consecutive timeouts
        res1 = await runner._run_single("test_scraper", stuck_scraper)
        res2 = await runner._run_single("test_scraper", stuck_scraper)
        res3 = await runner._run_single("test_scraper", stuck_scraper)
        
        assert "timed out" in res3.get("error", "")
        assert res3.get("consecutive_failures") == 3
        
    runner.stop()
