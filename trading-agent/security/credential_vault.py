# ==============================================================================
# File: security/credential_vault.py
# ==============================================================================

"""
Secure Credential Vault & Sensitive Output Masking for Monika Trading Agent.
Integrates with Windows Credential Manager via ctypes for plaintext-free storage
on Windows, with graceful in-memory and environment variable fallback for VPS/Linux.
Includes automated sensitive token masking for logs and telemetry.
"""

import os
import re
import sys
import logging
from typing import Optional, Set, Dict, Any

logger = logging.getLogger("TradingAgent.Security.CredentialVault")

# Common API key and credential patterns
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"),          # Anthropic
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),              # OpenAI
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),              # Google Gemini
    re.compile(r"gsk_[a-zA-Z0-9_\-]{20,}"),             # Groq
    re.compile(r"(password|passwd|pwd|token|api_key|secret)\s*[:=]\s*['\"]?([^'\"\s,}&]+)", re.IGNORECASE),
]


class _WindowsCredManager:
    """Internal ctypes wrapper for advapi32 Windows Credential Manager."""

    def __init__(self):
        self.available = False
        if sys.platform != "win32":
            return

        try:
            import ctypes
            from ctypes import wintypes

            class CREDENTIALW(ctypes.Structure):
                _fields_ = [
                    ('Flags', wintypes.DWORD),
                    ('Type', wintypes.DWORD),
                    ('TargetName', wintypes.LPWSTR),
                    ('Comment', wintypes.LPWSTR),
                    ('LastWritten', wintypes.FILETIME),
                    ('CredentialBlobSize', wintypes.DWORD),
                    ('CredentialBlob', ctypes.c_char_p),
                    ('Persist', wintypes.DWORD),
                    ('AttributeCount', wintypes.DWORD),
                    ('Attributes', ctypes.c_void_p),
                    ('TargetAlias', wintypes.LPWSTR),
                    ('UserName', wintypes.LPWSTR),
                ]

            self.CREDENTIALW = CREDENTIALW
            self.ctypes = ctypes
            self.wintypes = wintypes

            advapi32 = ctypes.windll.advapi32
            self.CredWriteW = advapi32.CredWriteW
            self.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
            self.CredWriteW.restype = wintypes.BOOL

            self.CredReadW = advapi32.CredReadW
            self.CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
            self.CredReadW.restype = wintypes.BOOL

            self.CredDeleteW = advapi32.CredDeleteW
            self.CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            self.CredDeleteW.restype = wintypes.BOOL

            self.CredFree = advapi32.CredFree
            self.CredFree.argtypes = [ctypes.c_void_p]

            self.available = True
        except Exception as e:
            logger.debug(f"Windows Credential Manager initialization skipped: {e}")
            self.available = False

    def write_credential(self, target: str, secret: str, user_name: str = "MonikaAgent") -> bool:
        if not self.available:
            return False
        try:
            secret_bytes = secret.encode("utf-8")
            cred = self.CREDENTIALW()
            cred.Type = 1  # CRED_TYPE_GENERIC
            cred.TargetName = target
            cred.CredentialBlobSize = len(secret_bytes)
            cred.CredentialBlob = secret_bytes
            cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
            cred.UserName = user_name
            return bool(self.CredWriteW(self.ctypes.byref(cred), 0))
        except Exception as e:
            logger.debug(f"Failed to write credential to Windows Credential Manager: {e}")
            return False

    def read_credential(self, target: str) -> Optional[str]:
        if not self.available:
            return None
        try:
            p_cred = self.ctypes.POINTER(self.CREDENTIALW)()
            res = self.CredReadW(target, 1, 0, self.ctypes.byref(p_cred))
            if res and p_cred:
                raw_bytes = self.ctypes.string_at(
                    p_cred.contents.CredentialBlob,
                    p_cred.contents.CredentialBlobSize
                )
                self.CredFree(p_cred)
                return raw_bytes.decode("utf-8")
            return None
        except Exception as e:
            logger.debug(f"Failed to read credential from Windows Credential Manager: {e}")
            return None

    def delete_credential(self, target: str) -> bool:
        if not self.available:
            return False
        try:
            return bool(self.CredDeleteW(target, 1, 0))
        except Exception as e:
            logger.debug(f"Failed to delete credential from Windows Credential Manager: {e}")
            return False


