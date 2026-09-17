# ==============================================================================
# File: tests/cli/test_tui_components.py
# Description: Unit Tests for TUI LiveTickerBanner trend arrows and components
# ==============================================================================

import pytest
from cli.tui import LiveTickerBanner


def test_live_ticker_banner_empty_quotes():
    """Verify ticker banner shows waiting message when quotes dictionary is empty."""
    banner = LiveTickerBanner()
    banner.update_status(
        real_count=0,
        paper_count=0,
        daily_pnl=0.0,
        pnl_pct=0.0,
        vix=15.2,
        kill_switch=False,
        system_paused=False,
        auto_execute=False,
        quotes={},
    )
    plain = banner.render().plain
    assert "MARKET FEED: AWAITING ACTIVE TICK DATA..." in plain


def test_live_ticker_banner_trend_arrows():
    """Verify ticker banner displays correct trend indicators (•, ▲, ▼) based on price movements."""
    banner = LiveTickerBanner()

    # Initial tick (no previous quote -> should display neutral bullet •)
    banner.update_status(
        real_count=1,
        paper_count=2,
        daily_pnl=120.50,
        pnl_pct=1.2,
        vix=14.5,
        kill_switch=False,
        system_paused=False,
        auto_execute=True,
        quotes={"EURUSD": 1.0850, "XAUUSD": 2300.00},
    )
    plain1 = banner.render().plain
    assert "EURUSD" in plain1
    assert "•" in plain1
    assert "XAUUSD" in plain1

    # Price increases: EURUSD goes up 1.0850 -> 1.0860
    banner.update_status(
        real_count=1,
        paper_count=2,
        daily_pnl=150.00,
        pnl_pct=1.5,
        vix=14.5,
        kill_switch=False,
        system_paused=False,
        auto_execute=True,
        quotes={"EURUSD": 1.0860, "XAUUSD": 2300.00},
    )
    plain2 = banner.render().plain
    assert "▲" in plain2  # EURUSD went up

    # Price decreases: EURUSD goes down 1.0860 -> 1.0820
    banner.update_status(
        real_count=1,
        paper_count=2,
        daily_pnl=80.00,
        pnl_pct=0.8,
        vix=14.5,
        kill_switch=False,
        system_paused=False,
        auto_execute=True,
        quotes={"EURUSD": 1.0820, "XAUUSD": 2300.00},
    )
    plain3 = banner.render().plain
    assert "▼" in plain3  # EURUSD went down


def test_tab_activation_handler():
    """Verify on_tabbed_content_tab_activated sets _tabs_mounted and triggers notify on tab switch."""
    from unittest.mock import MagicMock
    from cli.tui import TradingDashboard

    app = TradingDashboard()
    app.notify = MagicMock()
    app._tabs_mounted = False

    # First event during mount should mark mounted without notify
    mock_event1 = MagicMock()
    mock_event1.tab.label_text = "Overview"
    app.on_tabbed_content_tab_activated(mock_event1)
    assert app._tabs_mounted is True
    app.notify.assert_not_called()

    # Subsequent event should call notify
    mock_event2 = MagicMock()
    mock_event2.tab.label_text = "Analysis"
    app.on_tabbed_content_tab_activated(mock_event2)
    app.notify.assert_called_once()
    args, _ = app.notify.call_args
    assert "ANALYSIS" in args[0]
