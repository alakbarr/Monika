# ==============================================================================
# File: tests/analysis/test_chart_workspace_and_stage2_integration.py
# ==============================================================================

"""
Integration and Unit Test Suite for Chart Workspace and Stage 2 Cognitive Pipeline.

Covers:
1. Pure Indicator Math & Canonical Presets (normalizer, clamping, vectorized series, evaluation).
2. Persistence (SqlAlchemyUserPreferenceRepository global and symbol overrides).
3. Headless Chart Generator & Vision Budget (multipanel generation and byte budget clamping).
4. Multimodal LLM Harness & Providers (image blocks, prompt concatenation, OpenAI normalizer).
5. Stage 2 Services, Confluence & Grounding (multi-TF workspace, alignment, anchor extraction).
6. FastAPI Chart Config & Workspace Endpoints (bundle, save, delete, workspace payload).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi import Request
import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from monika.application.agent.harness.agent_harness import AgentHarness
from monika.application.analysis.calculators.confluence_calculator import calculate_confluence
from monika.application.analysis.tools.domain.multimodal_tools import VisionImageProcessor
from monika.application.analysis.validators.in_harness_grounding import extract_verified_anchors
from monika.application.services.technical_indicator_service import TechnicalIndicatorService
from monika.core.analytics.chart_generator import generate_configured_workspace_chart_async
from monika.domain.indicators.technical import (
    CHART_WORKSPACE_PRESETS,
    compute_cvd_series,
    compute_donchian_channels,
    compute_ichimoku_series,
    compute_keltner_channels,
    compute_obv,
    compute_supertrend,
    compute_vwap,
    compute_wma,
    evaluate_workspace_indicators,
    normalize_chart_workspace_config,
)
from monika.infrastructure.database.domain_models.market import PriceOHLCV
from monika.infrastructure.database.models import Base
from monika.infrastructure.database.repositories.user_preference_repository import (
    CHART_WORKSPACE_CATEGORY,
    SqlAlchemyUserPreferenceRepository,
)
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.interfaces.dashboard.rbac import Role
from monika.interfaces.dashboard.routes.trading_endpoints.market_data import (
    delete_chart_workspace_override,
    get_chart_workspace,
    get_chart_workspace_config_bundle,
    save_chart_workspace_config,
)
from monika.interfaces.dashboard.schemas import ChartConfigSaveRequest


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================


async def _init_in_memory_session() -> tuple[Any, AsyncSession]:
    """Create an isolated in-memory SQLite database and return engine and session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    return engine, session


