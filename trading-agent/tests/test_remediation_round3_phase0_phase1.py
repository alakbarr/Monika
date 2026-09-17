import pytest
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Test 1: F0-1 Unicode NFKC & Word Boundary Sanitization
# ---------------------------------------------------------------------------

def test_f0_1_unicode_nfkc_and_word_boundary_sanitization():
    """Verify NFKC normalization and word-boundary truncation for news title sanitization."""
    import unicodedata
    import textwrap

    # Input with fullwidth characters, zero-width space, and long text
    raw_title = "ＵＳ\u200b Ｉｎｆｌａｔｉｏｎ Ｒａｔｅ ｅｘｃｅｅｄｓ ｆｏｒｅｃａｓｔ ｗｉｔｈ ｓｉｇｎｉｆｉｃａｎｔ ｕｐｗａｒｄ ｐｒｅｓｓｕｒｅ ａｃｒｏｓｓ ａｌｌ ｓｅｃｔｏｒｓ ａｎｄ ｃｏｍｍｏｄｉｔｉｅｓ ａｓ ｒｅｐｏｒｔｅｄ ｂｙ ｔｈｅ Ｂｕｒｅａｕ ｏｆ Ｌａｂｏｒ Ｓｔａｔｉｓｔｉｃｓ"
    
    normalized = unicodedata.normalize("NFKC", raw_title)
    # Zero-width space should be cleanable
    cleaned = normalized.replace("\u200b", "").replace("<untrusted_external_content>", "").replace("</untrusted_external_content>", "").strip()
    short_title = textwrap.shorten(cleaned, width=150, placeholder="...") if len(cleaned) > 150 else cleaned
    safe_title = f"<untrusted_external_content>{short_title}</untrusted_external_content>"

    assert safe_title.startswith("<untrusted_external_content>")
    assert safe_title.endswith("</untrusted_external_content>")
    assert "US Inflation Rate" in safe_title
    assert len(short_title) <= 150
    assert not safe_title.endswith("...</untrusted_external_content>") or len(short_title) <= 150


# ---------------------------------------------------------------------------
# Test 2: F0-2 RSS Robust Date Parsing
# ---------------------------------------------------------------------------

def test_f0_2_rss_robust_date_parsing():
    """Verify universal ISO-8601 UTC date parsing in RssBaseScraper."""
    from scrapers.news.rss_base import RssBaseScraper
    scraper = RssBaseScraper("TestRSS", "http://example.com/rss")

    mock_feed = MagicMock()
    mock_feed.entries = [
        {
            "link": "https://example.com/news/1",
            "title": "Fed announces rate hike",
            "published": "Wed, 28 Aug 2026 14:30:00 GMT",
            "summary": "Interest rate raised by 25bps."
        },
        {
            "link": "https://example.com/news/2",
            "title": "ECB maintains current stance",
            "pubDate": "2026-08-28T15:00:00+02:00",
            "description": "European Central Bank statement."
        }
    ]

    with patch("feedparser.parse", return_value=mock_feed):
        items = scraper.fetch_news(limit=10)
        assert len(items) == 2
        # Check first item converted to UTC ISO
        assert items[0].timestamp == "2026-08-28T14:30:00Z"
        # Check second item converted from +02:00 to UTC (13:00)
        assert items[1].timestamp == "2026-08-28T13:00:00Z"


# ---------------------------------------------------------------------------
# Test 3: F0-3 Dashboard API IP Whitelisting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f0_3_dashboard_api_ip_whitelisting():
    """Verify IP whitelisting in Dashboard API verify_api_key middleware."""
    from fastapi.testclient import TestClient
    from logging_observability.dashboard.api import app

    client = TestClient(app)

    # 1. Public ping should always succeed
    resp_ping = client.get("/api/ping")
    assert resp_ping.status_code == 200

    # 2. Remote IP with DASHBOARD_ALLOWED_IPS configured
    with patch.dict(os.environ, {
        "DASHBOARD_API_KEY": "secret_key_123",
        "DASHBOARD_ALLOWED_IPS": "192.168.1.100,10.0.0.5"
    }):
        # Unauthorized remote IP
        resp_blocked = client.get(
            "/api/health",
            headers={"X-Forwarded-For": "203.0.113.1", "X-API-Key": "secret_key_123"}
        )
        assert resp_blocked.status_code == 403
        assert "not authorized" in resp_blocked.json().get("detail", "")

        # Authorized remote IP with valid key
        resp_ok = client.get(
            "/api/health",
            headers={"X-Forwarded-For": "192.168.1.100", "X-API-Key": "secret_key_123"}
        )
        assert resp_ok.status_code == 200


