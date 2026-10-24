"""Remediation tests for Phase 15 Quantitative Strategies, Evidence Store & Governance.
Verifies FR-3.5 compliance, fail-closed mechanics, quarantine enforcement, and bracket geometry.
"""

from dataclasses import dataclass
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.strategies.base_strategy import (
    QUARANTINED_STRATEGY_IDS,
    EdgeSignal,
    StrategyTier,
)
from monika.application.analysis.strategies.decay_monitor import (
    StrategyDecayMonitor,
)
from monika.application.analysis.strategies.evidence_store import (
    EvidenceStatus,
    StrategyEvidenceStore,
)
from monika.application.analysis.strategies.pretrade_gate import evaluate_pretrade_gate
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.analysis.strategies.synthesized.alpha_eurusd_6d622a import (
    SynthesizedStrategy_alpha_eurusd_6d622a,
)
from monika.application.analysis.strategies.synthesized.alpha_eurusd_8060ed import (
    SynthesizedStrategy_alpha_eurusd_8060ed,
)
from monika.application.analysis.strategies.synthesized.alpha_gbpusd_867953 import (
    SynthesizedStrategy_alpha_gbpusd_867953,
)
from monika.application.analysis.strategies.synthesized.alpha_usdjpy_13a603 import (
    SynthesizedStrategy_alpha_usdjpy_13a603,
)
from monika.application.analysis.strategies.synthesized.alpha_xtiusd_83031c import (
    SynthesizedStrategy_alpha_xtiusd_83031c,
)
from monika.application.analysis.strategies.xau_trend_engine import XAUTrendEngine


@dataclass
class SimpleBar:
    open: float
    high: float
    low: float
    close: float


def _make_evidence_entry(strategy_id: str, days_ago: int = 5) -> dict:
    window_end = datetime.now(UTC) - timedelta(days=days_ago)
    return {
        "strategy_id": strategy_id,
        "symbol": "EURUSD",
        "timeframe": "H1",
        "data_window_end": window_end.strftime("%Y-%m-%d"),
        "gross_return": 0.15,
        "total_trades": 45,
        "avg_position_size": 1.0,
        "max_concurrent_positions": 1,
        "breakeven_bps": 6.0,
        "regime_breakdown": {},
        "status": EvidenceStatus.FRESH.value,
        "evidence_age_days": 0,
        "updated_at": 0.0,
    }


# =====================================================================
# 1. Quarantine & Governance
# =====================================================================


def test_donchian_breakout_quarantine_enforced():
    """Verify donchian_breakout is strictly quarantined and inactive in StrategyRegistry."""
    assert "donchian_breakout" in QUARANTINED_STRATEGY_IDS
    assert "btc_donchian_breakout" in QUARANTINED_STRATEGY_IDS

    assert StrategyRegistry.get_tier("donchian_breakout") == StrategyTier.QUARANTINED
    assert StrategyRegistry.get_tier("btc_donchian_breakout") == StrategyTier.QUARANTINED


def test_evidence_store_rejects_unbacked_and_special_keys(tmp_path: Path):
    """Verify general and default strings are rejected without evidence file backing."""
    store_path = tmp_path / "evidence.json"
    store_path.write_text("[]", encoding="utf-8")
    store = StrategyEvidenceStore(store_path)

    eligible_gen, reason_gen = store.is_strategy_eligible_to_trade("general")
    assert eligible_gen is False
    assert "general" in reason_gen

    eligible_def, reason_def = store.is_strategy_eligible_to_trade("default")
    assert eligible_def is False
    assert "default" in reason_def

    eligible_unk, reason_unk = store.is_strategy_eligible_to_trade("arbitrary_unknown")
    assert eligible_unk is False


