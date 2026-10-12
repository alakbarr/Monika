"""
File: analysis/memory/playbook_linter.py
Strict linter for synthesized trading playbooks.
Enforces declarative rule structures, empirical metadata, numeric invariants,
and guards against narrative incident-log style entries.
"""

import re
import yaml
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class PlaybookLintResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlaybookLinter:
    """
    Audits trading playbooks before admission into active memory.
    Ensures playbooks are actionable, empirical, and free of narrative fluff.
    """

    REQUIRED_METADATA = ["symbol", "regime", "timeframe", "min_rr"]
    VALID_REGIMES = {
        "TRENDING", "TRENDING_UP", "TRENDING_DOWN",
        "RANGING", "BREAKOUT", "HIGH_VOLATILITY", "LOW_VOLATILITY",
        "MEAN_REVERTING", "ANY"
    }

    # Narrative post-mortem / diary phrases that indicate an incident log rather than a systematic playbook
    NARRATIVE_PATTERNS = [
        r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\bwe\s+lost\b",
        r"\bi\s+lost\b",
        r"\bmy\s+trade\b",
        r"\bour\s+trade\b",
        r"\blast\s+week\b",
        r"\byesterday\b",
        r"\bpost-mortem\b",
        r"\bincident\s+log\b",
        r"\bunfortunately\b",
        r"\bi\s+should\s+have\b",
        r"\bwe\s+should\s+have\b"
    ]

    # Required structural sections in the markdown body
    REQUIRED_SECTIONS = [
        re.compile(r"^#+\s*(trigger|entry|condition)", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^#+\s*(invalidation|stop\s*loss|exit)", re.IGNORECASE | re.MULTILINE),
    ]

    def __init__(self, min_rr_threshold: float = 1.0):
        self.min_rr_threshold = min_rr_threshold

    def parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """Extract YAML frontmatter and body from markdown content."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                raw_fm = parts[1].strip()
                body = parts[2].strip()
                try:
                    meta = yaml.safe_load(raw_fm) or {}
                    if isinstance(meta, dict):
                        return meta, body
                except Exception:
                    pass
        return {}, content

    def lint(self, content: str) -> PlaybookLintResult:
        """Audits the playbook content against structural and empirical invariants."""
        errors: List[str] = []
        warnings: List[str] = []

        if not content or not content.strip():
            return PlaybookLintResult(is_valid=False, errors=["Playbook content is empty."])

        metadata, body = self.parse_frontmatter(content)

        # 1. Validate Frontmatter / Metadata
        if not metadata:
            errors.append("Missing YAML frontmatter (enclosed by '---').")
        else:
            for req in self.REQUIRED_METADATA:
                if req not in metadata:
                    errors.append(f"Missing required metadata field: '{req}'.")

            # Check regime
            regime = str(metadata.get("regime", "")).upper()
            if regime and regime not in self.VALID_REGIMES:
                warnings.append(
                    f"Regime '{regime}' is non-standard. Expected one of: {sorted(list(self.VALID_REGIMES))}"
                )

            # Check min_rr
            if "min_rr" in metadata:
                try:
                    min_rr = float(metadata["min_rr"])
                    if min_rr < self.min_rr_threshold:
                        errors.append(
                            f"Numeric invariant violation: min_rr ({min_rr}) is below threshold ({self.min_rr_threshold})."
                        )
                except (ValueError, TypeError):
                    errors.append(f"Invalid numeric value for min_rr: {metadata['min_rr']}")

            # Check win_rate if present
            if "win_rate" in metadata:
                try:
                    wr = float(metadata["win_rate"])
                    if wr > 1.0:
                        wr = wr / 100.0  # normalize percentage
                    if not (0.0 <= wr <= 1.0):
                        errors.append(f"win_rate must be between 0.0 and 1.0, got: {metadata['win_rate']}")
                except (ValueError, TypeError):
                    errors.append(f"Invalid numeric value for win_rate: {metadata['win_rate']}")

        # 2. Check for narrative incident log patterns
        body_lower = body.lower()
        for pat in self.NARRATIVE_PATTERNS:
            if re.search(pat, body_lower):
                errors.append(
                    f"Narrative anti-pattern detected: matches '{pat}'. Playbooks must be declarative forward-looking rules, not post-mortem incident logs."
                )

        # 3. Check for required structural sections
        for section_regex in self.REQUIRED_SECTIONS:
            if not section_regex.search(body):
                errors.append(
                    f"Missing required structural section matching pattern: '{section_regex.pattern}'. Playbooks must define explicit trigger/entry and invalidation rules."
                )

        # 4. Length / Substance checks
        lines = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("#")]
        if len(lines) < 3:
            errors.append("Playbook body lacks sufficient substance (fewer than 3 declarative content lines).")

        is_valid = len(errors) == 0
        return PlaybookLintResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            metadata=metadata
        )
