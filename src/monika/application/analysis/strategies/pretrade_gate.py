from datetime import datetime, timezone
from typing import Optional

import monika.core.primitives.clock as clock
from monika.application.analysis.calculators.regime_classifier import (
    classify_market_regime,
    compute_bollinger_donchian_chop,
)
from monika.application.analysis.calculators.volume_profile import compute_volume_profile
from monika.core.validation.data_validator import is_crypto_symbol


async def evaluate_pretrade_gate(
    session, symbol: str, settings: dict, strategy_type: Optional[str] = None, as_of: Optional[datetime] = None
) -> tuple[bool, str]:
    """
    Evaluates institutional pre-trade gates:
    1. Session Rollover Deadzone (21:55 - 22:15 UTC) to avoid 5-10x interbank spread explosions.
    2. Bollinger-Donchian Volatility Squeeze / Chop.
    3. Volume Profile balance / imbalance regime alignment.
    4. ADX trend strength threshold.
    """
    settings = settings or {}

    # 1. Microstructure: Session Rollover Deadzone Guard (exempts 24/7 crypto)
    rollover_enabled = settings.get("trading", {}).get("risk", {}).get("rollover_protection_enabled", True)
    is_crypto = is_crypto_symbol(symbol)
    if rollover_enabled and not is_crypto:
        now_utc = as_of or clock.now()
        cur_h = now_utc.hour
        cur_m = now_utc.minute
        if (cur_h == 21 and cur_m >= 55) or (cur_h == 22 and cur_m < 15):
            return False, "session_rollover_deadzone: high spread risk during 21:55-22:15 UTC interbank rollover"

    # If strategy_type is not provided, rollover check is the universal gate
    if not strategy_type:
        return True, "ok"

    # 2. Volatility Chop Gate
    chop = await compute_bollinger_donchian_chop(session, symbol, "H4", settings, as_of=as_of)
    if chop.get("chop_block") and strategy_type == "trend":
        return False, f"chop_block: {chop.get('reason')}"

    # 3. Volume Profile Regime Alignment (Fail-Closed)
    vp = await compute_volume_profile(session, symbol, settings, as_of=as_of)
    if "error" in vp:
        if strategy_type in ("trend", "mean_reversion"):
            return False, f"volume_profile_unavailable: {vp['error']}"
    else:
        if vp.get("regime") == "imbalanced" and strategy_type == "mean_reversion":
            return False, "imbalanced volume regime blocks mean-reversion"
        if vp.get("regime") == "balanced" and strategy_type == "trend":
            return False, "balanced volume regime blocks pure trend-following"

    # 4. ADX Trend Confirmation (Fail-Closed)
    regime = await classify_market_regime(session, symbol, settings, as_of=as_of)
    min_adx = settings.get("trading", {}).get("edge_strategy", {}).get("min_adx_for_trend", 20)
    if strategy_type == "trend":
        adx_val = regime.get("adx")
        if adx_val is None:
            return False, "ADX indicator data unavailable for trend confirmation"
        if adx_val < min_adx:
            return False, f"ADX={adx_val:.1f} < {min_adx}"

    return True, "ok"
