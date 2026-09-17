from analysis.calculators.volume_profile import compute_volume_profile
from analysis.calculators.regime_classifier import compute_bollinger_donchian_chop, classify_market_regime

async def evaluate_pretrade_gate(session, symbol: str, settings: dict, strategy_type: str) -> tuple[bool, str]:
    """strategy_type: 'mean_reversion' | 'trend'"""
    chop = await compute_bollinger_donchian_chop(session, symbol, 'H4', settings)
    if chop.get('chop_block') and strategy_type == 'trend':
        return False, f"chop_block: {chop.get('reason')}"

    vp = await compute_volume_profile(session, symbol, settings)
    if 'error' not in vp:
        if vp['regime'] == 'imbalanced' and strategy_type == 'mean_reversion':
            return False, "imbalanced volume regime blocks mean-reversion"
        if vp['regime'] == 'balanced' and strategy_type == 'trend':
            return False, "balanced volume regime blocks pure trend-following"

    regime = await classify_market_regime(session, symbol, settings)
    min_adx = settings.get('trading', {}).get('edge_strategy', {}).get('min_adx_for_trend', 20)
    if strategy_type == 'trend' and regime.get('adx') is not None and regime['adx'] < min_adx:
        return False, f"ADX={regime['adx']:.1f} < {min_adx}"

    return True, "ok"
