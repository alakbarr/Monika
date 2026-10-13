"""
Multi-Scope Content Threat & Prompt Injection Detector.
Thin facade delegating to the unified security scanner: security.prompt_injection_scanner.
"""

from typing import Any, Dict, List, Set

from monika.core.security.prompt_injection_scanner import INVISIBLE_CHARS, PromptInjectionScanner

# Re-export patterns for backward compatibility with existing tests
INJECTION_PATTERNS = [
    p.pattern
    for p, _, _ in (
        PromptInjectionScanner.OVERRIDE_PATTERNS
        + PromptInjectionScanner.JAILBREAK_PATTERNS
        + PromptInjectionScanner.DELIMITER_PATTERNS
    )
]

EXFILTRATION_PATTERNS = [p.pattern for p, _, _ in PromptInjectionScanner.EXFILTRATION_PATTERNS]


class ThreatDetector:
    """Security scanner detecting adversarial promptware and covert unicode injection."""

    MAX_SCAN_CHARS: int = PromptInjectionScanner.MAX_SCAN_CHARS

    @classmethod
    def scan(cls, text: str, scope: str = "all") -> list[dict[str, Any]]:
        """
        Scan text for prompt injections, secret exfiltration, and unicode obfuscation.
        Returns a list of detected threats. An empty list signifies clean text.
        """
        if not text or not isinstance(text, str):
            return []

        result = PromptInjectionScanner.scan(text, threshold=0.70)
        findings: list[dict[str, Any]] = []

        for p_label in result.detected_patterns:
            if "invisible_unicode" in p_label:
                findings.append(
                    {
                        "type": "invisible_unicode",
                        "char": "unicode_control",
                        "pos": 0,
                        "severity": "high",
                    }
                )
            elif "exfiltration" in p_label or "env_file" in p_label or "ssh_key" in p_label:
                findings.append(
                    {
                        "type": "exfiltration_threat",
                        "pattern": p_label,
                        "match": p_label,
                        "severity": "critical",
                    }
                )
            else:
                findings.append(
                    {
                        "type": "prompt_injection",
                        "pattern": p_label,
                        "match": p_label,
                        "severity": "critical",
                    }
                )

        return findings

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Strips invisible unicode, neutralizes BiDi overrides, and normalizes characters."""
        return PromptInjectionScanner.sanitize_unicode(text)

    @classmethod
    def is_clean(cls, text: str, scope: str = "all") -> bool:
        """Helper returning True if input has zero threat findings."""
        return PromptInjectionScanner.is_clean(text)


# Default module-level singleton instance
threat_detector = ThreatDetector()
