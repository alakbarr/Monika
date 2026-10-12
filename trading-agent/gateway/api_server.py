"""
Compatibility facade shim for legacy api_server.py.
Re-exports from canonical monika.interfaces.gateway.api_server.
"""

from __future__ import annotations

import monika.interfaces.gateway.api_server as _canonical

from monika.interfaces.gateway.api_server import (
    AVAILABLE_MODELS,
    ChatCompletionRequest,
    ChatMessage,
    app,
    chat_completions,
    execute_query,
    general_webhook_ingress,
    get_default_chat_agent,
    health_check,
    list_models,
    logger,
    set_agent_runner,
    terminal_websocket,
    tradingview_webhook,
)

__all__ = ['AVAILABLE_MODELS', 'ChatCompletionRequest', 'ChatMessage', 'app', 'chat_completions', 'execute_query', 'general_webhook_ingress', 'get_default_chat_agent', 'health_check', 'list_models', 'logger', 'set_agent_runner', 'terminal_websocket', 'tradingview_webhook']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
