import pytest
from datetime import datetime, timezone, timedelta, date
from utils import clock
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.calculators.macro_bias_filter import (
    _NEUTRAL_RATE_ESTIMATES,
    _rate_score,
    compute_currency_macro_score,
)
from analysis.tools.handlers.macro_tools import (
    handle_get_interest_rates,
    handle_get_central_bank_expectations,
    handle_get_bond_yield_spreads,
)
from analysis.calculators.economic_surprise import compute_surprise_scores
from database.models import (
    InterestRate,
    EconomicCalendar,
    CentralBankRateExpectation,
    TreasuryYield,
    BondYieldData,
)

def test_neutral_rate_estimates_exist():
    """All 5 major central bank currency neutral rates must be configured."""
    for ccy in ['USD', 'EUR', 'GBP', 'JPY', 'AUD']:
        assert ccy in _NEUTRAL_RATE_ESTIMATES
        assert isinstance(_NEUTRAL_RATE_ESTIMATES[ccy], (int, float))
    assert _NEUTRAL_RATE_ESTIMATES['JPY'] < _NEUTRAL_RATE_ESTIMATES['USD']
    assert _NEUTRAL_RATE_ESTIMATES['AUD'] > _NEUTRAL_RATE_ESTIMATES['EUR']

@pytest.mark.asyncio
async def test_rate_score_calculation():
    """Rate score must calculate divergence from domestic neutral rate."""
    mock_session = AsyncMock()
    mock_row = MagicMock(spec=InterestRate)
    mock_row.rate_percent = 5.25
    mock_row.effective_date = datetime(2026, 6, 1, tzinfo=timezone.utc)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_row
    mock_session.execute.return_value = mock_res

    score = await _rate_score(mock_session, 'USD')
    # (5.25 - 2.75) / 3.0 = 2.50 / 3.0 = 0.833
    assert 0.80 <= score <= 0.85

@pytest.mark.asyncio
async def test_handle_get_interest_rates_with_differentials(db_session):
    """Tool handle_get_interest_rates must return rate differentials matrix and mandate profiles."""
    rates_data = [
        ("FED", 5.00),
        ("ECB", 3.75),
        ("BOE", 4.75),
        ("BOJ", 1.00),
        ("RBA", 4.35),
    ]
    for bank, r_pct in rates_data:
        db_session.add(InterestRate(
            bank=bank,
            rate_percent=r_pct,
            effective_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            next_meeting_date=datetime(2026, 7, 15, tzinfo=timezone.utc),
        ))
    await db_session.commit()

    args = {}
    ctx = {"session": db_session}
    res = await handle_get_interest_rates(args, **ctx)

    assert res["count"] == 5
    assert "rate_differentials" in res
    diffs = res["rate_differentials"]
    
    # EURUSD spread = 3.75 - 5.00 = -1.25
    assert "EURUSD" in diffs
    assert diffs["EURUSD"]["spread_pct"] == -1.25
    assert diffs["EURUSD"]["advantage"] == "USD"

    # USDJPY spread = 5.00 - 1.00 = +4.00
    assert "USDJPY" in diffs
    assert diffs["USDJPY"]["spread_pct"] == 4.00
    assert "carry_trade_context" in diffs["USDJPY"]

    # Mandate profiles
    assert "mandate_profiles" in res
    assert "FED" in res["mandate_profiles"]
    assert "Dual" in res["mandate_profiles"]["FED"]["mandate"]
    assert "Deflation" in res["mandate_profiles"]["BOJ"]["mandate"]


@pytest.mark.asyncio
async def test_handle_get_interest_rates_with_date_object():
    """Verify handle_get_interest_rates handles effective_date of type datetime.date cleanly without UnboundLocalError."""
    mock_session = AsyncMock()
    mock_row = MagicMock(spec=InterestRate)
    mock_row.bank = "FED"
    mock_row.rate_percent = 5.25
    mock_row.effective_date = date(2026, 6, 1)
    mock_row.next_meeting_date = date(2026, 7, 15)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_res

    res = await handle_get_interest_rates({}, session=mock_session)
    assert res["count"] == 1
    assert "data_age_days" in res
    assert isinstance(res["data_age_days"], int)
    assert res["data_age_days"] >= 0

@pytest.mark.asyncio
async def test_economic_surprise_inverts_unemployment():
    """Unemployment higher than forecast must yield a negative surprise score."""
    mock_session = AsyncMock()

    # Event 1: NFP higher than forecast -> Positive surprise (hawkish)
    ev_nfp = MagicMock(spec=EconomicCalendar)
    ev_nfp.event_name = "Non-Farm Employment Change"
    ev_nfp.actual = "250K"
    ev_nfp.forecast = "200K"
    ev_nfp.surprise_score = None

    # Event 2: Unemployment Rate higher than forecast -> Negative surprise (dovish)
    ev_unemp = MagicMock(spec=EconomicCalendar)
    ev_unemp.event_name = "Unemployment Rate"
    ev_unemp.actual = "4.3%"
    ev_unemp.forecast = "4.1%"
    ev_unemp.surprise_score = None

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [ev_nfp, ev_unemp]
    mock_session.execute.return_value = mock_res

    updated = await compute_surprise_scores(mock_session)
    assert updated == 2
    assert ev_nfp.surprise_score > 0  # (250-200)/200 * 100 = +25.0
    assert ev_unemp.surprise_score < 0  # (4.3-4.1)/4.1 inverted = negative


