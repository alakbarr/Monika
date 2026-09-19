"""
Prompt injection threat scanner and sanitizer tailored to trading safety.
"""

import re
from typing import List, Tuple

THREAT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE), "instruction_override"),
    (re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE), "role_hijack"),
    (re.compile(r"<\s*(?:system|developer|assistant)\s*>", re.IGNORECASE), "tag_injection"),
    (re.compile(r"system\s*:\s*", re.IGNORECASE), "role_prefix_injection"),
    (re.compile(r"(?:buy|sell|long|short)\s+(?:immediately|now|everything|all\s+in)", re.IGNORECASE), "trade_manipulation"),
    (re.compile(r"disable\s+(?:risk|stop.?loss|sl|kill.?switch)", re.IGNORECASE), "safety_bypass"),
    (re.compile(r"set\s+(?:leverage|lot.?size)\s+(?:to\s+)?(?:max|maximum|\d{3,})", re.IGNORECASE), "risk_manipulation"),
    (re.compile(r"override\s+(?:risk\s+gate|position\s+guardian|drawdown)", re.IGNORECASE), "risk_override"),
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
    Evaluates content for threats. If any threat pattern is discovered,
    the text is blocked from entering LLM context and replaced with a warning notice.
    """
    threats = scan_content(text)
    if threats:
        names = ", ".join(t[0] for t in threats)
        return (
            f"[BLOCKED: Data from '{source}' contained potential injection/manipulation "
            f"patterns ({names}). Content not loaded to protect execution safety.]"
        )
    return text
