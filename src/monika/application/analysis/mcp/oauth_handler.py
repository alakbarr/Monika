"""
Backward-compatibility facade for oauth_handler.
Canonical location: monika.infrastructure.mcp.oauth_handler
"""

import sys
import monika.infrastructure.mcp.oauth_handler as _canonical

from monika.infrastructure.mcp.oauth_handler import (
    OAuthCallbackServer,
    OAuthTokenStorage,
    generate_pkce_pair,
)

__all__ = [
    "generate_pkce_pair",
    "OAuthCallbackServer",
    "OAuthTokenStorage",
]

sys.modules[__name__] = _canonical
