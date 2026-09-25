import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from database.models import (
    StructureBreak, FVGZone, OrderBlock, VIXData, TechnicalIndicator,
    FundamentalBrief, DXYData, COTReport, SRZone, FedWatchProbability, PriceOHLCV, SwingPoint,
    PatternScreeningCache
)

logger = logging.getLogger('TradingAgent.ConfluenceCalculator')

from utils.calibration.cot_thresholds import cot_extreme_score
from datetime import datetime, timezone
import utils.clock as clock

from typing import Optional

SYMBOL_TO_COT_CODE = {
    'EURUSD': '099741',
    'GBPUSD': '096742',
    'AUDUSD': '232741',
    'USDJPY': '097741',
    'XAUUSD': '088691',
}

async def _get_cot_alignment_value(session, symbol: str, as_of: Optional[datetime] = None):
    """Return cot_extreme_score() result (-1 extreme_long, 0 normal, +1 extreme_short)
    if COT data is fresh (<=10 days), else None (unknown -> tidak dinilai, fail-neutral)."""
    cot_code = SYMBOL_TO_COT_CODE.get(symbol)
    if not cot_code:
        return None
    stmt = select(COTReport).where(COTReport.market_code == cot_code)
    if as_of:
        stmt = stmt.where(COTReport.report_date <= as_of)
    stmt = stmt.order_by(COTReport.report_date.desc()).limit(1)
    cot_row = (await session.execute(stmt)).scalar_one_or_none()
    if not cot_row:
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
            raw_probs = probs_data.get('probabilities', probs_data) if isinstance(probs_data, dict) else {}
            max_prob = 0.0
            for k, v in raw_probs.items():
                if isinstance(v, (int, float)) and v > max_prob:
                    max_prob = float(v)
                elif isinstance(v, dict) and isinstance(v.get('probability'), (int, float)):
                    p_val = float(v['probability'])
                    if p_val > max_prob:
                        max_prob = p_val
            if max_prob > 85: scores["fedwatch"] = 3
            elif max_prob > 70: scores["fedwatch"] = 2
            elif max_prob > 50: scores["fedwatch"] = 1
        except Exception as e:
            logger.debug(f"Confluence fedwatch sub-calculation skipped: {e}")

    # 2. COT Extreme (0-3)
    cot_code = SYMBOL_TO_COT_CODE.get(symbol)
    
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
                        scores['cot'] = int(round(3 * cot_weight))
                    else:
                        ratio = abs(cot_row.leveraged_long - cot_row.leveraged_short) / total
                        raw_score = 2 if ratio > 0.5 else 1 if ratio > 0.3 else 0
                        scores['cot'] = int(round(raw_score * cot_weight))
            else:
                scores['cot'] = 0  # COT > 7 hari tidak dihitung

    # 3. Price Momentum vs ATR (0-3)
    atr_stmt = (
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.timeframe == 'D1')
        .where(TechnicalIndicator.indicator_name == 'ATR_14')
    )
    if as_of:
        atr_stmt = atr_stmt.where(TechnicalIndicator.timestamp <= as_of)
    atr_stmt = atr_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    atr_row = (await session.execute(atr_stmt)).scalar_one_or_none()
    
    price_stmt = (
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == 'D1')
    )
    if as_of:
        price_stmt = price_stmt.where(PriceOHLCV.timestamp <= as_of)
    price_stmt = price_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(20)
    prices = (await session.execute(price_stmt)).scalars().all()
    
    if atr_row and len(prices) >= 20:
        try:
            atr_val = 0
            raw_atr = json.loads(atr_row.value_json)
            if isinstance(raw_atr, dict):
                atr_val = float(raw_atr.get('atr', raw_atr.get('value', 0)))
            else:
                atr_val = float(raw_atr)
                
            if atr_val > 0:
                high_20 = max(p.high for p in prices)
                low_20 = min(p.low for p in prices)
                run_up = high_20 - low_20
                ratio = run_up / atr_val
                
                if ratio > 5: scores["momentum"] = 3
                elif ratio > 3: scores["momentum"] = 2
                elif ratio > 2: scores["momentum"] = 1
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
    as_of: Optional[datetime] = None
) -> dict:
    """
    Menghitung confluence score secara deterministik.
    Jika direction/entry_price tidak diberikan (pre-hoc bundler), 
    mengembalikan skor potensial untuk BUY dan SELL berdasarkan current price.
    """
    from analysis.calculators.daily_range_calculator import compute_daily_range_context
    settings = settings or {}
    risk_cfg = settings.get('trading', {}).get('risk', {})
    min_rr_ratio = float(risk_cfg.get('min_rr_ratio', 1.3))
    intraday_min_sl_atr_mult = float(risk_cfg.get('intraday_min_sl_atr_multiplier', 1.0))
    adr_ctx = await compute_daily_range_context(session, symbol, settings, as_of=as_of)
    
    # 1. Fetch data with look-ahead bias immunity (bar duration offsets)
    from datetime import timedelta
    h4_cutoff = (as_of - timedelta(hours=4)) if as_of else None
    d1_cutoff = (as_of - timedelta(days=1)) if as_of else None
    
    # ATR (H4)
    atr_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == 'H4',
        TechnicalIndicator.indicator_name == 'ATR_14'
    )
    if h4_cutoff:
        atr_stmt = atr_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    atr_stmt = atr_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    atr_row = (await session.execute(atr_stmt)).scalar_one_or_none()
    
    atr_val = 0
    if atr_row:
        atr_data = json.loads(atr_row.value_json)
        if isinstance(atr_data, dict):
            atr_val = float(atr_data.get('atr', 0) or atr_data.get('value', 0))
        else:
            atr_val = float(atr_data or 0)
            
    # RSI (H4)
    rsi_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == 'H4',
        TechnicalIndicator.indicator_name == 'RSI_14'
    )
    if h4_cutoff:
        rsi_stmt = rsi_stmt.where(TechnicalIndicator.timestamp <= h4_cutoff)
    rsi_stmt = rsi_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    rsi_row = (await session.execute(rsi_stmt)).scalar_one_or_none()
    
    rsi_val = None
    if rsi_row:
        try:
            rsi_data = json.loads(rsi_row.value_json)
            rsi_val = float(rsi_data.get('rsi', 50))
        except Exception as e:
            logger.debug(f"Confluence RSI sub-calculation skipped: {e}")
            
    # D1 Structure
    d1_stmt = select(StructureBreak).where(
        StructureBreak.symbol == symbol,
        StructureBreak.timeframe == 'D1'
    )
    if d1_cutoff:
        d1_stmt = d1_stmt.where(StructureBreak.formed_at <= d1_cutoff)
    d1_stmt = d1_stmt.order_by(StructureBreak.formed_at.desc()).limit(1)
    d1_breaks = (await session.execute(d1_stmt)).scalars().first()
    
    # FVG (H4)
    fvg_stmt = select(FVGZone).where(
        FVGZone.symbol == symbol,
        FVGZone.timeframe == 'H4'
    )
    if h4_cutoff:
        fvg_stmt = fvg_stmt.where(FVGZone.formed_at <= h4_cutoff).where(
            or_(FVGZone.filled_at.is_(None), FVGZone.filled_at > as_of)
        )
    else:
        fvg_stmt = fvg_stmt.where(FVGZone.filled_at.is_(None))
    fvg_stmt = fvg_stmt.order_by(FVGZone.formed_at.desc()).limit(5)
    fvgs = (await session.execute(fvg_stmt)).scalars().all()
    
    # OB (H4)
    ob_stmt = select(OrderBlock).where(
        OrderBlock.symbol == symbol,
        OrderBlock.timeframe == 'H4'
    )
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
    sr_stmt = select(SRZone).where(
        SRZone.symbol == symbol,
        SRZone.timeframe.in_(['H4', 'D1'])
    )
    if as_of:
        sr_stmt = sr_stmt.where(SRZone.last_touched <= (h4_cutoff or as_of))
    sr_zones = (await session.execute(sr_stmt)).scalars().all()
    
    # Swing Points for OTE
    swings_stmt = select(SwingPoint).where(
        SwingPoint.symbol == symbol,
        SwingPoint.timeframe == 'H4'
    )
    if h4_cutoff:
        swings_stmt = swings_stmt.where(SwingPoint.timestamp <= h4_cutoff)
    if as_of:
        swings_stmt = swings_stmt.where(SwingPoint.timestamp <= as_of)
    swings_stmt = swings_stmt.order_by(SwingPoint.timestamp.desc()).limit(2)
    recent_swings = (await session.execute(swings_stmt)).scalars().all()
    
    cot_alignment_val = await _get_cot_alignment_value(session, symbol, as_of=as_of)
    
    from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
    sweep_result = await detect_liquidity_sweep(session, symbol, settings or {}, as_of=as_of)

    # Microstructure Order Flow Snapshot (F11)
    of_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT"
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
        from analysis.strategies.registry import StrategyRegistry
        quant_signals = await StrategyRegistry.evaluate_all(session=session, symbol=symbol, settings=settings)
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

    def _compute_for_direction(test_direction, test_entry, test_sl, test_tp):
        score = 0
        issues = []
        if sweep_result.get('structure_confirmed') and sweep_result.get('valid_for_direction') == test_direction:
            score += 2
        
        # Quant Alpha Strategy Edge Bonus
        if quant_signals:
            has_quant_concordance = any(
                getattr(s, "valid", False) and str(getattr(s, "direction", "")).lower() == test_direction
                for s in quant_signals
            )
            if has_quant_concordance:
                score += 2

        # === MECHANICAL VERIFICATION: RSI ===
        if rsi_val is not None:
            if 40 <= rsi_val <= 60:
                score += 1
            elif test_direction == 'buy' and rsi_val < 30:
                score += 1  # Oversold bounce setup aligned with BUY
            elif test_direction == 'sell' and rsi_val > 70:
                score += 1  # Overbought reversal setup aligned with SELL
            elif test_direction == 'buy' and rsi_val > 70:
                issues.append(f'RSI overbought at {rsi_val:.1f} for BUY setup — invalidates rsi_neutral factor')
            elif test_direction == 'sell' and rsi_val < 30:
                issues.append(f'RSI oversold at {rsi_val:.1f} for SELL setup — invalidates rsi_neutral factor')
        
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
                    issues.append(f'R:R ratio too low: {rr:.2f} (minimum {min_rr_ratio:.1f} required)')
            if atr_val > 0:
                sl_atr_ratio = sl_dist / atr_val
                if sl_atr_ratio < intraday_min_sl_atr_mult * 0.7:
                    issues.append(f'SL too tight: {sl_atr_ratio:.2f}x ATR (minimum {intraday_min_sl_atr_mult}x required).')
                elif sl_atr_ratio < intraday_min_sl_atr_mult:
                    issues.append(f'SL marginally tight: {sl_atr_ratio:.2f}x ATR.')
            if adr_ctx and 'error' not in adr_ctx:
                tp_band_min = adr_ctx['target_tp_min_distance']
                tp_band_max = adr_ctx['target_tp_max_distance']
                sl_adr_max = adr_ctx['target_sl_max_distance']
                if tp_dist < tp_band_min * 0.9:
                    issues.append(f"TP below intraday-range target band ({tp_dist:.5f} < {tp_band_min:.5f}, 50% ADR).")
                elif tp_dist > tp_band_max * 1.1:
                    issues.append(f"TP above intraday-range target band ({tp_dist:.5f} > {tp_band_max:.5f}, 80% ADR).")
                else:
                    score += 1  # bonus: TP well-positioned within the ADR target band
                if sl_dist > sl_adr_max * 1.1:
                    issues.append(f"SL exceeds intraday-range max ({sl_dist:.5f} > {sl_adr_max:.5f}, 35% ADR).")
        
        # D1 Structure
        if d1_breaks:
            aligned = (
                (test_direction == 'buy' and d1_breaks.direction == 'bullish') or
                (test_direction == 'sell' and d1_breaks.direction == 'bearish')
            )
            if aligned:
                score += 2
                
        # FVG/OB Proximity
        if test_entry and atr_val > 0:
            proximity = atr_val * 0.5
            near_fvg = False
            for fvg in fvgs:
                if test_direction == 'buy' and fvg.gap_low <= test_entry <= fvg.gap_high + proximity:
                    near_fvg = True; break
                if test_direction == 'sell' and fvg.gap_low - proximity <= test_entry <= fvg.gap_high:
                    near_fvg = True; break
            if near_fvg:
                score += 2
                
            near_ob = False
            for ob in obs:
                if ob.price_low - proximity <= test_entry <= ob.price_high + proximity:
                    near_ob = True; break
            if near_ob:
                score += 2
                
            if not near_fvg and not near_ob:
                logger.debug(f'Entry {test_entry} not near any H4 FVG or Order Block (optional confluence).')
                
        # S/R Zone Bonus
        if test_entry and atr_val > 0:
            near_sr = False
            for sr in sr_zones:
                if sr.price_low - atr_val * 0.25 <= test_entry <= sr.price_high + atr_val * 0.25:
                    near_sr = True
                    break
            if near_sr:
                score += 1
                
        # OTE Bonus
        if test_entry and len(recent_swings) >= 2:
            s1 = recent_swings[0]
            s2 = recent_swings[1]
            if s1.type != s2.type:
                now_utc = clock.now()
                s1_ts = s1.timestamp.replace(tzinfo=timezone.utc) if s1.timestamp.tzinfo is None else s1.timestamp
                s2_ts = s2.timestamp.replace(tzinfo=timezone.utc) if s2.timestamp.tzinfo is None else s2.timestamp
                if (now_utc - s1_ts).days <= 14 and (now_utc - s2_ts).days <= 14:
                    high = max(s1.price, s2.price)
                    low = min(s1.price, s2.price)
                    swing_range = high - low
                    if swing_range > 0:
                        if test_direction == 'buy':
                            fib = (high - test_entry) / swing_range
                        else:
                            fib = (test_entry - low) / swing_range
                        if 0.618 <= fib <= 0.786:
                            score += 1
                
        # VIX
        if vix_row:
            if vix_row.close < 20:
                score += 1
            elif vix_row.close >= 30:
                issues.append(f'VIX={vix_row.close:.1f} >= 30 (system-level pause threshold).')
                
        # Fundamental Bias
        if brief and brief.structured_json:
            try:
                b_data = json.loads(brief.structured_json)
                c_bias = b_data.get("currency_bias", {})
                
                # Extrapolate for symbol
                base = symbol[:3]
                quote = symbol[3:6]
                base_bias = str(c_bias.get(base, '')).lower()
                if not base_bias and base in ('XTI', 'XBR'):
                    base_bias = str(c_bias.get('OIL', '')).lower()
                elif not base_bias and base == 'XAU':
                    base_bias = str(c_bias.get('GOLD', '')).lower()

                quote_bias = str(c_bias.get(quote, '')).lower()
                if not quote_bias and quote == 'USD':
                    quote_bias = str(c_bias.get('USD', '')).lower()

                if test_direction == 'buy':
                    if 'bullish' in base_bias or 'bearish' in quote_bias:
                        score += 2
                        if 'strong' in base_bias or 'strong' in quote_bias:
                            score += 1
                elif test_direction == 'sell':
                    if 'bearish' in base_bias or 'bullish' in quote_bias:
                        score += 2
                        if 'strong' in base_bias or 'strong' in quote_bias:
                            score += 1
            except Exception:
                pass
                
        # DXY confirms
        is_usd_base = symbol.startswith('USD')
        is_usd_quote = symbol.endswith('USD')
        if dxy_trend == 'strengthening':
            if (test_direction == 'buy' and is_usd_base) or (test_direction == 'sell' and is_usd_quote):
                score += 1
        elif dxy_trend == 'weakening':
            if (test_direction == 'buy' and is_usd_quote) or (test_direction == 'sell' and is_usd_base):
                score += 1

        # cot_aligned scoring
        if cot_alignment_val is not None:
            is_against = (test_direction == 'buy' and cot_alignment_val == 1) or \
                         (test_direction == 'sell' and cot_alignment_val == -1)
            if not is_against:
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
            if (test_direction == "buy" and p_bias == "bullish") or \
               (test_direction == "sell" and p_bias == "bearish"):
                score += 1

        return score, issues

    if direction:
        score, issues = _compute_for_direction(direction, entry_price, sl, tp)
        return {
            "computed_score": score,
            "blocking_issues": issues
        }
    else:
        # Pre-hoc context, we don't know the exact entry. Use last close price if entry is not provided
        price_to_test = entry_price
        if not price_to_test:
            from database.models import PriceOHLCV
            last_price_row = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            if last_price_row:
                price_to_test = last_price_row.close
                
        buy_s, _ = _compute_for_direction('buy', price_to_test, None, None)
        sell_s, _ = _compute_for_direction('sell', price_to_test, None, None)
        
        return {
            "buy_potential_score": buy_s,
            "sell_potential_score": sell_s,
            "reference_price": price_to_test
        }
