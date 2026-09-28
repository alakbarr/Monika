"""
Security and Credential Management Package for Monika Trading Agent.
Provides credential vault, sensitive data masking, and egress security controls.
"""

from security.credential_vault import (
    CredentialVault,
    SensitiveMaskingFilter,
    get_secret,
    set_secret,
    delete_secret,
    mask_sensitive,
    vault,
)
from security import terminal_guard, prompt_injection_scanner, ssrf_guard

__all__ = [
    "CredentialVault",
    "SensitiveMaskingFilter",
    "get_secret",
    "set_secret",
    "delete_secret",
    "mask_sensitive",
    "vault",
    "terminal_guard",
    "prompt_injection_scanner",
    "ssrf_guard",
]
