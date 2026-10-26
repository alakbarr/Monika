import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import (
    COTReport,
    DXYData,
    FedWatchProbability,
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

logger = logging.getLogger("TradingAgent.ConfluenceCalculator")

from datetime import datetime, timezone
from typing import Optional

import monika.core.primitives.clock as clock
from monika.core.calibration.cot_thresholds import cot_extreme_score
from monika.domain.market.instrument_identity import SYMBOL_TO_COT_MAP, get_cot_code_for_symbol

SYMBOL_TO_COT_CODE = dict(SYMBOL_TO_COT_MAP)


async def _get_cot_alignment_value(session, symbol: str, as_of: Optional[datetime] = None):
    """Return cot_extreme_score() result (-1 extreme_long, 0 normal, +1 extreme_short)
    if COT data is fresh (<=10 days), else None (unknown -> tidak dinilai, fail-neutral)."""
    cot_code = get_cot_code_for_symbol(symbol) or SYMBOL_TO_COT_CODE.get(symbol)
    if not cot_code:
        return None
    stmt = select(COTReport).where(COTReport.market_code == cot_code)
    if as_of:
        stmt = stmt.where(COTReport.report_date <= as_of)
    stmt = stmt.order_by(COTReport.report_date.desc()).limit(1)
    cot_row = (await session.execute(stmt)).scalar_one_or_none()
    if not cot_row or not getattr(cot_row, "report_date", None):
        return None
    now = as_of or clock.now()
    report_date = cot_row.report_date
    if report_date.tzinfo is None:
        report_date = report_date.replace(tzinfo=timezone.utc)
    if (now - report_date).days > 10:
        return None
    total = cot_row.leveraged_long + cot_row.leveraged_short
    if total <= 0:
        return None
    percentile = cot_row.leveraged_long / total * 100
    return cot_extreme_score(symbol, percentile)


async def calculate_priced_in_subscores(session: AsyncSession, symbol: str, as_of: Optional[datetime] = None) -> dict:
    """
    Hitung otomatis Method 1 (FedWatch), Method 2 (COT extreme), Method 3 (price momentum vs ATR).
    Mengembalikan sub-skor.
    """
    scores = {"fedwatch": 0, "cot": 0, "momentum": 0, "total_auto": 0}

    # 1. FedWatch (0-3)
    fw_stmt = select(FedWatchProbability)
    if as_of:
        fw_stmt = fw_stmt.where(FedWatchProbability.fetched_at <= as_of)
    fw_stmt = fw_stmt.order_by(FedWatchProbability.fetched_at.desc()).limit(1)
    fedwatch_row = (await session.execute(fw_stmt)).scalar_one_or_none()

    if fedwatch_row and fedwatch_row.probabilities_json:
        try:
            probs_data = json.loads(fedwatch_row.probabilities_json)
            raw_probs = probs_data.get("probabilities", probs_data) if isinstance(probs_data, dict) else {}
            max_prob = 0.0
            for k, v in raw_probs.items():
                if isinstance(v, (int, float)) and v > max_prob:
                    max_prob = float(v)
                elif isinstance(v, dict) and isinstance(v.get("probability"), (int, float)):
                    p_val = float(v["probability"])
                    if p_val > max_prob:
                        max_prob = p_val
            if max_prob > 85:
                scores["fedwatch"] = 3
            elif max_prob > 70:
                scores["fedwatch"] = 2
            elif max_prob > 50:
                scores["fedwatch"] = 1
        except Exception as e:
            logger.debug(f"Confluence fedwatch sub-calculation skipped: {e}")

    # 2. COT Extreme (0-3)
    cot_code = get_cot_code_for_symbol(symbol) or SYMBOL_TO_COT_CODE.get(symbol)

    if cot_code:
        cot_stmt = select(COTReport).where(COTReport.market_code == cot_code)
        if as_of:
            cot_stmt = cot_stmt.where(COTReport.report_date <= as_of)
        cot_stmt = cot_stmt.order_by(COTReport.report_date.desc()).limit(1)
        cot_row = (await session.execute(cot_stmt)).scalar_one_or_none()

        if cot_row:
            # Tambahkan age check — COT > 14 hari tidak reliable untuk priced-in
            now = as_of or clock.now()
            report_date_tz = cot_row.report_date
            if report_date_tz.tzinfo is None:
                report_date_tz = report_date_tz.replace(tzinfo=timezone.utc)
            days_old = (now - report_date_tz).days

            if days_old <= 7:  # Hanya COT fresh (max 1 minggu) yang valid
                cot_weight = 1.0 if days_old <= 3 else 0.5
                total = cot_row.leveraged_long + cot_row.leveraged_short
                if total > 0:
                    percentile = (cot_row.leveraged_long / total) * 100
                    extreme = cot_extreme_score(symbol, percentile)
                    if extreme != 0:
                        scores["cot"] = int(round(3 * cot_weight))
                    else:
                        ratio = abs(cot_row.leveraged_long - cot_row.leveraged_short) / total
                        raw_score = 2 if ratio > 0.5 else 1 if ratio > 0.3 else 0
                        scores["cot"] = int(round(raw_score * cot_weight))
            else:
                scores["cot"] = 0  # COT > 7 hari tidak dihitung

    # 3. Price Momentum vs ATR (0-3)
    atr_stmt = (
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.timeframe == "D1")
        .where(TechnicalIndicator.indicator_name == "ATR_14")
    )
    if as_of:
        atr_stmt = atr_stmt.where(TechnicalIndicator.timestamp <= as_of)
    atr_stmt = atr_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    atr_row = (await session.execute(atr_stmt)).scalar_one_or_none()

    price_stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol).where(PriceOHLCV.timeframe == "D1")
    if as_of:
        price_stmt = price_stmt.where(PriceOHLCV.timestamp <= as_of)
    price_stmt = price_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(20)
    prices = (await session.execute(price_stmt)).scalars().all()

    if atr_row and len(prices) >= 20:
        try:
            atr_val = 0
            raw_atr = json.loads(atr_row.value_json)
            if isinstance(raw_atr, dict):
                atr_val = float(raw_atr.get("atr", raw_atr.get("value", 0)))
            else:
                atr_val = float(raw_atr)

            if atr_val > 0:
                high_20 = max(p.high for p in prices)
                low_20 = min(p.low for p in prices)
                run_up = high_20 - low_20
                ratio = run_up / atr_val

                if ratio > 5:
                    scores["momentum"] = 3
                elif ratio > 3:
                    scores["momentum"] = 2
                elif ratio > 2:
                    scores["momentum"] = 1
        except Exception as e:
            logger.debug(f"Confluence momentum sub-calculation skipped: {e}")

    scores["total_auto"] = scores["fedwatch"] + scores["cot"] + scores["momentum"]
    return scores


