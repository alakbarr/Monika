import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from monika.application.analysis.calculators.confluence_calculator import calculate_confluence
from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from monika.application.analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_confluence_calculator_regime_b_breakout_verified():
    """Verify that Regime B breakout factors are deterministically verified and awarded."""
    mock_session = AsyncMock()

    # Mock ADR context
    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={
                "target_tp_min_distance": 0.0030,
                "target_tp_max_distance": 0.0080,
                "target_sl_max_distance": 0.0035,
            },
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
    ):
        # Test calculation with explicit Regime B factor claims
        factors = ["breakout_expansion", "volume_expansion", "trend_continuation", "momentum_expansion"]

        # Mock database rows for technical indicators and prices
        class MockRow:
            def __init__(self, val_dict, vol=150.0):
                import json
                from datetime import datetime, timezone

                self.value_json = json.dumps(val_dict)
                self.close = 1.1000
                self.high = 1.1050
                self.low = 1.0950
                self.volume = vol
                self.report_date = None
                self.price_low = 1.0950
                self.price_high = 1.1050
                self.timestamp = datetime.now(timezone.utc)
                self.structured_json = None
                self.direction = "bullish"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MockRow({"value": 1.1000, "atr": 0.0020, "rsi": 62.0})
        # Set first bar volume higher to trigger volume expansion
        h4_bars = [MockRow({"value": 1.1000}, vol=300.0)] + [MockRow({"value": 1.1000}, vol=150.0) for _ in range(9)]
        mock_result.scalars.return_value.all.return_value = h4_bars
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        res = await calculate_confluence(
            session=mock_session,
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1200,  # higher than prior bars
            sl=1.1160,
            tp=1.1280,
            settings={},
            confluence_factors=factors,
        )

        assert "computed_score" in res
        # Score must contain deterministic points for verified breakout factors
        assert res["computed_score"] >= 4


@pytest.mark.asyncio
async def test_signal_arbitrator_neutral_timesfm_preserves_llm_wait():
    """Without TimesFM directional confirmation the LLM wait stance must be preserved."""
    quant_signal = EdgeSignal(
        strategy_id="tokyo_open_sweep",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=155.20,
        stop_loss=154.80,
        take_profit=156.40,
        factor_family="mean_reversion",
    )

    arb = SignalArbitrator(settings={})
    mock_db = MagicMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin_nested.return_value = mock_nested
    res = await arb.arbitrate(
        session=mock_db,
        symbol="USDJPY",
        llm_decision={"decision": "wait", "confidence": 0.50},
        llm_confidence=0.50,
        quant_signal=quant_signal,
        macro_brief=None,
        timesfm_skew=0.0,  # Neutral / offline TimesFM
    )

    assert isinstance(res, ArbitrationResult)
    assert res.decision == "wait", (
        f"Arbitration reason: {res.arbitration_reason}, selected: {res.selected_source}, meta: {res.meta}"
    )
    assert res.risk_multiplier == 0.0


@pytest.mark.asyncio
async def test_confluence_calculator_h4_structure_overrides_stale_d1_and_separates_directions():
    """Verify H4 structure break overrides lagging opposite D1 structure break and separates pre-hoc buy/sell scores."""
    mock_session = AsyncMock()
    as_of = datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)

    class _SB:
        def __init__(self, direction: str):
            self.direction = direction

    def _exec_side_effect(stmt):
        q = str(stmt)
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        res.scalars.return_value.first.return_value = None
        if "structure_breaks" in q:
            if not getattr(_exec_side_effect, "sb_called", False):
                _exec_side_effect.sb_called = True
                # First StructureBreak query is D1 (stale bearish)
                res.scalars.return_value.first.return_value = _SB("bearish")
            else:
                # Second StructureBreak query is H4 (fresh bullish shift)
                res.scalars.return_value.first.return_value = _SB("bullish")
        return res

    mock_session.execute = AsyncMock(side_effect=_exec_side_effect)

    sig_buy = EdgeSignal(
        strategy_id="smc_fvg_trend_confluence",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.88,
    )
    sig_sell_weak = EdgeSignal(
        strategy_id="minor_counter",
        symbol="GBPUSD",
        direction="sell",
        valid=True,
        confidence=0.58,
    )

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={
                "target_tp_min_distance": 0.0030,
                "target_tp_max_distance": 0.0080,
                "target_sl_max_distance": 0.0035,
            },
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
        patch(
            "monika.application.analysis.strategies.registry.StrategyRegistry.evaluate_all",
            new_callable=AsyncMock,
            return_value=[sig_buy, sig_sell_weak],
        ),
    ):
        res = await calculate_confluence(
            session=mock_session,
            symbol="GBPUSD",
            entry_price=1.3250,
            settings={},
            as_of=as_of,
        )
        assert res["buy_potential_score"] > res["sell_potential_score"]
        assert res["directional_separation"] >= 3
        assert res["dominant_direction"] == "buy"


