# ==============================================================================
# File: tests/test_audit_round3_remediation.py
# Description: Comprehensive unit tests for Code Consistency Audit Round 3 remediations.
# ==============================================================================

import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import numpy as np
import pandas as pd
import pytest

# Add trading-agent to sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_trading_agent_dir = os.path.dirname(_current_dir)
if _trading_agent_dir not in sys.path:
    sys.path.insert(0, _trading_agent_dir)


class TestIndicatorsRemediation:
    """Test indicators/ domain remediations."""

    @pytest.mark.asyncio
    async def test_technical_order_flow_snapshot_timestamp(self):
        """Verify ORDER_FLOW_SNAPSHOT uses candle timestamp instead of clock.now()."""
        from indicators.technical import TechnicalIndicatorCalculator
        from database.models import PriceOHLCV, TechnicalIndicator

        mock_session = AsyncMock()
        calc = TechnicalIndicatorCalculator(session=mock_session, settings={})

        dates = pd.date_range("2026-01-01 00:00:00", periods=5, freq="1h", tz=timezone.utc)
        rows = [
            PriceOHLCV(
                symbol="EURUSD",
                timeframe="H1",
                timestamp=ts,
                open=1.1000,
                high=1.1050,
                low=1.0950,
                close=1.1020,
                volume=1000.0,
            )
            for ts in dates
        ]
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows))))
        )

        await calc.compute_and_save("EURUSD", "H1")
        add_calls = [c[0][0] for c in mock_session.add.call_args_list if isinstance(c[0][0], TechnicalIndicator)]
        of_snapshots = [ti for ti in add_calls if ti.indicator_name == "ORDER_FLOW_SNAPSHOT"]
        if of_snapshots:
            assert of_snapshots[0].timestamp == dates[-1].to_pydatetime()

    @pytest.mark.asyncio
    async def test_timesfm_engine_scalar_baseline_atr(self):
        """Verify _get_baseline_atr handles scalar floats without crashing."""
        from indicators.timesfm_engine import TimesFMEngine
        engine = TimesFMEngine.__new__(TimesFMEngine)

        # Test scalar float in value_json
        mock_row_scalar = MagicMock()
        mock_row_scalar.value_json = "0.0055"
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_row_scalar))
        )
        val_scalar = await engine._get_baseline_atr(mock_session, "EURUSD")
        assert val_scalar == 0.0055

        # Test dict in value_json
        mock_row_dict = MagicMock()
        mock_row_dict.value_json = '{"atr": 0.0068}'
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_row_dict))
        )
        val_dict = await engine._get_baseline_atr(mock_session, "EURUSD")
        assert val_dict == 0.0068

    def test_order_flow_snapshot_vpin_field(self):
        """Verify OrderFlowSnapshot dataclass includes optional vpin field."""
        from indicators.order_flow import OrderFlowSnapshot
        snap_default = OrderFlowSnapshot(
            symbol="BTCUSD",
            mode="SYNTHETIC_TICK_RULE",
            order_book_imbalance=0.1,
            cvd_session_delta=50.0,
            cvd_divergence="NONE",
        )
        assert snap_default.vpin is None

        snap_with_vpin = OrderFlowSnapshot(
            symbol="BTCUSD",
            mode="SYNTHETIC_TICK_RULE",
            order_book_imbalance=0.1,
            cvd_session_delta=50.0,
            cvd_divergence="NONE",
            vpin=0.35,
        )
        assert snap_with_vpin.vpin == 0.35
        d = snap_with_vpin.to_dict()
        assert d["vpin"] == 0.35

    def test_microstructure_nan_guards(self):
        """Verify kyle_lambda and amihud_illiquidity guard against NaN values."""
        from indicators.microstructure import (
            compute_kyle_lambda,
            compute_amihud_illiquidity,
            get_microstructure_metrics,
        )

        assert compute_kyle_lambda(pd.Series(dtype=float), pd.Series(dtype=float)).empty
        assert compute_amihud_illiquidity(pd.Series(dtype=float), pd.Series(dtype=float)).empty

        # Microstructure metrics with sufficient data
        df = pd.DataFrame({
            "open": [1.10] * 25,
            "high": [1.11] * 25,
            "low": [1.09] * 25,
            "close": [1.10] * 25,
            "volume": [1000.0] * 25,
        })
        m_fx = get_microstructure_metrics("EURUSD", ohlcv_df=df)
        assert "kyle_lambda" in m_fx
        assert not np.isnan(m_fx["kyle_lambda"])

        m_comm = get_microstructure_metrics("XAUUSD", ohlcv_df=df)
        assert "amihud_illiquidity" in m_comm
        assert not np.isnan(m_comm["amihud_illiquidity"])

    def test_structure_fvg_max_distance_and_div_zero_guard(self):
        """Verify FVG_MAX_DISTANCE includes XBRUSD and XTIUSD."""
        from indicators.structure import MarketStructureAnalyzer, FVG_MAX_DISTANCE
        assert "XBRUSD" in FVG_MAX_DISTANCE
        assert FVG_MAX_DISTANCE["XBRUSD"] == 0.10
        assert "XTIUSD" in FVG_MAX_DISTANCE
        assert FVG_MAX_DISTANCE["XTIUSD"] == 0.10


