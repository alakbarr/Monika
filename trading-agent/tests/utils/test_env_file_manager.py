"""
Unit tests for EnvFileManager.
"""

import os
import tempfile
import pytest
from utils.infra.env_file_manager import EnvFileManager


def test_update_env_values_preserves_comments_and_updates():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_env = os.path.join(tmpdir, ".env")
        initial_content = (
            "# Core Database Configuration\n"
            "DATABASE_URL=postgresql://localhost/db\n"
            "\n"
            "# MT5 Settings\n"
            "MT5_ACCOUNT=12345\n"
            "MT5_SERVER=\"MetaQuotes-Demo\"\n"
        )
        with open(test_env, "w", encoding="utf-8") as f:
            f.write(initial_content)

        updates = {
            "MT5_ACCOUNT": "67890",
            "GEMINI_API_KEY": "AIzaSyTestKey",
            "SPACED_VALUE": "Hello World with spaces",
        }

        ok = EnvFileManager.update_env_values(updates, env_path=test_env)
        assert ok is True

        with open(test_env, "r", encoding="utf-8") as f:
            content = f.read()

        assert "# Core Database Configuration" in content
        assert "DATABASE_URL=postgresql://localhost/db" in content
        assert "MT5_ACCOUNT=67890" in content
        assert "MT5_SERVER=\"MetaQuotes-Demo\"" in content
        assert "GEMINI_API_KEY=AIzaSyTestKey" in content
        assert 'SPACED_VALUE="Hello World with spaces"' in content


def test_is_configured_logic():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_env = os.path.join(tmpdir, ".env")
        with open(test_env, "w", encoding="utf-8") as f:
            f.write("MT5_ACCOUNT=111\nDATABASE_URL=postgres://test\nGEMINI_API_KEY=testkey\n")

        # In-file check
        assert EnvFileManager.is_configured(env_path=test_env) is True

        # Incomplete file check
        empty_env = os.path.join(tmpdir, "empty.env")
        with open(empty_env, "w", encoding="utf-8") as f:
            f.write("MT5_ACCOUNT=111\n")
        assert EnvFileManager.is_configured(env_path=empty_env) is False
