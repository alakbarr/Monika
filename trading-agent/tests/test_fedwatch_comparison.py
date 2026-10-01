"""
Unit and Integration Tests for CME FedWatch Historical Comparison & Systematic Tool Enhancements.
Tests:
1. handle_get_fedwatch_probabilities with compare_hours_ago, event_time, meeting_date, include_history.
2. handle_get_central_bank_expectations with compare_hours_ago and event_time.
3. handle_get_economic_calendar with event_name filtering and lookback expansion.
4. handle_get_news_items with query text search.
5. handle_get_price_history with as_of timestamp filtering.
6. ChatToolRouter macro routing and inclusion of get_central_bank_expectations.
7. ChatAgent._classify_query_complexity distinguishing factual macro queries from deep research.
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from analysis.tools.handlers.macro_tools import (
    handle_get_fedwatch_probabilities,
    handle_get_central_bank_expectations,
    handle_get_economic_calendar,
)
from analysis.tools.handlers.news_tools import handle_get_news_items
from analysis.tools.handlers.market_data_tools import handle_get_price_history
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS


class MockFedRow:
    def __init__(self, id_: int, meeting_date: str, probabilities_json: str, fetched_at: datetime):
        self.id = id_
        self.meeting_date = meeting_date
        self.probabilities_json = probabilities_json
        self.fetched_at = fetched_at


class MockCalendarRow:
    def __init__(self, event_name: str, event_time: datetime, impact: str = "high", currency: str = "USD"):
        self.event_name = event_name
        self.event_time = event_time
        self.impact = impact
        self.currency = currency
        self.actual = "3.0%"
        self.forecast = "3.3%"
        self.previous = "3.0%"
        self.surprise_score = -0.5


class MockNewsRow:
    def __init__(self, title: str, summary: str, published_at: datetime, currency: str = "USD"):
        self.id = 1
        self.title = title
        self.summary = summary
        self.published_at = published_at
        self.currency = currency
        self.source = "ForexLive"
        self.url = "http://example.com"
        self.impact_level = "high"


class MockPriceRow:
    def __init__(self, symbol: str, timeframe: str, dt: datetime, o=2650.0, h=2660.0, l=2645.0, c=2655.0, v=1000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.timestamp = dt
        self.open_time = dt
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


# ==============================================================================
# 1. CME FedWatch Comparison Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_fedwatch_compare_hours_ago():
    """Verify compare_hours_ago produces exact before/after deltas and narrative."""
    now_utc = datetime(2026, 9, 30, 15, 0, 0, tzinfo=timezone.utc)
    mock_records = [
        # Current snapshot (14:50 UTC)
        MockFedRow(
            id_=2,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.629, "HIKE": 0.371}),
            fetched_at=datetime(2026, 9, 30, 14, 50, 0, tzinfo=timezone.utc),
        ),
        # Prior snapshot (12:40 UTC, ~2 hours ago)
        MockFedRow(
            id_=1,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.529, "HIKE": 0.471}),
            fetched_at=datetime(2026, 9, 30, 12, 40, 0, tzinfo=timezone.utc),
        ),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_records
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.clock.now", return_value=now_utc):
        res = await handle_get_fedwatch_probabilities(
            {"meeting_date": "2026-10-28", "compare_hours_ago": 2},
            session=mock_session,
        )

    assert res.get("count") == 1
    meeting = res["meetings"][0]
    assert meeting["meeting_date"] == "2026-10-28"
    assert "comparison" in meeting

    cmp = meeting["comparison"]
    assert cmp["current_probabilities"]["HOLD"] == 0.629
    assert cmp["current_probabilities"]["HIKE"] == 0.371
    assert cmp["prior_probabilities"]["HOLD"] == 0.529
    assert cmp["prior_probabilities"]["HIKE"] == 0.471

    # Deltas: HOLD went from 52.9% to 62.9% (+10.0%), HIKE went from 47.1% to 37.1% (-10.0%)
    assert cmp["deltas_pct"]["HOLD"] == 10.0
    assert cmp["deltas_pct"]["HIKE"] == -10.0
    assert "narrative_summary" in cmp
    assert "HIKE" in cmp["narrative_summary"] and "HOLD" in cmp["narrative_summary"]


@pytest.mark.asyncio
async def test_fedwatch_event_time_comparison():
    """Verify event_time splits snapshots into pre-event and post-event."""
    now_utc = datetime(2026, 9, 30, 15, 0, 0, tzinfo=timezone.utc)
    mock_records = [
        # Post-event snapshot (13:45 UTC)
        MockFedRow(
            id_=3,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.651, "HIKE": 0.349}),
            fetched_at=datetime(2026, 9, 30, 13, 45, 0, tzinfo=timezone.utc),
        ),
        # Pre-event snapshot (11:33 UTC)
        MockFedRow(
            id_=1,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.552, "HIKE": 0.448}),
            fetched_at=datetime(2026, 9, 30, 11, 33, 0, tzinfo=timezone.utc),
        ),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_records
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.clock.now", return_value=now_utc):
        # Event was at 12:30:00 UTC (Core PCE release)
        res = await handle_get_fedwatch_probabilities(
            {"event_time": "2026-09-30T12:30:00Z"},
            session=mock_session,
        )

    meeting = res["meetings"][0]
    cmp = meeting["comparison"]
    assert cmp["comparison_mode"] == "pre_vs_post_event"
    # Pre-event (11:33) Hike was 44.8%, Post-event (13:45) Hike dropped to 34.9%
    assert cmp["deltas_pct"]["HIKE"] == -9.9
    assert cmp["deltas_pct"]["HOLD"] == 9.9


@pytest.mark.asyncio
async def test_fedwatch_include_history():
    """Verify include_history preserves the timeline of snapshots rather than discarding."""
    mock_records = [
        MockFedRow(
            id_=3,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.65}),
            fetched_at=datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc),
        ),
        MockFedRow(
            id_=2,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.60}),
            fetched_at=datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc),
        ),
        MockFedRow(
            id_=1,
            meeting_date="2026-10-28",
            probabilities_json=json.dumps({"HOLD": 0.55}),
            fetched_at=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
        ),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_records
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    res = await handle_get_fedwatch_probabilities(
        {"include_history": True},
        session=mock_session,
    )

    meeting = res["meetings"][0]
    assert "history" in meeting
    assert len(meeting["history"]) == 3
    assert meeting["history"][0]["probabilities"]["HOLD"] == 0.65
    assert meeting["history"][2]["probabilities"]["HOLD"] == 0.55


class MockCBRateExpectationRow:
    def __init__(self, id_: int, bank: str, prob_hike: float, prob_hold: float, prob_cut: float, fetched_at: datetime):
        self.id = id_
        self.bank = bank
        self.prob_hike = prob_hike
        self.prob_hold = prob_hold
        self.prob_cut = prob_cut
        self.meeting_date = "2026-10-28"
        self.current_rate = 5.25
        self.source = "CME FedWatch"
        self.fetched_at = fetched_at


# ==============================================================================
# 2. Central Bank Expectations Comparison Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_central_bank_expectations_comparison():
    """Verify handle_get_central_bank_expectations supports temporal comparison for FED."""
    now_utc = datetime(2026, 9, 30, 15, 0, 0, tzinfo=timezone.utc)
    mock_records = [
        MockCBRateExpectationRow(
            id_=2,
            bank="FED",
            prob_hike=0.37,
            prob_hold=0.63,
            prob_cut=0.0,
            fetched_at=datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc),
        ),
        MockCBRateExpectationRow(
            id_=1,
            bank="FED",
            prob_hike=0.47,
            prob_hold=0.53,
            prob_cut=0.0,
            fetched_at=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
        ),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_records
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.clock.now", return_value=now_utc):
        res = await handle_get_central_bank_expectations(
            {"bank": "FED", "compare_hours_ago": 2},
            session=mock_session,
        )

    assert "FED" in res["expectations"]
    fed_data = res["expectations"]["FED"]
    assert "comparison" in fed_data
    assert fed_data["comparison"]["deltas_pct"]["HIKE"] == -10.0


# ==============================================================================
# 3. Economic Calendar Search Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_economic_calendar_event_name_filter():
    """Verify event_name filter in economic calendar matches event name properly."""
    now_utc = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    mock_events = [
        MockCalendarRow("Core PCE Price Index (YoY)", now_utc - timedelta(hours=2)),
        MockCalendarRow("GDP Annualized (QoQ)", now_utc - timedelta(hours=3)),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_events[0]]
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.clock.now", return_value=now_utc):
        res = await handle_get_economic_calendar(
            {"event_name": "PCE"},
            session=mock_session,
        )

    assert res["count"] == 1
    assert "PCE" in res["events"][0]["event_name"]


# ==============================================================================
# 4. News Items Search Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_news_items_query_filter():
    """Verify news items handler filters by query across title and summary."""
    now_utc = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    mock_news = [
        MockNewsRow("Fed rate outlook shifts after PCE data", "Investors price in lower chance of hike", now_utc),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_news
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.clock.now", return_value=now_utc):
        res = await handle_get_news_items(
            {"query": "Fed rate"},
            session=mock_session,
        )

    assert res["count"] == 1
    assert "Fed rate outlook" in res["items"][0]["title"]


# ==============================================================================
# 5. Price History as_of Filter Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_price_history_as_of_filter():
    """Verify price history handler supports as_of filtering."""
    now_utc = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    mock_bars = [
        MockPriceRow("XAUUSD", "H1", now_utc - timedelta(hours=2)),
        MockPriceRow("XAUUSD", "H1", now_utc - timedelta(hours=1)),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_bars
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    res = await handle_get_price_history(
        {"symbol": "XAUUSD", "timeframe": "H1", "as_of": "2026-09-30T13:00:00Z"},
        session=mock_session,
    )

    assert isinstance(res, list)
    assert len(res) == 2
    assert "open" in res[0]


# ==============================================================================
# 6. ChatToolRouter Macro Routing Tests
# ==============================================================================

def test_chat_tool_router_macro_tools():
    """Verify ChatToolRouter routes macro queries to include get_central_bank_expectations."""
    router = ChatToolRouter(TELEGRAM_TOOLS)
    routed = router.route_tools_for_query("berapa probabilitas suku bunga the fed berikutnya? bandingkan dengan sebelumnya")
    tool_names = {t["name"] for t in routed}

    assert "get_fedwatch_probabilities" in tool_names
    assert "get_central_bank_expectations" in tool_names
    assert "get_economic_calendar" in tool_names


# ==============================================================================
# 7. ChatAgent Complexity Heuristic Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_classify_query_complexity_macro_heuristics():
    """Verify macro queries route to deep_research."""
    from telegram_bot.chat_agent import ChatAgent

    agent = ChatAgent(user_id=12345, settings={})

    # Macro event inquiry -> routes to deep_research
    q1 = "berapa probabilitasnya sebelum berita rilis? apakah probabilitas hike menurun dari sebelum berita rilis dibandingkan setelah rilis?"
    assert agent._is_macro_event_query(q1) is True
    tier1 = await agent._classify_query_complexity(q1)
    assert tier1 == "deep_research"

    # Macro rate query -> routes to deep_research
    q2 = "Sekarang berapa probabilitas perubahan suku bunga the fed berikutnya? bandingkan juga perubahannya dari beberapa jam yang lalu"
    assert agent._is_macro_event_query(q2) is True
    tier2 = await agent._classify_query_complexity(q2)
    assert tier2 == "deep_research"

    # Explicit deep research intent -> routes to deep_research
    q3 = "Lakukan riset mendalam bedah peristiwa FOMC dan probabilitas skenario suku bunga The Fed secara komprehensif"
    tier3 = await agent._classify_query_complexity(q3)
    assert tier3 == "deep_research"


# ==============================================================================
# 8. Stage 1 Prefetcher FedWatch Correlation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_stage1_databundler_correlates_recent_usd_event():
    """Verify Stage1DataBundler automatically detects recent past USD events and queries FedWatch comparison."""
    from analysis.prefetch.stage1_prefetcher import Stage1DataBundler

    mock_session = AsyncMock()
    settings = {"trading": {"asset_universe": ["EURUSD", "XAUUSD"]}}
    bundler = Stage1DataBundler(session=mock_session, settings=settings)

    event_time_str = "2026-09-30T14:30:00+00:00"
    mock_events = [
        {
            "event_name": "<untrusted_external_content>Core PCE Price Index (YoY)</untrusted_external_content>",
            "currency": "USD",
            "impact": "high",
            "actual": "3.0%",
            "event_time": event_time_str,
        }
    ]

    async def mock_execute(tool_name, args):
        if tool_name == "get_economic_calendar":
            return {"count": 1, "events": mock_events}
        elif tool_name == "get_fedwatch_probabilities":
            if args.get("event_time") == event_time_str:
                return {
                    "count": 1,
                    "meetings": [{"meeting_date": "2026-10-28", "probabilities": {"HOLD": 0.629, "HIKE": 0.371}}],
                    "comparisons": [
                        {
                            "meeting_date": "2026-10-28",
                            "reference_time": event_time_str,
                            "comparison_mode": "pre_vs_post_event",
                            "current_probabilities": {"HOLD": 0.629, "HIKE": 0.371},
                            "prior_probabilities": {"HOLD": 0.529, "HIKE": 0.471},
                            "deltas_pct": {"HIKE": -10.0, "HOLD": 10.0},
                            "shift_summary": "Pergeseran ekspektasi rapat 2026-10-28: HIKE 47.1% -> 37.1% (-10.0%), HOLD 52.9% -> 62.9% (+10.0%)",
                        }
                    ],
                }
            return {
                "count": 1,
                "meetings": [{"meeting_date": "2026-10-28", "probabilities": {"HOLD": 0.629, "HIKE": 0.371}}],
            }
        return {}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    # Patch secondary non-critical async routines
    with patch("data_sources.crypto_orderbook_depth.CryptoOrderbookDepth.fetch_snapshot", AsyncMock(return_value=None)), \
         patch("data_sources.sovereign_yield_spreads.SovereignYieldSpreads.get_spreads", AsyncMock(return_value={})), \
         patch("data_sources.gold_physical_radar.GoldPhysicalRadar.fetch_radar", AsyncMock(return_value=MagicMock(institutional_flow_bias="neutral", gld_1d_change_pct=0, xau_sentiment_conviction=0, summary=""))), \
         patch("utils.validation.data_validator.validate_data_freshness", AsyncMock(return_value={"ready": True})):

        compressed_json, satisfied, bundled_data = await bundler.prefetch_all_data()

    assert "fedwatch" in bundled_data
    assert "fedwatch_comparison" in bundled_data
    comp = bundled_data["fedwatch_comparison"]
    assert comp["mode"] == "pre_vs_post_event"
    assert comp["referenced_event"] == "Core PCE Price Index (YoY)"
    assert comp["event_time"] == event_time_str
    assert comp["deltas_pct"] == {"HIKE": -10.0, "HOLD": 10.0}
    assert "HIKE 47.1% -> 37.1% (-10.0%)" in comp["shift_summary"]


@pytest.mark.asyncio
async def test_stage1_databundler_multi_event_correlation():
    """Verify Stage1DataBundler tracks multiple USD events occurring at different hours of the day (19:30, 20:45, 21:00, 01:00)."""
    from analysis.prefetch.stage1_prefetcher import Stage1DataBundler

    mock_session = AsyncMock()
    bundler = Stage1DataBundler(session=mock_session, settings={"trading": {"asset_universe": ["XAUUSD"]}})

    t1 = "2026-09-30T12:30:00+00:00"  # 19:30 WIB: Core PCE
    t2 = "2026-09-30T13:45:00+00:00"  # 20:45 WIB: Flash PMI
    t3 = "2026-09-30T14:00:00+00:00"  # 21:00 WIB: ISM Manufacturing
    t4 = "2026-09-30T18:00:00+00:00"  # 01:00 WIB: FOMC Minutes

    mock_events = [
        {"event_name": "<untrusted_external_content>Core PCE Price Index (YoY)</untrusted_external_content>", "currency": "USD", "impact": "high", "actual": "3.0%", "event_time": t1},
        {"event_name": "<untrusted_external_content>S&P Global Manufacturing PMI</untrusted_external_content>", "currency": "USD", "impact": "medium", "actual": "49.5", "event_time": t2},
        {"event_name": "<untrusted_external_content>ISM Manufacturing PMI</untrusted_external_content>", "currency": "USD", "impact": "high", "actual": "47.2", "event_time": t3},
        {"event_name": "<untrusted_external_content>FOMC Meeting Minutes</untrusted_external_content>", "currency": "USD", "impact": "high", "actual": "neutral", "event_time": t4},
    ]

    async def mock_execute(tool_name, args):
        if tool_name == "get_economic_calendar":
            return {"count": 4, "events": mock_events}
        elif tool_name == "get_fedwatch_probabilities":
            ev_t = args.get("event_time")
            deltas = {
                t1: {"HIKE": -9.9, "HOLD": 9.9},
                t2: {"HIKE": -1.5, "HOLD": 1.5},
                t3: {"HIKE": +3.0, "HOLD": -3.0},
                t4: {"HIKE": +0.5, "HOLD": -0.5},
            }.get(ev_t, {"HIKE": 0.0, "HOLD": 0.0})

            return {
                "count": 1,
                "meetings": [{"meeting_date": "2026-10-28", "probabilities": {"HOLD": 0.60, "HIKE": 0.40}}],
                "comparisons": [
                    {
                        "meeting_date": "2026-10-28",
                        "reference_time": ev_t,
                        "comparison_mode": "pre_vs_post_event",
                        "current_probabilities": {"HOLD": 0.60, "HIKE": 0.40},
                        "prior_probabilities": {"HOLD": 0.50, "HIKE": 0.50},
                        "deltas_pct": deltas,
                        "shift_summary": f"Pergeseran {ev_t}: HIKE delta {deltas['HIKE']}%",
                    }
                ],
            }
        return {}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    with patch("data_sources.crypto_orderbook_depth.CryptoOrderbookDepth.fetch_snapshot", AsyncMock(return_value=None)), \
         patch("data_sources.sovereign_yield_spreads.SovereignYieldSpreads.get_spreads", AsyncMock(return_value={})), \
         patch("data_sources.gold_physical_radar.GoldPhysicalRadar.fetch_radar", AsyncMock(return_value=MagicMock(institutional_flow_bias="neutral", gld_1d_change_pct=0, xau_sentiment_conviction=0, summary=""))), \
         patch("utils.validation.data_validator.validate_data_freshness", AsyncMock(return_value={"ready": True})):

        _, _, bundled_data = await bundler.prefetch_all_data()

    comp = bundled_data["fedwatch_comparison"]
    assert comp["mode"] == "multi_event_pre_vs_post"
    assert comp["total_events_tracked"] == 4
    assert len(comp["all_event_shifts"]) == 4
    # Memverifikasi bahwa setiap event waktu (19:30, 20:45, 21:00, 01:00 WIB) masing-masing mendapatkan komparasi sebelum vs sesudahnya
    times_tracked = [s["event_time"] for s in comp["all_event_shifts"]]
    assert times_tracked == [t1, t2, t3, t4]
    assert "Core PCE" in comp["all_event_shifts"][0]["events"]
    assert comp["all_event_shifts"][0]["deltas_pct"]["HIKE"] == -9.9
    assert "FOMC Meeting Minutes" in comp["all_event_shifts"][3]["events"]
    assert comp["all_event_shifts"][3]["deltas_pct"]["HIKE"] == 0.5



# ==============================================================================
# 9. Stage 1 Baseline Calculator Repricing Delta Tests
# ==============================================================================

def test_stage1_priced_in_baseline_repricing_delta():
    """Verify calculate_stage1_priced_in_baseline factors in fedwatch_repricing_delta >= 10.0%."""
    from analysis.calculators.stage1_priced_in import calculate_stage1_priced_in_baseline

    # Base case without repricing delta: score = 0
    res_base = calculate_stage1_priced_in_baseline(
        symbol="EUR",
        cot_percentile=50.0,
        fedwatch_dominant_prob=60.0,
        fedwatch_repricing_delta=3.0,
    )
    assert res_base["score"] == 0
    assert res_base["is_priced_in"] is False

    # Repricing delta shock of -10.5% (dovish/hawkish repricing)
    res_shock = calculate_stage1_priced_in_baseline(
        symbol="EUR",
        cot_percentile=50.0,
        fedwatch_dominant_prob=60.0,
        fedwatch_repricing_delta=-10.5,
    )
    assert res_shock["score"] == 1
    assert any("FedWatch repricing shift -10.5%" in r for r in res_shock["reasons"])


# ==============================================================================
# 10. Pydantic Schema Validation with FedWatch Shift Tests
# ==============================================================================

def test_submit_fundamental_brief_schema_fedwatch_shift():
    """Verify SubmitFundamentalBriefSchema accepts fedwatch_shift_summary and fedwatch_repricing_delta_pct."""
    from analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    valid_payload = {
        "checklist": {
            "bias_vs_narrative_match": True,
            "contradiction_existed": False,
        },
        "key_data_points_used": {
            "dxy_trend_5d": "strengthening +0.8%",
            "vix_close": 15.5,
            "fedwatch_dominant_pct": 62.9,
            "fedwatch_repricing_delta_pct": -10.0,
            "treasury_10y_yield_pct": 4.25,
            "cot_leveraged_long_pct": 52.0,
        },
        "macro_narrative": "Pasar merepricing ekspektasi suku bunga pasca rilis Core PCE yang lebih rendah. Probabilitas Hike turun 10% menjadi 37.1%.",
        "currency_bias": {
            "USD": "bearish",
            "EUR": "bullish",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "bullish",
        },
        "invalidation_conditions": {
            "USD": "Bias USD bearish batal jika DXY D1 close di atas 103.50 atau yield 10Y naik melampaui 4.50%",
            "EUR": "Bias EUR bullish batal jika EURUSD menembus support kunci di 1.0850 dengan volume tinggi",
            "XAU": "Bias XAU bullish batal jika emas breakdown di bawah 2620.00 USD akibat lonjakan yield riil",
        },
        "currency_confidence": {
            "USD": 0.75,
            "EUR": 0.70,
            "XAU": 0.80,
        },
        "risk_sentiment": "risk-on",
        "macro_regime": "disinflation_growth",
        "confidence": 0.75,
        "priced_in_assessment": {
            "dominant_driver": "Fed Rate Cut Expectations post PCE",
            "priced_in_score": 6,
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": 52.0,
            "retail_sentiment_percentile": 48.0,
            "fedwatch_shift_summary": "Hike odds 37.1% vs 47.1% pre-PCE (-10.0%)",
        },
        "strongest_counter_thesis": "Jika rilis data ketenagakerjaan NFP mendatang melonjak di atas 250k, ekspektasi pemotongan suku bunga Fed akan dibatalkan seketika dan memicu rebound tajam dolar.",
    }

    brief = SubmitFundamentalBriefSchema.model_validate(valid_payload)
    assert brief.key_data_points_used.fedwatch_repricing_delta_pct == -10.0
    assert brief.priced_in_assessment.fedwatch_shift_summary == "Hike odds 37.1% vs 47.1% pre-PCE (-10.0%)"


# ==============================================================================
# 11. Stage 1 to Stage 2 Repricing Inheritance Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_stage1_to_stage2_repricing_inheritance():
    """Verify Stage 2's get_fundamental_brief preserves and returns FedWatch repricing shift fields."""
    from analysis.tools.executor import ToolExecutor
    from database.models import FundamentalBrief

    now = datetime(2026, 9, 30, 16, 0, 0, tzinfo=timezone.utc)
    mock_brief_row = FundamentalBrief(
        id=42,
        generated_at=now,
        valid_until=now + timedelta(hours=12),
        content_markdown="Macro analysis narrative with PCE Fed repricing.",
        confidence=0.75,
        risk_sentiment="risk-on",
        structured_json=json.dumps({
            "generated_at": now.isoformat(),
            "macro_narrative": "Probabilitas Hike turun dari 47.1% ke 37.1% pasca Core PCE.",
            "currency_bias": {"USD": "bearish", "EUR": "bullish", "XAU": "bullish"},
            "currency_confidence": {"USD": 0.75, "EUR": 0.70, "XAU": 0.80},
            "key_data_points_used": {
                "dxy_trend_5d": "-0.4%",
                "vix_close": 15.5,
                "fedwatch_dominant_pct": 62.9,
                "fedwatch_repricing_delta_pct": -10.0,
            },
            "priced_in_assessment": {
                "dominant_driver": "Fed Rate Cut Expectations post PCE",
                "priced_in_score": 6,
                "sell_the_news_risk": "medium",
                "fedwatch_shift_summary": "Hike odds 37.1% vs 47.1% pre-PCE (-10.0%)",
            },
        }),
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_brief_row
    mock_session.execute = AsyncMock(return_value=mock_res)

    executor = ToolExecutor(session=mock_session, settings={})
    brief_data = await executor._tool_get_fundamental_brief({})

    assert brief_data["brief_id"] == 42
    assert "key_data_points_used" in brief_data
    assert brief_data["key_data_points_used"]["fedwatch_repricing_delta_pct"] == -10.0
    assert "priced_in_assessment" in brief_data
    assert brief_data["priced_in_assessment"]["fedwatch_shift_summary"] == "Hike odds 37.1% vs 47.1% pre-PCE (-10.0%)"


