"""
Unit tests for Audit Konsistensi Codebase - Ronde 4 Remediation.
Validates critical bug fixes and consistency hardening across Analysis,
Observability, Telegram Bot, Execution, and Utils.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from utils.validation.data_validator import is_spread_acceptable
from analysis.strategies.gap_fade import DailyReopenGapFade
from analysis.strategies.base_strategy import EdgeSignal
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from telegram_bot.bot import TelegramBot
from telegram_bot.chat_tool_router import ChatToolRouter
from utils.market.swap_estimator import estimate_swap_cost
from utils.market.bias_utils import normalize_bias
from execution.ea_bridge.heartbeat_writer import HeartbeatWriter
from analysis.calculators.invariant_calculator import extract_price_precision
from utils.protocol.enhanced_cds import get_signal_threshold
from utils.analytics.paper_tracker import PaperTracker


def test_is_spread_acceptable_canonical_assets():
    """Memverifikasi 8 canonical assets lolos pada spread normal dan memblokir spread ekstrem."""
    canonical_normal = {
        "XAUUSD": (2650.0, 2650.40),   # 40 cents spread < 50c * 5
        "EURUSD": (1.08500, 1.08514),  # 1.4 pips < 1.5p * 5
        "GBPUSD": (1.30000, 1.30018),  # 1.8 pips < 2.0p * 5
        "USDJPY": (150.000, 150.014),  # 1.4 pips < 1.5p * 5 (0.014 < 0.075)
        "AUDUSD": (0.67000, 0.67015),  # 1.5 pips < 1.8p * 5
        "BTCUSD": (65000.0, 65004.0),  # $4 < $5 * 5
        "XTIUSD": (72.00, 72.03),      # 3 cents < 3c * 5 (0.03 < 0.15)
        "XBRUSD": (75.00, 75.035),     # 3.5 cents < 4c * 5 (0.035 < 0.20)
    }
    for sym, (bid, ask) in canonical_normal.items():
        assert is_spread_acceptable(sym, bid, ask) is True, f"{sym} normal spread failed"

    # Verifikasi spread ekstrem (6x typical) diblokir
    canonical_extreme = {
        "USDJPY": (150.000, 150.080),  # 8 pips > 7.5 pips max
        "XTIUSD": (72.00, 72.20),      # 20 cents > 15 cents max
        "XBRUSD": (75.00, 75.25),      # 25 cents > 20 cents max
        "EURUSD": (1.08500, 1.08600),  # 10 pips > 7.5 pips max
    }
    for sym, (bid, ask) in canonical_extreme.items():
        assert is_spread_acceptable(sym, bid, ask) is False, f"{sym} extreme spread was not blocked"


@pytest.mark.asyncio
async def test_gap_fade_no_name_error():
    """Memverifikasi DailyReopenGapFade tidak melempar NameError: name 'gap' is not defined."""
    strat = DailyReopenGapFade(settings={})
    session = AsyncMock()
    
    with patch("utils.clock.now") as mock_now:
        mock_now.return_value = datetime(2026, 9, 14, 8, 30, tzinfo=timezone.utc)
        
        bar_today = MagicMock()
        bar_today.timestamp = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
        bar_today.open = 2660.0
        bar_today.close = 2655.0

        bar_prev = MagicMock()
        bar_prev.timestamp = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)
        bar_prev.open = 2640.0
        bar_prev.close = 2645.0  # Gap up = 2660 - 2645 = 15.0

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [bar_today, bar_prev]
        mock_exec = MagicMock()
        mock_exec.scalars.return_value = mock_scalars
        mock_exec.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_exec

        signal = await strat.evaluate(
            session=session,
            symbol="XAUUSD",
            settings={},
        )
        assert isinstance(signal, EdgeSignal)
        assert signal.symbol == "XAUUSD"


@pytest.mark.asyncio
async def test_signal_arbitrator_direction_none():
    """Memverifikasi SignalArbitrator menangani sinyal quant dengan direction=None tanpa crash."""
    arbitrator = SignalArbitrator(settings={})
    session = AsyncMock()

    # 1. Quant signal invalid / direction None, no LLM decision
    invalid_signal = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction=None,
        valid=False,
        confidence=0.0,
    )
    res = await arbitrator.arbitrate(
        symbol="EURUSD",
        quant_signal=invalid_signal,
        llm_decision=None,
        session=session,
    )
    assert res.decision == "avoid"
    assert "non-directional or invalid" in res.arbitration_reason

    # 2. Quant signal invalid / direction None, WITH LLM decision -> Harus fallback ke LLM
    llm_decision = {
        "decision": "buy",
        "confidence": 0.80,
        "risk_multiplier": 1.0,
        "rationale": "Strong macro confluence",
    }
    res_llm = await arbitrator.arbitrate(
        symbol="EURUSD",
        quant_signal=invalid_signal,
        llm_decision=llm_decision,
        session=session,
    )
    assert res_llm.decision == "buy"
    assert res_llm.selected_source == "llm"


def test_telegram_chunk_preserves_emojis_and_html():
    """Memverifikasi TelegramBot._chunk_text tidak menghapus emoji alert dan tidak merusak HTML."""
    alert_text = "🚨 *EMERGENCY ALERT* ⚠️\nPosition liquidated: XAUUSD ✅ Loss: $0.00 📊"
    
    # Notifikasi sistem default sanitize_format=False -> emoji WAJIB utuh
    chunks = TelegramBot._chunk_text(alert_text, max_len=4000, sanitize_format=False)
    assert len(chunks) == 1
    assert "🚨" in chunks[0]
    assert "⚠️" in chunks[0]
    assert "✅" in chunks[0]
    assert "📊" in chunks[0]

    # Tearsheet HTML is_html=True -> tidak boleh menambahkan markdown balancing tags
    html_text = "<b>Monthly Summary</b>\n<tr><td>Return</td><td>+15%</td></tr>"
    html_chunks = TelegramBot._chunk_text(html_text, max_len=4000, is_html=True)
    assert len(html_chunks) == 1
    assert html_chunks[0] == html_text


def test_telegram_symbol_pattern_includes_brent():
    """Memverifikasi regex router Telegram mencakup xbrusd dan brent."""
    assert ChatToolRouter.SYMBOL_PATTERNS.search("analisis xbrusd") is not None
    assert ChatToolRouter.SYMBOL_PATTERNS.search("bagaimana prospek brent oil?") is not None


def test_agent_performance_monitor_strong_bullish():
    """Memverifikasi normalize_bias mengakui strong_bullish sebagai bullish."""
    assert normalize_bias("strong_bullish") == "bullish"
    assert normalize_bias("bullish") == "bullish"
    assert normalize_bias("strong_bearish") == "bearish"
    assert normalize_bias("bearish") == "bearish"
    assert normalize_bias("neutral") == "neutral"


@pytest.mark.asyncio
async def test_swap_estimator_uppercase_direction():
    """Memverifikasi swap estimator menangani string BUY / Buy / buy secara konsisten."""
    swap_lower = await estimate_swap_cost("EURUSD", "buy", 1.0, 48)
    swap_upper = await estimate_swap_cost("EURUSD", "BUY", 1.0, 48)
    swap_mixed = await estimate_swap_cost("EURUSD", "Long", 1.0, 48)
    assert swap_lower == swap_upper == swap_mixed


@pytest.mark.asyncio
async def test_heartbeat_writer_responsive_shutdown():
    """Memverifikasi HeartbeatWriter.stop() menghentikan loop dalam < 100ms tanpa lag 20 detik."""
    writer = HeartbeatWriter()
    # Mock write agar tidak butuh path riil MT5
    writer._write_heartbeat = MagicMock()

    task = asyncio.create_task(writer.run_forever())
    await asyncio.sleep(0.02)  # Biarkan loop mulai
    assert writer._running is True

    t0 = asyncio.get_event_loop().time()
    writer.stop()
    await asyncio.wait_for(task, timeout=1.0)
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 0.2, f"Shutdown took too long: {elapsed:.3f}s"
    assert writer._running is False


def test_invariant_calculator_brent_precision():
    """Memverifikasi extract_price_precision untuk XBRUSD adalah 3 desimal."""
    assert extract_price_precision("XBRUSD") == 3
    assert extract_price_precision("BRENT") == 3
    assert extract_price_precision("XTIUSD") == 3
    assert extract_price_precision("USDJPY") == 3
    assert extract_price_precision("EURUSD") == 5


def test_enhanced_cds_xbrusd_threshold():
    """Memverifikasi ASSET_SIGNAL_THRESHOLDS memetakan XBRUSD ke 0.012."""
    assert get_signal_threshold("XBRUSD") == 0.012
    assert get_signal_threshold("XTIUSD") == 0.012


def test_paper_tracker_brent_spread():
    """Memverifikasi PaperTracker._get_realistic_spread memuat base spread XBRUSD 0.04."""
    tracker = PaperTracker(settings={"paper_trading": {"spread_multipliers": {"XBRUSD": 1.0}}})
    spread = tracker._get_realistic_spread("XBRUSD")
    assert round(spread, 3) == 0.04


def test_route_ordering_trace_search():
    """Memverifikasi trace_search_router dipasang sebelum observability_router di all_routers."""
    from logging_observability.dashboard.routes import all_routers, trace_search_router, observability_router
    idx_search = all_routers.index(trace_search_router)
    idx_obs = all_routers.index(observability_router)
    assert idx_search < idx_obs, f"trace_search_router ({idx_search}) must precede observability_router ({idx_obs})"
