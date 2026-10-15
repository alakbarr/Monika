# ==============================================================================
# File: scripts/empirical_alpha/signals.py
# Unified aggregator for all institutional systematic alpha generators
# ==============================================================================

from typing import Dict, Callable, Optional, Any
from scripts.empirical_alpha.ultra_signals import get_ultra_signal_universe
from scripts.empirical_alpha.asset_pool_signals import generate_asset_signal_pool
from scripts.empirical_alpha.session_signals import get_asset_specific_signals
from scripts.empirical_alpha.multi_indicator_signals import get_mega_signal_pool
from scripts.empirical_alpha.omni_signals import build_omni_signals
from scripts.empirical_alpha.targeted_signals import build_targeted_signals


def build_all_signals(ev: Any, sym: str) -> Dict[str, Callable[[int], Optional[str]]]:
    """Combines all systematic signals across all asset universes and time horizons."""
    sigs: Dict[str, Callable[[int], Optional[str]]] = {}
    sigs.update(get_ultra_signal_universe(ev))
    sigs.update(generate_asset_signal_pool(ev))
    sigs.update(get_asset_specific_signals(ev, sym))
    sigs.update(get_mega_signal_pool(ev, sym))
    sigs.update(build_omni_signals(ev, sym))
    sigs.update(build_targeted_signals(ev, sym))
    return sigs
