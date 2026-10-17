import pytest
from unittest.mock import AsyncMock, patch

from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.stages.per_asset.context_builder import (
    SPECIALIST_PROMPTS,
    _render_specialist_prompt,
)
from monika.application.analysis.stages.per_asset.specialist_pipeline import (
    SpecialistPipeline,
)
from monika.application.analysis.tools.domain.macro_handlers import (
    MacroToolHandlers,
)
from monika.application.analysis.tools.domain.technical_handlers import (
    TechnicalToolHandlers,
)
from monika.application.analysis.tools.handlers.macro.sentiment_commodities import (
    COT_CODE_TO_NAME,
    handle_get_cot_report,
)
from monika.domain.indicators.technical import TechnicalIndicatorCalculator
from monika.infrastructure.llm.prompt_compressor import PromptBundleCompressor


# --------------------------------------------------------------------------
# 1. Plumbing & Data Handlers Tests
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_atr_resolves_atr_14(mock_async_session):
    handlers = TechnicalToolHandlers()
    mock_calc = AsyncMock()
    mock_calc.get_snapshot.return_value = {"ATR_14": {"value": 1.25, "direction": "rising"}}
    with patch(
        "monika.domain.indicators.technical.TechnicalIndicatorCalculator",
        return_value=mock_calc,
    ):
        res = await handlers.get_atr(symbol="EURUSD", timeframe="H4", period=14, session=mock_async_session)
        assert res["atr"] == 1.25
        assert res["symbol"] == "EURUSD"
        assert res["period"] == 14


@pytest.mark.asyncio
async def test_get_structure_breaks_formatting(mock_async_session):
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    handlers = TechnicalToolHandlers()
    mock_break = MagicMock()
    mock_break.type = "BOS"
    mock_break.direction = "bullish"
    mock_break.price = 1.1250
    mock_break.broken_price = 1.1200
    mock_break.formed_at = datetime.now(timezone.utc)

    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.all.return_value = [mock_break]
    mock_async_session.execute = AsyncMock(return_value=mock_exec_res)

    res = await handlers.get_structure_breaks(symbol="EURUSD", timeframe="H4", session=mock_async_session)
    assert res["symbol"] == "EURUSD"
    assert len(res["breaks"]) == 1
    assert res["breaks"][0]["type"] == "BOS"


@pytest.mark.asyncio
async def test_get_price_history_limit_honored(mock_async_session):
    handlers = TechnicalToolHandlers()
    mock_client = AsyncMock()

    async def mock_get_rates(symbol, timeframe, count):
        return [{"time": f"2026-10-{i:02d}", "close": 1.10} for i in range(count)]

    mock_client.get_rates = AsyncMock(side_effect=mock_get_rates)
    with patch(
        "monika.infrastructure.brokers.mt5_client.get_mt5_client",
        return_value=mock_client,
    ):
        res = await handlers.get_price_history(symbol="EURUSD", timeframe="H4", limit=25, session=mock_async_session)
        assert len(res) == 25


def test_cot_code_to_name_mapping():
    assert COT_CODE_TO_NAME["088691"] == "GOLD (Precious Metal)"
    assert COT_CODE_TO_NAME["067651"] == "WTI CRUDE OIL (Energy Commodity)"
    assert COT_CODE_TO_NAME["099741"] == "EUR (Euro FX)"
    assert COT_CODE_TO_NAME["096742"] == "GBP (British Pound)"
    assert COT_CODE_TO_NAME["097741"] == "JPY (Japanese Yen)"
    assert COT_CODE_TO_NAME["232741"] == "AUD (Australian Dollar)"


# --------------------------------------------------------------------------
# 2. Anti-Truncation & Prompt Compressor Tests
# --------------------------------------------------------------------------
def test_prompt_compressor_no_destructive_summarized():
    compressor = PromptBundleCompressor({})
    long_text = "Detailed macro fundamental analysis text without truncation. " * 30
    payload = {"macro_analysis": long_text}
    compressed = compressor.compress_stage2_dict(payload, max_tokens=1000)
    assert "... [summarized]" not in compressed
    assert len(compressed) > 0


def test_prompt_compressor_64k_default():
    compressor = PromptBundleCompressor({})
    test_bundle = "A" * 50000
    res = compressor.compress_stage2_bundle(test_bundle, symbol="EURUSD", max_tokens=64000)
    assert len(res) == 50000


# --------------------------------------------------------------------------
# 3. Stage 2 Prefetcher Structural Tests
# --------------------------------------------------------------------------
def test_compress_history_handles_both_list_and_dict(mock_async_session):
    bundler = Stage2DataBundler(mock_async_session)
    # 1. Dict format
    dict_history = {
        "bars": [{"time": "2026-10-10T12:00:00Z", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100}]
    }
    csv_dict = bundler._compress_history(dict_history, "EURUSD")
    assert "time,O,H,L,C,V" in csv_dict
    assert "1.15" in csv_dict

    # 2. List format
    list_history = [
        {"time": "2026-10-10T12:00:00Z", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100}
    ]
    csv_list = bundler._compress_history(list_history, "EURUSD")
    assert "time,O,H,L,C,V" in csv_list
    assert "1.15" in csv_list


