# ==============================================================================
# File: tests/services/test_system_status_service.py
# ==============================================================================

import pytest
from unittest.mock import MagicMock
from services.system_status_service import SystemStatusService
from services.market_data_service import MarketDataService
from utils.infra.container import ServiceContainer


def test_system_status_service_health():
    container = ServiceContainer()
    mock_mt5 = MagicMock(connected=True)
    mock_exec = MagicMock(paper_trading=False)
    container.register_instance("mt5_client", mock_mt5)
    container.register_instance("execution_service", mock_exec)

    health = SystemStatusService.get_system_health(container)
    assert health["status"] == "HEALTHY"
    assert health["broker"]["connected"] is True
    assert health["broker"]["type"] == "mt5_live"


def test_market_data_service_quote():
    container = ServiceContainer()
    mock_mt5 = MagicMock()
    mock_mt5.get_quote.return_value = {"symbol": "EURUSD", "bid": 1.0850, "ask": 1.0852}
    container.register_instance("mt5_client", mock_mt5)

    quote = MarketDataService.get_latest_quote("EURUSD", container)
    assert quote is not None
    assert quote["symbol"] == "EURUSD"
    assert quote["bid"] == 1.0850
