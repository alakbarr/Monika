import logging
import json
from typing import Dict, Any, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig

logger = logging.getLogger('TradingAgent.Graph.ReflectionNode')

async def reflection_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Cross-asset reflection: reviews all decisions collectively before execution.
    Detects: correlation conflicts, score inflation patterns, systematic bias.
    """
    configurable = (config.get('configurable') if isinstance(config, dict) else getattr(config, 'configurable', None)) or {}
    scheduler = configurable.get('scheduler') if isinstance(configurable, dict) else None
    summary = state.get('summary', {})
    actionable = state.get('actionable_trades', [])
    
    if not actionable:
        return {'summary': summary}
    
    # === CHECK 1: Correlation conflict detection ===
    try:
        from utils.protocol.context_coherence import compute_cross_pair_contradictions
        analyses_dict = dict(actionable)
        contradictions = compute_cross_pair_contradictions(analyses_dict)
        if contradictions:
            logger.warning(f"[Reflection] Cross-pair contradictions detected: {contradictions[0]['description']}")
            # Keep only the recommended direction if there is a conflict
            recommended = contradictions[0].get('recommended_filter')
            if recommended in ('USD_STRONG', 'KEEP_STRONG_USD'):
                kept_symbols = set(contradictions[0].get('strong_usd_symbols', []))
                actionable = [(sym, r) for sym, r in actionable if sym in kept_symbols or sym not in contradictions[0].get('weak_usd_symbols', [])]
            elif recommended in ('USD_WEAK', 'KEEP_WEAK_USD'):
                kept_symbols = set(contradictions[0].get('weak_usd_symbols', []))
                actionable = [(sym, r) for sym, r in actionable if sym in kept_symbols or sym not in contradictions[0].get('strong_usd_symbols', [])]
            summary['reflection_contradiction_filtered'] = contradictions[0]['description']
    except Exception as e:
        logger.debug(f"[Reflection] Cross-pair contradiction check failed: {e}")

    CORRELATION_GROUPS = {
        'usd_long': ['EURUSD_sell', 'GBPUSD_sell', 'AUDUSD_sell', 'USDJPY_buy', 'XAUUSD_sell'],
        'usd_short': ['EURUSD_buy', 'GBPUSD_buy', 'AUDUSD_buy', 'USDJPY_sell', 'XAUUSD_buy']
    }
    
    usd_exposure = {}
    for sym, r in actionable:
        direction = r.get('decision', 'wait')
        key = f'{sym}_{direction}'
        for group_name, members in CORRELATION_GROUPS.items():
            if key in members:
                usd_exposure[group_name] = usd_exposure.get(group_name, 0) + 1
    
    max_same_direction = max(usd_exposure.values()) if usd_exposure else 0
    if max_same_direction >= 3:
        direction_str = 'LONG USD' if usd_exposure.get('usd_long', 0) > usd_exposure.get('usd_short', 0) else 'SHORT USD'
        logger.warning(
            f'[Reflection] Extreme {direction_str} bias: {max_same_direction} correlated pairs. '
            f'Filtering to max 2 trades in same direction.'
        )
        # Keep only highest confidence 2 in dominant correlated direction
        dominant_group = 'usd_long' if usd_exposure.get('usd_long', 0) >= usd_exposure.get('usd_short', 0) else 'usd_short'
        dominant_members = CORRELATION_GROUPS[dominant_group]
        filtered = []
        same_dir_count = 0
        for sym, r in sorted(actionable, key=lambda x: x[1].get('confidence', 0), reverse=True):
            direction = r.get('decision', 'wait')
            key = f'{sym}_{direction}'
            if key in dominant_members:
                if same_dir_count < 2:
                    filtered.append((sym, r))
                    same_dir_count += 1
            else:
                filtered.append((sym, r))
        actionable = filtered
        summary['reflection_filtered'] = f'Reduced from {max_same_direction} to 2 correlated trades'
    
    # === CHECK 2: Score inflation pattern detection ===
    confluence_scores = [
        r.get('confluence_score') 
        for _, r in actionable 
        if r.get('confluence_score') is not None
    ]
    
    if len(confluence_scores) >= 2:
        avg_score = sum(confluence_scores) / len(confluence_scores)
        if avg_score >= 10.5:  # All assets reporting very high scores simultaneously is suspicious
            logger.warning(
                f'[Reflection] Potential score inflation: avg confluence = {avg_score:.1f} '
                f'across {len(confluence_scores)} assets. Adding +1 to effective threshold.'
            )
            # Mark for execution node to apply stricter check
            summary['reflection_score_inflation_suspected'] = True
    
    # === CHECK 3: VIX-adjusted filtering ===
    # Defensive default: Assume elevated volatility (VIX=25) when data is unavailable,
    # constraining trade concurrency to 1 trade under fail-safe posture.
    vix_value = None
    try:
        from database.db import get_session
        from database.models import VIXData
        from sqlalchemy import select
        async with get_session() as session:
            vix_row = (await session.execute(
                select(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
        
        if vix_row and vix_row.close is not None:
            vix_value = vix_row.close
        else:
            # VIX data tidak ada di DB — gunakan defensive default (25.1)
            vix_value = 25.1
            logger.warning('[Reflection] VIX data not found in DB. Applying defensive default VIX=25.1')
    except Exception as e:
        # Query gagal — gunakan defensive default (25.1)
        vix_value = 25.1
        logger.warning(f'[Reflection] VIX query failed ({e}). Applying defensive default VIX=25.1')
    
    if vix_value > 38:
        # Extreme VIX: only keep highest confidence trade
        if len(actionable) > 1:
            actionable = sorted(actionable, key=lambda x: x[1].get('confidence', 0), reverse=True)[:1]
            summary['reflection_vix_filtered'] = f'VIX={vix_value:.1f} > 38: limited to 1 trade'
            logger.info(f'[Reflection] VIX={vix_value:.1f}: filtered to 1 highest-confidence trade (extreme volatility)')
    elif vix_value > 25:
        # Elevated VIX: keep top 2 highest confidence trades
        if len(actionable) > 2:
            actionable = sorted(actionable, key=lambda x: x[1].get('confidence', 0), reverse=True)[:2]
            summary['reflection_vix_filtered'] = f'VIX={vix_value:.1f} > 25: limited to top 2 trades'
            logger.info(f'[Reflection] VIX={vix_value:.1f}: filtered to top 2 trades (elevated volatility)')
    
    # --- MACRO NARRATIVE CROSS-VALIDATION ---
    SYMBOL_CURRENCY_MAP = {
        'EURUSD': ('EUR', 'USD'), 'GBPUSD': ('GBP', 'USD'),
        'USDJPY': ('USD', 'JPY'), 'AUDUSD': ('AUD', 'USD'),
        'USDCAD': ('USD', 'CAD'), 'USDCHF': ('USD', 'CHF'),
        'NZDUSD': ('NZD', 'USD'), 'EURJPY': ('EUR', 'JPY'),
        'GBPJPY': ('GBP', 'JPY'), 'EURGBP': ('EUR', 'GBP'),
        'XAUUSD': ('XAU', 'USD'), 'XTIUSD': ('OIL', 'USD'),
        'XBRUSD': ('OIL', 'USD'),
        'BTCUSD': ('BTC', 'USD'), 'ETHUSD': ('ETH', 'USD')
    }
    try:
        from database.db import get_session
        from database.models import FundamentalBrief
        from sqlalchemy import select
        async with get_session() as session:
            brief_row = (await session.execute(
                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
            )).scalar_one_or_none()
        
        if brief_row and brief_row.structured_json:
            import json
            brief_data = json.loads(brief_row.structured_json)
            currency_bias = brief_data.get('currency_bias', {})
            
            if currency_bias:
                inconsistent_trades = []
                consistent_trades = []
                
                for sym, r in actionable:
                    direction = r.get('decision', 'wait')
                    import re
                    clean_sym = re.sub(r'[^A-Z]', '', sym.upper())[:6]
                    base, quote = SYMBOL_CURRENCY_MAP.get(sym, SYMBOL_CURRENCY_MAP.get(clean_sym, (None, None)))
                    if base is None and len(clean_sym) == 6:
                        base, quote = clean_sym[:3], clean_sym[3:]
                    
                    if base is None or quote is None:
                        consistent_trades.append((sym, r))
                        continue
                    
                    from utils.market.bias_utils import normalize_bias
                    base_bias = normalize_bias(currency_bias.get(base, 'neutral'))
                    quote_bias = normalize_bias(currency_bias.get(quote, 'neutral'))
                    
                    if direction == 'buy':
                        is_consistent = (base_bias == 'bullish' or quote_bias == 'bearish')
                        is_consistent = is_consistent or (base_bias == 'neutral' and quote_bias == 'neutral')
                    elif direction == 'sell':
                        is_consistent = (base_bias == 'bearish' or quote_bias == 'bullish')
                        is_consistent = is_consistent or (base_bias == 'neutral' and quote_bias == 'neutral')
                    else:
                        is_consistent = True
                    
                    if not is_consistent:
                        logger.warning(
                            f'[Reflection] MACRO INCONSISTENCY: {sym} {direction.upper()} '
                            f'contradicts brief bias ({base}={base_bias}, {quote}={quote_bias}). '
                            f'Requiring higher confluence or filtering.'
                        )
                        r_copy = dict(r)
                        r_copy['macro_inconsistent'] = True
                        r_copy['macro_inconsistency_detail'] = f'{sym} {direction.upper()} contradicts brief: {base}={base_bias}, {quote}={quote_bias}'
                        inconsistent_trades.append((sym, r_copy))
                    else:
                        consistent_trades.append((sym, r))
                
                if inconsistent_trades and consistent_trades:
                    logger.warning(f'[Reflection] Filtering {len(inconsistent_trades)} macro-inconsistent trades in favor of {len(consistent_trades)} consistent ones.')
                    summary['reflection_macro_inconsistent_filtered'] = [f"{sym} {r.get('decision','?').upper()}" for sym, r in inconsistent_trades]
                    actionable = consistent_trades
                elif inconsistent_trades and not consistent_trades:
                    logger.warning('[Reflection] ALL actionable trades are macro-inconsistent. Proceeding but flagging all.')
                    summary['reflection_all_macro_inconsistent'] = True
                    actionable = inconsistent_trades
    except Exception as e:
        logger.warning(f'[Reflection] Macro consistency check failed (non-fatal): {e}')

    logger.info(f'[Reflection] Final actionable after reflection: {[s for s, _ in actionable]}')
    return {
        'summary': summary,
        'actionable_trades': actionable,
        'reflection_applied': True
    }