@pytest.mark.asyncio
async def test_cot_alignment_and_priced_in_subscores_full_coverage(db_session):
    """Cover _get_cot_alignment_value and calculate_priced_in_subscores across all branches."""
    from datetime import timedelta
    from monika.application.analysis.calculators.confluence_calculator import (
        _get_cot_alignment_value,
        calculate_priced_in_subscores,
    )
    from monika.infrastructure.database.models import (
        COTReport,
        FedWatchProbability,
        PriceOHLCV,
        TechnicalIndicator,
    )

    as_of = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)

    # 1. Unknown symbol returns None
    assert await _get_cot_alignment_value(db_session, "UNKNOWN_ASSET", as_of=as_of) is None
    # Empty DB returns None
    assert await _get_cot_alignment_value(db_session, "EURUSD", as_of=as_of) is None

    # 2. Stale COT report (> 10 days old, naive datetime) returns None
    stale_cot = COTReport(
        report_date=datetime(2026, 9, 1, 0, 0),  # naive
        market_code="099741",  # EUR
        dealer_long=100,
        dealer_short=100,
        asset_mgr_long=100,
        asset_mgr_short=100,
        leveraged_long=500,
        leveraged_short=500,
    )
    db_session.add(stale_cot)
    await db_session.commit()
    assert await _get_cot_alignment_value(db_session, "EURUSD", as_of=as_of) is None

    # 3. Fresh COT with total == 0 returns None
    zero_cot = COTReport(
        report_date=datetime(2026, 10, 13, 0, 0),
        market_code="099741",
        dealer_long=0,
        dealer_short=0,
        asset_mgr_long=0,
        asset_mgr_short=0,
        leveraged_long=0,
        leveraged_short=0,
    )
    db_session.add(zero_cot)
    await db_session.commit()
    assert await _get_cot_alignment_value(db_session, "EURUSD", as_of=as_of) is None

    # 4. Fresh COT with extreme long positioning + priced-in subscores (FedWatch >85, >70, >50, corrupt; COT fresh/stale; Momentum >5, >3, >2, corrupt)
    extreme_cot = COTReport(
        report_date=datetime(2026, 10, 14, 0, 0),
        market_code="099741",
        dealer_long=100,
        dealer_short=100,
        asset_mgr_long=100,
        asset_mgr_short=100,
        leveraged_long=950,
        leveraged_short=50,
    )
    fw_high = FedWatchProbability(
        meeting_date="2026-11-01",
        probabilities_json='{"probabilities": {"hold": 90.0}}',
        fetched_at=as_of - timedelta(hours=1),
    )
    atr_scalar = TechnicalIndicator(
        symbol="EURUSD",
        timeframe="D1",
        indicator_name="ATR_14",
        timestamp=as_of - timedelta(hours=2),
        value_json="0.0100",
    )
    # 20 D1 bars with range 0.0600 -> ratio = 6.0 (> 5 -> momentum = 3)
    d1_bars = [
        PriceOHLCV(
            symbol="EURUSD",
            timeframe="D1",
            timestamp=as_of - timedelta(days=i + 1),
            open=1.1000,
            high=1.1600 if i == 0 else 1.1100,
            low=1.1000,
            close=1.1050,
            volume=1000.0,
        )
        for i in range(20)
    ]
    db_session.add_all([extreme_cot, fw_high, atr_scalar, *d1_bars])
    await db_session.commit()

    cot_val = await _get_cot_alignment_value(db_session, "EURUSD", as_of=as_of)
    assert cot_val in (-1, 0, 1)

    sub1 = await calculate_priced_in_subscores(db_session, "EURUSD", as_of=as_of)
    assert sub1["fedwatch"] == 3
    assert sub1["cot"] == 3
    assert sub1["momentum"] == 3

    # Test FedWatch >70 (nested dict format), COT non-extreme ratio >0.3, Momentum >3 (dict ATR)
    fw_mid = FedWatchProbability(
        meeting_date="2026-11-01",
        probabilities_json='{"cut_25": {"probability": 75.0}}',
        fetched_at=as_of,
    )
    mod_cot = COTReport(
        report_date=datetime(2026, 10, 14, 12, 0),
        market_code="099741",
        dealer_long=100,
        dealer_short=100,
        asset_mgr_long=100,
        asset_mgr_short=100,
        leveraged_long=680,
        leveraged_short=320,  # 68% -> non-extreme, ratio = 360/1000 = 0.36 > 0.3
    )
    atr_dict = TechnicalIndicator(
        symbol="EURUSD",
        timeframe="D1",
        indicator_name="ATR_14",
        timestamp=as_of,
        value_json='{"atr": 0.0150}',  # run_up 0.0600 / 0.0150 = 4.0 (> 3 -> momentum = 2)
    )
    db_session.add_all([fw_mid, mod_cot, atr_dict])
    await db_session.commit()
    sub2 = await calculate_priced_in_subscores(db_session, "EURUSD", as_of=as_of)
    assert sub2["fedwatch"] == 2
    assert sub2["cot"] == 1
    assert sub2["momentum"] == 2

    # Test FedWatch >50, COT >7 days old, Momentum >2
    as_of_later = as_of + timedelta(days=10)
    fw_low = FedWatchProbability(
        meeting_date="2026-11-01",
        probabilities_json='{"hold": 55.0}',
        fetched_at=as_of_later,
    )
    atr_low = TechnicalIndicator(
        symbol="EURUSD",
        timeframe="D1",
        indicator_name="ATR_14",
        timestamp=as_of_later,
        value_json='{"atr": 0.0240}',  # run_up 0.0600 / 0.0240 = 2.5 (> 2 -> momentum = 1)
    )
    db_session.add_all([fw_low, atr_low])
    await db_session.commit()
    sub3 = await calculate_priced_in_subscores(db_session, "EURUSD", as_of=as_of_later)
    assert sub3["fedwatch"] == 1
    assert sub3["cot"] == 0
    assert sub3["momentum"] == 1

    # Test corrupt JSON in FedWatch and ATR
    as_of_corrupt = as_of_later + timedelta(days=1)
    fw_bad = FedWatchProbability(
        meeting_date="2026-11-01",
        probabilities_json="{bad_json",
        fetched_at=as_of_corrupt,
    )
    atr_bad = TechnicalIndicator(
        symbol="EURUSD",
        timeframe="D1",
        indicator_name="ATR_14",
        timestamp=as_of_corrupt,
        value_json="{bad_json",
    )
    db_session.add_all([fw_bad, atr_bad])
    await db_session.commit()
    sub4 = await calculate_priced_in_subscores(db_session, "EURUSD", as_of=as_of_corrupt)
    assert sub4["fedwatch"] == 0
    assert sub4["momentum"] == 0


