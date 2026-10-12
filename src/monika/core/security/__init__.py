"""
Security and Credential Management Package for Monika Trading Agent.
Provides credential vault, sensitive data masking, and egress security controls.
"""

from monika.core.security.credential_vault import (
    CredentialVault,
    SensitiveMaskingFilter,
    get_secret,
    set_secret,
    delete_secret,
    mask_sensitive,
    vault,
)
from monika.core.security import terminal_guard, prompt_injection_scanner, ssrf_guard, nt_guard, supply_chain_quarantine
from monika.core.security.terminal_guard import assert_safe_read_path, assert_safe_write_path
from monika.core.security.nt_guard import assert_safe_nt_path, is_dangerous_nt_namespace, sanitize_path
from monika.core.security.supply_chain_quarantine import SupplyChainQuarantine, QuarantineVerdict

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
    "nt_guard",
    "supply_chain_quarantine",
    "assert_safe_read_path",
    "assert_safe_write_path",
    "assert_safe_nt_path",
    "is_dangerous_nt_namespace",
    "sanitize_path",
    "SupplyChainQuarantine",
    "QuarantineVerdict",
]
