from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.graph.nodes.data_node import fetch_data_node
from monika.application.graph.state import TradingState


def _make_dummy_state(symbols=None) -> TradingState:
    return {
        "symbols": symbols or ["XAUUSD", "EURUSD"],
        "market_regime": "normal",
        "vix_level": 15.0,
        "brief_confidence": 0.8,
        "asset_analyses": {},
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "approved_trades": [],
        "errors": [],
        "should_pause": False,
        "weekend_symbols_override": None,
        "stale_assets": [],
        "summary": {},
        "actionable_trades": [],
        "reflection_applied": None,
        "node_errors": {},
        "data_quality_scores": {},
        "cycle_id": "test-cycle-1",
        "fundamental_retry_count": 0,
        "prior_cycle_insights": {},
        "consecutive_wait_count": 0,
        "last_buy_sell_cycle": None,
        "ssvp_per_symbol_contexts": {},
        "ssvp_cds_score": 0.0,
        "ssvp_blocked": False,
        "ssvp_reconciliation_context": None,
        "context_snapshot_id": None,
        "ssvp_retry_count": 0,
    }


@pytest.mark.asyncio
async def test_data_node_htf_w1_graceful_degradation():
    """Verify that W1 and D1 OHLCV staleness results in graceful degradation without pausing Stage 2."""
    state = _make_dummy_state(["XAUUSD", "EURUSD"])

    mock_scheduler = MagicMock()
    mock_scheduler.asset_universe = ["XAUUSD", "EURUSD"]
    mock_scheduler.mt5_timeframes = ["H1", "H4", "D1", "W1"]
    mock_scheduler.settings = {"data_quality": {}, "trading": {}}
    mock_scheduler._refresh_data_sources = AsyncMock(return_value={"status": "ok"})
    mock_scheduler._mt5 = MagicMock()
    mock_scheduler._mt5.fetch_and_save_all = AsyncMock(return_value={"XAUUSD/H1": 1, "EURUSD/H1": 1})

    # Simulate W1 OHLCV and W1 Indicator errors only
    validation_w1_only = {
        "ready": False,
        "warnings": [],
        "errors": [
            "XAUUSD/W1 OHLCV is 197.6h old (stale)",
            "EURUSD/W1 OHLCV is 197.6h old (stale)",
            "XAUUSD/W1 Indicator is 197.6h old (stale)",
            "EURUSD/W1 Indicator is 197.6h old (stale)",
        ],
    }

    with (
        patch(
            "monika.core.validation.data_validator.validate_data_freshness",
            new_callable=AsyncMock,
            return_value=validation_w1_only,
        ),
        patch(
            "monika.application.analysis.calculators.economic_surprise.compute_surprise_scores",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.classify_unscored_news",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.create_news_digest",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.application.services.technical_indicator_service.TechnicalIndicatorService.compute_all_symbols",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.services.market_structure_service.MarketStructureService.analyze_all",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.analysis.prefetch.macro_preprocessor.MacroPreprocessor.run_all_and_save",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.core.analytics.paper_tracker.PaperTracker.should_regenerate_performance_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.performance_reviewer.should_regenerate_fundamental_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.analysis_tracker.detect_score_inflation",
            new_callable=AsyncMock,
            return_value={"insufficient_data": True},
        ),
        patch(
            "monika.core.analytics.analysis_tracker.compute_and_persist_factor_point_overrides",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        config = {"configurable": {"scheduler": mock_scheduler}}
        res = await fetch_data_node(state, config)

        # Must NOT pause because W1 is higher-timeframe context
        assert res.get("should_pause") is False
        assert len(res.get("stale_assets", [])) == 0


@pytest.mark.asyncio
async def test_data_node_active_recovery_flow():
    """Verify that active in-cycle recovery recovers stale OHLCV and resolves errors."""
    state = _make_dummy_state(["XAUUSD", "EURUSD"])

    mock_scheduler = MagicMock()
    mock_scheduler.asset_universe = ["XAUUSD", "EURUSD"]
    mock_scheduler.mt5_timeframes = ["H1", "H4"]
    mock_scheduler.settings = {"data_quality": {}, "trading": {}}
    mock_scheduler._refresh_data_sources = AsyncMock(return_value={"status": "ok"})
    mock_scheduler._mt5 = MagicMock()
    mock_scheduler._mt5.fetch_and_save_all = AsyncMock(return_value={"XAUUSD/H1": 10})

    # First validation returns stale H1 OHLCV for XAUUSD; second validation after recovery returns ready: True
    val_stale = {"ready": False, "warnings": [], "errors": ["XAUUSD/H1 OHLCV is 4.5h old (stale)"]}
    val_clean = {"ready": True, "warnings": [], "errors": []}

    mock_validate = AsyncMock(side_effect=[val_stale, val_clean])

    with (
        patch(
            "monika.core.validation.data_validator.validate_data_freshness",
            mock_validate,
        ),
        patch(
            "monika.application.analysis.calculators.economic_surprise.compute_surprise_scores",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.classify_unscored_news",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.create_news_digest",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.application.services.technical_indicator_service.TechnicalIndicatorService.compute_all_symbols",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.services.technical_indicator_service.TechnicalIndicatorService.compute_and_save",
            new_callable=AsyncMock,
            return_value=50,
        ),
        patch(
            "monika.application.services.market_structure_service.MarketStructureService.analyze_all",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.analysis.prefetch.macro_preprocessor.MacroPreprocessor.run_all_and_save",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.core.analytics.paper_tracker.PaperTracker.should_regenerate_performance_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.performance_reviewer.should_regenerate_fundamental_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.analysis_tracker.detect_score_inflation",
            new_callable=AsyncMock,
            return_value={"insufficient_data": True},
        ),
        patch(
            "monika.core.analytics.analysis_tracker.compute_and_persist_factor_point_overrides",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        config = {"configurable": {"scheduler": mock_scheduler}}
        res = await fetch_data_node(state, config)

        # Active recovery must trigger targeted fetch_and_save_all
        assert mock_validate.await_count == 2
        assert res.get("should_pause") is False
        assert len(res.get("stale_assets", [])) == 0


@pytest.mark.asyncio
async def test_data_node_per_asset_quarantine():
    """Verify that when 1 asset is critically stale, only that asset is quarantined while healthy assets proceed."""
    state = _make_dummy_state(["XAUUSD", "EURUSD"])

    mock_scheduler = MagicMock()
    mock_scheduler.asset_universe = ["XAUUSD", "EURUSD"]
    mock_scheduler.mt5_timeframes = ["H1"]
    mock_scheduler.settings = {"data_quality": {}, "trading": {}}
    mock_scheduler._refresh_data_sources = AsyncMock(return_value={"status": "ok"})
    mock_scheduler._mt5 = MagicMock()
    mock_scheduler._mt5.fetch_and_save_all = AsyncMock(return_value={"XAUUSD/H1": 0})

    # XAUUSD is stale and unrecovered, but EURUSD is completely healthy
    val_partial = {"ready": False, "warnings": [], "errors": ["XAUUSD/H1 OHLCV is 10.0h old (stale)"]}

    with (
        patch(
            "monika.core.validation.data_validator.validate_data_freshness",
            new_callable=AsyncMock,
            return_value=val_partial,
        ),
        patch(
            "monika.application.analysis.calculators.economic_surprise.compute_surprise_scores",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.classify_unscored_news",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "monika.application.analysis.prefetch.news_digest.NewsDigestProcessor.create_news_digest",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.application.services.technical_indicator_service.TechnicalIndicatorService.compute_all_symbols",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.services.market_structure_service.MarketStructureService.analyze_all",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.analysis.prefetch.macro_preprocessor.MacroPreprocessor.run_all_and_save",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.core.analytics.paper_tracker.PaperTracker.should_regenerate_performance_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.performance_reviewer.should_regenerate_fundamental_notes",
            new_callable=AsyncMock,
            return_value=(False, "ok"),
        ),
        patch(
            "monika.core.analytics.analysis_tracker.detect_score_inflation",
            new_callable=AsyncMock,
            return_value={"insufficient_data": True},
        ),
        patch(
            "monika.core.analytics.analysis_tracker.compute_and_persist_factor_point_overrides",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        config = {"configurable": {"scheduler": mock_scheduler}}
        res = await fetch_data_node(state, config)

        # Per-asset isolation: XAUUSD is quarantined, but Stage 2 does not pause because EURUSD is healthy
        assert res.get("should_pause") is False
        assert "XAUUSD" in res.get("stale_assets", [])
        assert "EURUSD" not in res.get("stale_assets", [])