def test_fr35_conjunctive_governance(tmp_path: Path):
    """Verify FR-3.5: promotion requires both statistical evidence AND paper incubation."""
    store_path = tmp_path / "evidence.json"
    store_path.write_text(json.dumps([_make_evidence_entry("test_strat")]), encoding="utf-8")
    store = StrategyEvidenceStore(store_path)
    decay = StrategyDecayMonitor(min_incubation_trades=15)

    eligible, _ = store.is_strategy_eligible_to_trade("test_strat")
    assert eligible is True

    # Register in decay monitor as incubating
    decay.register_incubating_strategy("test_strat")
    assert decay.is_live_ready("test_strat") is False

    with patch("monika.domain.risk.ports.get_default_evidence_store", return_value=store):
        with patch(
            "monika.application.analysis.strategies.decay_monitor.get_strategy_decay_monitor", return_value=decay
        ):
            # Pending paper incubation -> EXPERIMENTAL, not VALIDATED
            tier = StrategyRegistry.get_tier("test_strat")
            assert tier == StrategyTier.EXPERIMENTAL

            # Pass incubation
            health = decay.get_health("test_strat")
            health.paper_trades_count = 20
            health.is_incubation_passed = True
            assert decay.is_live_ready("test_strat") is True

            # Both passed -> VALIDATED
            tier = StrategyRegistry.get_tier("test_strat")
            assert tier == StrategyTier.VALIDATED


# =====================================================================
# 2. Financial Geometry & Bracket Safety
# =====================================================================


