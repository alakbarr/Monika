"""
Prompt injection threat scanner and sanitizer tailored to trading safety.
Thin facade delegating to the unified security scanner: security.prompt_injection_scanner.
"""

from typing import Any, List, Tuple
from security.prompt_injection_scanner import PromptInjectionScanner

# Re-export patterns for backward compatibility with existing tests
THREAT_PATTERNS: List[Tuple[Any, str]] = [
    (p, label)
    for p, _, label in (
        PromptInjectionScanner.OVERRIDE_PATTERNS
        + PromptInjectionScanner.JAILBREAK_PATTERNS
        + PromptInjectionScanner.TRADING_MANIPULATION_PATTERNS
        + PromptInjectionScanner.DELIMITER_PATTERNS
    )
]


def scan_content(text: str) -> List[Tuple[str, str]]:
    """
    Scans input text for prompt injection and trade manipulation patterns.
    Returns list of (threat_type, matched_snippet).
    """
    if not text or not isinstance(text, str):
        return []

    findings: List[Tuple[str, str]] = []
    for pattern, name in THREAT_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append((name, match.group(0)))
    return findings


def sanitize_or_block(text: str, source: str = "external_data") -> str:
    """
    Evaluates content for threats via PromptInjectionScanner.
    If unsafe, the text is blocked and replaced with a safety warning notice.
    """
    return PromptInjectionScanner.sanitize_or_block(text, source=source)
