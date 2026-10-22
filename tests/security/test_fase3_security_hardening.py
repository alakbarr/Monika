"""
Unit & property tests for Phase 3 Security Hardening.
Verifies TerminalGuard deobfuscation, NTGuard DOS device blocking,
SupplyChainQuarantine fail-closed logic, CredentialVault atomic protection,
StatefulStreamScrubber boundary splitting, and WorktreeManager safety guards.
"""

import base64
import os
import tempfile
from pathlib import Path
import pytest

from monika.core.security.credential_vault import _EncryptedFileVault, VaultDecryptionError, CredentialVault
from monika.core.security.nt_guard import assert_safe_nt_path
from monika.core.security.supply_chain_quarantine import SupplyChainQuarantine
from monika.core.security.terminal_guard import (
    deobfuscate_command,
    extract_powershell_encoded_command,
    is_hardline_blocked_command,
)
from monika.core.streaming.stream_scrubber import StatefulStreamScrubber
from monika.infrastructure.sandboxes.worktree_manager import WorktreeManager


# ---------------------------------------------------------------------------
# 1. TerminalGuard Deobfuscation & Bypass Prevention
# ---------------------------------------------------------------------------


def test_terminal_guard_cmd_caret_deobfuscation():
    """Verify CMD caret (^) insertion evasion is neutralized."""
    raw_cmd = "r^m^d^i^r /s /q C:\\"
    deobf = deobfuscate_command(raw_cmd)
    assert "^" not in deobf
    assert "rmdir" in deobf.lower()

    is_blocked, reason = is_hardline_blocked_command(raw_cmd)
    assert is_blocked is True
    assert "prohibited" in reason.lower()


def test_terminal_guard_powershell_encoded_command():
    """Verify Base64 UTF-16LE encoded PowerShell commands are extracted and blocked."""
    payload = "Remove-Item -Path C:\\ -Recurse -Force"
    b64_utf16 = base64.b64encode(payload.encode("utf-16le")).decode("ascii")

    cmd_line = f"powershell.exe -NoProfile -EncodedCommand {b64_utf16}"
    extracted = extract_powershell_encoded_command(cmd_line)
    assert extracted is not None
    assert "remove-item" in extracted.lower()

    is_blocked, reason = is_hardline_blocked_command(cmd_line)
    assert is_blocked is True
    assert "prohibited" in reason.lower()


def test_terminal_guard_dotnet_reflection_and_wipers():
    """Verify .NET reflection secret reading and disk wipers are blocked."""
    # .NET Reflection secret access
    cmd_reflection = '[System.IO.File]::ReadAllText(".env")'
    is_blocked, _ = is_hardline_blocked_command(cmd_reflection)
    assert is_blocked is True

    # Unix shred / wipe
    assert is_hardline_blocked_command("shred -u .env")[0] is True
    assert is_hardline_blocked_command("srm -rf /var")[0] is True
    assert is_hardline_blocked_command("wipe -rf /home")[0] is True

    # Pipeline deletion
    cmd_pipe = "Get-ChildItem -Path . -Recurse | Remove-Item -Force"
    assert is_hardline_blocked_command(cmd_pipe)[0] is True


# ---------------------------------------------------------------------------
# 2. NTGuard DOS Device & Quoted Path Hardening
# ---------------------------------------------------------------------------


def test_nt_guard_dos_device_names_blocked():
    """Verify MS-DOS reserved device names (CON, NUL, AUX, PRN, COM1, LPT1) are blocked."""
    for dev in ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]:
        with pytest.raises(PermissionError, match="Dangerous Windows NT-namespace path detected"):
            assert_safe_nt_path(dev)

        with pytest.raises(PermissionError, match="Dangerous Windows NT-namespace path detected"):
            assert_safe_nt_path(f"C:\\Windows\\{dev}")


