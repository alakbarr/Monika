"""
Tests for PR-18: Secure Credential Vault & Sensitive Output Masking.
Verifies memory vault, Windows Credential Manager integration, secret masking, and logging filter.
"""

import os
import sys
import logging
from io import StringIO
import pytest
from unittest.mock import MagicMock, patch

from security.credential_vault import (
    CredentialVault,
    SensitiveMaskingFilter,
    get_secret,
    set_secret,
    delete_secret,
    mask_sensitive,
    vault,
)


def test_in_memory_credential_vault():
    test_vault = CredentialVault(target_prefix="MonikaTest:")
    
    assert test_vault.get_secret("NON_EXISTENT_KEY") is None
    assert test_vault.get_secret("NON_EXISTENT_KEY", default="default_val") == "default_val"
    
    # Set and get
    test_vault.set_secret("TEST_API_KEY", "super_secret_token_12345", persist_to_os=False)
    assert test_vault.get_secret("TEST_API_KEY") == "super_secret_token_12345"
    
    # Delete
    deleted = test_vault.delete_secret("TEST_API_KEY")
    assert deleted is True
    assert test_vault.get_secret("TEST_API_KEY") is None


def test_fallback_to_environ():
    test_vault = CredentialVault(target_prefix="MonikaTest:")
    
    os.environ["MONIKA_TEST_ENV_VAR"] = "env_secret_val"
    try:
        assert test_vault.get_secret("MONIKA_TEST_ENV_VAR") == "env_secret_val"
    finally:
        os.environ.pop("MONIKA_TEST_ENV_VAR", None)


def test_windows_credential_manager_integration():
    test_vault = CredentialVault(target_prefix="MonikaUnitTest:")
    
    if sys.platform == "win32" and test_vault._win_mgr.available:
        # Live Windows Credential Manager integration test
        key = "UNIT_TEST_WIN_KEY"
        secret = "win_vault_secret_9988"
        
        saved = test_vault.set_secret(key, secret, persist_to_os=True)
        assert saved is True
        
        # Verify read from OS vault via new fresh vault instance (no memory cache)
        fresh_vault = CredentialVault(target_prefix="MonikaUnitTest:")
        retrieved = fresh_vault.get_secret(key)
        assert retrieved == secret
        
        # Cleanup
        fresh_vault.delete_secret(key)
        assert fresh_vault.get_secret(key) is None
    else:
        # Fallback or non-Windows test with mocks
        with patch.object(test_vault._win_mgr, "write_credential", return_value=True) as mock_write, \
             patch.object(test_vault._win_mgr, "read_credential", return_value="mocked_secret") as mock_read:
            test_vault._win_mgr.available = True
            test_vault.set_secret("MOCK_KEY", "val", persist_to_os=True)
            mock_write.assert_called_once()
            
            val = test_vault.get_secret("MOCK_KEY_UNCACHED")
            assert val == "mocked_secret"


def test_mask_sensitive_registered_secrets():
    test_vault = CredentialVault()
    test_vault.register_secret("my_super_top_secret_broker_password")
    
    raw = "Connecting to MT5 with password=my_super_top_secret_broker_password for account 1001"
    masked = test_vault.mask_sensitive(raw)
    
    assert "my_super_top_secret_broker_password" not in masked
    assert "[REDACTED]" in masked


def test_mask_sensitive_regex_patterns():
    test_vault = CredentialVault()
    
    # Anthropic key pattern
    anthropic_raw = "Using key sk-ant-api03-abcdef12345678901234567890 to call claude-3-5"
    anthropic_masked = test_vault.mask_sensitive(anthropic_raw)
    assert "sk-ant-api03-abcdef12345678901234567890" not in anthropic_masked
    assert "[REDACTED]" in anthropic_masked
    
    # OpenAI key pattern
    openai_raw = "Using OpenAI key sk-12345678901234567890abcdef"
    openai_masked = test_vault.mask_sensitive(openai_raw)
    assert "sk-12345678901234567890abcdef" not in openai_masked
    assert "[REDACTED]" in openai_masked
    
    # Gemini key pattern
    gemini_raw = "Gemini key AIzaSyD123456789012345678901234567890"
    gemini_masked = test_vault.mask_sensitive(gemini_raw)
    assert "AIzaSyD123456789012345678901234567890" not in gemini_masked
    assert "[REDACTED]" in gemini_masked


def test_sensitive_masking_logging_filter():
    test_vault = CredentialVault()
    test_vault.register_secret("db_super_password_999")
    
    logger = logging.getLogger("TestSensitiveLogger")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(SensitiveMaskingFilter(vault_instance=test_vault))
    logger.addHandler(handler)
    
    logger.info("Connecting to DB postgresql://user:db_super_password_999@localhost/trading")
    log_output = log_stream.getvalue()
    
    assert "db_super_password_999" not in log_output
    assert "[REDACTED]" in log_output


def test_global_vault_convenience_functions():
    set_secret("GLOBAL_KEY", "global_secret_val", persist_to_os=False)
    assert get_secret("GLOBAL_KEY") == "global_secret_val"
    
    masked = mask_sensitive("Exposing global_secret_val in response")
    assert "global_secret_val" not in masked
    
    delete_secret("GLOBAL_KEY")
    assert get_secret("GLOBAL_KEY") is None
