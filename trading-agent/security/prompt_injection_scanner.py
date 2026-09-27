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

Evaluation Matrix:
- Instruction Override Attempts (e.g. "Ignore previous instructions", "SYSTEM PROMPT OVERRIDE")
- Role-play / Persona Hijacking ("You are now DAN", "Pretend to be an unrestricted AI")
- Privilege Escalation / Execution Requests ("Execute trade immediately with max lot", "Bypass risk gate")
- Delimiter & Token Smuggling (Markdown/XML injections, fake system role tokens)

Threshold:
- Score in [0.0, 1.0]
- If threat_score >= 0.70: Block content completely and raise PromptInjectionThreatDetected.
- If 0.35 <= threat_score < 0.70: Strip suspicious injection sentences, retain harmless facts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger("TradingAgent.Security.PromptInjectionScanner")


class PromptInjectionThreatDetected(ValueError):
    """Raised when incoming content exceeds prompt injection threat threshold."""
    pass


@dataclass(frozen=True)
class InjectionScanResult:
    is_safe: bool
    threat_score: float
    detected_patterns: List[str] = field(default_factory=list)
    sanitized_text: str = ""
    rejection_reason: str = ""


class PromptInjectionScanner:
    """Multi-layer adversarial injection and jailbreak detector."""

    # High-severity override patterns (weight: 0.40 - 0.60)
    OVERRIDE_PATTERNS = [
        (re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", re.IGNORECASE), 0.60, "instruction_override"),
        (re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|system)\s+rules?", re.IGNORECASE), 0.60, "rule_override"),
        (re.compile(r"(?:system\s+prompt|core\s+instruction)\s*[:=]\s*", re.IGNORECASE), 0.50, "system_prompt_tamper"),
        (re.compile(r"(?:stop\s+being\s+a\s+trading\s+assistant|you\s+are\s+no\s+longer\s+a)", re.IGNORECASE), 0.55, "role_inversion"),
        (re.compile(r"(?:bypass|disable|override)\s+(?:risk\s+gate|circuit\s+breaker|position\s+limits?)", re.IGNORECASE), 0.60, "safety_gate_bypass"),
        (re.compile(r"(?:force\s+execute|immediately\s+buy|all\s+in|max\s+leverage)", re.IGNORECASE), 0.40, "coercive_trade_execution"),
    ]

    # Persona hijacking / DAN patterns (weight: 0.30 - 0.50)
    JAILBREAK_PATTERNS = [
        (re.compile(r"\b(?:DAN|Do\s+Anything\s+Now)\b", re.IGNORECASE), 0.50, "dan_jailbreak"),
        (re.compile(r"unrestricted\s+mode|jailbreak|developer\s+mode\s+output", re.IGNORECASE), 0.45, "developer_mode_exploit"),
        (re.compile(r"pretend\s+you\s+have\s+no\s+(?:limits|restrictions|filters)", re.IGNORECASE), 0.45, "restriction_evasion"),
    ]

    # Token & Delimiter smuggling (weight: 0.30 - 0.45)
    DELIMITER_PATTERNS = [
        (re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.IGNORECASE), 0.55, "raw_chatml_injection"),
        (re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE), 0.50, "llama_delimiter_injection"),
        (re.compile(r"HUMAN:\s*|ASSISTANT:\s*", re.IGNORECASE), 0.35, "turn_role_injection"),
    ]

    @classmethod
    def scan(cls, text: str, threshold: float = 0.70) -> InjectionScanResult:
        """
        Scans input string and returns risk assessment.
        Blocks when threat_score >= threshold (default: 0.70).
        """
        if not text or not isinstance(text, str):
            return InjectionScanResult(is_safe=True, threat_score=0.0, sanitized_text=text or "")

        total_threat = 0.0
        detected = []

        all_rules = cls.OVERRIDE_PATTERNS + cls.JAILBREAK_PATTERNS + cls.DELIMITER_PATTERNS

        for pattern, weight, label in all_rules:
            matches = pattern.findall(text)
            if matches:
                # Diminishing returns on repeated pattern matches
                match_weight = min(weight * 1.5, weight + (0.1 * (len(matches) - 1)))
                total_threat += match_weight
                detected.append(f"{label} ({len(matches)}x)")

        # Cap score at 1.0
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

        # Mild threat: sanitize by stripping matching hostile fragments
        sanitized = text
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
