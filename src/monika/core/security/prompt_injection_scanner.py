# ==============================================================================
# File: security/prompt_injection_scanner.py
# Monika Defensive Shield: Multi-Layer Prompt Injection & Jailbreak Scanner
# ==============================================================================

"""
Prompt Injection & Jailbreak Defensive Scanner.

Protects Monika's multi-agent reasoning from hostile adversarial injection
embedded in external data sources:
- Scraped news and RSS feeds
- Scraped social media / forum posts
- Web search / web reader results
- Economic calendar notes
- Inbound user chat messages

Evaluation Matrix:
- Instruction Override Attempts ("Ignore previous instructions", "SYSTEM PROMPT OVERRIDE")
- Role-play / Persona Hijacking ("You are now DAN", "Pretend to be an unrestricted AI")
- Privilege Escalation / Execution Requests ("Execute trade immediately with max lot", "Bypass risk gate")
- Trading & Risk Manipulation ("Disable stop loss", "Override risk gate/drawdown", "Max leverage")
- Secret Exfiltration ("curl $KEY", "cat .env", "id_rsa")
- Hidden HTML/CSS Smuggling (<!--...-->, style="display:none")
- Delimiter & Token Smuggling (Markdown/XML injections, fake system role tokens)
- Invisible & BiDi Unicode Steganography (ZWS, ZWNJ, LRO, RLO, BOM)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger("TradingAgent.Security.PromptInjectionScanner")


class PromptInjectionThreatDetected(ValueError):
    """Raised when incoming content exceeds prompt injection threat threshold."""

    pass


@dataclass(frozen=True)
class InjectionScanResult:
    is_safe: bool
    threat_score: float
    detected_patterns: list[str] = field(default_factory=list)
    sanitized_text: str = ""
    rejection_reason: str = ""


# Invisible Unicode, Zero-Width Characters, and BiDi Overrides
INVISIBLE_CHARS: set[int] = (
    set(range(0x200B, 0x200F))  # ZWS, ZWNJ, ZWJ, LRM, RLM
    | set(range(0x202A, 0x202F))  # LRE, RLE, PDF, LRO, RLO
    | {0xFEFF, 0x2060, 0x00AD}  # BOM, Word Joiner, Soft Hyphen
)


class PromptInjectionScanner:
    """Multi-layer adversarial injection, jailbreak, and financial manipulation detector."""

    MAX_SCAN_CHARS: int = 65_536

    # High-severity override patterns (weight: 0.70 - 0.85)
    OVERRIDE_PATTERNS = [
        (
            re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", re.IGNORECASE),
            0.75,
            "instruction_override",
        ),
        (
            re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|system)\s+rules?", re.IGNORECASE),
            0.75,
            "rule_override",
        ),
        (re.compile(r"(?:system\s+prompt|core\s+instruction)\s*[:=]\s*", re.IGNORECASE), 0.70, "system_prompt_tamper"),
        (
            re.compile(r"(?:stop\s+being\s+a\s+trading\s+assistant|you\s+are\s+no\s+longer\s+a)", re.IGNORECASE),
            0.70,
            "role_inversion",
        ),
        (
            re.compile(r"override\s+(?:all\s+)?safety\s+(?:checks|rules|guidelines)", re.IGNORECASE),
            0.75,
            "safety_override",
        ),
    ]

    # Persona hijacking / DAN patterns (weight: 0.70 - 0.80)
    JAILBREAK_PATTERNS = [
        (re.compile(r"\b(?:DAN|Do\s+Anything\s+Now)\b", re.IGNORECASE), 0.75, "dan_jailbreak"),
        (
            re.compile(r"unrestricted\s+mode|jailbreak|developer\s+mode\s+output", re.IGNORECASE),
            0.70,
            "developer_mode_exploit",
        ),
        (
            re.compile(r"pretend\s+(?:to\s+be|you\s+have\s+no\s+(?:limits|restrictions|filters))", re.IGNORECASE),
            0.70,
            "restriction_evasion",
        ),
        (re.compile(r"you\s+are\s+now\s+(?:a|an)\b", re.IGNORECASE), 0.70, "role_hijack"),
    ]

    # Trading & Risk Manipulation patterns (weight: 0.70 - 0.80)
    TRADING_MANIPULATION_PATTERNS = [
        (
            re.compile(r"(?:bypass|disable)\s+(?:risk\s+gate|circuit\s+breaker|position\s+limits?)", re.IGNORECASE),
            0.75,
            "safety_gate_bypass",
        ),
        (re.compile(r"disable\s+(?:risk|stop.?loss|sl|kill.?switch)", re.IGNORECASE), 0.75, "safety_bypass"),
        (re.compile(r"override\s+(?:risk\s+gate|position\s+guardian|drawdown)", re.IGNORECASE), 0.75, "risk_override"),
        (
            re.compile(
                r"set\s+(?:leverage|lot.?size)\s+(?:to\s+)?(?:max|maximum|\d{3,})|max(?:imum)?\s+leverage",
                re.IGNORECASE,
            ),
            0.70,
            "risk_manipulation",
        ),
        (
            re.compile(r"(?:buy|sell|long|short)\s+(?:immediately|now|everything|all\s+in)", re.IGNORECASE),
            0.75,
            "trade_manipulation",
        ),
        (re.compile(r"(?:force\s+execute|max\s+leverage)", re.IGNORECASE), 0.70, "forced_execution"),
    ]

    # Exfiltration Protection (weight: 0.70 - 0.85)
    EXFILTRATION_PATTERNS = [
        (
            re.compile(r"curl\s+[^\n]*\$(?:[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASS|AUTH))", re.IGNORECASE),
            0.80,
            "credential_exfiltration",
        ),
        (re.compile(r"cat\s+[^\n]*\.env\b", re.IGNORECASE), 0.85, "env_file_access"),
        (re.compile(r"(?:authorized_keys|id_rsa|id_ed25519)", re.IGNORECASE), 0.75, "ssh_key_access"),
        (re.compile(r"\bexfiltrate\b", re.IGNORECASE), 0.70, "exfiltration_keyword"),
    ]

    # Delimiter, Token, and Hidden HTML/CSS smuggling (weight: 0.50 - 0.75)
    DELIMITER_PATTERNS = [
        (re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.IGNORECASE), 0.75, "raw_chatml_injection"),
        (re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE), 0.75, "llama_delimiter_injection"),
        (re.compile(r"HUMAN:\s*|ASSISTANT:\s*", re.IGNORECASE), 0.50, "turn_role_injection"),
        (re.compile(r"<\s*(?:system|developer|assistant)\s*>", re.IGNORECASE), 0.60, "tag_injection"),
        (re.compile(r"system\s*:\s*", re.IGNORECASE), 0.50, "role_prefix_injection"),
        (re.compile(r"<!--[\s\S]*?-->"), 0.50, "hidden_html_comment"),
        (
            re.compile(r'<(?:div|span)\s+style=[\'"][^\'"]*display:\s*none[\'"]', re.IGNORECASE),
            0.60,
            "hidden_css_injection",
        ),
    ]

    @classmethod
    def sanitize_unicode(cls, text: str) -> str:
        """Strips invisible and BiDi characters, and applies NFKC normalization."""
        if not text or not isinstance(text, str):
            return ""
        normalized = unicodedata.normalize("NFKC", text)
        return "".join(ch for ch in normalized if ord(ch) not in INVISIBLE_CHARS)

    @classmethod
    def scan(cls, text: str, threshold: float = 0.70) -> InjectionScanResult:
        """
        Scans input string and returns risk assessment.
        Blocks when threat_score >= threshold (default: 0.70).
        """
        if not text or not isinstance(text, str):
            return InjectionScanResult(is_safe=True, threat_score=0.0, sanitized_text=text or "")

        bounded_text = text[: cls.MAX_SCAN_CHARS]
        detected = []
        total_threat = 0.0

        # 1. Unicode invisible characters check
        invisible_count = sum(1 for ch in bounded_text[:10_000] if ord(ch) in INVISIBLE_CHARS)
        if invisible_count > 0:
            total_threat += min(0.80, 0.40 + (0.05 * invisible_count))
            detected.append("invisible_unicode")

        # Normalize unicode via NFKC to prevent homoglyph evasion
        normalized = cls.sanitize_unicode(bounded_text)

        all_rules = (
            cls.OVERRIDE_PATTERNS
            + cls.JAILBREAK_PATTERNS
            + cls.TRADING_MANIPULATION_PATTERNS
            + cls.EXFILTRATION_PATTERNS
            + cls.DELIMITER_PATTERNS
        )

        for pattern, weight, label in all_rules:
            matches = pattern.findall(normalized)
            if matches:
                match_weight = min(weight * 1.5, weight + (0.1 * (len(matches) - 1)))
                total_threat += match_weight
                if label not in detected:
                    detected.append(label)

        final_score = min(1.0, round(total_threat, 3))

        if final_score >= threshold:
            reason = f"High prompt injection risk ({final_score:.2f} >= {threshold:.2f}): {', '.join(detected)}"
            logger.warning(f"[Security] Rejected hostile input: {reason}")
            return InjectionScanResult(
                is_safe=False,
                threat_score=final_score,
                detected_patterns=detected,
                sanitized_text="",
                rejection_reason=reason,
            )

        sanitized = normalized
        if final_score > 0.0:
            for pattern, _, _ in all_rules:
                sanitized = pattern.sub("[REDACTED_PROMPT_INJECTION]", sanitized)

        return InjectionScanResult(
            is_safe=True,
            threat_score=final_score,
            detected_patterns=detected,
            sanitized_text=sanitized,
            rejection_reason="",
        )

    @classmethod
    def assert_safe(cls, text: str, threshold: float = 0.70) -> str:
        """Helper that raises PromptInjectionThreatDetected if unsafe, or returns sanitized text."""
        result = cls.scan(text, threshold=threshold)
        if not result.is_safe:
            raise PromptInjectionThreatDetected(result.rejection_reason)
        return result.sanitized_text

    @classmethod
    def sanitize_or_block(cls, text: str, source: str = "external_data", threshold: float = 0.70) -> str:
        """
        Evaluates content for threats. If unsafe, blocks content and returns a safety warning.
        Compatible with utils.security.threat_scanner interface.
        """
        result = cls.scan(text, threshold=threshold)
        if not result.is_safe:
            names = ", ".join(result.detected_patterns)
            return (
                f"[BLOCKED: Data from '{source}' contained potential injection/manipulation "
                f"patterns ({names}). Content not loaded to protect execution safety.]"
            )
        return result.sanitized_text

    @classmethod
    def is_clean(cls, text: str, threshold: float = 0.70) -> bool:
        """Returns True if input text contains zero detected threat patterns."""
        result = cls.scan(text, threshold=threshold)
        return result.is_safe and len(result.detected_patterns) == 0
