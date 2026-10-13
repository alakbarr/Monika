# ==============================================================================
# File: tests/security/test_fase4_central_config_and_security.py
# Description: Unit and integration tests for Fase 4 architectural security
# ==============================================================================

import os
from unittest.mock import MagicMock, patch
import pytest

from monika.infrastructure.database.db import get_database_url
import monika.infrastructure.database.db as db_mod
from monika.infrastructure.brokers.mt5_client import MT5Client
from monika.core.security.credential_vault import vault
from monika.infrastructure.credentials.credential_pool import CredentialPool
from monika.infrastructure.infra.log_redactor import redact_sensitive_text
from monika.interfaces.dashboard.routes.config import _mask_yaml_text
from monika.interfaces.dashboard.rbac import Role, resolve_role


def test_get_database_url_lazy_resolution():
    """Verify get_database_url resolves lazily across central settings, env, and fallback."""
    # 1. Fallback to default SQLite when no settings and no env
    with patch.dict(os.environ, {"DATABASE_URL": ""}):
        with patch("monika.core.config.settings.load_settings", return_value={}):
            assert get_database_url() == "sqlite+aiosqlite:///monika.db"

    # 2. Central settings takes precedence
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://env_host/env_db"}):
        with patch(
            "monika.core.config.settings.load_settings",
            return_value={"database": {"url": "postgresql+asyncpg://cfg_host/cfg_db"}},
        ):
            assert get_database_url() == "postgresql+asyncpg://cfg_host/cfg_db"

    # 3. Env fallback when settings lacks database.url
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://env_host/env_db"}):
        with patch("monika.core.config.settings.load_settings", return_value={}):
            assert get_database_url() == "postgresql+asyncpg://env_host/env_db"

    # 4. PEP 562 attribute access: db_mod.DATABASE_URL
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite+aiosqlite:///pep562_test.db"}):
        with patch("monika.core.config.settings.load_settings", return_value={}):
            assert db_mod.DATABASE_URL == "sqlite+aiosqlite:///pep562_test.db"


def test_mt5_client_credential_resolution():
    """Verify MT5Client resolves credentials from settings -> CredentialVault -> env."""
    # 1. From settings
    cfg_settings = {
        "execution": {
            "mt5_account": 998877,
            "mt5_password": "cfg_password",
            "mt5_server": "DemoServer",
            "mt5_path": "C:/Custom/terminal64.exe",
        }
    }
    client = MT5Client(settings=cfg_settings)
    assert client.account == 998877
    assert client.password == "cfg_password"
    assert client.server == "DemoServer"
    assert client.path == "C:/Custom/terminal64.exe"

    # 2. From CredentialVault when not in settings
    vault.set_secret("MT5_ACCOUNT", "123456")
    vault.set_secret("MT5_PASSWORD", "vault_secret_pass")
    try:
        client_vault = MT5Client(settings={})
        assert client_vault.account == 123456
        assert client_vault.password == "vault_secret_pass"
    finally:
        vault.delete_secret("MT5_ACCOUNT")
        vault.delete_secret("MT5_PASSWORD")


def test_credential_pool_credential_vault_integration():
    """Verify CredentialPool integrates with CredentialVault for secret loading and registration."""
    vault.set_secret("GROQ_API_KEYS", "gsk_vault_test_key_12345678901234567890")
    try:
        pool = CredentialPool(auto_init_env=True)
        key = pool.get_key("groq")
        assert key == "gsk_vault_test_key_12345678901234567890"

        # Verify dynamic redaction registration
        masked = redact_sensitive_text("Calling Groq with key gsk_vault_test_key_12345678901234567890 for Llama-3")
        assert "gsk_vault_test_key_12345678901234567890" not in masked
        assert "[REDACTED_GROQ_KEY]" in masked or "[REDACTED]" in masked
    finally:
        vault.delete_secret("GROQ_API_KEYS")


def test_log_redactor_comprehensive_patterns():
    """Verify log redactor strips Groq, DeepSeek, Tavily, FRED, and Finnhub tokens."""
    # Groq
    t_groq = "Using Groq: gsk_12345678901234567890abcdef"
    assert "[REDACTED_GROQ_KEY]" in redact_sensitive_text(t_groq)

    # DeepSeek
    t_deepseek = "Using DeepSeek: sk-0123456789abcdef0123456789abcdef"
    assert "[REDACTED_DEEPSEEK_KEY]" in redact_sensitive_text(t_deepseek)

    # Tavily
    t_tavily = "Search via tvly-abcdef1234567890abcdef12"
    assert "[REDACTED_TAVILY_KEY]" in redact_sensitive_text(t_tavily)

    # FRED
    t_fred = "FRED query: fred_api_key=0123456789abcdef0123456789abcdef"
    assert "[REDACTED_FRED_KEY]" in redact_sensitive_text(t_fred)

    # Finnhub
    t_finnhub = "Finnhub quote: token=c123456789abcdef0123"
    assert "[REDACTED_FINNHUB_KEY]" in redact_sensitive_text(t_finnhub)


def test_mask_yaml_text_comprehensive():
    """Verify _mask_yaml_text masks sensitive tokens while preserving non-sensitive settings."""
    raw_yaml = """
app_name: "TradingAgent"
webhook_url: "https://discord.com/api/webhooks/123/secret_token"
database_url: "postgresql+asyncpg://admin:super_secret_pw@db.host:5432/trading"
passphrase: "encryption_passphrase_here"
auth_token: "jwt_token_12345"
max_tokens: 8192
token_budget: 100000
    """.strip()

    masked = _mask_yaml_text(raw_yaml)

    assert "https://discord.com/api/webhooks/123/secret_token" not in masked
    assert "super_secret_pw" not in masked
    assert "encryption_passphrase_here" not in masked
    assert "jwt_token_12345" not in masked
    # Non-sensitive keys must NOT be masked!
    assert "max_tokens: 8192" in masked
    assert "token_budget: 100000" in masked


def test_rbac_localhost_viewer_default():
    """Verify unconfigured localhost access defaults safely to Role.VIEWER."""
    with patch.dict(os.environ, {"DASHBOARD_API_KEYS": "", "DASHBOARD_API_KEY": ""}):
        assert resolve_role("", is_localhost=True) == Role.VIEWER
        with pytest.raises(PermissionError):
            resolve_role("", is_localhost=False)