@pytest.mark.asyncio
async def test_prefetch_auto_populates_cot_and_asset_sentiments(mock_async_session):
    bundler = Stage2DataBundler(mock_async_session)

    executed_tools = {}

    async def mock_execute(tool_name, inp):
        executed_tools[tool_name] = inp
        if tool_name == "get_cot_report":
            return {"market_codes": inp.get("market_codes"), "reports": [{"market_name": "WTI CRUDE OIL"}]}
        if tool_name == "get_structure_breaks":
            return {"breaks": []}
        if tool_name == "get_smc_zones":
            return {"zones": []}
        return {"data": "ok"}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    with (
        patch(
            "monika.application.analysis.validators.core_data_validator.CoreDataValidator.validate_and_fetch_core_data",
            new_callable=AsyncMock,
        ) as mock_val,
        patch("monika.core.validation.data_validator.validate_data_freshness", new_callable=AsyncMock) as mock_fresh,
        patch("monika.core.validation.data_validator.check_data_coherence", new_callable=AsyncMock) as mock_coh,
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
        ) as mock_tfm,
    ):
        mock_val.return_value = (True, {}, [])
        mock_fresh.return_value = {"ready": True, "errors": [], "warnings": []}
        mock_coh.return_value = {"coherent": True, "issues": []}
        mock_tfm.return_value = None

        # Test XTIUSD: auto-populates COT 067651 and fetches eia_oil_inventory
        _, data = await bundler.fetch_bundle("XTIUSD")
        assert "get_cot_report" in executed_tools
        assert executed_tools["get_cot_report"]["market_codes"] == ["067651"]
        assert "get_eia_oil_inventory" in executed_tools
        assert "structure_breaks_D1" in data
        assert "smc_zones_D1" in data

        # Test BTCUSD: fetches fear_greed_index and funding_rate, skips COT
        executed_tools.clear()
        _, data_btc = await bundler.fetch_bundle("BTCUSD")
        assert "get_fear_greed_index" in executed_tools
        assert "get_funding_rate" in executed_tools
        assert "cot_report" not in data_btc


# --------------------------------------------------------------------------
# 4. Specialist Prompts, Key Slicing, and Best Entry Zone
# --------------------------------------------------------------------------
def test_specialist_prompts_and_quantitative_guide():
    rendered_tech = _render_specialist_prompt(SPECIALIST_PROMPTS["technical"], "EURUSD", "EUR", "USD")
    rendered_sent = _render_specialist_prompt(SPECIALIST_PROMPTS["sentiment"], "XTIUSD", "XTI", "USD")
    rendered_macro = _render_specialist_prompt(SPECIALIST_PROMPTS["macro"], "XAUUSD", "XAU", "USD")

    # Technical Specialist checks
    assert "recommended_entry_zone" in rendered_tech
    assert "AC1_20" in rendered_tech
    assert "ADX_14" in rendered_tech
    assert "YANG_ZHANG_VOL_20" in rendered_tech
    assert "target asset" in rendered_tech.lower()
    assert "{symbol}" not in rendered_tech

    # Sentiment Specialist checks
    assert "EIA Crude Oil Inventory" in rendered_sent
    assert "WTI CRUDE OIL" in rendered_sent
    assert "XTIUSD" in rendered_sent

    # Macro Specialist checks
    assert "US 10Y TIPS Real Yields" in rendered_macro
    assert "XAUUSD" in rendered_macro


def test_specialist_pipeline_slice_mapping():
    pipeline = SpecialistPipeline()
    sample_data = {
        "active_playbook_id": "PB-SMC-01",
        "playbook_screening": {"signal": "valid"},
        "eia_oil_inventory": {"draw": -2.0},
        "market_regime": "trending",
    }
    tech_view = pipeline._build_structured_specialist_view(sample_data, "technical")
    assert "active_playbook_id" in tech_view
    assert "playbook_screening" in tech_view

    sent_view = pipeline._build_structured_specialist_view(sample_data, "sentiment")
    assert "eia_oil_inventory" in sent_view


# --------------------------------------------------------------------------
# 5. Technical Indicators Series Depth
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_technical_indicator_series_depth_contract(mock_async_session):
    calc = TechnicalIndicatorCalculator(mock_async_session, {})
    with patch.object(calc, "get_snapshot") as mock_snap:
        mock_snap.return_value = {
            "RSI_14": {
                "value": 55.0,
                "prev": 53.0,
                "delta": 2.0,
                "direction": "rising",
                "series": [45.0, 48.0, 50.0, 53.0, 55.0],
            }
        }
        snap = await calc.get_snapshot("EURUSD", "H4", series_depth=15)
        rsi = snap["RSI_14"]
        assert len(rsi["series"]) == 5
        assert rsi["direction"] == "rising"
