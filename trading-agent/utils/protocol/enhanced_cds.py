"""
Enhanced Context Divergence Score (CDS) System
Implements 3-dimensional CDS per "Hallucination as Context Drift" research:
- Spatial: beliefs about environment (brief bias vs price action)
- Temporal: timestamp alignment across data sources
- Task: decision history consistency
"""

import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('TradingAgent.EnhancedCDS')

# Per-research: CDS = 1 - cosine_similarity(c_i, c_j)
# We approximate via semantic agreement scoring (0=agree, 1=max_divergence)

SPATIAL_WEIGHT = 0.35   # Environment beliefs
TEMPORAL_WEIGHT = 0.35  # Data freshness synchronization
TASK_WEIGHT = 0.30      # Decision history consistency


ASSET_SIGNAL_THRESHOLDS = {
    'BTCUSD': 0.015,    # 1.5% — crypto volatile
    'ETHUSD': 0.02,     # 2%
    'XAUUSD': 0.008,    # 0.8% — gold medium
    'XTIUSD': 0.012,    # 1.2% — oil medium
    'XBRUSD': 0.012,    # 1.2% — brent oil medium
    'EURUSD': 0.005,    # 0.5% — forex noise filter
    'GBPUSD': 0.005,
    'USDJPY': 0.005,
    'AUDUSD': 0.005,
    'DEFAULT': 0.005,
}

def get_signal_threshold(symbol: str) -> float:
    return ASSET_SIGNAL_THRESHOLDS.get(symbol, ASSET_SIGNAL_THRESHOLDS['DEFAULT'])

async def compute_spatial_cds(
    session: AsyncSession,
    symbol: str,
    brief_currency_bias: dict,
    lookback_bars: int = 20
) -> float:
    """
    Compute spatial CDS: divergence between Stage 1 macro beliefs
    and current price action reality.
    
    Returns: 0.0 (no divergence) to 1.0 (maximum divergence)
    """
    from database.models import PriceOHLCV
    from utils.protocol.context_coherence import SYMBOL_CURRENCY_MAP
    
    signal_threshold = get_signal_threshold(symbol)

    pair_info = SYMBOL_CURRENCY_MAP.get(symbol)
    if not pair_info:
        return 0.0

    base_currency = pair_info['base']
    quote_currency = pair_info['quote']

    bars = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == 'H4')
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(lookback_bars)
    )).scalars().all()

    if len(bars) < 5:
        return 0.0

    bars = list(reversed(bars))
    first_close = bars[0].close
    last_close = bars[-1].close

    if not first_close or first_close <= 0:
        return 0.0

    pct_change = (last_close - first_close) / first_close

    if abs(pct_change) < signal_threshold:
        return 0.0  # Movement too small to be meaningful

    # Determine what price action implies about currency direction
    if pct_change > 0:
        base_implied = 'bullish'
        quote_implied = 'bearish'
    else:
        base_implied = 'bearish'
        quote_implied = 'bullish'

    from utils.market.bias_utils import normalize_bias
    base_brief_bias = normalize_bias(brief_currency_bias.get(base_currency, 'neutral'))
    quote_brief_bias = normalize_bias(brief_currency_bias.get(quote_currency, 'neutral'))

    # Count divergences weighted by magnitude of price move
    magnitude_factor = min(abs(pct_change) / 0.01, 3.0)  # Cap at 3x for >1% moves

    divergences = 0.0
    checks = 0

    if base_brief_bias not in ('neutral',):
        checks += 1
        if base_implied != base_brief_bias:
            divergences += 1.0 * magnitude_factor
    
    if quote_brief_bias not in ('neutral',):
        checks += 1
        if quote_implied != quote_brief_bias:
            divergences += 1.0 * magnitude_factor

    if checks == 0:
        return 0.0

    # Normalize: 0.0 to 1.0
    raw_cds = divergences / checks
    return min(raw_cds, 1.0)