@pytest.mark.asyncio
async def test_calculate_confluence_comprehensive_branches(db_session):
    """Cover all remaining branches in calculate_confluence (SMC proximity, OTE, VIX, FundamentalBrief, DXY, VPIN, PatternCache, RSI/ADR issues)."""
    import json
    from datetime import timedelta
    import monika.core.primitives.clock as clock
    from monika.infrastructure.database.models import (
        COTReport,
        DXYData,
        FundamentalBrief,
        FVGZone,
        OrderBlock,
        PatternScreeningCache,
        PriceOHLCV,
        SRZone,
        StructureBreak,
        SwingPoint,
        TechnicalIndicator,
        VIXData,
    )

    as_of = datetime(2026, 10, 15, 8, 15, tzinfo=timezone.utc)  # 08:15 UTC -> is_london_open_spike
    h4_ts = as_of - timedelta(hours=5)

    # Seed indicators: scalar ATR_14, RSI_14 (25.0 oversold), EMA_20, EMA_50, ORDER_FLOW_SNAPSHOT (vpin < 0.50)
    db_session.add_all(
        [
            TechnicalIndicator(
                symbol="EURUSD", timeframe="H4", indicator_name="ATR_14", timestamp=h4_ts, value_json="0.0020"
            ),
            TechnicalIndicator(
                symbol="EURUSD", timeframe="H4", indicator_name="RSI_14", timestamp=h4_ts, value_json='{"rsi": 25.0}'
            ),
            TechnicalIndicator(
                symbol="EURUSD", timeframe="H4", indicator_name="EMA_20", timestamp=h4_ts, value_json='{"ema": 1.0900}'
            ),
            TechnicalIndicator(
                symbol="EURUSD", timeframe="H4", indicator_name="EMA_50", timestamp=h4_ts, value_json='{"ema": 1.0950}'
            ),
            TechnicalIndicator(
                symbol="EURUSD",
                timeframe="H1",
                indicator_name="ORDER_FLOW_SNAPSHOT",
                timestamp=h4_ts,
                value_json='{"vpin": 0.30}',
            ),
            # 6 H4 bars
            *[
                PriceOHLCV(
                    symbol="EURUSD",
                    timeframe="H4",
                    timestamp=h4_ts - timedelta(hours=4 * i),
                    open=1.0950,
                    high=1.1000,
                    low=1.0900,
                    close=1.0930,
                    volume=100.0,
                )
                for i in range(6)
            ],
            # D1 & H4 aligned structure breaks
            StructureBreak(
                symbol="EURUSD",
                timeframe="D1",
                type="BOS",
                direction="bullish",
                price=1.0950,
                formed_at=as_of - timedelta(days=2),
            ),
            StructureBreak(
                symbol="EURUSD",
                timeframe="H4",
                type="BOS",
                direction="bullish",
                price=1.0940,
                formed_at=h4_ts,
            ),
            # Aligned & unaligned FVG and OB
            FVGZone(
                symbol="EURUSD",
                timeframe="H4",
                direction="bearish",
                gap_low=1.0925,
                gap_high=1.0935,
                formed_at=h4_ts,
                filled_at=None,
            ),
            FVGZone(
                symbol="EURUSD",
                timeframe="H4",
                direction="bullish",
                gap_low=1.0925,
                gap_high=1.0935,
                formed_at=h4_ts,
                filled_at=None,
            ),
            OrderBlock(
                symbol="EURUSD",
                timeframe="H4",
                direction="bearish",
                price_low=1.0925,
                price_high=1.0935,
                formed_at=h4_ts,
                mitigated_at=None,
            ),
            OrderBlock(
                symbol="EURUSD",
                timeframe="H4",
                direction="bullish",
                price_low=1.0925,
                price_high=1.0935,
                formed_at=h4_ts,
                mitigated_at=None,
            ),
            # SRZone near 1.0930
            SRZone(
                symbol="EURUSD",
                timeframe="H4",
                price_low=1.0928,
                price_high=1.0932,
                strength=3,
                last_touched=h4_ts,
            ),
            # 2 SwingPoints for OTE: high=1.1000, low=1.0900 -> for buy at 1.0930, fib = (1.1000-1.0930)/0.0100 = 0.70 (in OTE!)
            SwingPoint(
                symbol="EURUSD",
                timeframe="H4",
                type="high",
                price=1.1000,
                timestamp=datetime(2026, 10, 14, 0, 0),  # naive within 14d
            ),
            SwingPoint(
                symbol="EURUSD",
                timeframe="H4",
                type="low",
                price=1.0900,
                timestamp=datetime(2026, 10, 13, 0, 0),
            ),
            # VIX < 20
            VIXData(date=datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc), close=15.0),
            # 5 DXY rows strengthening (dxy[0].close > dxy[4].close)
            *[
                DXYData(
                    date=datetime(2026, 10, 14 - i, 0, 0, tzinfo=timezone.utc),
                    close=105.0 - i * 0.5,
                )
                for i in range(5)
            ],
            # COTReport fresh extreme short (leveraged_long=50, leveraged_short=950 -> cot_alignment_val = -1 favors buy)
            COTReport(
                report_date=as_of - timedelta(days=2),
                market_code="099741",
                dealer_long=100,
                dealer_short=100,
                asset_mgr_long=100,
                asset_mgr_short=100,
                leveraged_long=50,
                leveraged_short=950,
            ),
            # FundamentalBrief with per_asset_macro_matrix strong_bullish
            FundamentalBrief(
                generated_at=h4_ts,
                content_markdown="Bullish EUR",
                structured_json=json.dumps(
                    {"per_asset_macro_matrix": {"EURUSD": {"directional_bias": "strong_bullish"}}}
                ),
            ),
            # PatternScreeningCache aligned
            PatternScreeningCache(
                symbol="EURUSD",
                screened_at=h4_ts,
                overall_bias="bullish",
                confidence="high",
            ),
        ]
    )
    await db_session.commit()

    adr_mock = {
        "target_tp_min_distance": 0.0050,
        "target_tp_max_distance": 0.0080,
        "target_sl_max_distance": 0.0035,
    }
    sig_invalid = EdgeSignal(strategy_id="inv", symbol="EURUSD", direction="buy", valid=False, confidence=0.9)
    sig_valid = EdgeSignal(strategy_id="val", symbol="EURUSD", direction="buy", valid=True, confidence=0.8)

    with (
        clock.frozen_time(as_of),
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value=adr_mock,
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": True, "valid_for_direction": "buy"},
        ),
        patch(
            "monika.application.analysis.strategies.registry.StrategyRegistry.evaluate_all",
            new_callable=AsyncMock,
            return_value=[sig_invalid, sig_valid],
        ),
    ):
        # 1. BUY with tight SL (<0.7x ATR), low RR, TP below band, London open spike
        res_buy = await calculate_confluence(
            db_session,
            "EURUSD",
            direction="buy",
            entry_price=1.0930,
            sl=1.0920,  # dist 0.0010 = 0.5x ATR (< 0.7x)
            tp=1.0935,  # dist 0.0005 -> RR = 0.5 (< 1.2) and TP < 0.0050*0.9
            settings={},
            as_of=as_of,
            confluence_factors=["breakout_expansion", "volume_expansion", "trend_continuation", "momentum_expansion"],
        )
        assert res_buy["computed_score"] > 5
        assert any("R:R ratio too low" in i for i in res_buy["blocking_issues"])
        assert any("SL too tight" in i for i in res_buy["blocking_issues"])
        assert any("TP below intraday-range" in i for i in res_buy["blocking_issues"])

        # 2. SELL at 1.0970 (in OTE for sell: (1.0970-1.0900)/0.01 = 0.70), marginally tight SL (0.85x ATR), TP above band, SL > max ADR
        res_sell = await calculate_confluence(
            db_session,
            "EURUSD",
            direction="sell",
            entry_price=1.0970,
            sl=1.1010,  # dist 0.0040 > 0.0035*1.1 (SL exceeds ADR max)
            tp=1.0850,  # dist 0.0120 > 0.0080*1.1 (TP above band)
            settings={
                "trading": {"risk": {"intraday_min_sl_atr_multiplier": 2.2}}
            },  # 0.0040/0.0020 = 2.0x < 2.2x (marginally tight)
            as_of=as_of.replace(hour=10, minute=0),  # 10:00 UTC standard London
        )
        assert any("RSI oversold" in i for i in res_sell["blocking_issues"])
        assert any("SL marginally tight" in i for i in res_sell["blocking_issues"])
        assert any("TP above intraday-range" in i for i in res_sell["blocking_issues"])
        assert any("SL exceeds intraday-range" in i for i in res_sell["blocking_issues"])

        # 3. Pre-hoc mode without entry_price (fetches last_price_row from PriceOHLCV) at off-peak 22:00 UTC
        res_prehoc = await calculate_confluence(
            db_session,
            "EURUSD",
            direction=None,
            entry_price=None,
            settings={},
            as_of=as_of.replace(hour=22, minute=0),
        )
        assert res_prehoc["reference_price"] == pytest.approx(1.0930)


