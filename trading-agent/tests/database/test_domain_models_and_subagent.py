"""Unit tests for domain models packaging (Phase 7)."""
import pytest
import database.domain_models as dm


def test_domain_models_imports():
    assert dm.Base is not None
    assert dm.PriceOHLCV is not None
    assert dm.OrderBlock is not None
    assert dm.Position is not None
    assert dm.TradeOutcome is not None
    assert dm.DecisionReflection is not None
    assert dm.FundamentalBrief is not None
    assert dm.AssetAnalysis is not None
    assert dm.TradingEvent is not None
    assert dm.SystemConfig is not None
    assert dm.NewsItem is not None
    assert dm.EconomicCalendar is not None
