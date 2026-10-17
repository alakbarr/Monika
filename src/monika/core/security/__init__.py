"""
Security and Credential Management Package for Monika Trading Agent.
Provides credential vault, sensitive data masking, and egress security controls.
"""

from monika.core.security import (
    log_redactor,
    nt_guard,
    prompt_injection_scanner,
    ssrf_guard,
    supply_chain_quarantine,
    terminal_guard,
)
from monika.core.security.credential_vault import (
    CredentialVault,
    SensitiveMaskingFilter,
    delete_secret,
    get_secret,
    mask_sensitive,
    set_secret,
    vault,
)
from monika.core.security.log_redactor import (
    RedactingFormatter,
    SensitiveDataFilter,
    redact_sensitive_text,
)
from monika.core.security.nt_guard import (
    SecurityViolationError,
    assert_safe_nt_path,
    is_dangerous_nt_namespace,
    sanitize_path,
)
from monika.core.security.prompt_injection_scanner import (
    InjectionScanResult,
    PromptInjectionScanner,
    PromptInjectionThreatDetected,
)
from monika.core.security.ssrf_guard import (
    SSRFViolationError,
    canonicalize_ip_or_host,
    is_url_safe,
    validate_request_url,
)
from monika.core.security.supply_chain_quarantine import QuarantineVerdict, SupplyChainQuarantine
from monika.core.security.terminal_guard import (
    CommandSecurityViolationError,
    assert_safe_read_path,
    assert_safe_write_path,
    is_hardline_blocked_command,
    validate_command,
)

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
    "log_redactor",
    "assert_safe_read_path",
    "assert_safe_write_path",
    "assert_safe_nt_path",
    "is_dangerous_nt_namespace",
    "sanitize_path",
    "SecurityViolationError",
    "CommandSecurityViolationError",
    "is_hardline_blocked_command",
    "validate_command",
    "SupplyChainQuarantine",
    "QuarantineVerdict",
    "PromptInjectionScanner",
    "PromptInjectionThreatDetected",
    "InjectionScanResult",
    "validate_request_url",
    "is_url_safe",
    "canonicalize_ip_or_host",
    "SSRFViolationError",
    "redact_sensitive_text",
    "SensitiveDataFilter",
    "RedactingFormatter",
]
