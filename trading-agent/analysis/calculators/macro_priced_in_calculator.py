import json
import logging
from typing import Optional, Any
from datetime import datetime
import utils.clock as clock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import FedWatchProbability, COTReport, NewsDigest
from utils.market.usd_strength_proxy import compute_usd_strength_proxy
from utils.calibration.cot_thresholds import cot_extreme_score

logger = logging.getLogger('TradingAgent.MacroPricedInCalculator')


async def calculate_macro_priced_in_baseline(session: AsyncSession, as_of: Optional[datetime] = None) -> dict[str, Any]:
    """
    Mirror dari calculate_priced_in_subscores() di Stage 2, tapi untuk level MACRO.
    Menggabungkan Method 1-4 dari market_dynamics_framework.md secara deterministik,
    sehingga Stage 1 tidak perlu menghitung manual dari raw tool output.
    """
    sim_time = as_of or clock.now()
    scores: dict[str, Any] = {'fedwatch': 0, 'cot': 0, 'usd_momentum': 0, 'news_saturation': 0, 'total_auto': 0}
    notes = []

    # Method 1: FedWatch dominant probability
    fw_stmt = select(FedWatchProbability)
    if sim_time is not None:
        fw_stmt = fw_stmt.where(FedWatchProbability.fetched_at <= sim_time)
    fw_row = (
        await session.execute(fw_stmt.order_by(FedWatchProbability.fetched_at.desc()).limit(1))
    ).scalar_one_or_none()
    if fw_row and fw_row.probabilities_json:
        try:
            probs = json.loads(fw_row.probabilities_json).get('probabilities', {})
            max_prob = max((v.get('probability', 0) for v in probs.values() if isinstance(v, dict)), default=0)
            if max_prob > 95:
                scores['fedwatch'] = 3
            elif max_prob > 88:
                scores['fedwatch'] = 2
            elif max_prob > 75:
                scores['fedwatch'] = 1
            notes.append(f'FedWatch dominant probability: {max_prob}%')
        except Exception as e:
            logger.debug(f'FedWatch parse failed: {e}')

    # Method 2: COT extreme (pakai EUR sebagai proxy USD positioning terbesar)
    cot_stmt = select(COTReport).where(COTReport.market_code == '099741')
    if sim_time is not None:
        cot_stmt = cot_stmt.where(COTReport.report_date <= sim_time.date())
    cot_rows = (
        await session.execute(
            cot_stmt.order_by(COTReport.report_date.desc()).limit(52)
        )
    ).scalars().all()
    percentile = None
    long_pct = None
    if cot_rows:
        cot_row = cot_rows[0]
        l_long = getattr(cot_row, 'leveraged_long', None)
        l_short = getattr(cot_row, 'leveraged_short', None)
        if isinstance(l_long, (int, float)) and isinstance(l_short, (int, float)):
            total = l_long + l_short
            if total > 0:
                long_pct = l_long / total * 100
                hist_ratios = []
                for r in cot_rows:
                    rl = getattr(r, 'leveraged_long', None)
                    rs = getattr(r, 'leveraged_short', None)
                    if isinstance(rl, (int, float)) and isinstance(rs, (int, float)) and (rl + rs) > 0:
                        hist_ratios.append(rl / (rl + rs) * 100)

                if len(hist_ratios) >= 5:
                    percentile = sum(1 for h in hist_ratios if h <= long_pct) / len(hist_ratios) * 100.0
                else:
                    percentile = long_pct

                extreme = cot_extreme_score('EURUSD', long_pct, hist_ratios if len(hist_ratios) >= 10 else None)
                if extreme != 0:
                    scores['cot'] = 3
                    notes.append(f'COT EUR leveraged funds EXTREME positioning ({long_pct:.1f}% long, {percentile:.1f}th percentile)')
                else:
                    ratio = abs(l_long - l_short) / total
                    scores['cot'] = 2 if ratio > 0.5 else 1 if ratio > 0.3 else 0

    scores['cot_long_pct'] = round(long_pct, 1) if long_pct is not None else None
    scores['cot_positioning_percentile'] = round(percentile, 1) if percentile is not None else None

    # Method 3: USD momentum via synthetic basket
    proxy = await compute_usd_strength_proxy(session, lookback_bars=20, timeframe='H4', as_of=sim_time)
    if 'error' not in proxy:
        change_pct = abs(proxy.get('weighted_usd_change_pct', 0))
        if change_pct > 3.0:
            scores['usd_momentum'] = 3
        elif change_pct > 2.0:
            scores['usd_momentum'] = 2
        elif change_pct > 1.0:
            scores['usd_momentum'] = 1
        notes.append(f"USD basket momentum: {proxy.get('weighted_usd_change_pct', 0):+.2f}% ({proxy.get('direction')})")

    # Method 4: News saturation — baca dari digest_metadata yang sudah dihitung news_digest.py
    digest_stmt = select(NewsDigest)
    if sim_time is not None:
        digest_stmt = digest_stmt.where(NewsDigest.generated_at <= sim_time)
    digest = (
        await session.execute(digest_stmt.order_by(NewsDigest.generated_at.desc()).limit(1))
    ).scalar_one_or_none()
    if digest and digest.digest_text and 'digest_metadata' in digest.digest_text:
        try:
            start = digest.digest_text.index('```digest_metadata') + len('```digest_metadata')
            end = digest.digest_text.index('```', start)
            metadata = json.loads(digest.digest_text[start:end].strip())
            saturation = metadata.get('priced_in_signal', {}).get('saturation_risk', 'LOW')
            scores['news_saturation'] = {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}.get(saturation, 0)
            notes.append(f'News saturation risk: {saturation}')
        except Exception as e:
            logger.debug(f'Digest metadata parse failed: {e}')

    scores['total_auto'] = sum([scores['fedwatch'], scores['cot'], scores['usd_momentum'], scores['news_saturation']])
    scores['notes'] = notes
    scores['computed_at'] = clock.now().isoformat()
    scores['interpretation'] = (
        'FULLY_PRICED_IN' if scores['total_auto'] >= 8 else
        'LARGELY_PRICED_IN' if scores['total_auto'] >= 5 else
        'PARTIALLY_PRICED_IN' if scores['total_auto'] >= 3 else
        'NOT_PRICED_IN'
    )
    return scores
