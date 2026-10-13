# ==============================================================================
# File: tests/tools/test_security_interceptors.py
# ==============================================================================

import os
import pytest
from pathlib import Path

from security.terminal_guard import (
    assert_safe_read_path,
    assert_safe_write_path,
    is_secret_credential_file,
    SecurityViolationError,
    CommandSecurityViolationError,
)
from security.ssrf_guard import SSRFViolationError
from analysis.tools.environments.tier2_kernel import Tier2HostKernelEnvironment
from analysis.tools.unified_registry import unified_tool_registry


def test_is_secret_credential_file():
    assert is_secret_credential_file(".env") is True
    assert is_secret_credential_file(".env.local") is True
    assert is_secret_credential_file(".env.production") is True
    assert is_secret_credential_file("id_rsa") is True
    assert is_secret_credential_file("server.key") is True
    assert is_secret_credential_file("cert.pem") is True
    assert is_secret_credential_file("service_credentials.json") is True
    assert is_secret_credential_file(".git-credentials") is True
    assert is_secret_credential_file(".netrc") is True
    assert is_secret_credential_file(".pgpass") is True

    # .env.example must be allowed as an architectural template
    assert is_secret_credential_file(".env.example") is False
    assert is_secret_credential_file("main.py") is False
    assert is_secret_credential_file("config.yaml") is False


def test_assert_safe_read_path_blocks_secrets(tmp_path):
    p = Path(__file__).resolve()
    repo_root = None
    for parent in p.parents:
        if (parent / "pyproject.toml").is_file():
            repo_root = parent
            break
    if not repo_root:
        repo_root = p.parents[3]

    # Attempting to read .env must raise SecurityViolationError
    with pytest.raises(SecurityViolationError, match="Access denied: Reading protected secret credential file"):
        assert_safe_read_path(str(repo_root / ".env"))

    # Attempting to read a .key file must raise SecurityViolationError
    with pytest.raises(SecurityViolationError, match="Access denied: Reading protected secret credential file"):
        assert_safe_read_path(str(repo_root / "secrets" / "private.key"))

    # Reading a normal file inside repo should succeed
    safe_path = str(repo_root / "src" / "monika" / "application" / "main.py")
    if not os.path.exists(safe_path):
        safe_path = str(repo_root / "trading-agent" / "main.py")
    res = assert_safe_read_path(safe_path)
    assert os.path.exists(res) or "main.py" in res


def test_tier2_kernel_env_sanitization():
    os.environ["DUMMY_GEMINI_API_KEY"] = "fake_gemini_key"
    os.environ["MT5_PASSWORD"] = "super_secret_pw"
    os.environ["SYSTEM_TEST_SAFE_VAR"] = "should_be_stripped_unless_whitelisted"

    tier2 = Tier2HostKernelEnvironment()
    sanitized = tier2._prepare_sanitized_env(extra_env={"EVIL_TOKEN": "12345", "SAFE_FLAG": "1"})

    # Sensitive keys must never leak into child process
    assert "DUMMY_GEMINI_API_KEY" not in sanitized
    assert "MT5_PASSWORD" not in sanitized
    assert "EVIL_TOKEN" not in sanitized
    assert sanitized.get("SAFE_FLAG") == "1"
    # PATH or systemroot must be preserved
    assert "PATH" in sanitized or "Path" in sanitized or "SYSTEMROOT" in sanitized


def test_unified_registry_security_interceptor_pipeline():
    # 1. SSRF block test
    with pytest.raises(SSRFViolationError):
        unified_tool_registry._run_security_interceptors(
            "fetch_web", {"url": "http://169.254.169.254/latest/meta-data"}
        )

    # 2. Terminal prohibited command test
    with pytest.raises(CommandSecurityViolationError):
        unified_tool_registry._run_security_interceptors("run_command", {"command": "rm -rf / --no-preserve-root"})

    # 3. Path read guard test for .env
    with pytest.raises(SecurityViolationError):
        unified_tool_registry._run_security_interceptors("read_file", {"path": ".env"})