def test_nt_guard_quoted_paths_stripped():
    """Verify surrounding quotes are stripped during normalization."""
    raw_quoted = '"C:\\Users\\test\\safe_file.txt"'
    cleaned = assert_safe_nt_path(raw_quoted)
    assert not cleaned.startswith('"')
    assert not cleaned.endswith('"')
    assert "safe_file.txt" in cleaned


# ---------------------------------------------------------------------------
# 3. SupplyChainQuarantine Fail-Closed Handling
# ---------------------------------------------------------------------------


def test_supply_chain_quarantine_fail_closed_invalid_dates():
    """Verify malformed release dates fail closed and quarantine the package."""
    scq = SupplyChainQuarantine()

    # String that is unparseable
    res_unparseable = scq.evaluate_package("some-pkg", "1.0.0", release_date="INVALID_DATE_STRING")
    assert res_unparseable.allowed is False
    assert res_unparseable.status == "QUARANTINED"
    assert "unparseable" in res_unparseable.reason.lower()

    # Invalid type
    res_bad_type = scq.evaluate_package("some-pkg", "1.0.0", release_date=123456789)
    assert res_bad_type.allowed is False
    assert res_bad_type.status == "QUARANTINED"


# ---------------------------------------------------------------------------
# 4. CredentialVault Atomic Save & Fail-Closed Load
# ---------------------------------------------------------------------------


def test_credential_vault_decryption_error_on_invalid_key(tmp_path):
    """Verify corrupted vault raises VaultDecryptionError instead of wiping secrets."""
    store_file = tmp_path / "vault.enc"
    store_file.write_bytes(b"CORRUPTED_CIPHERTEXT_1234567890_NOT_DECRYPTABLE")

    v = _EncryptedFileVault(vault_path=store_file)
    with pytest.raises(VaultDecryptionError):
        v.load_store()


def test_credential_vault_mask_sensitive_no_leak():
    """Verify mask_sensitive masks completely without 2-character prefix/suffix leaks."""
    vault = CredentialVault(target_prefix="TEST_")
    secret = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
    masked = vault.mask_sensitive(secret)
    assert "sk" not in masked
    assert "yz" not in masked
    assert "***[REDACTED]***" in masked


# ---------------------------------------------------------------------------
# 5. StatefulStreamScrubber Boundary & Gemini Key Scrubbing
# ---------------------------------------------------------------------------


def test_stream_scrubber_gemini_and_groq_keys():
    """Verify Gemini and Groq API keys are redacted across deltas."""
    scrubber = StatefulStreamScrubber(redact_secrets=True)
    # Gemini AIza key
    gemini_key = "AIzaSyD-1234567890abcdefghijklmnopqrstuv"
    res1 = scrubber.process_delta(f"Key is {gemini_key} ready.")
    flushed = scrubber.flush()
    full = res1 + flushed
    assert gemini_key not in full
    assert "[REDACTED_GEMINI_KEY]" in full


def test_stream_scrubber_partial_tag_split():
    """Verify '<' split across delta boundary within thinking block does not cause hang."""
    scrubber = StatefulStreamScrubber(strip_thinking=True)
    # Split closing tag </think>: '<' in delta 1, '/think>visible' in delta 2
    delta1 = "<think>internal thoughts here<"
    delta2 = "/think>Visible user response."

    out1 = scrubber.process_delta(delta1)
    out2 = scrubber.process_delta(delta2)
    flushed = scrubber.flush()

    total_visible = (out1 + out2 + flushed).strip()
    assert "internal thoughts" not in total_visible
    assert "Visible user response." in total_visible


# ---------------------------------------------------------------------------
# 6. WorktreeManager Repository Root Protection
# ---------------------------------------------------------------------------


def test_worktree_manager_refuses_repo_root_removal():
    """Verify WorktreeManager raises ValueError when asked to delete the main repo root."""
    wm = WorktreeManager()
    with pytest.raises(ValueError, match="Refusing to"):
        wm.remove_worktree(wm.repo_path)
