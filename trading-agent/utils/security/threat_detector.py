"""
Multi-Scope Content Threat & Prompt Injection Detector.

Provides defense against:
1. Prompt Injections (jailbreaks, instruction overrides, hidden HTML).
2. Secret Exfiltration attempts (credentials, .env inspection).
3. Invisible & Bidirectional Unicode obfuscation (ZWS, BiDi overrides).
Applies across ALL ingested surfaces (scraped news, RSS feeds, economic calendar, and user messages).
"""

import re
import unicodedata
from typing import Any, Dict, List, Set

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"system\s+prompt\s+override",
    r"you\s+are\s+now\s+a\b",
    r"pretend\s+to\s+be\b",
    r"disregard\s+all\s+(?:prior|previous)\s+rules",
    r"override\s+(?:all\s+)?safety\s+(?:checks|rules|guidelines)",
    r"<!--[\s\S]*?-->",  # Hidden HTML comment injection
    r'<div\s+style=[\'"][^\'"]*display:\s*none[\'"]',  # Hidden CSS injection
    r'<span\s+style=[\'"][^\'"]*display:\s*none[\'"]',
]

EXFILTRATION_PATTERNS = [
    r"curl\s+[^\n]*\$(?:[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASS|AUTH))",
    r"cat\s+[^\n]*\.env\b",
    r"authorized_keys",
    r"(?:id_rsa|id_ed25519)",
    r"exfiltrate",
]

# Invisible Unicode, Zero-Width Characters, and BiDi Overrides
INVISIBLE_CHARS: Set[int] = (
    set(range(0x200B, 0x200F))  # ZWS, ZWNJ, ZWJ, LRM, RLM
    | set(range(0x202A, 0x202F))  # LRE, RLE, PDF, LRO, RLO
    | {0xFEFF, 0x2060, 0x00AD}    # BOM, Word Joiner, Soft Hyphen
)


class ThreatDetector:
    """Security scanner detecting adversarial promptware and covert unicode injection."""

    MAX_SCAN_CHARS: int = 65_536

    @classmethod
    def scan(cls, text: str, scope: str = "all") -> List[Dict[str, Any]]:
        """
        Scan text for prompt injections, secret exfiltration, and unicode obfuscation.
        Returns a list of detected threats. An empty list signifies clean text.
        """
        if not text or not isinstance(text, str):
            return []

        findings: List[Dict[str, Any]] = []
        bounded_text = text[:cls.MAX_SCAN_CHARS]

        # 1. Unicode Steganography & BiDi Scanning
        for idx, char in enumerate(bounded_text[:10_000]):
            code = ord(char)
            if code in INVISIBLE_CHARS:
                findings.append({
                    "type": "invisible_unicode",
                    "char": hex(code),
                    "pos": idx,
                    "severity": "high",
                })

        # Normalize via NFKC to defeat homoglyph obfuscation
        normalized = unicodedata.normalize("NFKC", bounded_text)

        # 2. Prompt Injection Scanning
        for pattern in INJECTION_PATTERNS:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                findings.append({
                    "type": "prompt_injection",
                    "pattern": pattern[:60],
                    "match": match.group(0)[:80],
                    "severity": "critical",
                })

        # 3. Exfiltration Scanning (if strict or all)
        if scope in ("all", "strict"):
            for pattern in EXFILTRATION_PATTERNS:
                match = re.search(pattern, normalized, re.IGNORECASE)
                if match:
                    findings.append({
                        "type": "exfiltration_threat",
                        "pattern": pattern[:60],
                        "match": match.group(0)[:80],
                        "severity": "critical",
                    })

        return findings

    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Strips invisible unicode, neutralizes BiDi overrides, and normalizes characters.
        Safe for consumption by LLM prompts.
        """
        if not text or not isinstance(text, str):
            return ""

        # Normalize unicode
        normalized = unicodedata.normalize("NFKC", text)

        # Filter out invisible and bidi control characters
        clean_chars = [ch for ch in normalized if ord(ch) not in INVISIBLE_CHARS]
        return "".join(clean_chars)

    @classmethod
    def is_clean(cls, text: str, scope: str = "all") -> bool:
        """Helper returning True if input has zero threat findings."""
        return len(cls.scan(text, scope=scope)) == 0


# Default module-level singleton instance
threat_detector = ThreatDetector()
