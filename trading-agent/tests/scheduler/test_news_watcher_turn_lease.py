import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from agent.turn_lease_manager import SymbolTurnLeaseManager
from scheduler.news_watcher import NewsWatcher
from database.models import NewsItem


@pytest.fixture(autouse=True)
def reset_turn_lease_singleton():
    import agent.turn_lease_manager as tlm
    tlm._GLOBAL_LEASE_MANAGER = None
    yield
    tlm._GLOBAL_LEASE_MANAGER = None


@pytest.fixture
def settings(tmp_path):
    return {
        "trading": {
            "schedule": {
                "news_check_minutes": 5,
                "news_watcher_state_file": str(tmp_path / "news_watcher_lease_test.json"),
            },
            "risk": {"max_daily_trades": 5},
        }
    }


def _make_news(title, impact="BREAKING"):
    news = MagicMock(spec=NewsItem)
    news.title = title
    news.summary = "Test breaking event"
    news.impact = impact
    news.currency_tags = "USD,XAU"
    news.sentiment = "BEARISH_USD,FRESH_CATALYST"
    news.fetched_at = datetime.now(timezone.utc)
    news.url = f"http://test.com/{title.replace(' ', '_')}"
    return news


@pytest.mark.asyncio
async def test_news_watcher_coalesces_into_active_turn_lease(settings):
    lease_mgr = SymbolTurnLeaseManager.get_instance()

    # Setup an active harness on XAUUSD
    mock_harness = MagicMock()
    mock_harness.enqueue_steering = MagicMock()

    acquired = await lease_mgr.acquire_lease(
        symbol="XAUUSD",
        holder_id="cycle_active_123",
        ttl_seconds=300.0,
        active_harness=mock_harness,
    )
    assert acquired is True

    watcher = NewsWatcher(settings)
    news_item = _make_news("BREAKING: Unexpected Fed Emergency Rate Cut 100bps")

    # Call _trigger_reanalysis with affected_symbols=["XAUUSD"]
    with patch("scheduler.news_watcher.get_session") as mock_gs:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_gs.return_value = mock_ctx

        # Mock position queries
        mock_scalar = MagicMock()
        mock_scalar.scalar_one_or_none.return_value = 0
        mock_session.execute.return_value = mock_scalar

        await watcher._trigger_reanalysis([news_item], ["XAUUSD"], fallback_mode=False)

    # Verify that steering was coalesced into active harness
    mock_harness.enqueue_steering.assert_called_once()
    call_kwargs = mock_harness.enqueue_steering.call_args.kwargs
    assert "BREAKING NEWS SHOCK" in call_kwargs.get("content", "")
    assert call_kwargs.get("sender") == "news_watcher"


@pytest.mark.asyncio
async def test_news_watcher_targeted_reanalysis_acquires_and_releases_lease(settings):
    lease_mgr = SymbolTurnLeaseManager.get_instance()
    watcher = NewsWatcher(settings)

    mock_per_asset = MagicMock()
    mock_per_asset.run_all = AsyncMock(return_value={
        "EURUSD": {"decision": "wait", "analysis_id": 101}
    })
    watcher._per_asset_stage = mock_per_asset

    # Before targeted reanalysis, EURUSD is not leased
    assert not await lease_mgr.is_symbol_leased("EURUSD")

    await watcher._run_targeted_reanalysis_and_route(["EURUSD"], context="Test Context")

    mock_per_asset.run_all.assert_awaited_once()

    # After targeted reanalysis, EURUSD lease is released
    assert not await lease_mgr.is_symbol_leased("EURUSD")