class CredentialVault:
    """
    Centralized credential vault managing access to sensitive tokens, keys, and passwords.
    Provides OS-level vault integration, in-memory isolation, and string redacting.
    """

    TARGET_PREFIX = "MonikaTradingAgent:"

    def __init__(self, target_prefix: Optional[str] = None):
        self.target_prefix = target_prefix or self.TARGET_PREFIX
        self._mem_store: Dict[str, str] = {}
        self._registered_secrets: Set[str] = set()
        self._win_mgr = _WindowsCredManager()

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a secret by key.
        Checks:
        1. In-memory cache
        2. Windows Credential Manager (if on Windows)
        3. OS Environment variables
        """
        # 1. In-memory cache
        if key in self._mem_store:
            return self._mem_store[key]

        # 2. Windows Credential Manager
        if self._win_mgr.available:
            target = f"{self.target_prefix}{key}"
            val = self._win_mgr.read_credential(target)
            if val is not None:
                self._mem_store[key] = val
                self.register_secret(val)
                return val

        # 3. Environment variables
        env_val = os.environ.get(key)
        if env_val is not None:
            self.register_secret(env_val)
            return env_val

        return default

    def set_secret(self, key: str, value: str, persist_to_os: bool = False) -> bool:
        """
        Store a secret in the vault.
        If persist_to_os=True and on Windows, writes to Windows Credential Manager.
        Always updates in-memory store and registration for masking.
        """
        if not key or value is None:
            return False

        self._mem_store[key] = value
        self.register_secret(value)

        if persist_to_os and self._win_mgr.available:
            target = f"{self.target_prefix}{key}"
            return self._win_mgr.write_credential(target, value)

        return True

    def delete_secret(self, key: str) -> bool:
        """Remove a secret from memory and OS vault."""
        removed = False
        if key in self._mem_store:
            val = self._mem_store.pop(key)
            if val in self._registered_secrets:
                self._registered_secrets.remove(val)
            removed = True

        if self._win_mgr.available:
            target = f"{self.target_prefix}{key}"
            if self._win_mgr.delete_credential(target):
                removed = True

        return removed

    def register_secret(self, value: str) -> None:
        """Register a secret string to ensure it is masked in log/telemetry outputs."""
        if value and len(value) >= 4:
            self._registered_secrets.add(value)

    def mask_sensitive(self, text: str) -> str:
        """Mask all registered secrets and regex patterns in a given string."""
        if not text:
            return text

        masked = str(text)

        # 1. Mask exact registered secrets
        for secret in self._registered_secrets:
            if secret in masked:
                if len(secret) > 8:
                    replacement = f"{secret[:2]}***[REDACTED]***{secret[-2:]}"
                else:
                    replacement = "***[REDACTED]***"
                masked = masked.replace(secret, replacement)

        # 2. Mask known regex key patterns
        for pattern in SECRET_PATTERNS:
            def _replace_match(m):
                full_m = m.group(0)
                # If matched group 2 (e.g. password: value)
                if len(m.groups()) >= 2:
                    k, v = m.group(1), m.group(2)
                    return f"{k}=***[REDACTED]***"
                if len(full_m) > 8:
                    return f"{full_m[:4]}***[REDACTED]***{full_m[-4:]}"
                return "***[REDACTED]***"

            masked = pattern.sub(_replace_match, masked)

        return masked


class SensitiveMaskingFilter(logging.Filter):
    """Logging filter to automatically redact passwords and tokens from log records."""

    def __init__(self, vault_instance: Optional[CredentialVault] = None):
        super().__init__()
        self.vault = vault_instance or vault

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = self.vault.mask_sensitive(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: self.vault.mask_sensitive(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(self.vault.mask_sensitive(str(a)) if isinstance(a, str) else a for a in record.args)
        except Exception:
            pass
        return True


# Global default singleton instance
vault = CredentialVault()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve secret from global vault."""
    return vault.get_secret(key, default)


def set_secret(key: str, value: str, persist_to_os: bool = False) -> bool:
    """Store secret in global vault."""
    return vault.set_secret(key, value, persist_to_os)


def delete_secret(key: str) -> bool:
    """Delete secret from global vault."""
    return vault.delete_secret(key)


def mask_sensitive(text: str) -> str:
    """Mask secrets and tokens in string."""
    return vault.mask_sensitive(text)
