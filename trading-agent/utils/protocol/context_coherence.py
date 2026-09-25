"""
Context Coherence Module
Analog of Context Divergence Score (CDS) and ContextMerge from:
"Hallucination as Context Drift" - Rodrigues (2026)

Detects when Stage 1 FundamentalBrief diverges from actual market state,
triggering explicit reconciliation before Stage 2 joint reasoning proceeds.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from utils.market.bias_utils import normalize_bias

logger = logging.getLogger('TradingAgent.ContextCoherence')

# ============================================================
# Constants — exposed at module level for cross-module access
# ============================================================

# Implied USD direction from each symbol's decision
USD_DIRECTION_IMPLICATIONS: dict[str, dict[str, str]] = {
    'EURUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'GBPUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'AUDUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'USDJPY': {'buy': 'USD_STRONG', 'sell': 'USD_WEAK'},
    'XAUUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'XTIUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'XBRUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
    'BTCUSD': {'buy': 'USD_WEAK',   'sell': 'USD_STRONG'},
}

# Currency-to-pair mapping for bias checking
SYMBOL_CURRENCY_MAP = {
    'EURUSD': {'base': 'EUR', 'quote': 'USD', 'inverted': False},
    'GBPUSD': {'base': 'GBP', 'quote': 'USD', 'inverted': False},
    'USDJPY': {'base': 'USD', 'quote': 'JPY', 'inverted': False},
    'AUDUSD': {'base': 'AUD', 'quote': 'USD', 'inverted': False},
    'XAUUSD': {'base': 'XAU', 'quote': 'USD', 'inverted': False},
    'XTIUSD': {'base': 'XTI', 'quote': 'USD', 'inverted': False},
    'XBRUSD': {'base': 'XBR', 'quote': 'USD', 'inverted': False},
    'BTCUSD': {'base': 'BTC', 'quote': 'USD', 'inverted': False},
}

# Minimum price change to be considered a "signal" (not noise)
SIGNAL_THRESHOLD_PCT = 0.003   # 0.3%
# CDS threshold above which reconciliation note is injected
CDS_TRIGGER_THRESHOLD = 0.35

def get_base_quote_tags(symbol: str) -> str:
    """Returns 'BASE,QUOTE' style tag string, canonical order."""
    info = SYMBOL_CURRENCY_MAP.get(symbol)
    if not info:
        return 'USD'
    return f"{info['base']},{info['quote']}"

# ============================================================
# 1. Brief-vs-Price Divergence (Stage 1 → Stage 2 context drift)
# ============================================================

async def compute_brief_price_divergence(
    session: AsyncSession,
    symbol: str,
    brief_currency_bias: dict,
    lookback_bars: int = 20,
) -> tuple[float, str]:
    """
    Compute Context Divergence Score (0.0 = coherent, 1.0 = highly divergent)
    between FundamentalBrief currency bias and actual recent price action.

    Returns (cds_score, reconciliation_note)
    - cds_score  : 0.0 = coherent, 0.5 = one conflict, 1.0 = both currencies conflict
    - note       : Human-readable reconciliation instruction for agent context
    """
    from database.models import PriceOHLCV

    pair_info = SYMBOL_CURRENCY_MAP.get(symbol)
    if not pair_info:
        return 0.0, ''

    base_currency = pair_info['base']
    quote_currency = pair_info['quote']
    is_inverted = pair_info['inverted']

    # --- Fetch recent H4 bars ---
    bars = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == 'H4')
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(lookback_bars)
    )).scalars().all()

    if len(bars) < 5:
        return 0.0, ''

    bars = list(reversed(bars))
    first_close = bars[0].close
    last_close = bars[-1].close

    if not first_close or first_close <= 0:
        return 0.0, ''

    pct_change = (last_close - first_close) / first_close

    # --- Derive actual implied bias from price action ---
    # For non-inverted pairs (e.g. EURUSD): UP = base bullish, quote bearish
    # For inverted (USDJPY): UP = base (USD) bullish, quote (JPY) bearish
    if abs(pct_change) < SIGNAL_THRESHOLD_PCT:
        # Price move too small to infer directional signal
        return 0.0, ''

    if pct_change > 0:
        base_actual  = 'bullish'
        quote_actual = 'bearish'
    else:
        base_actual  = 'bearish'
        quote_actual = 'bullish'

    # For inverted pairs logic remains the same (base=USD for USDJPY)

    # --- Compare with brief bias ---
    from utils.market.bias_utils import normalize_bias
    base_bias  = normalize_bias(brief_currency_bias.get(base_currency, 'neutral'))
    quote_bias = normalize_bias(brief_currency_bias.get(quote_currency, 'neutral'))

    divergences = []

    if base_bias not in ('neutral',) and base_actual != base_bias:
        divergences.append(
            f"{base_currency}: Stage 1 brief='{base_bias}', "
            f"recent {symbol} price action implies='{base_actual}'"
        )

    if quote_bias not in ('neutral',) and quote_actual != quote_bias:
        divergences.append(
            f"{quote_currency}: Stage 1 brief='{quote_bias}', "
            f"recent {symbol} price action implies='{quote_actual}'"
        )

    if not divergences:
        return 0.0, ''

    cds_score = min(1.0, len(divergences) * 0.5)
    pct_str = f"{pct_change * 100:+.2f}%"
    hours_covered = len(bars) * 4  # H4 bars → hours

    note = (
        f"\n\n{'='*60}\n"
        f"⚠️  CONTEXT COHERENCE WARNING — {symbol}\n"
        f"{'='*60}\n"
        f"Context Divergence Score: {cds_score:.2f} (threshold: {CDS_TRIGGER_THRESHOLD})\n"
        f"\nConflict detected between Stage 1 macro brief and recent price action:\n"
        f"  {symbol} moved {pct_str} over the last {hours_covered} hours (H4 data).\n\n"
        f"Divergences:\n"
    )
    for d in divergences:
        note += f"  → {d}\n"

    note += (
        f"\n[MANDATORY RECONCILIATION REQUIRED]\n"
        f"Before submitting your final decision, you MUST explicitly state in your rationale:\n"
        f"  1. WHY this contradiction exists (brief stale? temporary move? noise?)\n"
        f"  2. WHICH source you trust more for THIS decision (price action OR brief bias) and why\n"
        f"  3. HOW this affects your confluence scoring\n\n"
        f"Acceptable responses:\n"
        f"  A. 'I trust price action — brief is {hours_covered}h old and market has moved significantly'\n"
        f"  B. 'I trust brief — price move is pre-event positioning, not a trend shift'\n"
        f"  C. 'Contradiction unresolved → WAIT until divergence closes'\n\n"
        f"DO NOT ignore this warning. Unaddressed contradictions are a leading cause\n"
        f"of false confidence signals in AI trading analysis.\n"
        f"{'='*60}\n"
    )

    return cds_score, note

# ============================================================
# 2. Cross-Tool Data Coherence Check (for Stage2DataBundler)
# ============================================================

def compute_bundle_coherence_issues(data: dict) -> list[str]:
    """
    Cross-validate multiple data sources within the Stage 2 bundle.
    Returns list of human-readable coherence issues to inject into bundle.

    Analogous to paper's finding that agents need to check for
    inconsistent world states before proceeding with joint reasoning.
    """
    issues = []

    brief_data = data.get('get_fundamental_brief', {})
    vix_data   = data.get('get_vix', {})
    dxy_data   = data.get('get_dxy', {})

    # --- 1. VIX vs brief risk_sentiment ---
    if brief_data and vix_data and not brief_data.get('error') and not vix_data.get('error'):
        risk_sentiment = brief_data.get('risk_sentiment', 'mixed')
        vix_latest = vix_data.get('latest', {})
        vix_close  = vix_latest.get('close') if vix_latest else None

        if vix_close is not None:
            if vix_close > 27 and risk_sentiment == 'risk-on':
                issues.append(
                    f"VIX={vix_close:.1f} indicates HIGH FEAR but Stage 1 brief says "
                    f"risk_sentiment='{risk_sentiment}'. "
                    f"VIX is real-time; trust VIX. Treat as risk-off environment. "
                    f"Increase confluence threshold by +1."
                )
            elif vix_close < 14 and risk_sentiment == 'risk-off':
                issues.append(
                    f"VIX={vix_close:.1f} indicates COMPLACENCY but brief says risk_sentiment='{risk_sentiment}'. "
                    f"Reconcile before deciding."
                )

    # --- 2. DXY trend vs USD bias in brief ---
    if brief_data and dxy_data and not brief_data.get('error') and not dxy_data.get('error'):
        dxy_trend = dxy_data.get('trend_5d', 'unknown')
        currency_bias = brief_data.get('currency_bias', {})
        usd_bias = normalize_bias(currency_bias.get('USD', 'neutral'))
        eur_bias = normalize_bias(currency_bias.get('EUR', 'neutral'))

        if dxy_trend == 'strengthening' and usd_bias == 'bearish':
            issues.append(
                f"DXY 5-day trend='{dxy_trend}' (USD gaining strength) "
                f"but brief says USD='{usd_bias}'. "
                f"DXY is price-based and more current. Reconsider USD bias."
            )
        elif dxy_trend == 'strengthening' and eur_bias == 'bullish':
            issues.append(
                f"DXY strengthening (USD strong) but brief says EUR='{eur_bias}'. "
                f"EUR and USD strength are strongly inversely correlated (~0.95). "
                f"EUR bullish thesis weakened by DXY trend."
            )
        elif dxy_trend == 'weakening' and usd_bias == 'bullish':
            issues.append(
                f"DXY 5-day trend='{dxy_trend}' (USD losing strength) "
                f"but brief says USD='{usd_bias}'. "
                f"Verify USD bullish thesis against DXY data."
            )

    # --- 3. Risk sentiment vs gold/JPY directional consistency ---
    # (gold and JPY are safe-havens: risk-off → gold/JPY bullish)
    if brief_data and not brief_data.get('error'):
        currency_bias = brief_data.get('currency_bias', {})
        risk_sentiment = brief_data.get('risk_sentiment', 'mixed')
        jpy_bias = normalize_bias(currency_bias.get('JPY', 'neutral'))
        xau_bias = normalize_bias(currency_bias.get('XAU', 'neutral'))

        if risk_sentiment == 'risk-on' and xau_bias == 'bullish':
            issues.append(
                f"Brief says risk_sentiment='risk-on' but XAU='{xau_bias}'. "
                f"Gold is a safe-haven — typically bearish in risk-on. "
                f"Verify gold bull thesis has idiosyncratic driver beyond risk sentiment."
            )
        elif risk_sentiment == 'risk-off' and jpy_bias == 'bearish':
            issues.append(
                f"Brief says risk_sentiment='risk-off' but JPY='{jpy_bias}'. "
                f"JPY is a safe-haven — typically bullish in risk-off. "
                f"Verify JPY bear thesis has idiosyncratic driver."
            )

    return issues

# ============================================================
# 3. Cross-Pair Contradiction Detection (Post-parallel analysis)
# ============================================================

def compute_cross_pair_contradictions(analyses_results: dict) -> list[dict]:
    """
    Detect contradictory USD directional signals across multiple pair analyses.

    Returns list of contradiction dicts with:
      - description: human-readable explanation
      - strong_usd_symbols: list of symbols implying USD strong
      - weak_usd_symbols: list of symbols implying USD weak
      - recommended_filter: which direction to keep (based on count/confidence)
    """
    strong_usd = {}  # symbol → confidence
    weak_usd   = {}  # symbol → confidence

    for symbol, result in analyses_results.items():
        decision = result.get('decision', 'wait')
        if decision not in ('buy', 'sell'):
            continue
        implications = USD_DIRECTION_IMPLICATIONS.get(symbol, {})
        usd_dir = implications.get(decision)
        confidence = result.get('confidence', 0.5)

        if usd_dir == 'USD_STRONG':
            strong_usd[symbol] = confidence
        elif usd_dir == 'USD_WEAK':
            weak_usd[symbol] = confidence

    if not (strong_usd and weak_usd):
        return []

    # Determine recommended filter: keep side with higher avg confidence
    avg_strong = sum(strong_usd.values()) / len(strong_usd) if strong_usd else 0
    avg_weak   = sum(weak_usd.values())   / len(weak_usd)   if weak_usd   else 0
    recommended = 'USD_STRONG' if avg_strong >= avg_weak else 'USD_WEAK'

    return [{
        'description': (
            f"USD direction contradiction: "
            f"Signals implying USD STRONG: {list(strong_usd.keys())} (avg_conf={avg_strong:.2f}). "
            f"Signals implying USD WEAK: {list(weak_usd.keys())} (avg_conf={avg_weak:.2f}). "
            f"Recommended: keep '{recommended}' side."
        ),
        'strong_usd_symbols': list(strong_usd.keys()),
        'weak_usd_symbols':   list(weak_usd.keys()),
        'recommended_filter': recommended,
        'avg_strong_conf':    avg_strong,
        'avg_weak_conf':      avg_weak,
    }]