async def calculate_confluence(
    session: AsyncSession,
    symbol: str,
    direction: Optional[str] = None,
    entry_price: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    settings: Optional[dict] = None,
    as_of: Optional[datetime] = None,
    confluence_factors: Optional[list[str]] = None,
) -> dict:
    """
    Menghitung confluence score secara deterministik.
    Jika direction/entry_price tidak diberikan (pre-hoc bundler),
    mengembalikan skor potensial untuk BUY dan SELL berdasarkan current price.
    """
    from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

    settings = settings or {}
    as_of = as_of or clock.get_simulated_now()
    risk_cfg = settings.get("trading", {}).get("risk", {})
    min_rr_ratio = float(risk_cfg.get("min_rr_ratio", 1.5))
    intraday_min_sl_atr_mult = float(risk_cfg.get("intraday_min_sl_atr_multiplier", 1.0))
    adr_ctx = await compute_daily_range_context(session, symbol, settings, as_of=as_of)

    # 1. Fetch data with look-ahead bias immunity (bar duration offsets)
    from datetime import timedelta

    h4_cutoff = (as_of - timedelta(hours=4)) if as_of else None
    d1_cutoff = (as_of - timedelta(days=1)) if as_of else None

    # ATR (H4)
    atr_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == "H4",
        TechnicalIndicator.indicator_name == "ATR_14",
    )
    if h4_cutoff:
        atr_stmt = atr_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    atr_stmt = atr_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    atr_row = (await session.execute(atr_stmt)).scalar_one_or_none()

    atr_val = 0
    if atr_row:
        atr_data = json.loads(atr_row.value_json)
        if isinstance(atr_data, dict):
            atr_val = float(atr_data.get("atr", 0) or atr_data.get("value", 0))
        else:
            atr_val = float(atr_data or 0)

    # RSI (H4)
    rsi_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == "H4",
        TechnicalIndicator.indicator_name == "RSI_14",
    )
    if h4_cutoff:
        rsi_stmt = rsi_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    rsi_stmt = rsi_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    rsi_row = (await session.execute(rsi_stmt)).scalar_one_or_none()

    rsi_val = None
    if rsi_row:
        try:
            rsi_data = json.loads(rsi_row.value_json)
            rsi_val = float(rsi_data.get("rsi", 50))
        except Exception as e:
            logger.debug(f"Confluence RSI sub-calculation skipped: {e}")

    # EMA 20 & EMA 50 (H4/H1) for trend continuation
    ema20_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe.in_(["H4", "H1"]),
        TechnicalIndicator.indicator_name == "EMA_20",
    )
    if h4_cutoff:
        ema20_stmt = ema20_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    ema20_row = (
        await session.execute(ema20_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1))
    ).scalar_one_or_none()
    ema20_val = None
    if ema20_row and ema20_row.value_json:
        try:
            d = json.loads(ema20_row.value_json)
            ema20_val = float(d.get("value", d.get("ema", 0.0)))
        except Exception as e:
            logger.debug(f"Confluence EMA20 sub-calculation skipped: {e}")

    ema50_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe.in_(["H4", "H1"]),
        TechnicalIndicator.indicator_name == "EMA_50",
    )
    if h4_cutoff:
        ema50_stmt = ema50_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    ema50_row = (
        await session.execute(ema50_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1))
    ).scalar_one_or_none()
    ema50_val = None
    if ema50_row and ema50_row.value_json:
        try:
            d = json.loads(ema50_row.value_json)
            ema50_val = float(d.get("value", d.get("ema", 0.0)))
        except Exception as e:
            logger.debug(f"Confluence EMA50 sub-calculation skipped: {e}")

    # Recent H4 bars for volume expansion & breakout levels
    recent_h4_stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "H4")
    if h4_cutoff:
        recent_h4_stmt = recent_h4_stmt.where(PriceOHLCV.timestamp <= h4_cutoff)
    recent_h4_bars = (
        (await session.execute(recent_h4_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(20))).scalars().all()
    )

    # D1 & H4 Structure
    d1_stmt = select(StructureBreak).where(StructureBreak.symbol == symbol, StructureBreak.timeframe == "D1")
    if d1_cutoff:
        d1_stmt = d1_stmt.where(StructureBreak.formed_at <= d1_cutoff)
    d1_stmt = d1_stmt.order_by(StructureBreak.formed_at.desc()).limit(1)
    d1_breaks = (await session.execute(d1_stmt)).scalars().first()

    h4_sb_stmt = select(StructureBreak).where(StructureBreak.symbol == symbol, StructureBreak.timeframe == "H4")
    if h4_cutoff:
        h4_sb_stmt = h4_sb_stmt.where(StructureBreak.formed_at <= h4_cutoff)
    h4_sb_stmt = h4_sb_stmt.order_by(StructureBreak.formed_at.desc()).limit(1)
    h4_breaks = (await session.execute(h4_sb_stmt)).scalars().first()

    # FVG (H4)
    fvg_stmt = select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == "H4")
    if h4_cutoff:
        fvg_stmt = fvg_stmt.where(FVGZone.formed_at <= h4_cutoff).where(
            or_(FVGZone.filled_at.is_(None), FVGZone.filled_at > as_of)
        )
    else:
        fvg_stmt = fvg_stmt.where(FVGZone.filled_at.is_(None))
    fvg_stmt = fvg_stmt.order_by(FVGZone.formed_at.desc()).limit(5)
    fvgs = (await session.execute(fvg_stmt)).scalars().all()

    # OB (H4)
    ob_stmt = select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == "H4")
    if h4_cutoff:
        ob_stmt = ob_stmt.where(OrderBlock.formed_at <= h4_cutoff).where(
            or_(OrderBlock.mitigated_at.is_(None), OrderBlock.mitigated_at > as_of)
        )
    else:
        ob_stmt = ob_stmt.where(OrderBlock.mitigated_at.is_(None))
    ob_stmt = ob_stmt.order_by(OrderBlock.formed_at.desc()).limit(5)
    obs = (await session.execute(ob_stmt)).scalars().all()

    # VIX
    vix_stmt = select(VIXData)
    if as_of:
        vix_stmt = vix_stmt.where(VIXData.date < as_of.date())
    vix_stmt = vix_stmt.order_by(VIXData.date.desc()).limit(1)
    vix_row = (await session.execute(vix_stmt)).scalar_one_or_none()

    # Fundamental Brief
    brief_stmt = select(FundamentalBrief)
    if as_of:
        brief_stmt = brief_stmt.where(FundamentalBrief.generated_at <= as_of)
    brief_stmt = brief_stmt.order_by(FundamentalBrief.generated_at.desc()).limit(1)
    brief = (await session.execute(brief_stmt)).scalar_one_or_none()

    # DXY
    dxy_stmt = select(DXYData)
    if as_of:
        dxy_stmt = dxy_stmt.where(DXYData.date < as_of.date())
    dxy_stmt = dxy_stmt.order_by(DXYData.date.desc()).limit(5)
    dxy = (await session.execute(dxy_stmt)).scalars().all()
    dxy_trend = "unknown"
    if len(dxy) >= 5:
        if dxy[0].close > dxy[4].close:
            dxy_trend = "strengthening"
        else:
            dxy_trend = "weakening"
    # S/R Zones
    sr_stmt = select(SRZone).where(SRZone.symbol == symbol, SRZone.timeframe.in_(["H4", "D1"]))
    if as_of:
        sr_stmt = sr_stmt.where(SRZone.last_touched <= (h4_cutoff or as_of))
    sr_zones = (await session.execute(sr_stmt)).scalars().all()

    # Swing Points for OTE
    swings_stmt = select(SwingPoint).where(SwingPoint.symbol == symbol, SwingPoint.timeframe == "H4")
    if h4_cutoff:
        swings_stmt = swings_stmt.where(SwingPoint.timestamp <= h4_cutoff)
    if as_of:
        swings_stmt = swings_stmt.where(SwingPoint.timestamp <= as_of)
    swings_stmt = swings_stmt.order_by(SwingPoint.timestamp.desc()).limit(2)
    recent_swings = (await session.execute(swings_stmt)).scalars().all()

    cot_alignment_val = await _get_cot_alignment_value(session, symbol, as_of=as_of)

    from monika.application.analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep

    sweep_result = await detect_liquidity_sweep(session, symbol, settings or {}, as_of=as_of)

    # Microstructure Order Flow Snapshot (F11)
    of_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol, TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT"
    )
    if as_of:
        of_stmt = of_stmt.where(TechnicalIndicator.timestamp <= as_of)
    of_stmt = of_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    of_row = (await session.execute(of_stmt)).scalar_one_or_none()
    of_data = {}
    if of_row and of_row.value_json:
        try:
            of_data = json.loads(of_row.value_json)
        except Exception:
            of_data = {}

    # Quant Strategy Edge Signals
    quant_signals = []
    try:
        from monika.application.analysis.strategies.registry import StrategyRegistry

        quant_signals = await StrategyRegistry.evaluate_all(
            session=session, symbol=symbol, settings=settings, as_of=as_of
        )
    except Exception as q_err:
        logger.debug(f"Confluence quant signals check skipped: {q_err}")

    # Historical Pattern Similarity Cache
    pattern_row = None
    try:
        pat_stmt = select(PatternScreeningCache).where(
            PatternScreeningCache.symbol == symbol,
        )
        if as_of:
            pat_stmt = pat_stmt.where(PatternScreeningCache.screened_at <= as_of)
        pat_stmt = pat_stmt.order_by(PatternScreeningCache.screened_at.desc()).limit(1)
        pattern_row = (await session.execute(pat_stmt)).scalar_one_or_none()
    except Exception as pat_err:
        logger.debug(f"Confluence pattern similarity cache check skipped: {pat_err}")

    # Factor 7 Pre-computation: User Chart Workspace alignment
    ws_eval_result = None
    try:
        from monika.domain.indicators.technical import evaluate_workspace_indicators
        from monika.infrastructure.database.repositories.user_preference_repository import (
            SqlAlchemyUserPreferenceRepository,
        )

        ws_repo = SqlAlchemyUserPreferenceRepository(session)
        workspace_config = await ws_repo.resolve_chart_workspace_config(symbol)
        ws_tf = str(workspace_config.get("timeframe", "H4")).upper()

        ws_ohlcv_stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == ws_tf)
        if as_of:
            ws_ohlcv_stmt = ws_ohlcv_stmt.where(PriceOHLCV.timestamp <= as_of)
        ws_ohlcv_stmt = ws_ohlcv_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(150)
        ws_rows_res = await session.execute(ws_ohlcv_stmt)
        ws_rows = ws_rows_res.scalars().all()

        if (
            isinstance(ws_rows, list)
            and len(ws_rows) >= 20
            and hasattr(ws_rows[0], "close")
            and isinstance(getattr(ws_rows[0], "close", None), (int, float))
        ):
            ws_rows_sorted = sorted(ws_rows, key=lambda r: getattr(r, "timestamp", None) or clock.now())
            df_ws = pd.DataFrame(
                [
                    {
                        "Date": r.timestamp,
                        "Open": float(r.open),
                        "High": float(r.high),
                        "Low": float(r.low),
                        "Close": float(r.close),
                        "Volume": float(getattr(r, "volume", 0.0) or 0.0),
                    }
                    for r in ws_rows_sorted
                ]
            )
            df_ws.set_index("Date", inplace=True)
            ws_eval_result = await asyncio.to_thread(evaluate_workspace_indicators, df_ws, workspace_config, 50)
    except Exception as ws_e:
        logger.debug(f"User chart workspace confluence alignment skipped: {ws_e}")

    def _compute_for_direction(test_direction, test_entry, test_sl, test_tp):
        score = 0
        issues = []
        factors = []
        near_fvg = False
        near_ob = False
        near_sr = False
        in_ote = False
        test_direction = str(test_direction or "").strip().lower()
        test_dir = test_direction
        if (
            sweep_result.get("structure_confirmed")
            and str(sweep_result.get("valid_for_direction", "")).lower() == test_dir
        ):
            score += 2

        # Quant Alpha Strategy Edge Bonus (Directionally Separated)
        opp_dir = "sell" if test_dir == "buy" else "buy"
        best_dir_quant = 0.0
        best_opp_quant = 0.0
        if quant_signals:
            for s in quant_signals:
                if not getattr(s, "valid", False):
                    continue
                s_dir = str(getattr(s, "direction", "")).lower()
                s_conf = max(
                    float(getattr(s, "edge_strength", 0.0) or 0.0),
                    float(getattr(s, "confidence", 0.0) or 0.0),
                    0.50,
                )
                if s_dir == test_dir and s_conf > best_dir_quant:
                    best_dir_quant = s_conf
                elif s_dir == opp_dir and s_conf > best_opp_quant:
                    best_opp_quant = s_conf
            if best_dir_quant > 0.0 and best_dir_quant >= best_opp_quant:
                score += 2

        # === MECHANICAL VERIFICATION: RSI ===
        if rsi_val is not None:
            if 40 <= rsi_val <= 60:
                score += 1
            elif test_dir == "buy" and rsi_val < 30:
                score += 1  # Oversold bounce setup aligned with BUY
            elif test_dir == "sell" and rsi_val > 70:
                score += 1  # Overbought reversal setup aligned with SELL
            elif test_dir == "buy" and rsi_val > 70:
                issues.append(f"RSI overbought at {rsi_val:.1f} for BUY setup — invalidates rsi_neutral factor")
            elif test_dir == "sell" and rsi_val < 30:
                issues.append(f"RSI oversold at {rsi_val:.1f} for SELL setup — invalidates rsi_neutral factor")

        # === MECHANICAL VERIFICATION: Session Timing ===
        eval_time = as_of or clock.now()
        now_hour = eval_time.hour
        now_minute = eval_time.minute
        decimal_hour = now_hour + now_minute / 60

        is_london = 8 <= decimal_hour < 16
        is_ny = 13 <= decimal_hour < 21
        is_overlap = 13 <= decimal_hour < 16
        is_off_peak = 21 <= decimal_hour or decimal_hour < 8  # 21:00-08:00 UTC (Asian/Off-peak session)
        is_london_open_spike = 8 <= decimal_hour < 8.5

        if is_overlap:
            score += 1  # session_prime bonus
        elif is_off_peak:
            score += 0  # FIX: neutral for Asian/off-peak (no penalty)
        elif is_london_open_spike:
            score += 0  # no bonus for spike zone
        elif is_london or is_ny:
            score += 0  # standard session, no bonus

        # Ensure score doesn't go below 0
        score = max(0, score)

        # RR
        if test_entry and test_sl and test_tp:
            sl_dist = abs(test_entry - test_sl)
            tp_dist = abs(test_entry - test_tp)
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if rr >= min_rr_ratio:
                    score += 1
                elif rr < min_rr_ratio * 0.8:
                    issues.append(f"R:R ratio too low: {rr:.2f} (minimum {min_rr_ratio:.1f} required)")
            if atr_val > 0:
                sl_atr_ratio = sl_dist / atr_val
                if sl_atr_ratio < intraday_min_sl_atr_mult * 0.7:
                    issues.append(
                        f"SL too tight: {sl_atr_ratio:.2f}x ATR (minimum {intraday_min_sl_atr_mult}x required)."
                    )
                elif sl_atr_ratio < intraday_min_sl_atr_mult:
                    issues.append(f"SL marginally tight: {sl_atr_ratio:.2f}x ATR.")
            if adr_ctx and "error" not in adr_ctx:
                tp_band_min = adr_ctx["target_tp_min_distance"]
                tp_band_max = adr_ctx["target_tp_max_distance"]
                sl_adr_max = adr_ctx["target_sl_max_distance"]
                if tp_dist < tp_band_min * 0.9:
                    issues.append(f"TP below intraday-range target band ({tp_dist:.5f} < {tp_band_min:.5f}, 50% ADR).")
                elif tp_dist > tp_band_max * 1.1:
                    issues.append(f"TP above intraday-range target band ({tp_dist:.5f} > {tp_band_max:.5f}, 80% ADR).")
                else:
                    score += 1  # bonus: TP well-positioned within the ADR target band
                if sl_dist > sl_adr_max * 1.1:
                    issues.append(f"SL exceeds intraday-range max ({sl_dist:.5f} > {sl_adr_max:.5f}, 35% ADR).")

        # H4 & D1 Structure Alignment (H4 takes priority over lagging D1)
        h4_dir = str(getattr(h4_breaks, "direction", "") or "").lower() if h4_breaks else ""
        d1_dir = str(getattr(d1_breaks, "direction", "") or "").lower() if d1_breaks else ""
        h4_aligned = (test_direction == "buy" and h4_dir == "bullish") or (
            test_direction == "sell" and h4_dir == "bearish"
        )
        h4_opposed = (test_direction == "buy" and h4_dir == "bearish") or (
            test_direction == "sell" and h4_dir == "bullish"
        )
        d1_aligned = (test_direction == "buy" and d1_dir == "bullish") or (
            test_direction == "sell" and d1_dir == "bearish"
        )
        if h4_aligned:
            score += 2
        if d1_aligned and not h4_opposed:
            score += 1 if h4_aligned else 2

        # FVG/OB Proximity (Directionally Aligned)
        if test_entry and atr_val > 0:
            proximity = atr_val * 0.5
            near_fvg = False
            for fvg in fvgs:
                fvg_dir = str(
                    getattr(fvg, "direction", "")
                    or (fvg.get("direction") if isinstance(fvg, dict) else "")
                    or (fvg.get("type") if isinstance(fvg, dict) else "")
                ).lower()
                is_fvg_aligned = (test_direction == "buy" and "bull" in fvg_dir) or (
                    test_direction == "sell" and "bear" in fvg_dir
                )
                if not is_fvg_aligned:
                    continue
                g_low = float(
                    getattr(fvg, "gap_low", 0.0)
                    or (fvg.get("gap_low", 0.0) if isinstance(fvg, dict) else 0.0)
                    or (fvg.get("price_low", 0.0) if isinstance(fvg, dict) else 0.0)
                )
                g_high = float(
                    getattr(fvg, "gap_high", 0.0)
                    or (fvg.get("gap_high", 0.0) if isinstance(fvg, dict) else 0.0)
                    or (fvg.get("price_high", 0.0) if isinstance(fvg, dict) else 0.0)
                )
                if test_direction == "buy" and g_low <= test_entry <= g_high + proximity:
                    near_fvg = True
                    break
                if test_direction == "sell" and g_low - proximity <= test_entry <= g_high:
                    near_fvg = True
                    break
            if near_fvg:
                score += 2

            near_ob = False
            for ob in obs:
                ob_dir = str(
                    getattr(ob, "direction", "")
                    or (ob.get("direction") if isinstance(ob, dict) else "")
                    or (ob.get("type") if isinstance(ob, dict) else "")
                ).lower()
                is_ob_aligned = (test_direction == "buy" and "bull" in ob_dir) or (
                    test_direction == "sell" and "bear" in ob_dir
                )
                if not is_ob_aligned:
                    continue
                p_low = float(
                    getattr(ob, "price_low", 0.0) or (ob.get("price_low", 0.0) if isinstance(ob, dict) else 0.0)
                )
                p_high = float(
                    getattr(ob, "price_high", 0.0) or (ob.get("price_high", 0.0) if isinstance(ob, dict) else 0.0)
                )
                if p_low - proximity <= test_entry <= p_high + proximity:
                    near_ob = True
                    break
            if near_ob:
                score += 2

            if not near_fvg and not near_ob:
                logger.debug(f"Entry {test_entry} not near any aligned H4 FVG or Order Block (optional confluence).")

        # S/R Zone Bonus
        if test_entry and atr_val > 0:
            near_sr = False
            for sr in sr_zones:
                sr_low = float(
                    getattr(sr, "price_low", 0.0) or (sr.get("price_low", 0.0) if isinstance(sr, dict) else 0.0)
                )
                sr_high = float(
                    getattr(sr, "price_high", 0.0) or (sr.get("price_high", 0.0) if isinstance(sr, dict) else 0.0)
                )
                if sr_low > 0 and sr_high > 0 and sr_low - atr_val * 0.25 <= test_entry <= sr_high + atr_val * 0.25:
                    near_sr = True
                    break
            if near_sr:
                score += 1

        # OTE Bonus
        if test_entry and len(recent_swings) >= 2:
            s1 = recent_swings[0]
            s2 = recent_swings[1]
            s1_type = getattr(s1, "type", None)
            s2_type = getattr(s2, "type", None)
            if s1_type is not None and s2_type is not None and s1_type != s2_type:
                now_utc = clock.now()
                s1_ts_raw = getattr(s1, "timestamp", None)
                s2_ts_raw = getattr(s2, "timestamp", None)
                if isinstance(s1_ts_raw, datetime) and isinstance(s2_ts_raw, datetime):
                    s1_ts = s1_ts_raw.replace(tzinfo=timezone.utc) if s1_ts_raw.tzinfo is None else s1_ts_raw
                    s2_ts = s2_ts_raw.replace(tzinfo=timezone.utc) if s2_ts_raw.tzinfo is None else s2_ts_raw
                    if (now_utc - s1_ts).days <= 14 and (now_utc - s2_ts).days <= 14:
                        p1 = float(getattr(s1, "price", 0.0))
                        p2 = float(getattr(s2, "price", 0.0))
                        high = max(p1, p2)
                        low = min(p1, p2)
                        swing_range = high - low
                        if swing_range > 0:
                            if test_direction == "buy":
                                fib = (high - test_entry) / swing_range
                            else:
                                fib = (test_entry - low) / swing_range
                            if 0.618 <= fib <= 0.786:
                                score += 1
                                in_ote = True

        # === MECHANICAL VERIFICATION: Regime B Breakout / Momentum Expansion ===
        breakout_ok = False
        volume_ok = False
        trend_ok = False
        momentum_ok = False

        if recent_h4_bars and len(recent_h4_bars) >= 5 and test_entry:
            prior_bars = recent_h4_bars[1:]
            prior_highs = [float(b.high) for b in prior_bars]
            prior_lows = [float(b.low) for b in prior_bars]
            allow_d1_break_fallback = bool(confluence_factors) and not h4_opposed
            if test_dir == "buy" and (
                test_entry >= max(prior_highs) or h4_aligned or (allow_d1_break_fallback and d1_aligned)
            ):
                breakout_ok = True
            elif test_dir == "sell" and (
                test_entry <= min(prior_lows) or h4_aligned or (allow_d1_break_fallback and d1_aligned)
            ):
                breakout_ok = True

            vols = [float(getattr(b, "volume", 0.0) or 0.0) for b in recent_h4_bars]
            if len(vols) >= 5:
                prior_vols = vols[1:]
                mean_prior_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 0.0
                recent_vol = vols[0]
                if mean_prior_vol > 0 and (recent_vol / mean_prior_vol) >= 1.15:
                    volume_ok = True

        if ema20_val is not None and ema50_val is not None:
            if test_dir == "buy" and ema20_val >= ema50_val:
                trend_ok = True
            elif test_dir == "sell" and ema20_val <= ema50_val:
                trend_ok = True
        elif h4_aligned or (d1_aligned and not h4_opposed):
            trend_ok = True

        if rsi_val is not None:
            if test_dir == "buy" and rsi_val >= 55.0:
                momentum_ok = True
            elif test_dir == "sell" and rsi_val <= 45.0:
                momentum_ok = True

        if confluence_factors:
            if "breakout_expansion" in confluence_factors:
                if breakout_ok:
                    score += 2
                else:
                    issues.append(
                        f"breakout_expansion factor claimed but entry {test_entry} does not breach recent 20-period swing high/low"
                    )
            if "volume_expansion" in confluence_factors:
                if volume_ok:
                    score += 2
                else:
                    issues.append("volume_expansion factor claimed but RVOL < 1.15x average volume")
            if "trend_continuation" in confluence_factors:
                if trend_ok:
                    score += 2
                else:
                    issues.append("trend_continuation factor claimed but EMA/D1 structure does not confirm trend")
            if "momentum_expansion" in confluence_factors:
                if momentum_ok:
                    score += 1
                else:
                    issues.append(
                        f"momentum_expansion factor claimed but RSI={rsi_val} does not indicate momentum expansion"
                    )
        else:
            # Pre-hoc potential score evaluation: volume_ok only boosts a direction with directional confirmation
            zone_pts = (2 if near_fvg else 0) + (2 if near_ob else 0) + (1 if near_sr else 0) + (1 if in_ote else 0)
            dir_volume_ok = volume_ok and (breakout_ok or trend_ok or momentum_ok)
            breakout_pts = (
                (2 if breakout_ok else 0)
                + (2 if dir_volume_ok else 0)
                + (2 if trend_ok else 0)
                + (1 if momentum_ok else 0)
            )
            if breakout_pts > zone_pts:
                score += breakout_pts - zone_pts

        # VIX
        if vix_row:
            if vix_row.close < 20:
                score += 1
            elif vix_row.close >= 30:
                issues.append(f"VIX={vix_row.close:.1f} >= 30 (system-level pause threshold).")

        # Fundamental Bias
        brief_json = getattr(brief, "structured_json", None)
        if brief and brief_json:
            try:
                b_data = json.loads(brief_json)
                import re as _re

                clean_sym = _re.sub(r"[^A-Z]", "", symbol.upper())
                matrix = b_data.get("per_asset_macro_matrix", {})
                asset_entry = matrix.get(clean_sym) or matrix.get(symbol.upper())

                asset_bias = ""
                if isinstance(asset_entry, dict):
                    asset_bias = str(asset_entry.get("directional_bias", "")).lower()

                if asset_bias:
                    if test_direction == "buy":
                        if "bullish" in asset_bias:
                            score += 2
                            if "strong" in asset_bias:
                                score += 1
                    elif test_direction == "sell":
                        if "bearish" in asset_bias:
                            score += 2
                            if "strong" in asset_bias:
                                score += 1
                else:
                    c_bias = b_data.get("currency_bias", {})
                    base = clean_sym[:3]
                    quote = clean_sym[3:6]
                    base_bias = str(c_bias.get(base, "")).lower()
                    if not base_bias and base in ("XTI", "XBR"):
                        base_bias = str(c_bias.get("OIL", "")).lower()
                    elif not base_bias and base == "XAU":
                        base_bias = str(c_bias.get("GOLD", "")).lower()

                    quote_bias = str(c_bias.get(quote, "")).lower()
                    if not quote_bias and quote == "USD":
                        quote_bias = str(c_bias.get("USD", "")).lower()

                    # Net directional differential scoring:
                    # Avoid dual-award when base and quote have the same bias direction
                    b_score = (
                        2
                        if "strong_bull" in base_bias
                        else (
                            1
                            if "bull" in base_bias
                            else (-2 if "strong_bear" in base_bias else (-1 if "bear" in base_bias else 0))
                        )
                    )
                    q_score = (
                        2
                        if "strong_bull" in quote_bias
                        else (
                            1
                            if "bull" in quote_bias
                            else (-2 if "strong_bear" in quote_bias else (-1 if "bear" in quote_bias else 0))
                        )
                    )
                    net_diff = b_score - q_score

                    if test_direction == "buy":
                        if net_diff >= 2:
                            score += 3
                        elif net_diff >= 1:
                            score += 2
                    elif test_direction == "sell":
                        if net_diff <= -2:
                            score += 3
                        elif net_diff <= -1:
                            score += 2
            except Exception:
                pass

        # DXY confirms
        is_usd_base = symbol.startswith("USD")
        is_usd_quote = symbol.endswith("USD")
        if dxy_trend == "strengthening":
            if (test_direction == "buy" and is_usd_base) or (test_direction == "sell" and is_usd_quote):
                score += 1
        elif dxy_trend == "weakening":
            if (test_direction == "buy" and is_usd_quote) or (test_direction == "sell" and is_usd_base):
                score += 1

        # cot_aligned scoring
        if cot_alignment_val is not None:
            is_favor = (test_direction == "buy" and cot_alignment_val == -1) or (
                test_direction == "sell" and cot_alignment_val == 1
            )
            is_against = (test_direction == "buy" and cot_alignment_val == 1) or (
                test_direction == "sell" and cot_alignment_val == -1
            )
            if direction is not None:
                if not is_against:
                    score += 1
            elif is_favor:
                score += 1

        # F11: Microstructure confirmation
        if of_data:
            vpin_val = of_data.get("vpin")
            if vpin_val is not None:
                if vpin_val < 0.50:
                    score += 1
                elif vpin_val > 0.70:
                    score = max(0, score - 1)
                    issues.append(f"Toxic informed flow (VPIN={vpin_val:.2f} > 0.70)")
            else:
                bias = str(of_data.get("bias", "")).lower()
                if (test_direction == "buy" and "bull" in bias) or (test_direction == "sell" and "bear" in bias):
                    score += 1

        # Historical Chart Pattern Similarity Alignment (+1 point)
        if pattern_row and getattr(pattern_row, "confidence", "") in ("high", "medium"):
            p_bias = getattr(pattern_row, "overall_bias", "neutral")
            if (test_direction == "buy" and p_bias == "bullish") or (test_direction == "sell" and p_bias == "bearish"):
                score += 1

        # Quantitative Factor Zoo Consensus (+1 point, directionally separated)
        if quant_signals and best_dir_quant >= best_opp_quant:
            concordant_edges = sum(
                1
                for sig in quant_signals
                if getattr(sig, "valid", True)
                and str(getattr(sig, "direction", "")).lower() == test_direction.lower()
                and max(float(getattr(sig, "edge_strength", 0.0) or 0.0), float(getattr(sig, "confidence", 0.0) or 0.0))
                >= 0.55
            )
            if concordant_edges >= 1:
                score += 1

        # 7. User Chart Workspace Indicator Alignment (±2 pts max, clamped to [0, 10])
        if ws_eval_result:
            try:
                overall = ws_eval_result.get("overall", {})
                ws_bias = str(overall.get("bias", "NEUTRAL")).upper()
                bull_cnt = int(overall.get("bullish_count", 0))
                bear_cnt = int(overall.get("bearish_count", 0))
                total_dir = bull_cnt + bear_cnt
                align_pct = float(overall.get("alignment_pct", 0.0))

                dir_test = str(test_direction or "").strip().upper()
                if total_dir >= 2 and ws_bias in ("BULLISH", "BEARISH"):
                    expected_bias = "BULLISH" if dir_test == "BUY" else "BEARISH"
                    if ws_bias == expected_bias:
                        if total_dir >= 3 and align_pct >= 75.0:
                            score += 2
                            factors.append(f"User Chart Workspace Strong Alignment ({ws_bias} {align_pct:.0f}%)")
                        elif align_pct >= 60.0:
                            score += 1
                            factors.append(f"User Chart Workspace Alignment ({ws_bias} {align_pct:.0f}%)")
                    else:
                        if total_dir >= 3 and align_pct >= 75.0:
                            score = max(0, score - 1)
                            factors.append(
                                f"User Chart Workspace Divergence ({ws_bias} {align_pct:.0f}% opposes {dir_test})"
                            )
            except Exception as e:
                logger.debug(f"Workspace alignment evaluation error: {e}")

        score = min(max(score, 0), 10)
        return score, issues, factors

    if direction:
        score, issues, factors = _compute_for_direction(direction, entry_price, sl, tp)
        return {"computed_score": score, "blocking_issues": issues, "factors": factors}
    else:
        # Pre-hoc context, we don't know the exact entry. Use last close price if entry is not provided
        price_to_test = entry_price
        if not price_to_test:
            price_stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol)
            if as_of:
                price_stmt = price_stmt.where(PriceOHLCV.timestamp <= as_of)
            last_price_row = (
                await session.execute(price_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(1))
            ).scalar_one_or_none()
            if last_price_row:
                price_to_test = last_price_row.close

        buy_s, _, buy_f = _compute_for_direction("buy", price_to_test, None, None)
        sell_s, _, sell_f = _compute_for_direction("sell", price_to_test, None, None)
        sep = abs(buy_s - sell_s)
        dom_dir = "buy" if buy_s >= sell_s + 2 else ("sell" if sell_s >= buy_s + 2 else "neutral")

        return {
            "buy_potential_score": buy_s,
            "sell_potential_score": sell_s,
            "directional_separation": sep,
            "dominant_direction": dom_dir,
            "reference_price": price_to_test,
        }


class ConfluenceCalculator:
    """
    Deterministic Confluence Calculator with user chart workspace integration.
    Provides calculate_score() keeping tool execution and ConfluenceVerifier in 100% parity.
    """

    def __init__(self, session: AsyncSession, settings: Optional[dict] = None):
        self.session = session
        self.settings = settings or {}

    async def calculate_score(
        self,
        symbol: str,
        direction: Optional[str] = None,
        entry_price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        as_of: Optional[datetime] = None,
        confluence_factors: Optional[list[str]] = None,
    ) -> dict:
        return await calculate_confluence(
            session=self.session,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            settings=self.settings,
            as_of=as_of,
            confluence_factors=confluence_factors,
        )
