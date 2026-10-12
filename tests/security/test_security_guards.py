# ==============================================================================
# File: tests/security/test_security_guards.py
# ==============================================================================

import os
import pytest
from pathlib import Path

from utils.security.nt_guard import (
    is_dangerous_nt_namespace,
    assert_safe_nt_path,
    SecurityViolationError,
)
from security.terminal_guard import (
    is_hardline_blocked_command,
    unwrap_command_quotes,
    assert_safe_write_path,
    DenialCircuitBreaker,
)
from security.credential_vault import (
    CredentialVault,
    create_opaque_handle,
    resolve_opaque_handle,
    mask_sensitive,
    _EncryptedFileVault,
)


class TestNTNamespaceGuard:
    """Test Windows NT-namespace and extended UNC path safety guard."""

    def test_safe_paths(self):
        safe_samples = [
            "C:\\Users\\Monika\\data\\trades.json",
            "/home/user/project/file.txt",
            "./relative/path/to/script.py",
            "data/cache/ohlcv.parquet",
        ]
        for p in safe_samples:
            assert is_dangerous_nt_namespace(p) is False
            assert assert_safe_nt_path(p) == p

    def test_dangerous_nt_paths(self):
        dangerous_samples = [
            "\\??\\C:\\Windows\\System32",
            "/??/C:/Windows/System32",
            "\\\\.\\PhysicalDrive0",
            "\\\\?\\UNC\\attacker.com\\share",
            "\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1",
            "C:\\data\\test.txt\x00evil.exe",
            "data/%00/leak",
        ]
        for p in dangerous_samples:
            assert is_dangerous_nt_namespace(p) is True
            with pytest.raises(SecurityViolationError):
                assert_safe_nt_path(p)


class TestTerminalGuard:
    """Test command blocklist, quote unwrapping, and safe write roots."""

    def test_quote_unwrapping(self):
        cmd = 'bash -c "rm -rf /"'
        assert unwrap_command_quotes(cmd) == "rm -rf /"

        ps_cmd = 'powershell.exe -Command "Stop-Computer -Force"'
        assert unwrap_command_quotes(ps_cmd) == "Stop-Computer -Force"

    def test_hardline_blocklist(self):
        blocked_commands = [
            "rm -rf /",
            "rm -rf /etc",
            "rm -rf ~",
            "del /s /q C:\\",
            "mkfs.ext4 /dev/sda1",
            "format D: /fs:NTFS",
            "dd if=/dev/zero of=/dev/sda",
            ":(){ :|:& };:",
            "kill -9 -1",
            "shutdown -h now",
            "Stop-Computer",
            'bash -c "rm -rf /"',
            "echo secret | sudo -S rm -rf /",
            "cat /etc/shadow",
            "type .env",
        ]
        for cmd in blocked_commands:
            is_blocked, reason = is_hardline_blocked_command(cmd)
            assert is_blocked is True, f"Expected '{cmd}' to be blocked!"
            assert "prohibited security signature" in reason

    def test_safe_commands_allowed(self):
        allowed = [
            "git status",
            "python -m pytest",
            "dir",
            "ls -la",
            "echo 'Hello World'",
            "pip list",
        ]
        for cmd in allowed:
            is_blocked, _ = is_hardline_blocked_command(cmd)
            assert is_blocked is False

    def test_assert_safe_write_path(self, tmp_path):
        safe_root = tmp_path / "workspace"
        safe_root.mkdir()
        
        # Valid write
        valid_file = safe_root / "output.txt"
        assert assert_safe_write_path(str(valid_file), safe_root=str(safe_root)) == str(valid_file)

        # Path traversal outside root
        outside_file = tmp_path / "outside.txt"
        with pytest.raises(SecurityViolationError, match="outside designated safe root"):
            assert_safe_write_path(str(outside_file), safe_root=str(safe_root))

        # Protected file (.env)
        env_file = safe_root / ".env"
        with pytest.raises(SecurityViolationError, match="protected system asset"):
            assert_safe_write_path(str(env_file), safe_root=str(safe_root))

        # Protected directory (.ssh)
        ssh_dir = safe_root / ".ssh" / "key"
        with pytest.raises(SecurityViolationError, match="protected directory"):
            assert_safe_write_path(str(ssh_dir), safe_root=str(safe_root))


class TestDenialCircuitBreaker:
    """Test consecutive rejection circuit breaker."""

    def test_circuit_breaker_trips_at_threshold(self):
        cb = DenialCircuitBreaker(threshold=3)
        assert cb.is_tripped is False

        assert cb.record_denial("denial 1") is False
        assert cb.is_tripped is False

        assert cb.record_denial("denial 2") is False
        assert cb.is_tripped is False

        # 3rd denial trips
        assert cb.record_denial("denial 3") is True
        assert cb.is_tripped is True
        assert "Security Circuit Breaker Tripped" in cb.trip_reason

        # Reset
        cb.reset()
        assert cb.is_tripped is False


class TestEnhancedCredentialVault:
    """Test encrypted file vault, opaque handles, and dynamic exact-byte redaction."""

    def test_opaque_handles(self):
        key = "TEST_API_KEY_123"
        handle = create_opaque_handle(key)
        assert handle.startswith("vault_handle_")
        assert key not in handle

    def test_dynamic_exact_byte_redaction(self):
        test_vault = CredentialVault()
        secret = "ultra_secret_broker_token_xyz999"
        test_vault.set_secret("BROKER_TOKEN", secret)

        raw_log = f"Connection failed with token: {secret} at port 443"
        masked = test_vault.mask_sensitive(raw_log)
        assert secret not in masked
        assert "[REDACTED]" in masked

    def test_encrypted_file_vault(self, tmp_path):
        vault_file = tmp_path / "vault.enc"
        file_vault = _EncryptedFileVault(vault_path=vault_file)
        
        data = {"MT5_PASS": "SuperSecurePass123!", "API_KEY": "sk-1234567890"}
        assert file_vault.save_store(data) is True
        assert vault_file.exists()
        assert b"SuperSecurePass123!" not in vault_file.read_bytes()

        # Load back
        loaded = file_vault.load_store()
        assert loaded == data