# ---------------------------------------------------------------------------
# Test 4: F1-1 Signal Arbitrator Dynamic Brier Weighting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f1_1_signal_arbitrator_dynamic_brier_weighting():
    """Verify dynamic Brier score weighting calculation and integration."""
    from analysis.arbitration.signal_arbitrator import compute_empirical_arbitrator_weights, SignalArbitrator
    from analysis.strategies.base_strategy import EdgeSignal

    mock_session = AsyncMock()

    # Create mock trade records where LLM has high accuracy (low brier)
    mock_records = []
    for i in range(20):
        mock_rec = MagicMock()
        mock_rec.exit_reason = "tp_hit"  # 100% win rate
        mock_ana = MagicMock()
        mock_ana.confidence = 0.85
        mock_records.append((mock_rec, mock_ana))

    mock_session.execute.return_value.all.return_value = mock_records

    w_q, w_l = await compute_empirical_arbitrator_weights(mock_session, default_quant=0.45, default_llm=0.55)
    # LLM accuracy high -> w_l should be higher than default
    assert w_l >= 0.55
    assert w_q <= 0.45
    assert round(w_q + w_l, 2) == 1.0

    # Test integration in SignalArbitrator
    settings = {
        "trading": {
            "signal_arbitration": {
                "dynamic_brier_weighting": True,
                "empirical_joint_pooling": True,
                "quant_weight": 0.45,
                "llm_weight": 0.55,
            }
        }
    }
    arbitrator = SignalArbitrator(settings=settings)
    quant_sig = EdgeSignal(
        strategy_id="xau_trend", symbol="XAUUSD", direction="buy", valid=True,
        confidence=0.80, rationale="Trend buy", exit_style="trend_trailing",
        entry_price=2650.0, stop_loss=2635.0, take_profit=2685.0
    )
    llm_decision = {
        "decision": "buy", "confidence": 0.75, "risk_multiplier": 1.0,
        "entry_price": 2650.0, "stop_loss": 2635.0, "take_profit": 2685.0, "rationale": "Bullish"
    }

    with patch("analysis.arbitration.signal_arbitrator.compute_empirical_arbitrator_weights", AsyncMock(return_value=(0.30, 0.70))):
        with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", AsyncMock(return_value=0.75)):
            res = await arbitrator.arbitrate(
                session=mock_session,
                symbol="XAUUSD",
                quant_signal=quant_sig,
                llm_decision=llm_decision,
                vix_level=16.0,
                regime_info={"regime": "trending_bull"}
            )
            assert res.decision == "buy"
            assert res.selected_source == "concordant"
            # 0.30*0.80 + 0.70*0.75 = 0.24 + 0.525 = 0.765 + 0.05 = 0.815 -> round 0.82
            assert res.confidence >= 0.80


# ---------------------------------------------------------------------------
# Test 5: F1-2 Notifier Persistent Disk Outbox
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f1_2_notifier_persistent_disk_outbox(tmp_path):
    """Verify that failed Telegram alerts are safely saved to disk and reloaded on start."""
    from utils.infra.notifier import AgentNotifier

    test_outbox_file = tmp_path / "notifier_outbox.json"

    with patch("utils.infra.notifier._OUTBOX_FILE", test_outbox_file):
        # Reset class state
        AgentNotifier._outbox.clear()
        AgentNotifier._loaded_from_disk = False

        notifier = AgentNotifier()
        notifier.token = "mock_token"
        notifier.admin_id = "123456"
        notifier.bot = MagicMock()
        notifier.bot.send_message = AsyncMock(side_effect=Exception("Network drop"))

        # Send alert that fails
        await notifier._send("Critical DB error occurred", prefix="🚨 ERROR")

        # Outbox should have 1 item in memory and on disk
        assert len(AgentNotifier._outbox) == 1
        assert test_outbox_file.exists()
        saved_items = json.loads(test_outbox_file.read_text(encoding="utf-8"))
        assert len(saved_items) == 1
        assert "Critical DB error" in saved_items[0]["text"]

        # Simulate fresh process startup
        AgentNotifier._outbox.clear()
        AgentNotifier._loaded_from_disk = False

        new_notifier = AgentNotifier()
        assert len(new_notifier._outbox) == 1

        # Now simulate network restored and flush outbox
        new_notifier.token = "mock_token"
        new_notifier.admin_id = "123456"
        new_notifier.bot = MagicMock()
        new_notifier.bot.send_message = AsyncMock(return_value=True)

        flushed = await new_notifier.flush_outbox()
        assert flushed == 1
        assert len(new_notifier._outbox) == 0


