"""
Master Unit & Integration Test Suite for Round 2 Phase 2 Remediation.

Covers:
1. Lesson Consolidator Symbol Partitioning (AX6-06)
2. Signal Arbitrator Concordant Entry Price ATR Gap Guard & Dynamic R:R (AX1-08)
3. Signal Arbitrator Dynamic Bayesian Concordant Boost (AX1-09)
4. Dynamic Correlation Crypto Uncertainty Buffer & Sizing Penalty (R2-F02)
5. RiskGate Broker Timezone Dynamic DST Configuration (R2-F03)
6. FXSSI Retail Sentiment Time-Series History Persistence (AXIS4-09)
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from utils.market.dynamic_correlation import (
    is_crypto_or_commodity_symbol,
    get_correlation_uncertainty_multiplier
)
from risk.risk_gate import get_trading_day_start
from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher


# ==============================================================================
# 1. Lesson Consolidator Symbol Partitioning (AX6-06)
# ==============================================================================

@pytest.mark.asyncio
async def test_lesson_consolidator_symbol_partitioning():
    """Verify consolidate_lessons_to_playbook queries partitions per symbol in asset_universe."""
    mock_session = AsyncMock()
    
    # Mock reflections returned for EURUSD, GBPUSD, BTCUSD
    def make_reflection(sym, idx):
        m = MagicMock()
        m.id = f"{sym}_{idx}"
        m.symbol = sym
        m.status = "resolved"
        m.specific_lesson = f"Lesson for {sym} setup {idx}"
        m.next_trade_adjustment = f"Adjustment {idx}"
        m.resolved_at = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        m.is_paper_whatif = False
        m.was_profitable = True
        m.process_was_sound = True
        return m

    # Setup return values for partitioned queries (each symbol gets 20 reflections)
    sym_lists = [
        [make_reflection("EURUSD", i) for i in range(20)],
        [make_reflection("GBPUSD", i) for i in range(20)],
        [make_reflection("BTCUSD", i) for i in range(20)]
    ]
    
    mock_results = []
    for s_list in sym_lists:
        res = MagicMock()
        res.scalars.return_value.all.return_value = s_list
        mock_results.append(res)

    mock_session.execute.side_effect = mock_results

    settings = {
        "trading": {
            "asset_universe": ["EURUSD", "GBPUSD", "BTCUSD"]
        }
    }

    mock_client = AsyncMock()
    mock_client.generate.return_value = "## EURUSD\n- Rule 1\n## GBPUSD\n- Rule 2\n## BTCUSD\n- Rule 3"

    with patch("analysis.providers.llm_factory.get_client_for_task", return_value=mock_client):
        result = await consolidate_lessons_to_playbook(mock_session, settings, auto_propose_only=True)
        assert result is not None
        assert "## EURUSD" in result
        assert "## BTCUSD" in result
        # Verify multiple partitioned queries were executed
        assert mock_session.execute.call_count >= 3


# ==============================================================================
# 2. Signal Arbitrator Concordant Entry Price ATR Gap Guard (AX1-08)
# ==============================================================================

@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_atr_gap_guard_quant_priority():
    """Verify ATR gap guard selects Quant levels when Quant has superior R:R and gap > 0.5 ATR."""
    arbitrator = SignalArbitrator(settings={
        "trading": {
            "arbitration": {
                "concordant_boost_conf": 0.05,
                "concordant_risk_multiplier": 1.15
            }
        }
    })

    # Quant setup: Entry 1.1000, SL 1.0950 (Risk 0.0050), TP 1.1150 (Reward 0.0150) -> R:R = 3.0
    quant_sig = MagicMock(
        symbol="EURUSD",
        direction="buy",
        confidence=0.80,
        strategy_id="xau_trend",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        meta={"atr": 0.0020}
    )

    # LLM setup: Stale/Divergent Entry 1.1050 (Gap = 0.0050 > 0.5*0.0020=0.0010)
    # SL 1.1020 (Risk 0.0030), TP 1.1080 (Reward 0.0030) -> R:R = 1.0
    llm_dec = {
        "decision": "buy",
        "confidence": 0.75,
        "entry_price": 1.1050,
        "stop_loss": 1.1020,
        "take_profit": 1.1080,
        "risk_multiplier": 1.0
    }

    mock_session = AsyncMock()
    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", new_callable=AsyncMock) as mock_cal:
        mock_cal.return_value = 0.75
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="EURUSD",
            quant_signal=quant_sig,
            llm_decision=llm_dec,
            market_regime="trending_bullish"
        )

        assert res.decision == "buy"
        assert res.selected_source == "concordant"
        # Should pick Quant's optimal R:R levels
        assert res.entry_price == 1.1000
        assert res.stop_loss == 1.0950
        assert res.take_profit == 1.1150
        assert res.meta.get("level_source") == "quant"


# ==============================================================================
# 3. Signal Arbitrator Dynamic Bayesian Concordant Boost (AX1-09)
# ==============================================================================

@pytest.mark.asyncio
async def test_signal_arbitrator_dynamic_bayesian_boost():
    """Verify concordant boost scales dynamically based on calibrated confidence."""
    arbitrator = SignalArbitrator(settings={
        "trading": {
            "signal_arbitration": {
                "concordant_boost_conf": 0.05,
                "quant_weight": 0.5,
                "llm_weight": 0.5,
                "dynamic_brier_weighting": False,
                "dynamic_bayesian_boost": True
            }
        }
    })

    quant_sig = MagicMock(
        symbol="EURUSD",
        direction="buy",
        confidence=0.85,
        strategy_id="xau_trend",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )

    llm_dec = {
        "decision": "buy",
        "confidence": 0.85,
        "entry_price": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "risk_multiplier": 1.0
    }

    mock_session = AsyncMock()
    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", new_callable=AsyncMock) as mock_cal:
        # High calibrated confidence triggers dynamic boost +0.02 (0.05 -> 0.07)
        mock_cal.return_value = 0.85
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="EURUSD",
            quant_signal=quant_sig,
            llm_decision=llm_dec,
            market_regime="trending_bullish"
        )

        assert res.meta.get("dynamic_boost") >= 0.07
        assert res.confidence >= 0.88


# ==============================================================================
# 4. Dynamic Correlation Crypto Uncertainty Buffer (R2-F02)
# ==============================================================================

def test_dynamic_correlation_crypto_uncertainty_buffer():
    """Verify get_correlation_uncertainty_multiplier applies 0.8x haircut on crypto static fallback."""
    assert is_crypto_or_commodity_symbol("BTCUSD") is True
    assert is_crypto_or_commodity_symbol("ETHUSD") is True
    assert is_crypto_or_commodity_symbol("XAUUSD") is True
    assert is_crypto_or_commodity_symbol("EURUSD") is False

    # Crypto static fallback -> 0.80 multiplier
    mult_crypto_fallback = get_correlation_uncertainty_multiplier("BTCUSD", "EURUSD", "static_fallback_insufficient_history")
    assert mult_crypto_fallback == 0.80

    # Commodity static fallback -> 0.80 multiplier
    mult_gold_fallback = get_correlation_uncertainty_multiplier("XAUUSD", "USDJPY", "static_fallback_insufficient_overlap")
    assert mult_gold_fallback == 0.80

    # Forex static fallback -> 1.00 multiplier
    mult_forex_fallback = get_correlation_uncertainty_multiplier("EURUSD", "GBPUSD", "static_fallback_insufficient_history")
    assert mult_forex_fallback == 1.00

    # Dynamic correlation -> 1.00 multiplier
    mult_dynamic = get_correlation_uncertainty_multiplier("BTCUSD", "EURUSD", "dynamic_ewma")
    assert mult_dynamic == 1.00


# ==============================================================================
# 5. RiskGate Broker Timezone Dynamic DST Configuration (R2-F03)
# ==============================================================================

def test_risk_gate_broker_timezone_configuration():
    """Verify get_trading_day_start respects broker_timezone and NY DST transition."""
    settings = {
        "trading": {
            "risk": {
                "broker_timezone": "America/New_York",
                "broker_rollover_hour": 17
            }
        }
    }

    # Summer EDT (UTC-4) on Aug 28, 2026 at 22:30 UTC -> after 17:00 NY (21:00 UTC)
    now_edt = datetime(2026, 8, 28, 22, 30, tzinfo=timezone.utc)
    start_edt = get_trading_day_start(settings, now=now_edt)
    assert start_edt == datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc)

    # Winter EST (UTC-5) on Jan 15, 2026 at 23:00 UTC -> after 17:00 NY (22:00 UTC)
    now_est = datetime(2026, 1, 15, 23, 0, tzinfo=timezone.utc)
    start_est = get_trading_day_start(settings, now=now_est)
    assert start_est == datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)

    # Explicit midnight UTC configuration
    settings_midnight = {
        "trading": {
            "risk": {
                "daily_rollover_utc_hour": 0
            }
        }
    }
    start_midnight = get_trading_day_start(settings_midnight, now=now_edt)
    assert start_midnight == datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc)


# ==============================================================================
# 6. FXSSI Retail Sentiment Time-Series History Persistence (AXIS4-09)
# ==============================================================================

@pytest.mark.asyncio
async def test_fxssi_sentiment_time_series_history_persistence():
    """Verify FXSSISentimentFetcher persists latest snapshot and append to time-series history."""
    mock_session = AsyncMock()

    fetcher = FXSSISentimentFetcher(session=mock_session, headless=True)
    fetcher.fetch_sync = MagicMock(return_value={
        "source": "fxssi",
        "fetched_at": "2026-08-29T10:00:00Z",
        "ratios": {
            "EURUSD": {"long_percent": 45.0, "short_percent": 55.0, "long_short_ratio": 0.8182},
            "XAUUSD": {"long_percent": 70.0, "short_percent": 30.0, "long_short_ratio": 2.3333}
        }
    })

    # Mock execute queries for SystemConfig
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_exec_res

    res = await fetcher.fetch()
    assert res.get("source") == "fxssi"
    assert "EURUSD" in res["ratios"]

    # Verify session.add was called for both fxssi_sentiment_latest and fxssi_sentiment_history
    assert mock_session.add.call_count >= 2
    assert mock_session.commit.called
