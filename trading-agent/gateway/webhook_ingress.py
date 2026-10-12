"""
Compatibility facade shim for legacy webhook_ingress.py.
Re-exports from canonical monika.interfaces.gateway.webhook_ingress.
"""

from __future__ import annotations

import monika.interfaces.gateway.webhook_ingress as _canonical

from monika.interfaces.gateway.webhook_ingress import (
    DEFAULT_REPLAY_WINDOW_SECONDS,
    MAX_NONCE_CACHE_SIZE,
    WebhookHandler,
    WebhookIngressResult,
    WebhookIngressRouter,
    WebhookIngressStatus,
    WebhookSignatureVerifier,
    get_webhook_router,
    logger,
    normalize_tradingview_payload,
)

__all__ = ['DEFAULT_REPLAY_WINDOW_SECONDS', 'MAX_NONCE_CACHE_SIZE', 'WebhookHandler', 'WebhookIngressResult', 'WebhookIngressRouter', 'WebhookIngressStatus', 'WebhookSignatureVerifier', 'get_webhook_router', 'logger', 'normalize_tradingview_payload']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
