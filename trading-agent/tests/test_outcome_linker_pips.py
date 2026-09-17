# ==============================================================================
# File: tests/test_outcome_linker_pips.py
# ==============================================================================

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

from risk.position_sizing import get_instrument_spec
from analysis.memory.outcome_linker import OutcomeLinker
from database.models import PriceOHLCV


def test_get_instrument_spec_precision():
    """Verify dynamic pip size and contract values for diverse asset classes."""
    eur_spec = get_instrument_spec("EURUSD")
    assert eur_spec.pip_size == 0.0001

    jpy_spec = get_instrument_spec("USDJPY")
    assert jpy_spec.pip_size == 0.01

    gold_spec = get_instrument_spec("XAUUSD")
    assert gold_spec.pip_size == 0.01

    btc_spec = get_instrument_spec("BTCUSD")
    assert btc_spec.pip_size == 1.0


def test_whatif_pips_calculation_multi_asset():
    """Verify pips calculation without hardcoded 10,000 multipliers."""
    # 1. EURUSD Buy: 1.0850 -> 1.0900 (+0.0050)
    eur_spec = get_instrument_spec("EURUSD")
    eur_diff_pips = ((1.0900 - 1.0850) / eur_spec.pip_size) * 1
    assert round(eur_diff_pips, 1) == 50.0

    # 2. XAUUSD Buy: 2500.00 -> 2510.00 (+10.00)
    gold_spec = get_instrument_spec("XAUUSD")
    gold_diff_pips = ((2510.00 - 2500.00) / gold_spec.pip_size) * 1
    assert round(gold_diff_pips, 1) == 1000.0  # Was previously corrupted to 100,000 with 10000x multiplier

    # 3. BTCUSD Buy: 60,000 -> 61,000 (+1000)
    btc_spec = get_instrument_spec("BTCUSD")
    btc_diff_pips = ((61000.0 - 60000.0) / btc_spec.pip_size) * 1
    assert round(btc_diff_pips, 1) == 1000.0  # Was previously corrupted to 10,000,000 with 10000x multiplier


@pytest.mark.asyncio
async def test_path_dependent_sl_hit_first():
    """Verify path-dependent evaluation correctly flags SL when low hits SL before high hits TP."""
    linker = OutcomeLinker()
    now = datetime.now(timezone.utc)
    symbol = "EURUSD"
    entry_price = 1.1000
    sl = 1.0950
    tp = 1.1100

    # Mock bars: first bar dips below SL, second bar rallies to TP
    bar1 = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now + timedelta(hours=1),
        open=1.1000,
        high=1.1020,
        low=1.0940,  # Below SL (1.0950)
        close=1.0960,
        volume=100.0
    )
    bar2 = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now + timedelta(hours=2),
        open=1.0960,
        high=1.1150,  # Above TP (1.1100)
        low=1.0955,
        close=1.1120,
        volume=120.0
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bar1, bar2]
    mock_session.execute.return_value = mock_result

    sl_hit, tp_hit = await linker._check_path_dependent_outcome(
        session=mock_session,
        symbol=symbol,
        start_time=now,
        end_time=now + timedelta(hours=24),
        entry_price=entry_price,
        proposed_sl=sl,
        proposed_tp=tp,
        direction=1,
        pip_size=0.0001
    )

    assert sl_hit is True
    assert tp_hit is False


@pytest.mark.asyncio
async def test_path_dependent_tp_hit_first():
    """Verify path-dependent evaluation correctly flags TP when high hits TP before low hits SL."""
    linker = OutcomeLinker()
    now = datetime.now(timezone.utc)
    symbol = "EURUSD"
    entry_price = 1.1000
    sl = 1.0950
    tp = 1.1100

    bar1 = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now + timedelta(hours=1),
        open=1.1000,
        high=1.1120,  # Above TP (1.1100)
        low=1.0980,
        close=1.1110,
        volume=150.0
    )
    bar2 = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now + timedelta(hours=2),
        open=1.1110,
        high=1.1130,
        low=1.0940,  # Below SL (1.0950) later
        close=1.0950,
        volume=80.0
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bar1, bar2]
    mock_session.execute.return_value = mock_result

    sl_hit, tp_hit = await linker._check_path_dependent_outcome(
        session=mock_session,
        symbol=symbol,
        start_time=now,
        end_time=now + timedelta(hours=24),
        entry_price=entry_price,
        proposed_sl=sl,
        proposed_tp=tp,
        direction=1,
        pip_size=0.0001
    )

    assert sl_hit is False
    assert tp_hit is True


