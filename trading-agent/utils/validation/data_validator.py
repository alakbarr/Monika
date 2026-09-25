# ==============================================================================
# File: utils/data_validator.py
# ==============================================================================

"""Validator Data — Cek kebaruan (freshness) data di DB sebelum analisis."""
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PriceOHLCV, NewsItem, FundamentalBrief

logger = logging.getLogger("TradingAgent.DataValidator")

DEFAULT_OHLCV_AGE = {"M15": 1.0, "H1": 3.0, "H4": 8.0, "D1": 32.0}
DEFAULT_IND_AGE = {"H1": 3.0, "H4": 8.0, "D1": 32.0}
DEFAULT_MACRO_AGE_DAYS = {
    "vix": 4.5,
    "treasury_yield": 4.5,
    "dxy": 4.5,
    "cot": 11.0,
    "fedwatch": 7.0,
}

def is_crypto_symbol(symbol: str) -> bool:
    """Cek apakah simbol merupakan aset crypto 24/7."""
    s = symbol.upper()
    prefixes = [
        "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA",
        "LTC", "AVAX", "LINK", "DOT", "UNI", "NEAR", "ATOM", "XLM", "MATIC"
    ]
    return any(s.startswith(p) for p in prefixes)

def is_forex_market_closed(dt: datetime) -> bool:
    """
    Cek apakah pasar Forex/Komoditas sedang tutup (Weekend).
    Tutup: Jumat 22:00 UTC sampai Minggu 22:00 UTC.
    """
    weekday = dt.weekday()
    hour = dt.hour
    return (weekday == 5) or (weekday == 6 and hour < 22) or (weekday == 4 and hour >= 22)

def is_market_reopen_window(dt: datetime) -> bool:
    """
    Jendela pembukaan kembali pasar Forex (Minggu 22:00 UTC - Senin 04:00 UTC).
    Pada jendela ini, bar penutupan Jumat masih menjadi referensi utama sampai bar baru lengkap.
    """
    weekday = dt.weekday()
    hour = dt.hour
    return (weekday == 6 and hour >= 22) or (weekday == 0 and hour < 4)