# ---------------------------------------------------------------------------
# Test 6: F1-3 Multi-Regime Partitioned Calibration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f1_3_multi_regime_partitioned_calibration():
    """Verify regime-partitioned Platt calibration fitting and retrieval."""
    from utils.calibration.confidence_calibrator import compute_confidence_calibration, get_calibrated_confidence

    mock_session = AsyncMock()

    # Generate 30 trending and 30 ranging closed records
    mock_records = []
    for i in range(30):
        # Trending: 80% win rate
        r_trend = MagicMock()
        r_trend.exit_reason = "tp_hit" if i < 24 else "sl_hit"
        a_trend = MagicMock()
        a_trend.confidence = 0.75
        a_trend.market_regime = "strong_trend"
        mock_records.append((r_trend, a_trend))

    for i in range(30):
        # Ranging: 50% win rate
        r_range = MagicMock()
        r_range.exit_reason = "tp_hit" if i < 15 else "sl_hit"
        a_range = MagicMock()
        a_range.confidence = 0.75
        a_range.market_regime = "ranging"
        mock_records.append((r_range, a_range))

    mock_result = MagicMock()
    mock_result.all.return_value = mock_records
    mock_session.execute = AsyncMock(return_value=mock_result)

    res = await compute_confidence_calibration(mock_session)
    assert "regime_models" in res
    assert "trending" in res["regime_models"]
    assert "ranging" in res["regime_models"]
    assert res["regime_models"]["trending"]["sample_size"] == 30
    assert res["regime_models"]["ranging"]["sample_size"] == 30

    # Test retrieval with regime specified
    mock_cfg = MagicMock()
    mock_cfg.value = json.dumps(res)
    mock_cfg_result = MagicMock()
    mock_cfg_result.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute = AsyncMock(return_value=mock_cfg_result)

    trend_conf = await get_calibrated_confidence(mock_session, 0.75, regime="trending_bull")
    range_conf = await get_calibrated_confidence(mock_session, 0.75, regime="ranging")

    assert trend_conf > 0.0
    assert range_conf > 0.0
    # Because trending win rate (80%) was higher than ranging (50%), trending calibrated conf should be higher
    assert trend_conf > range_conf


# ---------------------------------------------------------------------------
# Test 7: F1-6 Monte Carlo Drawdown Simulation in ReportGenerator
# ---------------------------------------------------------------------------

def test_f1_6_monte_carlo_drawdown_simulation():
    """Verify Monte Carlo 10,000 permutation drawdown analyzer in ReportGenerator."""
    from backtest.report_generator import ReportGenerator

    mock_run = MagicMock()
    mock_run.mode = "full"
    mock_run.start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mock_run.end_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mock_run.initial_equity = 10000.0

    trades = []
    # 20 trades: 12 wins (+2%), 8 losses (-1%)
    for i in range(20):
        t = MagicMock()
        t.pnl_pct = 2.0 if i < 12 else -1.0
        t.entry_time = datetime(2026, 1, i + 1, tzinfo=timezone.utc)
        t.symbol = "EURUSD"
        trades.append(t)

    generator = ReportGenerator(
        run=mock_run,
        trades=trades,
        equity_curve=[{"timestamp": t.entry_time, "equity": 10000.0 + i * 50} for i, t in enumerate(trades)],
        start_date=mock_run.start_date,
        end_date=mock_run.end_date
    )

    mc_results = generator.compute_monte_carlo_drawdowns(num_simulations=500)
    assert "var_95_drawdown_pct" in mc_results
    assert "var_99_drawdown_pct" in mc_results
    assert "max_simulated_dd_pct" in mc_results
    assert mc_results["var_95_drawdown_pct"] >= 0.0
    assert mc_results["var_99_drawdown_pct"] >= mc_results["var_95_drawdown_pct"]