@pytest.mark.asyncio
async def test_handle_get_central_bank_expectations_with_data():
    """Verify handle_get_central_bank_expectations returns probabilities and priced-in scores."""
    mock_session = AsyncMock()

    def make_exp(bank, cur_rate, hike, hold, cut, m_date="2026-06-15"):
        r = MagicMock(spec=CentralBankRateExpectation)
        r.bank = bank
        r.current_rate = cur_rate
        r.prob_hike = hike
        r.prob_hold = hold
        r.prob_cut = cut
        r.meeting_date = m_date
        r.source = "centralbank.watch"
        r.fetched_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        return r

    rows = [
        make_exp("FED", 5.25, 0.0, 85.0, 15.0),
        make_exp("ECB", 3.75, 0.0, 10.0, 90.0),
        make_exp("BOJ", 0.50, 75.0, 25.0, 0.0),
    ]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = rows
    mock_session.execute.return_value = mock_res

    args = {}
    ctx = {"session": mock_session}
    res = await handle_get_central_bank_expectations(args, **ctx)

    assert res["count"] == 3
    assert "expectations" in res
    exps = res["expectations"]

    # FED: Hold is 85% -> Largely Priced In (score 7)
    assert "FED" in exps
    assert exps["FED"]["dominant_expected_action"] == "hold"
    assert exps["FED"]["dominant_probability_pct"] == 85.0
    assert exps["FED"]["priced_in_score"] == 7
    assert exps["FED"]["priced_in_label"] == "Largely Priced In"

    # ECB: Cut is 90% -> Fully Priced In (score 9)
    assert "ECB" in exps
    assert exps["ECB"]["dominant_expected_action"] == "cut"
    assert exps["ECB"]["priced_in_score"] == 9
    assert exps["ECB"]["priced_in_label"] == "Fully Priced In"

    # BOJ: Hike is 75% -> Largely Priced In (score 7)
    assert "BOJ" in exps
    assert exps["BOJ"]["dominant_expected_action"] == "hike"
    assert exps["BOJ"]["priced_in_score"] == 7


@pytest.mark.asyncio
async def test_handle_get_central_bank_expectations_with_null_probabilities():
    """Verify handle_get_central_bank_expectations handles NULL prob_* values gracefully without TypeError."""
    mock_session = AsyncMock()
    row = MagicMock(spec=CentralBankRateExpectation)
    row.bank = "RBA"
    row.current_rate = 4.35
    row.prob_hike = None
    row.prob_hold = 80.0
    row.prob_cut = None
    row.meeting_date = "2026-07-01"
    row.source = "centralbank.watch"
    row.fetched_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [row]
    mock_session.execute.return_value = mock_res

    res = await handle_get_central_bank_expectations({}, session=mock_session)
    assert res["count"] == 1
    assert "RBA" in res["expectations"]
    assert res["expectations"]["RBA"]["dominant_expected_action"] == "hold"
    assert res["expectations"]["RBA"]["dominant_probability_pct"] == 80.0
    assert res["expectations"]["RBA"]["probabilities"]["hike"] == 0.0
    assert res["expectations"]["RBA"]["probabilities"]["cut"] == 0.0


@pytest.mark.asyncio
async def test_handle_get_central_bank_expectations_empty_fallback():
    """Verify empty central bank expectation rows trigger fallback with web_search guidance."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    args = {}
    ctx = {"session": mock_session}
    res = await handle_get_central_bank_expectations(args, **ctx)

    assert res["expectations"] == {}
    assert res["fallback_tool"] == "web_search"
    assert "ECB" in res["suggested_queries"]
    assert "BOJ" in res["suggested_queries"]


@pytest.mark.asyncio
async def test_handle_get_bond_yield_spreads_with_2y_and_10y(db_session):
    """Verify handle_get_bond_yield_spreads calculates both 10Y and 2Y yield spreads."""
    d = (clock.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # US Treasuries
    db_session.add(TreasuryYield(tenor="10Y", date=d, yield_percent=4.40))
    db_session.add(TreasuryYield(tenor="2Y", date=d, yield_percent=4.10))

    # Sovereign intl yields
    db_session.add(BondYieldData(country_tenor="DE_10Y", date=d, yield_percent=2.40))
    db_session.add(BondYieldData(country_tenor="DE_2Y", date=d, yield_percent=2.50))
    db_session.add(BondYieldData(country_tenor="UK_10Y", date=d, yield_percent=4.20))
    db_session.add(BondYieldData(country_tenor="UK_2Y", date=d, yield_percent=4.15))
    db_session.add(BondYieldData(country_tenor="JP_10Y", date=d, yield_percent=1.20))
    db_session.add(BondYieldData(country_tenor="JP_2Y", date=d, yield_percent=0.60))
    db_session.add(BondYieldData(country_tenor="AU_10Y", date=d, yield_percent=4.00))
    db_session.add(BondYieldData(country_tenor="AU_2Y", date=d, yield_percent=3.80))
    await db_session.commit()

    args = {"days_back": 15}
    ctx = {"session": db_session}
    res = await handle_get_bond_yield_spreads(args, **ctx)

    assert "yield_spreads_10y" in res
    assert "yield_spreads_2y" in res

    # DE 10Y: US (4.40) - DE (2.40) = 2.00
    spread_10y_de = res["yield_spreads_10y"].get("DE_10Y")
    assert spread_10y_de is not None
    assert spread_10y_de["current_spread"] == 2.00

    # DE 2Y: US (4.10) - DE (2.50) = 1.60
    spread_2y_de = res["yield_spreads_2y"].get("DE_2Y")
    assert spread_2y_de is not None
    assert spread_2y_de["current_spread"] == 1.60

    # JP 2Y: US (4.10) - JP (0.60) = 3.50
    spread_2y_jp = res["yield_spreads_2y"].get("JP_2Y")
    assert spread_2y_jp is not None
    assert spread_2y_jp["current_spread"] == 3.50

