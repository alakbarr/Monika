from datetime import datetime, timezone
import utils.clock as clock
from analysis.calculators.volume_profile import compute_volume_profile
from analysis.calculators.regime_classifier import compute_bollinger_donchian_chop, classify_market_regime

async def evaluate_pretrade_gate(session, symbol: str, settings: dict, strategy_type: str) -> tuple[bool, str]:
    """
    Evaluates institutional pre-trade gates:
    1. Session Rollover Deadzone (21:55 - 22:15 UTC) to avoid 5-10x interbank spread explosions.
    2. Bollinger-Donchian Volatility Squeeze / Chop.
    3. Volume Profile balance / imbalance regime alignment.
    4. ADX trend strength threshold.
    """
    settings = settings or {}

    # 1. Microstructure: Session Rollover Deadzone Guard
    rollover_enabled = settings.get('trading', {}).get('risk', {}).get('rollover_protection_enabled', True)
    if rollover_enabled:
        now_utc = clock.now()
        cur_h = now_utc.hour
        cur_m = now_utc.minute
        if (cur_h == 21 and cur_m >= 55) or (cur_h == 22 and cur_m < 15):
            return False, "session_rollover_deadzone: high spread risk during 21:55-22:15 UTC interbank rollover"

    # 2. Volatility Chop Gate
    chop = await compute_bollinger_donchian_chop(session, symbol, 'H4', settings)
    if chop.get('chop_block') and strategy_type == 'trend':
        return False, f"chop_block: {chop.get('reason')}"

    # 3. Volume Profile Regime Alignment
    vp = await compute_volume_profile(session, symbol, settings)
    if 'error' not in vp:
        if vp.get('regime') == 'imbalanced' and strategy_type == 'mean_reversion':
            return False, "imbalanced volume regime blocks mean-reversion"
        if vp.get('regime') == 'balanced' and strategy_type == 'trend':
            return False, "balanced volume regime blocks pure trend-following"

    # 4. ADX Trend Confirmation
    regime = await classify_market_regime(session, symbol, settings)
    min_adx = settings.get('trading', {}).get('edge_strategy', {}).get('min_adx_for_trend', 20)
    if strategy_type == 'trend' and regime.get('adx') is not None and regime['adx'] < min_adx:
        return False, f"ADX={regime['adx']:.1f} < {min_adx}"

    return True, "ok"
