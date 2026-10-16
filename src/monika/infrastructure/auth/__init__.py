# ==============================================================================
# File: infrastructure/auth/__init__.py
# ==============================================================================

"""
OAuth and Subscription Credential Management for Monika Trading Agent.
"""

from monika.infrastructure.auth.antigravity_bridge import (
    DEFAULT_ANTIGRAVITY_PROXY_URL,
    check_antigravity_bridge_health,
    get_antigravity_home,
    is_antigravity_installed,
)
from monika.infrastructure.auth.claude_oauth import (
    CLAUDE_OAUTH_CLIENT_ID,
    exchange_code_for_token,
    generate_pkce_pair,
    get_claude_authorization_url,
    get_claude_credentials_path,
    read_claude_code_credentials,
    refresh_claude_token,
    resolve_claude_access_token,
)
from monika.infrastructure.auth.codex_device_flow import (
    CODEX_OAUTH_CLIENT_ID,
    DEFAULT_CODEX_BASE_URL,
    exchange_codex_code,
    get_codex_cli_auth_path,
    poll_codex_authorization,
    read_codex_cli_credentials,
    refresh_codex_token,
    request_codex_device_code,
    resolve_codex_access_token,
)
from monika.infrastructure.auth.oauth_store import (
    decode_jwt_claims,
    delete_oauth_tokens,
    get_oauth_tokens,
    get_token_expiry_timestamp,
    is_token_expiring,
    list_authenticated_providers,
    save_oauth_tokens,
)

__all__ = [
    "CLAUDE_OAUTH_CLIENT_ID",
    "CODEX_OAUTH_CLIENT_ID",
    "DEFAULT_ANTIGRAVITY_PROXY_URL",
    "DEFAULT_CODEX_BASE_URL",
    "check_antigravity_bridge_health",
    "decode_jwt_claims",
    "delete_oauth_tokens",
    "exchange_code_for_token",
    "exchange_codex_code",
    "generate_pkce_pair",
    "get_antigravity_home",
    "get_claude_authorization_url",
    "get_claude_credentials_path",
    "get_codex_cli_auth_path",
    "get_oauth_tokens",
    "get_token_expiry_timestamp",
    "is_antigravity_installed",
    "is_token_expiring",
    "list_authenticated_providers",
    "poll_codex_authorization",
    "read_claude_code_credentials",
    "read_codex_cli_credentials",
    "refresh_claude_token",
    "refresh_codex_token",
    "request_codex_device_code",
    "resolve_claude_access_token",
    "resolve_codex_access_token",
    "save_oauth_tokens",
]
