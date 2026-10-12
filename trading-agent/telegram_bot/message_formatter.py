"""
Compatibility facade shim for legacy message_formatter.py.
Re-exports from canonical monika.interfaces.telegram.message_formatter.
"""

from __future__ import annotations

import monika.interfaces.telegram.message_formatter as _canonical

from monika.interfaces.telegram.message_formatter import (
    DEFAULT_SLIP_WIDTH,
    DEFAULT_USD_IDR_RATE,
    convert_usd_to_idr,
    format_alert_slip,
    format_approvals_slip,
    format_cot_slip,
    format_crystallized_slip,
    format_currency_dual,
    format_fear_greed_slip,
    format_fedwatch_slip,
    format_help_slip,
    format_idr_currency,
    format_pipeline_slip,
    format_playbooks_slip,
    format_positions_slip,
    format_reconcile_slip,
    format_risk_deep_slip,
    format_risk_slip,
    format_rollback_slip,
    format_stats_slip,
    format_status_slip,
    format_trailing_slip,
    format_yields_slip,
    get_fintech_badge,
    make_footer,
    make_header,
)

__all__ = ['DEFAULT_SLIP_WIDTH', 'DEFAULT_USD_IDR_RATE', 'convert_usd_to_idr', 'format_alert_slip', 'format_approvals_slip', 'format_cot_slip', 'format_crystallized_slip', 'format_currency_dual', 'format_fear_greed_slip', 'format_fedwatch_slip', 'format_help_slip', 'format_idr_currency', 'format_pipeline_slip', 'format_playbooks_slip', 'format_positions_slip', 'format_reconcile_slip', 'format_risk_deep_slip', 'format_risk_slip', 'format_rollback_slip', 'format_stats_slip', 'format_status_slip', 'format_trailing_slip', 'format_yields_slip', 'get_fintech_badge', 'make_footer', 'make_header']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
