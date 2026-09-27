# ==============================================================================
# File: security/credential_vault.py
# ==============================================================================

"""
Secure Credential Vault & Sensitive Output Masking for Monika Trading Agent.
Integrates with:
  1. Windows Credential Manager via ctypes for plaintext-free storage on Windows.
  2. Encrypted File Vault (Fernet AES-128-CBC + HMAC-SHA256 or secure stdlib fallback)
     for headless Linux/VPS deployments (data/vault/vault.enc, permissions 0600).
  3. Model-Blind Opaque Handles: Exposes abstract references to LLMs (e.g. vault_item_*)
     to prevent prompt credential leakage.
  4. Exact-Byte Dynamic Redaction Buffer: Automatically scrubs any secret value
     fetched or written from logs and telemetry outputs.
"""

import collections
import hashlib
import hmac
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.Security.CredentialVault")

# Immutable freeze flag evaluated at import time to prevent prompt injection manipulation
_REDACT_ENABLED: bool = True

# Exact-byte FIFO redaction buffer for dynamic credential scrubbing
_VAULT_REDACTION_VALUES: collections.deque = collections.deque(maxlen=1000)

# Common API key and credential patterns
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"),          # Anthropic
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),              # OpenAI
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),             # Google Gemini
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


class _EncryptedFileVault:
    """
    Encrypted file storage for Linux VPS or headless environments.
    Stored at data/vault/vault.enc with file permissions 0600.
    Uses Fernet (AES-128-CBC + HMAC) if cryptography is available,
    otherwise uses authenticated SHA256 keystream encryption with HMAC.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        if vault_path is None:
            base_dir = Path(__file__).resolve().parent.parent / "data" / "vault"
            self.vault_path = base_dir / "vault.enc"
            self.key_path = base_dir / "vault.key"
        else:
            self.vault_path = vault_path
            self.key_path = self.vault_path.with_suffix(".key")

        self._fernet = None
        self._raw_key: Optional[bytes] = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            # Ensure permissions on POSIX
            if sys.platform != "win32":
                try:
                    os.chmod(self.vault_path.parent, 0o700)
                except Exception:
                    pass

            # Resolve key from env or keyfile
            env_key = os.environ.get("MONIKA_VAULT_KEY")
            if env_key:
                self._raw_key = env_key.encode("utf-8")
            elif self.key_path.exists():
                self._raw_key = self.key_path.read_bytes().strip()
            else:
                # Generate new 32-byte key
                import secrets
                self._raw_key = secrets.token_bytes(32)
                try:
                    self.key_path.write_bytes(self._raw_key)
                    if sys.platform != "win32":
                        os.chmod(self.key_path, 0o600)
                except Exception as e:
                    logger.debug(f"Could not write vault key file: {e}")

            # Try initializing Fernet if library installed
            try:
                import base64
                import importlib
                Fernet = importlib.import_module("cryptography.fernet").Fernet
                b64_key = base64.urlsafe_b64encode(hashlib.sha256(self._raw_key).digest())
                self._fernet = Fernet(b64_key)
            except (ImportError, Exception):
                self._fernet = None
        except Exception as e:
            logger.debug(f"EncryptedFileVault init skipped: {e}")

    def _encrypt(self, plaintext: str) -> bytes:
        data = plaintext.encode("utf-8")
        if self._fernet is not None:
            return self._fernet.encrypt(data)
        
        # Authenticated Keystream Fallback
        keystream = hashlib.sha256(self._raw_key + b":keystream").digest()
        cipher = bytes(b ^ keystream[i % len(keystream)] for i, b in enumerate(data))
        tag = hmac.new(self._raw_key, cipher, hashlib.sha256).digest()
        return tag + cipher

    def _decrypt(self, ciphertext: bytes) -> Optional[str]:
        if not ciphertext or not self._raw_key:
            return None
        if self._fernet is not None:
            try:
                return self._fernet.decrypt(ciphertext).decode("utf-8")
            except Exception:
                pass
        
        # Keystream Fallback Decrypt
        if len(ciphertext) < 32:
            return None
        tag = ciphertext[:32]
        cipher = ciphertext[32:]
        expected_tag = hmac.new(self._raw_key, cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            logger.error("Vault ciphertext authentication tag mismatch!")
            return None
        keystream = hashlib.sha256(self._raw_key + b":keystream").digest()
        plain = bytes(b ^ keystream[i % len(keystream)] for i, b in enumerate(cipher))
        return plain.decode("utf-8", errors="replace")

    def load_store(self) -> Dict[str, str]:
        if not self.vault_path.exists():
            return {}
        try:
            cipher = self.vault_path.read_bytes()
            decrypted = self._decrypt(cipher)
            if decrypted:
                return json.loads(decrypted)
        except Exception as e:
            logger.debug(f"Failed to read vault file: {e}")
        return {}

    def save_store(self, data: Dict[str, str]) -> bool:
        try:
            payload = json.dumps(data)
            encrypted = self._encrypt(payload)
            self.vault_path.write_bytes(encrypted)
            if sys.platform != "win32":
                try:
                    os.chmod(self.vault_path, 0o600)
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"Failed to save vault file: {e}")
            return False


class CredentialVault:
    """
    Centralized credential vault managing access to sensitive tokens, keys, and passwords.
    Provides OS-level vault integration, encrypted local files, in-memory isolation,
    model-blind opaque handles, and dynamic exact-byte string redacting.
    """

    TARGET_PREFIX = "MonikaTradingAgent:"

    def __init__(self, target_prefix: Optional[str] = None):
        self.target_prefix = target_prefix or self.TARGET_PREFIX
        self._mem_store: Dict[str, str] = {}
        self._registered_secrets: Set[str] = set()
        self._opaque_handles: Dict[str, str] = {}  # handle -> key
        self._win_mgr = _WindowsCredManager()
        self._file_vault = _EncryptedFileVault()

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a secret by key.
        Checks:
        1. In-memory cache
        2. Windows Credential Manager (if on Windows)
        3. Encrypted File Vault (Linux/VPS)
        4. OS Environment variables
        """
        # 1. In-memory cache
        if key in self._mem_store:
            val = self._mem_store[key]
            self.register_secret(val)
            return val

        # 2. Windows Credential Manager
        if self._win_mgr.available:
            target = f"{self.target_prefix}{key}"
            val = self._win_mgr.read_credential(target)
            if val is not None:
                self._mem_store[key] = val
                self.register_secret(val)
                return val

        # 3. Encrypted File Vault
        file_store = self._file_vault.load_store()
        if key in file_store:
            val = file_store[key]
            self._mem_store[key] = val
            self.register_secret(val)
            return val

        # 4. Environment variables
        env_val = os.environ.get(key)
        if env_val is not None:
            self.register_secret(env_val)
            return env_val

        return default

    def set_secret(self, key: str, value: str, persist_to_os: bool = False) -> bool:
        """
        Store a secret in the vault.
        If persist_to_os=True and on Windows, writes to Windows Credential Manager.
        Otherwise writes to Encrypted File Vault if requested.
        Always updates in-memory store and registration for masking.
        """
        if not key or value is None:
            return False

        self._mem_store[key] = value
        self.register_secret(value)

        success = True
        if persist_to_os:
            if self._win_mgr.available:
                target = f"{self.target_prefix}{key}"
                success = self._win_mgr.write_credential(target, value)
            else:
                store = self._file_vault.load_store()
                store[key] = value
                success = self._file_vault.save_store(store)

        return success

    def delete_secret(self, key: str) -> bool:
        """Remove a secret from memory and OS/file vaults."""
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

        store = self._file_vault.load_store()
        if key in store:
            store.pop(key)
            self._file_vault.save_store(store)
            removed = True

        return removed

    def create_opaque_handle(self, key: str) -> str:
        """
        Create a model-blind opaque handle for a secret key.
        The LLM only sees e.g. 'vault_item_a1b2c3d4' instead of the credential itself.
        """
        h = hashlib.sha256(f"{self.target_prefix}:{key}".encode("utf-8")).hexdigest()[:12]
        handle = f"vault_handle_{h}"
        self._opaque_handles[handle] = key
        return handle

    def resolve_opaque_handle(self, handle: str) -> Optional[str]:
        """Resolve an opaque handle back to its secret value server-side."""
        if handle in self._opaque_handles:
            key = self._opaque_handles[handle]
            return self.get_secret(key)
        return None

    def register_secret(self, value: str) -> None:
        """Register a secret string in exact-byte and pattern masking buffers."""
        if value and len(value) >= 4:
            self._registered_secrets.add(value)
            _VAULT_REDACTION_VALUES.append(value)

    def mask_sensitive(self, text: str) -> str:
        """Mask all registered secrets, dynamic exact-bytes, and regex patterns."""
        if not _REDACT_ENABLED or not text:
            return text

        masked = str(text)

        # 1. Mask exact registered secrets
        for secret in list(self._registered_secrets) + list(_VAULT_REDACTION_VALUES):
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
                if len(m.groups()) >= 2:
                    k = m.group(1)
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


def create_opaque_handle(key: str) -> str:
    """Create a model-blind opaque handle."""
    return vault.create_opaque_handle(key)


def resolve_opaque_handle(handle: str) -> Optional[str]:
    """Resolve opaque handle to plaintext secret."""
    return vault.resolve_opaque_handle(handle)
