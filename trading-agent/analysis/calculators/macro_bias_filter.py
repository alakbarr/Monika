import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import TreasuryYield, InterestRate
from utils.protocol.context_coherence import SYMBOL_CURRENCY_MAP
from typing import Optional
import utils.clock as clock
logger = logging.getLogger('TradingAgent.MacroBiasFilter')
_CCY_TO_BANK = {'USD': 'FED', 'EUR': 'ECB', 'GBP': 'BOE', 'JPY': 'BOJ', 'AUD': 'RBA'}

# Proksi suku bunga netral (r*) spesifik per yurisdiksi bank sentral
_NEUTRAL_RATE_ESTIMATES = {
    'USD': 2.75,
    'EUR': 2.25,
    'GBP': 2.75,
    'JPY': 0.75,
    'AUD': 3.50,
}

async def _yield_momentum_score(session: AsyncSession, lookback_days: int, as_of: Optional[datetime] = None) -> float:
    ref_date = as_of.date() if isinstance(as_of, datetime) else (as_of or clock.now().date())
    since = ref_date - timedelta(days=lookback_days + 3)
    stmt = (
        select(TreasuryYield)
        .where(TreasuryYield.tenor == '10Y')
        .where(TreasuryYield.date >= since)
        .where(TreasuryYield.date <= ref_date)
        .order_by(TreasuryYield.date.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) < 2:
        return 0.0
    change = rows[-1].yield_percent - rows[0].yield_percent
    return max(-1.0, min(1.0, change / 0.15))  # +/-0.15% over window = "strong" move

async def _rate_score(session: AsyncSession, currency: str, as_of: Optional[datetime] = None) -> float:
    bank = _CCY_TO_BANK.get(currency)
    if not bank:
        return 0.0
    stmt = select(InterestRate).where(InterestRate.bank == bank)
    if as_of:
        ref_date = as_of.date() if isinstance(as_of, datetime) else as_of
        stmt = stmt.where(InterestRate.effective_date <= ref_date)
    row = (await session.execute(stmt.order_by(InterestRate.effective_date.desc()).limit(1))).scalar_one_or_none()
    if not row:
        return 0.0
    neutral_r = _NEUTRAL_RATE_ESTIMATES.get(currency, 2.50)
    # Stance relatif terhadap suku bunga netral domestik r* (+/-3.0% normal range)
    return max(-1.0, min(1.0, (row.rate_percent - neutral_r) / 3.0))

async def compute_currency_macro_score(session: AsyncSession, currency: str, settings: dict, as_of: Optional[datetime] = None) -> dict:
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('macro_bias', {})
    lookback = int(cfg.get('yield_lookback_days', 5))
    y = await _yield_momentum_score(session, lookback, as_of=as_of) if currency == 'USD' else 0.0
    r = await _rate_score(session, currency, as_of=as_of)

    from utils.market.usd_strength_proxy import compute_usd_strength_proxy
    proxy = await compute_usd_strength_proxy(session, lookback_bars=20, timeframe='H4', as_of=as_of)
    dxy = max(-1.0, min(1.0, proxy.get('weighted_usd_change_pct', 0.0) / 2.0))

    from database.models import VIXData
    from sqlalchemy import select
    vix_stmt = select(VIXData)
    if as_of:
        ref_date = as_of.date() if isinstance(as_of, datetime) else as_of
        vix_stmt = vix_stmt.where(VIXData.date <= ref_date)
    vix = (await session.execute(vix_stmt.order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
    risk = 0.0
    if vix:
        # Safe haven vs Risk-on currency transmission mapping
        risk_dir = {'USD': 1.0, 'JPY': 0.8, 'AUD': -1.0, 'GBP': -0.6, 'EUR': -0.3, 'XAU': 0.5}.get(currency, 0.0)
        if vix.close > 22:
            risk = risk_dir * min(1.0, (vix.close - 20) / 20)

    # Bobot diferensial: Suku bunga & ekspektasi kebijakan moneter adalah driver dominan
    if currency == 'USD':
        score = round(0.35*y + 0.35*r + 0.15*dxy + 0.15*risk, 3)
    elif currency == 'AUD':
        # AUD sangat dipengaruhi oleh risk appetite global dan siklus komoditas (terms of trade)
        score = round(0.50*r - 0.20*dxy + 0.30*risk, 3)
    elif currency == 'JPY':
        # JPY sangat sensitif terhadap carry trade funding & unwinding saat risk-off
        score = round(0.55*r - 0.25*dxy + 0.20*risk, 3)
    elif currency == 'GBP':
        # GBP dipengaruhi oleh suku bunga BoE dan kerentanan fiskal/twin deficit saat risk-off
        score = round(0.55*r - 0.25*dxy + 0.20*risk, 3)
    else:
        score = round(0.60*r - 0.25*dxy + 0.15*risk, 3)

    return {'currency': currency, 'score': score, 'yield_component': y, 'rate_component': r,
            'dxy_component': dxy, 'risk_component': risk}

async def evaluate_macro_alignment(session: AsyncSession, symbol: str, direction: str | None, settings: dict, as_of: Optional[datetime] = None) -> dict:
    """
    CAVEAT: True 'real yield' = nominal yield - inflation expectations (TIPS
    breakeven). This system's FRED config only pulls nominal DGS10 (see
    config/settings.yaml `data_sources.fred.series`). This is a deterministic
    PROXY (yield momentum + policy-rate level), not a genuine real-yield calc.
    To upgrade: add `real_yield_10y: DFII10` to the FRED series config and
    verify `data_sources/fred_treasury_yield.py` supports arbitrary
    series->tenor mapping (see "modules to verify").
    """
    result = {'symbol': symbol, 'direction': direction, 'aligned': True,
              'strong_conflict': False, 'reasons': []}
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('macro_bias', {})
    if not cfg.get('enabled', True):
        result['reasons'].append('disabled_in_settings'); return result
    threshold = float(cfg.get('strong_misalignment_threshold', 0.8))

    if symbol == 'XAUUSD':
        usd = await compute_currency_macro_score(session, 'USD', settings, as_of=as_of)
        pair_score = -usd['score']  # gold inversely tracks USD real-yield/rate pressure
        implied = 'buy' if pair_score > 0 else ('sell' if pair_score < 0 else None)
        result.update(pair_macro_score=pair_score, implied_direction=implied, usd_score=usd)
    else:
        pair = SYMBOL_CURRENCY_MAP.get(symbol)
        if not pair or (pair['base'] not in _CCY_TO_BANK and pair['base'] != 'USD'):
            result['reasons'].append('no_macro_mapping_fail_open'); return result
        base = pair['base'] if pair['base'] in _CCY_TO_BANK else 'USD'
        quote = pair['quote'] if pair['quote'] in _CCY_TO_BANK else 'USD'
        base_d = await compute_currency_macro_score(session, base, settings, as_of=as_of)
        quote_d = await compute_currency_macro_score(session, quote, settings, as_of=as_of)
        pair_score = round(base_d['score'] - quote_d['score'], 3)
        if pair['inverted']:
            pair_score = -pair_score
        implied = 'buy' if pair_score > 0 else ('sell' if pair_score < 0 else None)
        result.update(pair_macro_score=pair_score, implied_direction=implied,
                       base_score=base_d, quote_score=quote_d)

    if direction and implied and implied != direction and abs(result['pair_macro_score']) >= threshold:
        result.update(aligned=False, strong_conflict=True)
        result['reasons'].append(f"Macro score={result['pair_macro_score']:+.2f} strongly implies "
                                  f"{implied.upper()}, opposing proposed {direction.upper()}.")
    else:
        result['reasons'].append(f"Macro score={result['pair_macro_score']:+.2f} — no strong conflict")
    return result