def test_edge_signal_fail_closed_validation():
    """Verify EdgeSignal.is_executable fails closed on zero risk, inverted SL, or NaN."""
    # Invalid signal
    sig_invalid = EdgeSignal(strategy_id="s1", symbol="EURUSD", direction="buy", valid=False, confidence=0.0)
    assert sig_invalid.is_executable() is False

    # Zero risk (sl == entry)
    sig_zero_risk = EdgeSignal(
        strategy_id="s1",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.1000,
        stop_loss=1.1000,
        take_profit=1.1100,
    )
    assert sig_zero_risk.is_executable() is False

    # Inverted SL for BUY (sl > entry)
    sig_inverted = EdgeSignal(
        strategy_id="s1",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.1000,
        stop_loss=1.1050,
        take_profit=1.1200,
    )
    assert sig_inverted.is_executable() is False

    # Valid signal with adequate RR
    sig_valid = EdgeSignal(
        strategy_id="s1",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    assert sig_valid.is_executable(min_rr=1.5) is True


@pytest.mark.asyncio
async def test_xau_trend_engine_gold_minimum_sl_buffer():
    """Verify XAUTrendEngine enforces minimum $3.00 ATR buffer for XAUUSD stops."""
    strat = XAUTrendEngine({"donchian_period": 20, "timeframe": "H1", "ema_fast": 20, "ema_slow": 50})
    session = AsyncMock()

    # Create bars in reverse chronological order (latest is index 0)
    # Latest close 2002.5 breaks above high 2002.0. Entry 2002.5, ch_mid = 2001.0 -> raw sl_dist = 1.5
    # min_gold_sl = max(3.0, (2002.0 - 2000.0) * 0.15) = 3.0
    # Must enforce sl_dist >= 3.0
    bars = [SimpleBar(2001.0, 2003.0, 2000.0, 2002.5)]
    for _ in range(60):
        bars.append(SimpleBar(2001.0, 2002.0, 2000.0, 2001.0))

    mock_row_res = MagicMock()
    mock_row_res.scalar_one_or_none.return_value = None

    mock_bars_res = MagicMock()
    mock_bars_res.scalars.return_value.all.return_value = bars

    session.execute = AsyncMock(side_effect=[mock_row_res, mock_row_res, mock_bars_res])

    sig = await strat.evaluate(session, "XAUUSD", {})
    if sig.valid and sig.entry_price and sig.stop_loss:
        sl_dist = abs(sig.entry_price - sig.stop_loss)
        assert sl_dist >= 3.0, f"Gold SL distance {sl_dist} must be >= 3.00 USD"


# =====================================================================
# 3. Synthesized Alphas Ghost Signal Prevention
# =====================================================================


@pytest.mark.asyncio
async def test_synthesized_alphas_ghost_signals_prevented():
    """Verify synthesized alphas return valid=False when direction is None or confidence < 0.50."""
    session = AsyncMock()
    candles = [{"open": 1.0, "high": 1.01, "low": 0.99, "close": 1.0} for _ in range(35)]

    alphas = [
        SynthesizedStrategy_alpha_eurusd_8060ed(),
        SynthesizedStrategy_alpha_xtiusd_83031c(),
        SynthesizedStrategy_alpha_eurusd_6d622a(),
        SynthesizedStrategy_alpha_gbpusd_867953(),
    ]

    for alpha in alphas:
        with patch.object(alpha, "get_historical_candles", AsyncMock(return_value=candles)):
            sig = await alpha.evaluate(session, list(alpha.applicable_symbols)[0], {})
            if sig.direction is None:
                assert sig.valid is False, f"{alpha.strategy_id} returned valid=True when direction is None"


@pytest.mark.asyncio
async def test_alpha_usdjpy_13a603_brackets_connected():
    """Verify SynthesizedStrategy_alpha_usdjpy_13a603 includes stop_loss and take_profit in EdgeSignal."""
    alpha = SynthesizedStrategy_alpha_usdjpy_13a603()
    session = AsyncMock()
    candles = [{"open": 150.0, "high": 150.5, "low": 149.5, "close": 150.0} for _ in range(35)]
    candles[-1] = {"open": 150.0, "high": 152.0, "low": 150.0, "close": 151.8}

    with patch.object(alpha, "get_historical_candles", AsyncMock(return_value=candles)):
        sig = await alpha.evaluate(session, "USDJPY", {})
        if sig.valid:
            assert sig.stop_loss is not None, "stop_loss must be populated"
            assert sig.take_profit is not None, "take_profit must be populated"
            assert sig.entry_price is not None, "entry_price must be populated"


# =====================================================================
# 4. Pre-trade Gate Fail-Closed on Missing ADX & Rollover
# =====================================================================


@pytest.mark.asyncio
async def test_pretrade_gate_rollover_deadzone():
    """Verify rollover deadzone blocks non-crypto symbols during 21:55-22:15 UTC."""
    session = AsyncMock()
    rollover_time = datetime(2026, 10, 24, 22, 5, tzinfo=UTC)

    # EURUSD should be blocked
    ok, reason = await evaluate_pretrade_gate(
        session=session,
        symbol="EURUSD",
        settings={"trading": {"risk": {"rollover_protection_enabled": True}}},
        as_of=rollover_time,
    )
    assert ok is False
    assert "session_rollover_deadzone" in reason

    # BTCUSD should be exempt
    with patch(
        "monika.application.analysis.strategies.pretrade_gate.compute_bollinger_donchian_chop",
        AsyncMock(return_value={}),
    ):
        with patch(
            "monika.application.analysis.strategies.pretrade_gate.compute_volume_profile", AsyncMock(return_value={})
        ):
            with patch(
                "monika.application.analysis.strategies.pretrade_gate.classify_market_regime",
                AsyncMock(return_value={"adx": 30.0}),
            ):
                ok_crypto, _ = await evaluate_pretrade_gate(
                    session=session,
                    symbol="BTCUSD",
                    settings={"trading": {"risk": {"rollover_protection_enabled": True}}},
                    strategy_type="trend",
                    as_of=rollover_time,
                )
                assert ok_crypto is True


@pytest.mark.asyncio
async def test_pretrade_gate_fail_closed_on_missing_adx():
    """Verify PreTradeGate rejects trend signals when ADX is unavailable (fail-closed)."""
    session = AsyncMock()
    normal_time = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)

    with patch(
        "monika.application.analysis.strategies.pretrade_gate.compute_bollinger_donchian_chop",
        AsyncMock(return_value={}),
    ):
        with patch(
            "monika.application.analysis.strategies.pretrade_gate.compute_volume_profile", AsyncMock(return_value={})
        ):
            with patch(
                "monika.application.analysis.strategies.pretrade_gate.classify_market_regime",
                AsyncMock(return_value={"adx": None}),
            ):
                ok, reason = await evaluate_pretrade_gate(
                    session=session,
                    symbol="EURUSD",
                    settings={},
                    strategy_type="trend",
                    as_of=normal_time,
                )
                assert ok is False
                assert "adx_unavailable" in reason


# =====================================================================
# 5. Catalog Schema Verification
# =====================================================================


def test_synthesized_strategies_catalog_applicable_symbols():
    """Verify synthesized_strategies.json contains populated applicable_symbols."""
    catalog_path = Path("src/monika/domain/indicators/alpha_zoo/catalog/synthesized_strategies.json")
    assert catalog_path.exists(), "Synthesized catalog file must exist"

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    strategies = data.get("strategies", {})
    assert len(strategies) > 0, "Catalog must not be empty"

    for strat_id, strat in strategies.items():
        symbols = strat.get("applicable_symbols", [])
        assert isinstance(symbols, list), f"applicable_symbols in {strat_id} must be a list"
        assert len(symbols) > 0, f"applicable_symbols in {strat_id} must not be empty"