def _create_synthetic_ohlcv_df(bars: int = 120, seed: int = 42) -> pd.DataFrame:
    """Generate a deterministic synthetic OHLCV DataFrame with DatetimeIndex."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=bars, freq="4h", tz="UTC")
    returns = rng.normal(0.0005, 0.005, size=bars)
    close = 100.0 * np.exp(np.cumsum(returns))
    high = close * (1.0 + rng.uniform(0.001, 0.008, size=bars))
    low = close * (1.0 - rng.uniform(0.001, 0.008, size=bars))
    open_ = (high + low) / 2.0
    volume = rng.uniform(100.0, 5000.0, size=bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ==============================================================================
# 1. Pure Indicator Math & Canonical Presets
# ==============================================================================


def test_normalize_chart_workspace_config_presets_and_clamping() -> None:
    """Verify all 4 canonical presets, extreme parameter clamping, and yang_zhang normalization."""
    # 1. Verify default fallback
    default_cfg = normalize_chart_workspace_config(None)
    assert default_cfg["preset_id"] == "smc_institutional"
    assert default_cfg["timeframe"] == "H4"
    assert default_cfg["vision_sync_enabled"] is True

    # 2. Verify all 4 canonical presets
    presets = ["smc_institutional", "trend_momentum", "volatility_reversion", "quant_orderflow"]
    for pid in presets:
        norm = normalize_chart_workspace_config({"preset_id": pid})
        assert norm["preset_id"] == pid
        assert "overlays" in norm
        assert "oscillators" in norm
        expected_preset = CHART_WORKSPACE_PRESETS[pid]
        assert norm["overlays"]["ema"]["enabled"] == expected_preset["overlays"]["ema"]["enabled"]
        assert norm["oscillators"]["rsi"]["enabled"] == expected_preset["oscillators"]["rsi"]["enabled"]

    # 3. Extreme parameter clamping
    raw_extreme = {
        "timeframe": "  m15  ",
        "vision_sync_enabled": False,
        "overlays": {
            "ema": {"enabled": True, "periods": [-50, 0, 1, 900, 9999]},
            "bollinger": {"enabled": True, "period": 1, "std_dev": 99.0},
            "keltner": {"enabled": True, "window": 999, "window_atr": 0, "multiplier": -5.0},
            "supertrend": {"enabled": True, "period": 1000, "multiplier": 50.0},
        },
        "oscillators": {
            "rsi": {"enabled": True, "period": 1, "overbought": 150.0, "oversold": -10.0},
            "macd": {"enabled": True, "fast": 500, "slow": 10, "signal": 0},
            "stochastic": {"enabled": True, "k_period": 0, "d_period": 200},
            "atr": {"enabled": True, "period": 1000},
            "cvd_volatility": {"enabled": True, "mode": "yang_zhang", "window": 1},
        },
    }
    clamped = normalize_chart_workspace_config(raw_extreme)

    assert clamped["timeframe"] == "M15"
    assert clamped["vision_sync_enabled"] is False

    # Periods clamped to [2, 500]
    ema_periods = clamped["overlays"]["ema"]["periods"]
    assert min(ema_periods) >= 2
    assert max(ema_periods) <= 500

    assert clamped["overlays"]["bollinger"]["period"] == 2
    assert clamped["overlays"]["bollinger"]["std_dev"] == 10.0  # Clamped to high=10.0

    assert clamped["overlays"]["keltner"]["window"] == 500
    assert clamped["overlays"]["keltner"]["window_atr"] == 2
    assert clamped["overlays"]["keltner"]["multiplier"] == 0.1  # Clamped to low=0.1

    assert clamped["overlays"]["supertrend"]["period"] == 500
    assert clamped["overlays"]["supertrend"]["multiplier"] == 20.0  # Clamped to high=20.0

    # RSI overbought [50, 95] and oversold [5, 50]
    assert clamped["oscillators"]["rsi"]["period"] == 2
    assert clamped["oscillators"]["rsi"]["overbought"] == 95.0
    assert clamped["oscillators"]["rsi"]["oversold"] == 5.0

    # MACD fast < slow invariant enforced
    macd = clamped["oscillators"]["macd"]
    assert macd["fast"] < macd["slow"]
    assert macd["signal"] >= 1

    # Stochastic clamping
    assert clamped["oscillators"]["stochastic"]["k_period"] == 2
    assert clamped["oscillators"]["stochastic"]["d_period"] == 100

    # ATR clamping
    assert clamped["oscillators"]["atr"]["period"] == 500

    # Mode yang_zhang -> yz_vol
    assert clamped["oscillators"]["cvd_volatility"]["mode"] == "yz_vol"
    assert clamped["oscillators"]["cvd_volatility"]["window"] == 2


def test_pure_indicator_series_functions() -> None:
    """Deterministic calculation of pure indicator series functions on 120-bar synthetic OHLCV."""
    df = _create_synthetic_ohlcv_df(bars=120, seed=42)
    high, low, close, volume, open_ = df["high"], df["low"], df["close"], df["volume"], df["open"]

    # 1. compute_wma
    wma = compute_wma(close, period=20)
    assert len(wma) == 120
    assert pd.isna(wma.iloc[0])
    assert pd.isna(wma.iloc[18])
    assert np.isfinite(wma.iloc[19])
    assert (wma.dropna() > 0).all()

    # 2. compute_vwap
    vwap_roll = compute_vwap(high, low, close, volume, window=20)
    assert len(vwap_roll) == 120
    assert (vwap_roll > 0).all()
    vwap_cum = compute_vwap(high, low, close, volume, window=None)
    assert len(vwap_cum) == 120
    assert (vwap_cum > 0).all()

    # 3. compute_supertrend
    st_val, st_dir = compute_supertrend(high, low, close, period=10, multiplier=3.0)
    assert len(st_val) == 120
    assert len(st_dir) == 120
    valid_dirs = set(st_dir.dropna().unique())
    assert valid_dirs.issubset({-1, 1})
    assert np.isfinite(st_val.iloc[-1])

    # 4. compute_keltner_channels
    kc_u, kc_m, kc_l = compute_keltner_channels(high, low, close, window=20, window_atr=10, multiplier=2.0)
    assert len(kc_u) == 120
    assert len(kc_m) == 120
    assert len(kc_l) == 120
    valid_mask = kc_u.notna() & kc_m.notna() & kc_l.notna()
    assert (kc_u[valid_mask] >= kc_m[valid_mask]).all()
    assert (kc_m[valid_mask] >= kc_l[valid_mask]).all()

    # 5. compute_donchian_channels
    dc_u, dc_m, dc_l = compute_donchian_channels(high, low, close, window=20)
    assert len(dc_u) == 120
    assert len(dc_m) == 120
    assert len(dc_l) == 120
    valid_dc = dc_u.notna() & dc_m.notna() & dc_l.notna()
    assert (dc_u[valid_dc] >= dc_m[valid_dc]).all()
    assert (dc_m[valid_dc] >= dc_l[valid_dc]).all()

    # 6. compute_ichimoku_series
    ichi = compute_ichimoku_series(high, low, close, tenkan_period=9, kijun_period=26, senkou_b_period=52)
    expected_keys = {"tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "chikou_span"}
    assert set(ichi.keys()) == expected_keys
    for k, s in ichi.items():
        assert len(s) == 120
    assert np.isfinite(ichi["tenkan_sen"].iloc[-1])
    assert np.isfinite(ichi["kijun_sen"].iloc[-1])

    # 7. compute_obv
    obv = compute_obv(close, volume)
    assert len(obv) == 120
    assert np.isfinite(obv.iloc[-1])

    # 8. compute_cvd_series
    cvd = compute_cvd_series(open_, high, low, close, volume)
    assert len(cvd) == 120
    assert np.isfinite(cvd.iloc[-1])


def test_evaluate_workspace_indicators_all_overlays_and_oscillators() -> None:
    """Evaluate workspace indicators with ALL overlays and ALL oscillators active."""
    df = _create_synthetic_ohlcv_df(bars=150, seed=42)
    all_active_config: dict[str, Any] = {
        "timeframe": "H4",
        "vision_sync_enabled": True,
        "overlays": {
            "ema": {"enabled": True, "periods": [20, 50, 200]},
            "sma": {"enabled": True, "periods": [20, 50]},
            "wma": {"enabled": True, "periods": [20]},
            "bollinger": {"enabled": True, "period": 20, "std_dev": 2.0},
            "keltner": {"enabled": True, "window": 20, "window_atr": 10, "multiplier": 2.0},
            "donchian": {"enabled": True, "window": 20},
            "vwap": {"enabled": True, "window": 20},
            "supertrend": {"enabled": True, "period": 10, "multiplier": 3.0},
            "ichimoku": {"enabled": True, "tenkan": 9, "kijun": 26, "senkou_b": 52},
            "pivot_points": {"enabled": True, "method": "classic"},
        },
        "oscillators": {
            "volume": {"enabled": True, "ma_period": 20},
            "rsi": {"enabled": True, "period": 14, "overbought": 70.0, "oversold": 30.0},
            "macd": {"enabled": True, "fast": 12, "slow": 26, "signal": 9},
            "stochastic": {"enabled": True, "k_period": 14, "d_period": 3},
            "adx": {"enabled": True, "period": 14},
            "atr": {"enabled": True, "period": 14},
            "cvd_volatility": {"enabled": True, "mode": "cvd", "window": 20},
        },
    }

    result = evaluate_workspace_indicators(df, all_active_config, max_bars=60)

    # 1. Series dictionary
    series = result["series"]
    assert "ema_20" in series
    assert "ema_50" in series
    assert "ema_200" in series
    assert "sma_20" in series
    assert "wma_20" in series
    assert "bb_upper" in series
    assert "kc_upper" in series
    assert "dc_upper" in series
    assert "vwap" in series
    assert "supertrend" in series
    assert "ichimoku_tenkan" in series
    assert "volume" in series
    assert "rsi" in series
    assert "macd_line" in series
    assert "stoch_k" in series
    assert "adx" in series
    assert "atr" in series
    assert "cvd" in series

    # Packed points length check (at most max_bars=60)
    assert len(series["ema_20"]) <= 60
    assert "time" in series["ema_20"][0]
    assert "value" in series["ema_20"][0]

    # 2. Pivot points
    pivots = result["pivot_points"]
    assert pivots is not None
    assert "pivot" in pivots
    assert "r1" in pivots
    assert "s1" in pivots

    # 3. Summary evaluations
    summary = result["summary"]
    assert "EMA_20" in summary
    assert "RSI_14" in summary
    assert "MACD" in summary
    assert "Supertrend" in summary
    for k, item in summary.items():
        assert item["signal"] in ("bullish", "bearish", "neutral")
        assert "details" in item

    # 4. Overall alignment metrics
    overall = result["overall"]
    assert overall["bias"] in ("bullish", "bearish", "neutral")
    assert overall["total_directional"] == overall["bullish_count"] + overall["bearish_count"]
    assert 0.0 <= overall["alignment_ratio"] <= 1.0
    assert 0.0 <= overall["alignment_pct"] <= 100.0
    assert overall["confluence_adjustment"] in (0, 1, 2)

    # 5. Declared figures
    figures = result["declared_figures"]
    assert "CLOSE" in figures
    assert "EMA_20" in figures
    assert "RSI_14" in figures
    assert "PIVOT" in figures
    assert all(isinstance(v, (int, float)) for v in figures.values())


def test_evaluate_workspace_indicators_empty_or_nan_fails_closed() -> None:
    """Verify empty, malformed, and NaN-heavy DataFrames fail closed without raising exceptions."""
    # 1. Empty DataFrame returns neutral defaults
    res_empty = evaluate_workspace_indicators(pd.DataFrame())
    assert res_empty["overall"]["bias"] == "neutral"
    assert res_empty["overall"]["confluence_adjustment"] == 0
    assert res_empty["overall"]["total_directional"] == 0
    assert res_empty["series"] == {}
    assert res_empty["summary"] == {}
    assert res_empty["declared_figures"] == {}

    # 2. DataFrame with 0 rows but required columns
    res_zero = evaluate_workspace_indicators(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
    assert res_zero["overall"]["bias"] == "neutral"
    assert res_zero["overall"]["confluence_adjustment"] == 0
    assert res_zero["declared_figures"] == {}
    assert res_zero["series"] == {}

    # 3. DataFrame missing required columns
    res_missing = evaluate_workspace_indicators(pd.DataFrame({"foo": [1, 2, 3]}))
    assert res_missing["overall"]["bias"] == "neutral"
    assert res_missing["overall"]["confluence_adjustment"] == 0
    assert res_missing["declared_figures"] == {}

    # 4. NaN-heavy DataFrame does not raise exception and returns structured result
    df_nan = pd.DataFrame(
        {
            "open": [np.nan] * 30,
            "high": [np.nan] * 30,
            "low": [np.nan] * 30,
            "close": [np.nan] * 30,
            "volume": [np.nan] * 30,
        }
    )
    res_nan = evaluate_workspace_indicators(df_nan)
    assert isinstance(res_nan, dict)
    assert "overall" in res_nan
    assert "series" in res_nan
    assert "declared_figures" in res_nan


# ==============================================================================
# 2. Persistence (SqlAlchemyUserPreferenceRepository)
# ==============================================================================


@pytest.mark.asyncio
async def test_user_preference_repository_global_and_symbol_override() -> None:
    """Verify bundle retrieval, global preferences, symbol overrides, and cascade fallback."""
    engine, session = await _init_in_memory_session()
    try:
        repo = SqlAlchemyUserPreferenceRepository(session)

        # 1. Initial bundle with no saved preferences
        bundle = await repo.get_chart_workspace_bundle()
        assert bundle["global"]["preset_id"] == "smc_institutional"
        assert bundle["symbols"] == {}

        # 2. Save global preference
        await repo.set_preference(
            CHART_WORKSPACE_CATEGORY,
            "global",
            {"preset_id": "trend_momentum", "timeframe": "H1"},
        )
        bundle_updated = await repo.get_chart_workspace_bundle()
        assert bundle_updated["global"]["preset_id"] == "trend_momentum"
        assert bundle_updated["global"]["timeframe"] == "H1"

        # 3. Save per-symbol override for XAUUSD
        await repo.set_preference(
            CHART_WORKSPACE_CATEGORY,
            "XAUUSD",
            {"preset_id": "volatility_reversion", "timeframe": "M15"},
        )

        # 4. Resolve XAUUSD (should resolve symbol override)
        cfg_xau = await repo.resolve_chart_workspace_config("XAUUSD")
        assert cfg_xau["preset_id"] == "volatility_reversion"
        assert cfg_xau["timeframe"] == "M15"
        assert cfg_xau["scope"] == "symbol"
        assert cfg_xau["symbol"] == "XAUUSD"

        # 5. Resolve EURUSD (no symbol override; should fallback to global)
        cfg_eur = await repo.resolve_chart_workspace_config("EURUSD")
        assert cfg_eur["preset_id"] == "trend_momentum"
        assert cfg_eur["timeframe"] == "H1"
        assert cfg_eur["scope"] == "global"

        # 6. Delete XAUUSD override -> falls back to global
        deleted = await repo.delete_preference(CHART_WORKSPACE_CATEGORY, "XAUUSD")
        assert deleted is True

        cfg_xau_fallback = await repo.resolve_chart_workspace_config("XAUUSD")
        assert cfg_xau_fallback["preset_id"] == "trend_momentum"
        assert cfg_xau_fallback["scope"] == "global"
    finally:
        await session.close()
        await engine.dispose()


# ==============================================================================
# 3. Headless Chart Generator & Vision Budget
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_configured_workspace_chart_and_vision_budget() -> None:
    """Render a multi-panel workspace chart and clamp bytes through VisionImageProcessor."""
    df = _create_synthetic_ohlcv_df(bars=40, seed=42)
    ohlcv_rows = [
        {
            "Date": idx.to_pydatetime(),
            "Open": float(row["open"]),
            "High": float(row["high"]),
            "Low": float(row["low"]),
            "Close": float(row["close"]),
            "Volume": float(row["volume"]),
        }
        for idx, row in df.iterrows()
    ]

    buf, saved_path = await generate_configured_workspace_chart_async(
        ohlcv_rows=ohlcv_rows,
        symbol="XAUUSD",
        timeframe="H4",
        workspace_config=CHART_WORKSPACE_PRESETS["quant_orderflow"],
        save_to_disk=False,
    )

    assert buf is not None
    assert isinstance(buf, io.BytesIO)
    raw_bytes = buf.getvalue()
    assert len(raw_bytes) > 0

    # Verify clamping through VisionImageProcessor
    clamped_bytes, mime_type = VisionImageProcessor.clamp_image_to_budget(raw_bytes)
    assert len(clamped_bytes) <= 262_144  # Max 256 KB budget
    assert mime_type in ("image/jpeg", "image/png")


# ==============================================================================
# 4. Multimodal LLM Harness & Providers
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_harness_multimodal_images_and_extra_context() -> None:
    """Verify AgentHarness.run_agent constructs list-based user message with multimodal images."""
    mock_llm = MagicMock()
    harness = AgentHarness(llm_client=mock_llm, settings={})

    mock_run_from_msgs = AsyncMock(return_value={"status": "completed"})
    harness.run_agent_from_messages = mock_run_from_msgs

    # 1. String user message + multimodal images + extra_context
    await harness.run_agent(
        session=None,
        system_prompt="Test system prompt",
        user_message="Analyze the setup on the chart",
        tools=[],
        multimodal_images=[{"media_type": "image/png", "data": "iVBORw0KGgo="}],
        extra_context="[SPECIALIST] Focus on order blocks and vwap",
    )

    assert mock_run_from_msgs.called
    call_kwargs = mock_run_from_msgs.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)

    # Check text block contains extra context
    text_blocks = [b for b in user_msg["content"] if b.get("type") == "text"]
    assert len(text_blocks) >= 1
    assert "Analyze the setup on the chart" in text_blocks[0]["text"]
    assert "[SPECIALIST]" in text_blocks[0]["text"]

    # Check image block has base64 source structure
    img_blocks = [b for b in user_msg["content"] if b.get("type") == "image"]
    assert len(img_blocks) == 1
    assert img_blocks[0]["source"]["type"] == "base64"
    assert img_blocks[0]["source"]["media_type"] == "image/png"
    assert img_blocks[0]["source"]["data"] == "iVBORw0KGgo="

    # 2. List user message + extra_context without TypeError
    list_user_msg = [{"type": "text", "text": "Initial text prompt"}]
    await harness.run_agent(
        session=None,
        system_prompt="System",
        user_message=list_user_msg,
        tools=[],
        extra_context="[SECONDARY CONTEXT]",
    )
    second_kwargs = mock_run_from_msgs.call_args.kwargs
    second_content = second_kwargs["messages"][0]["content"]
    assert isinstance(second_content, list)
    assert "[SECONDARY CONTEXT]" in second_content[0]["text"]


def test_openai_provider_normalize_messages_preserves_multimodal_image_blocks() -> None:
    """Verify OpenAIProvider._normalize_messages converts image block into OpenAI image_url format."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-test-dummy")

    raw_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect technical chart"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "aW1hZ2VkYXRhMTIz",
                    },
                },
            ],
        }
    ]

    normalized = provider._normalize_messages(raw_messages)
    assert len(normalized) == 1
    msg = normalized[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)

    # Find image_url block
    img_blocks = [b for b in msg["content"] if b.get("type") == "image_url"]
    assert len(img_blocks) == 1
    expected_url = "data:image/png;base64,aW1hZ2VkYXRhMTIz"
    assert img_blocks[0]["image_url"]["url"] == expected_url