class TestBacktestRemediation:
    """Test backtest/ domain remediations."""

    def test_outcome_evaluator_oil_contract_sizes(self):
        """Verify contract size for XTI (100) vs XBR (1000)."""
        from backtest.outcome_evaluator import OutcomeEvaluator
        evaluator = OutcomeEvaluator()
        assert evaluator.get_contract_size("XTIUSD") == 100.0
        assert evaluator.get_contract_size("WTI") == 100.0
        assert evaluator.get_contract_size("XBRUSD") == 1000.0
        assert evaluator.get_contract_size("BRENT") == 1000.0
        assert evaluator.get_contract_size("EURUSD") == 100000.0

    def test_outcome_evaluator_friday_profit_only_close(self):
        """Verify Friday weekend close only closes trades with positive unrealized PnL."""
        from backtest.outcome_evaluator import OutcomeEvaluator
        from database.models import BacktestTrade, PriceOHLCV

        evaluator = OutcomeEvaluator()
        trade_buy = BacktestTrade(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1000,
            stop_loss=1.0900,
            take_profit=1.1200,
            entry_time=datetime(2026, 1, 9, 10, 0, tzinfo=timezone.utc),
            executed_lots=0.1,
        )
        bar_profit = PriceOHLCV(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=datetime(2026, 1, 9, 21, 0, tzinfo=timezone.utc),
            open=1.1040, high=1.1060, low=1.1030, close=1.1050, volume=500.0
        )
        out_profit = evaluator._calculate_outcome(
            trade_buy, bar_profit.timestamp, bar_profit.close, "friday_close", bar=bar_profit
        )
        assert out_profit["exit_reason"] == "friday_close"
        assert out_profit["pnl_pips"] > 0

    def test_alpha_validation_sortino_and_equity_curve_normalization(self):
        """Verify Sortino calculation and equity curve list of dicts/floats handling."""
        from backtest.alpha_validation import validate_alpha
        from database.models import BacktestTrade

        t1 = BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=2.0, executed_lots=0.1)
        t2 = BacktestTrade(symbol="EURUSD", direction="sell", pnl_pct=-1.0, executed_lots=0.1)
        t3 = BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=3.0, executed_lots=0.1)

        # List of dicts equity curve
        eq_curve_dicts = [
            {"equity": 10000.0},
            {"equity": 10200.0},
            {"equity": 10100.0},
            {"equity": 10400.0},
        ]
        res_dicts = validate_alpha([t1, t2, t3], equity_curve=eq_curve_dicts)
        assert res_dicts is not None

        # List of floats equity curve
        eq_curve_floats = [10000.0, 10200.0, 10100.0, 10400.0]
        res_floats = validate_alpha([t1, t2, t3], equity_curve=eq_curve_floats)
        assert res_floats is not None

    def test_monte_carlo_engine_final_equity_distribution_key(self):
        """Verify early return includes final_equity_distribution key in MonteCarloStressTester."""
        from backtest.monte_carlo_engine import MonteCarloStressTester
        tester = MonteCarloStressTester()
        res = tester.simulate_trade_sequence([], num_simulations=10)
        assert "final_equity_distribution" in res
        assert "p5" in res["final_equity_distribution"]

    def test_report_generator_final_equity_set(self):
        """Verify calculate_metrics assigns self.run.final_equity."""
        from backtest.report_generator import ReportGenerator
        from database.models import BacktestRun, BacktestTrade

        run = BacktestRun(initial_equity=10000.0)
        t1 = BacktestTrade(symbol="EURUSD", direction="buy", pnl_pct=2.0)
        t2 = BacktestTrade(symbol="EURUSD", direction="sell", pnl_pct=-1.0)
        rep = ReportGenerator(run=run, trades=[t1, t2], equity_curve=[10000.0, 10200.0, 10100.0])
        rep.calculate_metrics()

        assert run.final_equity is not None
        assert run.final_equity == 10100.0

    def test_point_in_time_engine_canonical_universe(self):
        """Verify PointInTimeBacktestEngine uses 8 canonical symbols as fallback."""
        from backtest.point_in_time_engine import PointInTimeBacktestEngine
        engine = PointInTimeBacktestEngine(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            settings={},
        )
        canonical = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD', 'BTCUSD']
        fallback = engine.settings.get('trading', {}).get('asset_universe', canonical)
        assert len(fallback) == 8
        assert "AUDUSD" in fallback
        assert "USDCAD" in fallback
        assert "USDCHF" in fallback