async def validate_data_freshness(
    session: AsyncSession,
    symbols: list[str],
    timeframes: list[str],
    max_ohlcv_age_hours: Optional[dict] = None,
    max_news_age_hours: float = 6.0,
    max_calendar_age_hours: float = 168.0,
    max_indicator_age_hours: Optional[dict] = None,
    max_macro_age_days: Optional[dict] = None,
    require_macro_data: bool = False,
    log_warning: bool = True,
) -> dict:
    """
    Cek apakah data cukup baru untuk analisis (Timeframe duration & Market hours aware).
    Returns: {"ready": bool, "warnings": list, "errors": list, "checked_at": str}
    """
    warnings = []
    errors = []
    from utils.clock import now as get_clock_now
    now = get_clock_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    
    ohlcv_thresholds = max_ohlcv_age_hours or DEFAULT_OHLCV_AGE
    ind_thresholds = max_indicator_age_hours or DEFAULT_IND_AGE
    macro_thresholds = max_macro_age_days or DEFAULT_MACRO_AGE_DAYS
    
    forex_closed = is_forex_market_closed(now)
    reopen_window = is_market_reopen_window(now)
    is_weekend_or_monday = forex_closed or (now.weekday() == 0)
    
    # Check OHLCV freshness
    for symbol in symbols:
        is_crypto = is_crypto_symbol(symbol)
        for tf in timeframes:
            tf_max_age = ohlcv_thresholds.get(tf, DEFAULT_OHLCV_AGE.get(tf, 8.0))
            latest = (await session.execute(
                select(PriceOHLCV.timestamp)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == tf)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            
            if latest is None:
                errors.append(f"No OHLCV data for {symbol}/{tf}")
            else:
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age_hours = (now - latest).total_seconds() / 3600
                
                # Jika pasar non-crypto sedang tutup akhir pekan, data penutupan Jumat adalah normal
                if not is_crypto and forex_closed:
                    continue
                
                # Toleransi saat pembukaan pasar Senin pagi (+48 jam untuk jeda akhir pekan)
                # Hanya berlaku jika data bar terakhir memang berada di dekat penutupan Jumat
                is_friday_close = (latest.weekday() == 4 and latest.hour >= 20) or (latest.weekday() == 5)
                effective_max_age = tf_max_age + (48.0 if (not is_crypto and reopen_window and is_friday_close) else 0.0)
                
                if age_hours > effective_max_age:
                    errors.append(f"{symbol}/{tf} OHLCV is {age_hours:.1f}h old (stale)")
    
    # Check Indicator freshness
    from database.models import TechnicalIndicator
    for symbol in symbols:
        is_crypto = is_crypto_symbol(symbol)
        for tf in timeframes:
            if tf == 'M15': 
                continue  # M15 only used for OHLCV paper trade tracking, no indicators
            tf_ind_max_age = ind_thresholds.get(tf, DEFAULT_IND_AGE.get(tf, 8.0))
            latest_ind = (await session.execute(
                select(TechnicalIndicator.timestamp)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == tf)
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            
            if latest_ind is None:
                errors.append(f"No TechnicalIndicator data for {symbol}/{tf}")
            else:
                if latest_ind.tzinfo is None:
                    latest_ind = latest_ind.replace(tzinfo=timezone.utc)
                ind_age_hours = (now - latest_ind).total_seconds() / 3600
                
                if not is_crypto and forex_closed:
                    continue
                
                effective_ind_max_age = tf_ind_max_age + (48.0 if (not is_crypto and reopen_window) else 0.0)
                if ind_age_hours > effective_ind_max_age:
                    errors.append(f"{symbol}/{tf} Indicator is {ind_age_hours:.1f}h old (stale)")

    # Check news freshness
    latest_news = (await session.execute(
        select(func.max(NewsItem.fetched_at))
    )).scalar_one_or_none()
    
    if latest_news is None:
        errors.append("No news items in database")
    else:
        if latest_news.tzinfo is None:
            latest_news = latest_news.replace(tzinfo=timezone.utc)
        news_age = (now - latest_news).total_seconds() / 3600
        eff_max_news_age = max_news_age_hours + (48.0 if forex_closed else 0.0)
        if news_age > eff_max_news_age:
            warnings.append(f"Latest news is {news_age:.1f}h old")

    # Check macro data freshness
    from database.models import EconomicCalendar, VIXData, TreasuryYield, DXYData, COTReport, FedWatchProbability
    from datetime import date
    
    cal_max_days = 2.0 if require_macro_data else (max_calendar_age_hours / 24.0)
    latest_cal = (await session.execute(
        select(func.max(EconomicCalendar.event_time))
    )).scalar_one_or_none()
    if latest_cal is not None:
        if latest_cal.tzinfo is None:
            latest_cal = latest_cal.replace(tzinfo=timezone.utc)
        cal_age_days = (now - latest_cal).total_seconds() / 86400
        if cal_age_days > cal_max_days:
            msg = f"Economic calendar data is {cal_age_days:.1f} days old (stale, max {cal_max_days:.1f}d)"
            if require_macro_data and not forex_closed and cal_age_days > 2.0:
                errors.append(msg)
            else:
                warnings.append(msg)
    else:
        msg = "Economic calendar data is empty (0 rows in DB)"
        if require_macro_data: errors.append(msg)
        else: warnings.append(msg)

    # 1. VIX Data
    vix_cfg_limit = float(macro_thresholds.get("vix", 4.5))
    eff_vix_max_days = vix_cfg_limit if is_weekend_or_monday else min(vix_cfg_limit, 3.0)
    latest_vix = (await session.execute(
        select(func.max(VIXData.date))
    )).scalar_one_or_none()
    if latest_vix is not None:
        vix_dt = datetime.combine(latest_vix, datetime.min.time(), tzinfo=timezone.utc) if isinstance(latest_vix, date) and not isinstance(latest_vix, datetime) else latest_vix
        if vix_dt.tzinfo is None:
            vix_dt = vix_dt.replace(tzinfo=timezone.utc)
        vix_age_days = (now - vix_dt).total_seconds() / 86400
        if vix_age_days > eff_vix_max_days:
            warnings.append(f"VIX data is {vix_age_days:.1f} days old (stale)")
    else:
        msg = "VIX data is empty (0 rows in DB)"
        if require_macro_data: errors.append(msg)
        else: warnings.append(msg)

    # 2. Treasury Yields
    yield_cfg_limit = float(macro_thresholds.get("treasury_yield", 4.5))
    eff_yield_max = yield_cfg_limit if is_weekend_or_monday else min(yield_cfg_limit, 3.0)
    latest_yield = (await session.execute(
        select(func.max(TreasuryYield.date))
    )).scalar_one_or_none()
    if latest_yield is not None:
        y_dt = datetime.combine(latest_yield, datetime.min.time(), tzinfo=timezone.utc) if isinstance(latest_yield, date) and not isinstance(latest_yield, datetime) else latest_yield
        if y_dt.tzinfo is None:
            y_dt = y_dt.replace(tzinfo=timezone.utc)
        yield_age_days = (now - y_dt).total_seconds() / 86400
        if yield_age_days > eff_yield_max:
            warnings.append(f"Treasury yield data is {yield_age_days:.1f} days old (stale)")
    else:
        msg = "Treasury yield data is empty (0 rows in DB)"
        if require_macro_data: errors.append(msg)
        else: warnings.append(msg)

    # 3. DXY
    dxy_cfg_limit = float(macro_thresholds.get("dxy", 4.5))
    eff_dxy_max = dxy_cfg_limit if is_weekend_or_monday else min(dxy_cfg_limit, 3.0)
    latest_dxy = (await session.execute(
        select(func.max(DXYData.date))
    )).scalar_one_or_none()
    if latest_dxy is not None:
        d_dt = datetime.combine(latest_dxy, datetime.min.time(), tzinfo=timezone.utc) if isinstance(latest_dxy, date) and not isinstance(latest_dxy, datetime) else latest_dxy
        if d_dt.tzinfo is None:
            d_dt = d_dt.replace(tzinfo=timezone.utc)
        dxy_age_days = (now - d_dt).total_seconds() / 86400
        if dxy_age_days > eff_dxy_max:
            warnings.append(f"DXY data is {dxy_age_days:.1f} days old (stale)")
    else:
        msg = "DXY data is empty (0 rows in DB)"
        if require_macro_data: errors.append(msg)
        else: warnings.append(msg)

    # 4. COT Report (Weekly CFTC)
    cot_max_days = float(macro_thresholds.get("cot", 11.0))
    latest_cot = (await session.execute(
        select(func.max(COTReport.report_date))
    )).scalar_one_or_none()
    if latest_cot is not None:
        cot_dt = datetime.combine(latest_cot, datetime.min.time(), tzinfo=timezone.utc) if isinstance(latest_cot, date) and not isinstance(latest_cot, datetime) else latest_cot
        if cot_dt.tzinfo is None:
            cot_dt = cot_dt.replace(tzinfo=timezone.utc)
        cot_age_days = (now - cot_dt).total_seconds() / 86400
        if cot_age_days > cot_max_days:
            warnings.append(f"COT report data is {cot_age_days:.1f} days old (stale)")
    else:
        warnings.append("COT report data is empty (0 rows in DB)")

    # 5. FedWatch Probabilities
    fedwatch_max_days = float(macro_thresholds.get("fedwatch", 7.0))
    latest_fedwatch = (await session.execute(
        select(func.max(FedWatchProbability.fetched_at))
    )).scalar_one_or_none()
    if latest_fedwatch is not None:
        if latest_fedwatch.tzinfo is None:
            latest_fedwatch = latest_fedwatch.replace(tzinfo=timezone.utc)
        fedwatch_age_days = (now - latest_fedwatch).total_seconds() / 86400
        if fedwatch_age_days > fedwatch_max_days:
            warnings.append(f"FedWatch probability data is {fedwatch_age_days:.1f} days old (stale)")
    else:
        warnings.append("FedWatch probability data is empty (0 rows in DB)")

    ready = len(errors) == 0
    
    result = {
        "ready": ready,
        "warnings": warnings,
        "errors": errors,
        "checked_at": now.isoformat(),
        "market_closed": forex_closed,
    }
    
    if errors:
        log_msg = (
            f'Data freshness validation: {len(errors)} items stale (Market closed/weekend: stale data expected). {" | ".join(errors[:2])}...'
            if forex_closed and len(errors) > 2 else
            f'Data freshness validation failed. Errors ({len(errors)}): {" | ".join(errors[:3])}...'
            if len(errors) > 3 else 
            f'Data freshness validation failed: {" | ".join(errors)}'
        )
        if forex_closed or not log_warning:
            logger.debug(log_msg)
        else:
            logger.warning(log_msg)
        
    return result

def is_spread_acceptable(symbol: str, bid: float, ask: float) -> bool:
    """Memeriksa apakah spread dalam batas aman (maks 5x spread normal)."""
    spread = abs(ask - bid)
    sym = (symbol or "").strip().upper()
    
    typical_spreads = {
        "XAUUSD": 0.50,    # 50 cents
        "EURUSD": 0.00015, # 1.5 pips
        "GBPUSD": 0.00020, # 2.0 pips
        "USDJPY": 0.015,   # 1.5 pips (0.01 per pip)
        "AUDUSD": 0.00018, # 1.8 pips
        "BTCUSD": 5.0,     # $5
        "XTIUSD": 0.030,   # 3 cents ($3 per lot)
        "XBRUSD": 0.040,   # 4 cents ($40 per lot)
    }
    
    if sym in typical_spreads:
        typical = typical_spreads[sym]
    else:
        from utils.market.instrument_identity import resolve_instrument_identity
        ident = resolve_instrument_identity(sym)
        typical = (ident.pip_size * 2.0) if ident and ident.pip_size else 0.0005
    
    if spread > (typical * 5):
        logger.warning(f"SPREAD CIRCUIT BREAKER: {symbol} spread is {spread:.5f} (typical: {typical}). Trading blocked.")
        return False
        
    return True


async def check_data_coherence(
    session: AsyncSession, 
    symbol: str,
    max_age_hours: Optional[float] = None,
    max_ohlcv_age_hours: Optional[dict] = None,
    max_indicator_age_hours: Optional[dict] = None,
) -> dict:
    """
    Pastikan semua data teknikal untuk satu simbol
    memiliki timestamp yang coherent (tidak ada yang terlalu stale)
    dengan batas usia berbasis timeframe (D1: 32h, H4: 8h).
    """
    from database.models import PriceOHLCV, TechnicalIndicator
    from sqlalchemy import select
    from utils.clock import now as get_clock_now
    
    now = get_clock_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
        
    issues = []
    is_crypto = is_crypto_symbol(symbol)
    forex_closed = is_forex_market_closed(now)
    reopen_window = is_market_reopen_window(now)
    
    ohlcv_thresholds = max_ohlcv_age_hours or DEFAULT_OHLCV_AGE
    ind_thresholds = max_indicator_age_hours or DEFAULT_IND_AGE
    
    for tf in ['H4', 'D1']:
        if max_age_hours is not None and max_ohlcv_age_hours is None:
            tf_ohlcv_max = max_age_hours if tf == 'H4' else DEFAULT_OHLCV_AGE.get(tf, 32.0)
            tf_ind_max = max_age_hours if tf == 'H4' else DEFAULT_IND_AGE.get(tf, 32.0)
        else:
            tf_ohlcv_max = ohlcv_thresholds.get(tf, DEFAULT_OHLCV_AGE.get(tf, 8.0))
            tf_ind_max = ind_thresholds.get(tf, DEFAULT_IND_AGE.get(tf, 8.0))
            
        effective_ohlcv_max = tf_ohlcv_max + (48.0 if (not is_crypto and (forex_closed or reopen_window)) else 0.0)
        effective_ind_max = tf_ind_max + (48.0 if (not is_crypto and (forex_closed or reopen_window)) else 0.0)
        
        # Check OHLCV
        latest_price = (await session.execute(
            select(PriceOHLCV.timestamp)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == tf)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        # Check Indicators
        latest_ind = (await session.execute(
            select(TechnicalIndicator.timestamp)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == tf)
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        if latest_price and latest_ind:
            if latest_price.tzinfo is None:
                latest_price = latest_price.replace(tzinfo=timezone.utc)
            if latest_ind.tzinfo is None:
                latest_ind = latest_ind.replace(tzinfo=timezone.utc)
                
            price_age = (now - latest_price).total_seconds() / 3600
            ind_age = (now - latest_ind).total_seconds() / 3600
            
            # Check desync between indicator and price based on timeframe duration
            max_allowed_desync = {"M15": 0.5, "H1": 1.5, "H4": 4.5, "D1": 25.0}.get(tf, 2.0)
            time_diff = abs((latest_ind - latest_price).total_seconds()) / 3600
            if time_diff > max_allowed_desync:
                issues.append(
                    f'{symbol}/{tf}: Indicator timestamp ({latest_ind}) '
                    f'differs from OHLCV ({latest_price}) by {time_diff:.1f}h (allowed: {max_allowed_desync}h) '
                    f'— indicators may not reflect latest prices'
                )
            
            if not (not is_crypto and forex_closed) and price_age > effective_ohlcv_max:
                issues.append(f'{symbol}/{tf}: OHLCV is {price_age:.1f}h old')
                
            if not (not is_crypto and forex_closed) and ind_age > effective_ind_max:
                issues.append(f'{symbol}/{tf}: Indicator is {ind_age:.1f}h old')
        elif not latest_price:
            issues.append(f'{symbol}/{tf}: No OHLCV data')
        elif not latest_ind:
            issues.append(f'{symbol}/{tf}: No Indicator data')
    
    return {
        'symbol': symbol,
        'coherent': len(issues) == 0,
        'issues': issues
    }