# ==============================================================================
# 5. Stage 2 Services, Confluence & Grounding
# ==============================================================================


@pytest.mark.asyncio
async def test_technical_indicator_service_multi_tf_workspace_summary() -> None:
    """Verify TechnicalIndicatorService multi-TF workspace summary, bias, and figures."""
    engine, session = await _init_in_memory_session()
    try:
        now = datetime.now(UTC)
        bars: list[PriceOHLCV] = []
        tf_steps = {
            "D1": timedelta(days=1),
            "H4": timedelta(hours=4),
            "H1": timedelta(hours=1),
            "M15": timedelta(minutes=15),
        }

        # Seed strongly bullish trending bars across D1, H4, H1, M15
        for tf, delta in tf_steps.items():
            for i in range(60):
                ts = now - (60 - i) * delta
                p = 1.1000 + (i * 0.0010)
                bars.append(
                    PriceOHLCV(
                        symbol="EURUSD",
                        timeframe=tf,
                        timestamp=ts,
                        open=p - 0.0005,
                        high=p + 0.0010,
                        low=p - 0.0010,
                        close=p,
                        volume=1000.0,
                    )
                )
        session.add_all(bars)
        await session.commit()

        svc = TechnicalIndicatorService(session=session, settings={})
        summary = await svc.compute_multi_tf_workspace_summary(
            symbol="EURUSD",
            workspace_config=CHART_WORKSPACE_PRESETS["trend_momentum"],
        )

        assert summary["symbol"] == "EURUSD"
        assert summary["primary_timeframe"] == "H4"
        assert summary["overall_bias"] == "BULLISH"
        assert summary["confluence_adjustment"] in (1, 2)

        # Scoped and unscoped declared figures
        figures = summary["declared_figures"]
        assert "CLOSE" in figures
        assert "H4_CLOSE" in figures
        assert "D1_CLOSE" in figures
        assert "H1_CLOSE" in figures
        assert "M15_CLOSE" in figures

        # Formatted report
        report = summary["formatted_report"]
        assert "=== TECHNICAL INDICATOR WORKSPACE: EURUSD ===" in report
        assert "[Multi-TF Matrix]" in report
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_confluence_calculator_user_chart_workspace_alignment() -> None:
    """Verify calculate_confluence awards alignment points for BUY and divergence penalty for SELL."""
    engine, session = await _init_in_memory_session()
    try:
        now = datetime.now(UTC)
        bars: list[PriceOHLCV] = []
        for i in range(60):
            ts = now - (60 - i) * timedelta(hours=4)
            p = 2000.0 + (i * 2.0)
            bars.append(
                PriceOHLCV(
                    symbol="XAUUSD",
                    timeframe="H4",
                    timestamp=ts,
                    open=p - 1.0,
                    high=p + 2.0,
                    low=p - 2.0,
                    close=p,
                    volume=1000.0,
                )
            )
        session.add_all(bars)

        # Save user workspace preference
        repo = SqlAlchemyUserPreferenceRepository(session)
        await repo.set_preference(CHART_WORKSPACE_CATEGORY, "XAUUSD", CHART_WORKSPACE_PRESETS["trend_momentum"])
        await session.commit()

        # BUY proposal (aligned with bullish trend)
        buy_res = await calculate_confluence(
            session=session,
            symbol="XAUUSD",
            direction="BUY",
            entry_price=2120.0,
        )

        # SELL proposal (opposed to bullish trend)
        sell_res = await calculate_confluence(
            session=session,
            symbol="XAUUSD",
            direction="SELL",
            entry_price=2120.0,
        )

        assert buy_res["computed_score"] > sell_res["computed_score"]
        assert any("User Chart Workspace" in f and "Alignment" in f for f in buy_res["factors"]), (
            f"Factors: {buy_res['factors']}"
        )
        assert any("User Chart Workspace Divergence" in f for f in sell_res["factors"]), (
            f"Factors: {sell_res['factors']}"
        )

        # Divergence must NOT introduce a hard blocking issue
        assert not any("workspace" in iss.lower() for iss in sell_res["blocking_issues"])
    finally:
        await session.close()
        await engine.dispose()