@pytest.mark.asyncio
async def test_path_dependent_zero_or_inverted_sl_fallback():
    """Verify that zero or inverted SL does not falsely trigger instant SL hit on SELL trades."""
    linker = OutcomeLinker()
    now = datetime.now(timezone.utc)
    symbol = "EURUSD"
    entry_price = 1.1000

    # Candle that moves normally (1.0990 to 1.1010)
    bar = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now + timedelta(hours=1),
        open=1.1000,
        high=1.1010,
        low=1.0990,
        close=1.0995,
        volume=100.0
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bar]
    mock_session.execute.return_value = mock_result

    # SELL with proposed_sl = 0.0: should NOT hit SL because fallback SL is entry + 50 pips = 1.1050
    sl_hit, tp_hit = await linker._check_path_dependent_outcome(
        session=mock_session,
        symbol=symbol,
        start_time=now,
        end_time=now + timedelta(hours=24),
        entry_price=entry_price,
        proposed_sl=0.0,
        proposed_tp=0.0,
        direction=-1,  # SELL
        pip_size=0.0001
    )

    assert sl_hit is False, "Zero SL must not falsely trigger hit on SELL bar"
    assert tp_hit is False


@pytest.mark.asyncio
async def test_path_dependent_timeframe_h1_filter():
    """Verify that _check_path_dependent_outcome queries specifically filter for H1 timeframe."""
    linker = OutcomeLinker()
    now = datetime.now(timezone.utc)
    symbol = "EURUSD"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    await linker._check_path_dependent_outcome(
        session=mock_session,
        symbol=symbol,
        start_time=now,
        end_time=now + timedelta(hours=24),
        entry_price=1.1000,
        proposed_sl=1.0950,
        proposed_tp=1.1100,
        direction=1,
        pip_size=0.0001,
    )

    assert mock_session.execute.called
    stmt = mock_session.execute.call_args[0][0]
    compiled_stmt = str(stmt)
    assert "price_ohlcv.timeframe =" in compiled_stmt


@pytest.mark.asyncio
async def test_process_paper_whatifs_timeframe_h1_filter():
    """Verify that process_paper_whatifs queries PriceOHLCV strictly with timeframe == 'H1'."""
    from database.models import DecisionReflection, AssetAnalysis
    from unittest.mock import patch

    linker = OutcomeLinker()
    now = datetime.now(timezone.utc)
    symbol = "EURUSD"

    reflection = MagicMock(spec=DecisionReflection)
    reflection.id = 101
    reflection.symbol = symbol
    reflection.decision = "BUY"
    reflection.whatif_entry_price = 1.1000
    reflection.status = "pending_whatif"

    analysis = MagicMock(spec=AssetAnalysis)
    analysis.id = 202
    analysis.generated_at = now - timedelta(hours=25)
    analysis.price_24h_after = None
    analysis.stop_loss = 1.0950
    analysis.take_profit = 1.1100

    bar = PriceOHLCV(
        symbol=symbol,
        timeframe="H1",
        timestamp=now,
        open=1.1050,
        high=1.1080,
        low=1.1040,
        close=1.1060,
        volume=100.0,
    )

    # Sequence of queries:
    # 1. Main join query for reflections
    # 2. Target 24h bar query -> returns bar
    mock_session = AsyncMock()
    
    mock_res_main = MagicMock()
    mock_res_main.all.return_value = [(reflection, analysis)]

    mock_res_bar = MagicMock()
    mock_res_bar.scalar_one_or_none.return_value = bar

    mock_session.execute.side_effect = [mock_res_main, mock_res_bar]

    with patch.object(linker, "_check_path_dependent_outcome", new_callable=AsyncMock, return_value=(False, True)), \
         patch("analysis.memory.outcome_linker.AlphaCalculator") as mock_calc_cls, \
         patch.object(linker.reflector, "reflect_on_trade", new_callable=AsyncMock):
        
        mock_calc = MagicMock()
        mock_calc.calculate_alpha = AsyncMock(return_value={
            "benchmark_name": "DXY", "benchmark_return": 0.1, "alpha_return": 0.5
        })
        mock_calc_cls.return_value = mock_calc

        await linker.process_paper_whatifs(session=mock_session)

    # Verify that the PriceOHLCV query (second execute call) included timeframe == 'H1'
    assert mock_session.execute.call_count >= 2
    bar_stmt = mock_session.execute.call_args_list[1][0][0]
    compiled_bar_stmt = str(bar_stmt)
    assert "price_ohlcv.timeframe =" in compiled_bar_stmt
    assert "price_ohlcv.symbol =" in compiled_bar_stmt



