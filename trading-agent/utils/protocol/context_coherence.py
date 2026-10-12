"""
Compatibility facade shim for legacy context_coherence.py.
Re-exports from canonical monika.application.protocol.context_coherence.
"""

from __future__ import annotations

import monika.application.protocol.context_coherence as _canonical

from monika.application.protocol.context_coherence import (
    CDS_TRIGGER_THRESHOLD,
    SIGNAL_THRESHOLD_PCT,
    SYMBOL_CURRENCY_MAP,
    USD_DIRECTION_IMPLICATIONS,
    compute_brief_price_divergence,
    compute_bundle_coherence_issues,
    compute_cross_pair_contradictions,
    get_base_quote_tags,
)

__all__ = ['CDS_TRIGGER_THRESHOLD', 'SIGNAL_THRESHOLD_PCT', 'SYMBOL_CURRENCY_MAP', 'USD_DIRECTION_IMPLICATIONS', 'compute_brief_price_divergence', 'compute_bundle_coherence_issues', 'compute_cross_pair_contradictions', 'get_base_quote_tags']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