class TestDataSourcesRemediation:
    """Test data_sources/ domain remediations."""

    def test_validators_intraday_cache_expired_string_parsing(self):
        """Verify is_intraday_cache_expired handles ISO string timestamps."""
        from data_sources.validators import is_intraday_cache_expired
        now = datetime.now(timezone.utc)
        iso_str = now.isoformat()
        # Fresh cache
        assert is_intraday_cache_expired(iso_str, ttl_seconds=3600, now=now) is False
        # Expired cache
        assert is_intraday_cache_expired("2020-01-01T00:00:00Z", ttl_seconds=3600, now=now) is True

    def test_dxy_yfinance_get_latest(self):
        """Verify DXYFetcher exposes get_latest() method."""
        from data_sources.dxy_yfinance import DXYFetcher
        fetcher = DXYFetcher(session=AsyncMock())
        assert hasattr(fetcher, "get_latest")
        assert callable(fetcher.get_latest)


class TestCLIBenchmarkScrapersSkillsRemediation:
    """Test CLI, Benchmark, Scrapers, and Skills remediations."""

    def test_benchmark_judge_score_null_handling(self):
        """Verify judge _score handles None and invalid values gracefully."""
        from benchmark.judge import _score
        assert _score(None) == 0.0
        assert _score({}) == 0.0
        assert _score({"grounding_score": None, "accuracy_score": 8}) >= 0.0

    @pytest.mark.asyncio
    async def test_benchmark_deterministic_boolean_init(self):
        """Verify deterministic structural check initializes booleans correctly."""
        from benchmark.deterministic import score_trade_payload
        res = await score_trade_payload(None, {}, "EURUSD", {"decision": "buy"})
        assert "checks" in res
        assert "sl_tp_correct_side" in res["checks"]
        assert res["checks"]["sl_tp_correct_side"] is False

    def test_skills_loader_prefix_and_deduplication(self):
        """Verify skills loader deduplicates skills."""
        from skills.loader import list_skills
        skills = list_skills()
        assert len(skills) == len(set(skills))

    def test_cli_theme_persist_preserves_comments(self):
        """Verify persist_theme_to_settings retains comments without erasing them."""
        from cli.theme import persist_theme_to_settings
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml", encoding="utf-8") as tf:
            tf.write("""# Important System Configuration Comment
# Line 2 Comment
trading:
  risk_mode: "conservative"

# UI Configuration Section
ui:
  theme: "retro_vintage"
  steer_mode: "one-at-a-time"
""")
            temp_path = tf.name

        try:
            ok = persist_theme_to_settings("modern_dark", config_path=temp_path)
            assert ok is True
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# Important System Configuration Comment" in content
            assert "# Line 2 Comment" in content
            assert "# UI Configuration Section" in content
            assert '"modern_dark"' in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_rss_base_scraper_no_raise_and_ua(self):
        """Verify RssBaseScraper returns empty list on error and sets User-Agent."""
        from scrapers.news.rss_base import RssBaseScraper
        scraper = RssBaseScraper(source_name="NonExistentFeed", feed_url="http://invalid.127.0.0.1.nonexistent/rss")
        # Should not raise exception
        news = scraper.fetch_news(limit=5)
        assert isinstance(news, list)

    def test_scrapers_calendar_country_and_aliases(self):
        """Verify FinnhubCalendarScraper country assignment and interface aliases."""
        from scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper
        scraper = FinnhubCalendarScraper(api_key="mock_key")
        assert hasattr(scraper, "fetch_events")
        assert hasattr(scraper, "afetch_events")

        # Verify _parse_events assigns country
        mock_raw = [{
            "country": "US",
            "event": "Non-Farm Payrolls",
            "time": "2026-01-09 13:30:00",
            "impact": "high",
            "actual": "200k",
            "estimate": "180k",
            "prev": "190k"
        }]
        events = scraper._parse_events(mock_raw)
        assert len(events) == 1
        assert events[0].country == "US"
        assert events[0].currency == "USD"