async def compute_temporal_cds(
    session: AsyncSession,
    symbol: str,
    settings: Optional[dict] = None,
    is_weekend: Optional[bool] = None,
) -> float:
    """
    Compute temporal CDS: how synchronized are data sources in time?
    High temporal CDS = data sources are from very different time points = unreliable joint analysis.
    
    Returns: 0.0 (all data synchronized) to 1.0 (maximum temporal spread)
    """
    from database.models import (
        PriceOHLCV, TechnicalIndicator, FundamentalBrief, VIXData
    )
    from utils.clock import now as get_clock_now

    now = get_clock_now()
    weekday = now.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
    if is_weekend is None:
        is_weekend = weekday >= 5
    is_monday_open = weekday == 0 and now.hour < 4  # Senin dini hari
    
    timestamps = {}

    # H4 OHLCV
    h4_ts = (await session.execute(
        select(PriceOHLCV.timestamp)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == 'H4')
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()
    if h4_ts:
        ts = h4_ts.replace(tzinfo=timezone.utc) if h4_ts.tzinfo is None else h4_ts
        timestamps['h4_ohlcv'] = (now - ts).total_seconds() / 3600

    # Technical Indicators
    ind_ts = (await session.execute(
        select(TechnicalIndicator.timestamp)
        .where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.timeframe == 'H4')
        .order_by(TechnicalIndicator.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()
    if ind_ts:
        ts = ind_ts.replace(tzinfo=timezone.utc) if ind_ts.tzinfo is None else ind_ts
        timestamps['indicators'] = (now - ts).total_seconds() / 3600

    # Fundamental Brief
    brief_ts = (await session.execute(
        select(FundamentalBrief.generated_at)
        .order_by(FundamentalBrief.generated_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if brief_ts:
        ts = brief_ts.replace(tzinfo=timezone.utc) if brief_ts.tzinfo is None else brief_ts
        timestamps['brief'] = (now - ts).total_seconds() / 3600

    # VIX: SKIP di weekend dan Senin pagi (normal tidak ada update)
    if not (is_weekend or is_monday_open):
        vix_ts = (await session.execute(
            select(VIXData.date)
            .order_by(VIXData.date.desc())
            .limit(1)
        )).scalar_one_or_none()
        if vix_ts:
            if hasattr(vix_ts, 'hour'):
                vix_dt = vix_ts.replace(tzinfo=timezone.utc) if vix_ts.tzinfo is None else vix_ts
            else:
                vix_dt = datetime(vix_ts.year, vix_ts.month, vix_ts.day, tzinfo=timezone.utc)
            timestamps['vix'] = (now - vix_dt).total_seconds() / 3600

    if len(timestamps) < 2:
        return 0.0

    ages = list(timestamps.values())
    max_age = max(ages)
    min_age = min(ages)
    age_spread_hours = max_age - min_age

    max_allowed = 6.0
    if settings:
        max_allowed = settings.get('ssvp', {}).get('temporal_cds_max_age_spread_hours', 6.0)

    # Weekend mode / Market closed handling for 24/5 assets
    is_crypto = symbol.upper().startswith(("BTC", "ETH", "SOL", "XRP"))
    if not is_crypto and (is_weekend or is_monday_open):
        return 0.0  # FX/Commodities markets are closed over the weekend; no temporal drift

    if is_weekend or is_monday_open:
        max_allowed = max_allowed * 2.5  # Toleransi lebih tinggi untuk Crypto di weekend

    if age_spread_hours <= max_allowed:
        return 0.0
    
    temporal_cds = min((age_spread_hours - max_allowed) / (max_allowed * 2), 1.0)
    return temporal_cds


async def compute_task_cds(
    session: AsyncSession,
    symbol: str,
    current_decision: Optional[str] = None
) -> float:
    """
    Compute task CDS: how consistent is the current analysis
    with accumulated decision history?
    
    High task CDS = current analysis dramatically contradicts recent history
    without structural explanation = possible hallucination.
    
    Returns: 0.0 (consistent with history) to 1.0 (contradicts history)
    """
    from database.models import AssetAnalysis

    if not current_decision or current_decision not in ('buy', 'sell'):
        return 0.0  # WAIT/AVOID decisions don't create consistency risk

    # Get last 5 analyses for this symbol
    recent_analyses = (await session.execute(
        select(AssetAnalysis)
        .where(AssetAnalysis.symbol == symbol)
        .where(AssetAnalysis.decision.in_(['buy', 'sell', 'wait', 'avoid']))
        .order_by(AssetAnalysis.generated_at.desc())
        .limit(5)
    )).scalars().all()

    if len(recent_analyses) < 3:
        return 0.0  # Insufficient history

    # Count consecutive WAITs before current analysis
    consecutive_waits = 0
    for analysis in recent_analyses:
        if analysis.decision in ('wait', 'avoid'):
            consecutive_waits += 1
        else:
            break

    # If 3+ consecutive WAITs and now suddenly BUY/SELL,
    # apply decaying penalty to break out of self-reinforcing WAIT loops.
    if consecutive_waits >= 3:
        task_cds = max(0.0, 0.25 - (consecutive_waits - 3) * 0.05)
        return task_cds

    # Check for directional flip without structure change
    last_tradeable = None
    for analysis in recent_analyses:
        if analysis.decision in ('buy', 'sell'):
            last_tradeable = analysis
            break

    if last_tradeable and last_tradeable.decision != current_decision:
        # Directional flip — check if it's within short timeframe (potentially reactive)
        time_since_last = (
            datetime.now(timezone.utc) - 
            last_tradeable.generated_at.replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600
        
        if time_since_last < 4.0:  # Flip within 4 hours
            # Rapid direction change - moderate task CDS
            return 0.25
    
    return 0.0


async def compute_composite_cds(
    session: AsyncSession,
    symbol: str,
    brief_data: dict,
    current_decision: Optional[str] = None,
    settings: Optional[dict] = None
) -> tuple[float, dict]:
    """
    Compute full 3-dimensional composite CDS for a symbol.
    
    Returns: (composite_cds: float, breakdown: dict)
    """
    currency_bias = brief_data.get('currency_bias', {}) if brief_data else {}

    spatial = await compute_spatial_cds(session, symbol, currency_bias)
    temporal = await compute_temporal_cds(session, symbol, settings)
    task = await compute_task_cds(session, symbol, current_decision)

    composite = (
        SPATIAL_WEIGHT * spatial +
        TEMPORAL_WEIGHT * temporal +
        TASK_WEIGHT * task
    )

    breakdown = {
        'spatial': round(spatial, 3),
        'temporal': round(temporal, 3),
        'task': round(task, 3),
        'composite': round(composite, 3),
        'dominant_dimension': max(
            [('spatial', spatial), ('temporal', temporal), ('task', task)],
            key=lambda x: x[1]
        )[0]
    }

    logger.debug(f"[CDS-{symbol}] spatial={spatial:.3f} temporal={temporal:.3f} task={task:.3f} → composite={composite:.3f}")

    return round(composite, 3), breakdown


def get_cds_thresholds(settings: Optional[dict] = None) -> dict:
    """Get CDS thresholds from settings or defaults (synchronous fallback)."""
    if settings:
        thresholds = settings.get('ssvp', {}).get('cds_thresholds', {})
        return {
            'warning': thresholds.get('warning', 0.35),
            'sync_trigger': thresholds.get('sync_trigger', 0.50),
            'block_buysell': thresholds.get('block_buysell', 0.65),
            'abort_all': thresholds.get('abort_all', 0.75),
        }
    return {
        'warning': 0.35,
        'sync_trigger': 0.50,
        'block_buysell': 0.65,
        'abort_all': 0.75,
    }

async def get_cds_thresholds_async(session: AsyncSession, settings: Optional[dict] = None) -> dict:
    """Get CDS thresholds, prioritizing dynamic overrides from DB."""
    from database.models import SystemConfig
    import json
    
    base = get_cds_thresholds(settings)
    
    try:
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "dynamic_cds_thresholds")
        )).scalar_one_or_none()
        
        if cfg and cfg.value:
            overrides = json.loads(cfg.value)
            for k in base.keys():
                if k in overrides:
                    base[k] = overrides[k]
                    
        # Clamp block_buysell to sane bounds regardless of auto-calibration
        base['block_buysell'] = max(0.4, min(0.7, base['block_buysell']))
    except Exception as e:
        logger.debug(f"Failed to fetch dynamic CDS thresholds: {e}")
        try:
            await session.rollback()
        except Exception:
            pass
        
    return base