@pytest.mark.asyncio
async def test_calculate_confluence_macro_currency_fallbacks_and_error_paths(db_session):
    """Cover RSI >70, VIX >=30, DXY weakening, VPIN >0.70 / bias fallback, currency_bias (XTIUSD/XAUUSD), and exception handlers."""
    import json
    from datetime import timedelta
    from monika.infrastructure.database.models import (
        DXYData,
        FundamentalBrief,
        PriceOHLCV,
        TechnicalIndicator,
        VIXData,
    )

    as_of = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
    h4_ts = as_of - timedelta(hours=5)

    # Seed corrupt indicators for XTIUSD to hit JSON exception blocks + VIX >= 30 + weakening DXY + VPIN > 0.70
    db_session.add_all(
        [
            TechnicalIndicator(
                symbol="XTIUSD", timeframe="H4", indicator_name="ATR_14", timestamp=h4_ts, value_json='{"atr": 1.0}'
            ),
            TechnicalIndicator(
                symbol="XTIUSD", timeframe="H4", indicator_name="RSI_14", timestamp=h4_ts, value_json='{"rsi": 75.0}'
            ),
            TechnicalIndicator(
                symbol="XTIUSD", timeframe="H4", indicator_name="EMA_20", timestamp=h4_ts, value_json="{bad"
            ),
            TechnicalIndicator(
                symbol="XTIUSD", timeframe="H4", indicator_name="EMA_50", timestamp=h4_ts, value_json="{bad"
            ),
            TechnicalIndicator(
                symbol="XTIUSD",
                timeframe="H1",
                indicator_name="ORDER_FLOW_SNAPSHOT",
                timestamp=h4_ts,
                value_json='{"vpin": 0.85}',
            ),
            VIXData(date=datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc), close=35.0),
            # 5 DXY rows weakening (latest 100.0 < oldest 104.0)
            *[
                DXYData(
                    date=datetime(2026, 10, 19 - i, 0, 0, tzinfo=timezone.utc),
                    close=100.0 + i * 1.0,
                )
                for i in range(5)
            ],
            FundamentalBrief(
                generated_at=h4_ts,
                content_markdown="Oil strong bull",
                structured_json=json.dumps({"currency_bias": {"OIL": "strong_bullish", "USD": "strong_bearish"}}),
            ),
            *[
                PriceOHLCV(
                    symbol="XTIUSD",
                    timeframe="H4",
                    timestamp=h4_ts - timedelta(hours=4 * i),
                    open=70.0,
                    high=71.0,
                    low=69.0,
                    close=70.0,
                    volume=100.0,
                )
                for i in range(6)
            ],
        ]
    )
    await db_session.commit()

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={
                "target_tp_min_distance": 1.0,
                "target_tp_max_distance": 3.0,
                "target_sl_max_distance": 1.5,
            },
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
        patch(
            "monika.application.analysis.strategies.registry.StrategyRegistry.evaluate_all",
            new_callable=AsyncMock,
            side_effect=RuntimeError("quant error"),
        ),
    ):
        # BUY on XTIUSD: RSI=75 overbought issue, VIX=35 issue, VPIN=0.85 issue, OIL strong_bullish (+3), DXY weakening (+1)
        res_oil_buy = await calculate_confluence(
            db_session,
            "XTIUSD",
            direction="buy",
            entry_price=70.0,
            sl=69.0,
            tp=72.0,
            as_of=as_of,
        )
        assert any("RSI overbought" in i for i in res_oil_buy["blocking_issues"])
        assert any("VIX=35.0 >= 30" in i for i in res_oil_buy["blocking_issues"])
        assert any("Toxic informed flow" in i for i in res_oil_buy["blocking_issues"])

        # SELL on XTIUSD: RSI=75 overbought bonus (+1), net_diff <= -2 when inverted, breakout sell check
        res_oil_sell = await calculate_confluence(
            db_session,
            "XTIUSD",
            direction="sell",
            entry_price=68.0,
            sl=69.0,
            tp=66.0,
            as_of=as_of,
        )
        assert "computed_score" in res_oil_sell

    # Test XAUUSD currency_bias ("GOLD": "bullish", net_diff=1) + ORDER_FLOW_SNAPSHOT bias fallback + RSI=50 + as_of=None
    as_of_gold = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            TechnicalIndicator(
                symbol="XAUUSD", timeframe="H4", indicator_name="RSI_14", timestamp=as_of_gold, value_json="{bad"
            ),
            TechnicalIndicator(
                symbol="XAUUSD",
                timeframe="H1",
                indicator_name="ORDER_FLOW_SNAPSHOT",
                timestamp=as_of_gold,
                value_json='{"bias": "bullish"}',
            ),
            FundamentalBrief(
                generated_at=as_of_gold,
                content_markdown="Gold bull",
                structured_json=json.dumps({"currency_bias": {"GOLD": "bullish", "USD": "neutral"}}),
            ),
        ]
    )
    await db_session.commit()

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={"error": "no adr"},
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
        patch("monika.core.primitives.clock.get_simulated_now", return_value=None),
    ):
        res_gold = await calculate_confluence(db_session, "XAUUSD", direction=None, entry_price=2000.0)
        assert res_gold["buy_potential_score"] >= 2

    # Test FundamentalBrief per_asset_macro_matrix strong_bearish, currency_bias net_diff = -1 & -2, and corrupt brief JSON + corrupt OF JSON
    as_of_bear = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            TechnicalIndicator(
                symbol="XAUUSD",
                timeframe="H1",
                indicator_name="ORDER_FLOW_SNAPSHOT",
                timestamp=as_of_bear,
                value_json="{bad_of_json",
            ),
            FundamentalBrief(
                generated_at=as_of_bear,
                content_markdown="Gold strong bear",
                structured_json=json.dumps(
                    {"per_asset_macro_matrix": {"XAUUSD": {"directional_bias": "strong_bearish"}}}
                ),
            ),
        ]
    )
    await db_session.commit()
    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={"error": "no adr"},
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
    ):
        res_bear = await calculate_confluence(
            db_session, "XAUUSD", direction="sell", entry_price=2000.0, as_of=as_of_bear
        )
        assert res_bear["computed_score"] >= 3

    # Cover remaining 9 lines: L407-408 (PatternScreeningCache error), L449 (40<=RSI<=60), L683 (breakout_expansion failed), L761 (missing USD in currency_bias), L792 (net_diff <= -2), L794 (net_diff <= -1), L795-796 (corrupt brief JSON)
    as_of_rem = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)
    h4_rem = as_of_rem - timedelta(hours=5)
    db_session.add_all(
        [
            TechnicalIndicator(
                symbol="GBPUSD", timeframe="H4", indicator_name="RSI_14", timestamp=h4_rem, value_json='{"rsi": 50.0}'
            ),
            *[
                PriceOHLCV(
                    symbol="GBPUSD",
                    timeframe="H4",
                    timestamp=h4_rem - timedelta(hours=4 * i),
                    open=1.3000,
                    high=1.3100,
                    low=1.2900,
                    close=1.3000,
                    volume=100.0,
                )
                for i in range(6)
            ],
            FundamentalBrief(
                generated_at=h4_rem,
                content_markdown="GBP bear, no USD key",
                structured_json=json.dumps({"currency_bias": {"GBP": "bearish"}}),
            ),
        ]
    )
    await db_session.commit()

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={"error": "no adr"},
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
    ):
        res_gbp = await calculate_confluence(
            db_session,
            "GBPUSD",
            direction="sell",
            entry_price=1.3000,  # inside [1.2900, 1.3100], so breakout_expansion fails -> hits L683
            as_of=as_of_rem,
            confluence_factors=["breakout_expansion"],
        )
        assert any("breakout_expansion factor claimed" in i for i in res_gbp["blocking_issues"])

        # Strong bearish currency_bias (net_diff = -2 -> L792)
        as_of_rem2 = as_of_rem + timedelta(days=1)
        db_session.add(
            FundamentalBrief(
                generated_at=as_of_rem2,
                content_markdown="GBP strong bear",
                structured_json=json.dumps({"currency_bias": {"GBP": "strong_bearish"}}),
            )
        )
        await db_session.commit()
        res_gbp2 = await calculate_confluence(
            db_session, "GBPUSD", direction="sell", entry_price=1.3000, as_of=as_of_rem2
        )
        assert res_gbp2["computed_score"] >= 3

        # Corrupt FundamentalBrief structured_json (L795-796) + PatternScreeningCache query error (L407-408)
        as_of_rem3 = as_of_rem2 + timedelta(days=1)
        db_session.add(
            FundamentalBrief(
                generated_at=as_of_rem3,
                content_markdown="Corrupt brief",
                structured_json="{not_valid_json",
            )
        )
        await db_session.commit()

        orig_execute = db_session.execute

        async def _exec_pat_err(stmt, *a, **kw):
            if "pattern_screening_cache" in str(stmt):
                raise RuntimeError("pattern cache db error")
            return await orig_execute(stmt, *a, **kw)

        with patch.object(db_session, "execute", side_effect=_exec_pat_err):
            res_gbp3 = await calculate_confluence(
                db_session, "GBPUSD", direction="sell", entry_price=1.3000, as_of=as_of_rem3
            )
            assert "computed_score" in res_gbp3