def test_in_harness_grounding_extracts_user_chart_figures() -> None:
    """Verify extract_verified_anchors extracts user_chart_figures from data_bundle."""
    data_bundle: dict[str, Any] = {
        "current_price": 2050.25,
        "atr_14": 12.5,
        "user_chart_workspace": {
            "declared_figures": {
                "CLOSE": 2050.25,
                "EMA_20": 2045.10,
                "EMA_50": 2030.00,
                "RSI_14": 68.5,
                "VWAP": 2048.00,
                "INVALID_NAN": float("nan"),
                "BOOL_SKIP": True,
            }
        },
    }

    anchors = extract_verified_anchors(data_bundle)
    assert anchors["current_price"] == 2050.25
    assert anchors["atr_14"] == 12.5

    assert "user_chart_figures" in anchors
    figs = anchors["user_chart_figures"]
    assert figs["CLOSE"] == 2050.25
    assert figs["EMA_20"] == 2045.10
    assert figs["RSI_14"] == 68.5
    assert "INVALID_NAN" not in figs
    assert "BOOL_SKIP" not in figs


# ==============================================================================
# 6. FastAPI Chart Config & Workspace Endpoints
# ==============================================================================


@pytest.mark.asyncio
async def test_fastapi_chart_config_and_workspace_endpoints() -> None:
    """Verify GET/PUT/DELETE chart-config and GET chart-workspace endpoints."""
    engine, session = await _init_in_memory_session()
    try:
        mock_req = MagicMock(spec=Request)
        mock_req.state = MagicMock()
        mock_req.state.role = Role.VIEWER
        mock_req.state.is_localhost = False

        # 1. GET /api/v1/market/chart-config
        bundle_resp = await get_chart_workspace_config_bundle(request=mock_req, session=session)
        assert "global" in bundle_resp
        assert "symbols" in bundle_resp
        assert "presets" in bundle_resp
        assert "updated_at" in bundle_resp

        # 2. PUT /api/v1/market/chart-config (save XAUUSD override)
        save_req = ChartConfigSaveRequest(
            scope="symbol",
            symbol="XAUUSD",
            config={"preset_id": "quant_orderflow", "timeframe": "H1"},
        )
        save_resp = await save_chart_workspace_config(payload=save_req, request=mock_req, session=session)
        assert save_resp["status"] == "ok"
        assert save_resp["scope"] == "symbol"
        assert save_resp["symbol"] == "XAUUSD"
        assert save_resp["config"]["preset_id"] == "quant_orderflow"

        # Verify XAUUSD in symbols bundle
        bundle_resp2 = await get_chart_workspace_config_bundle(request=mock_req, session=session)
        assert "XAUUSD" in bundle_resp2["symbols"]

        # 3. DELETE /api/v1/market/chart-config/XAUUSD
        del_resp = await delete_chart_workspace_override(symbol="XAUUSD", request=mock_req, session=session)
        assert del_resp["status"] == "ok"
        assert del_resp["symbol"] == "XAUUSD"

        # Verify XAUUSD no longer in symbols bundle
        bundle_resp3 = await get_chart_workspace_config_bundle(request=mock_req, session=session)
        assert "XAUUSD" not in bundle_resp3["symbols"]

        # 4. GET /api/v1/market/chart-workspace/EURUSD?timeframe=H4&count=60
        ws_resp = await get_chart_workspace(
            symbol="EURUSD",
            request=mock_req,
            timeframe="H4",
            count=60,
            session=session,
        )
        assert ws_resp["symbol"] == "EURUSD"
        assert ws_resp["timeframe"] == "H4"
        assert len(ws_resp["candles"]) > 0
        assert "workspace_config" in ws_resp
        assert "indicator_series" in ws_resp
        assert "indicator_summary" in ws_resp
        assert "structure" in ws_resp
    finally:
        await session.close()
        await engine.dispose()
