"""
File: skills/trading_skill_linter.py
Automated linter and validator for trading playbook skills.
Ensures concise descriptions (<=80 chars), valid market regime tags,
structural heading standards, and absence of conversational bloat.
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

logger = logging.getLogger("TradingAgent.Skills.Linter")

VALID_REGIMES: Set[str] = {
    "trending", "ranging", "breakout", "high_volatility",
    "low_volatility", "mean_reverting", "any", "all", "universal"
}

CONVERSATIONAL_BLOAT_PATTERNS = [
    r"\bas an ai\b",
    r"\bi am an ai\b",
    r"\bhello\b",
    r"\bwelcome to this\b",
    r"\blet'?s dive in\b",
    r"\bin this guide,? i will\b",
    r"\bfeel free to\b",
]


@dataclass
class LintIssue:
    """Represents a single skill linting defect."""
    file: str
    rule: str
    severity: str  # 'ERROR' | 'WARNING'
    message: str
    line: Optional[int] = None

    def __str__(self) -> str:
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity}] {self.file}{loc} - {self.rule}: {self.message}"


class TradingSkillLinter:
    """Linter enforcing institutional production hygiene on trading skills."""

    MAX_DESCRIPTION_CHARS: int = 80
    MAX_SKILL_CHARS: int = 25000
    MIN_SKILL_CHARS: int = 50

    def lint_skill(self, content: str, filename: str = "skill.md") -> List[LintIssue]:
        """Lints raw markdown skill content."""
        issues: List[LintIssue] = []

        if not content or len(content.strip()) < self.MIN_SKILL_CHARS:
            issues.append(LintIssue(
                file=filename,
                rule="MIN_LENGTH",
                severity="ERROR",
                message=f"Skill content is empty or too short (< {self.MIN_SKILL_CHARS} chars)."
            ))
            return issues

        if len(content) > self.MAX_SKILL_CHARS:
            issues.append(LintIssue(
                file=filename,
                rule="MAX_LENGTH",
                severity="WARNING",
                message=f"Skill content ({len(content)} chars) exceeds recommended budget ({self.MAX_SKILL_CHARS} chars)."
            ))

        # Check frontmatter or metadata block
        frontmatter, body = self._extract_frontmatter(content)
        if frontmatter:
            # 1. Description length
            desc = frontmatter.get("description", "")
            if desc:
                if len(desc) > self.MAX_DESCRIPTION_CHARS:
                    issues.append(LintIssue(
                        file=filename,
                        rule="DESCRIPTION_TOO_LONG",
                        severity="ERROR",
                        message=f"Description is {len(desc)} chars (must be <= {self.MAX_DESCRIPTION_CHARS} chars)."
                    ))
            else:
                issues.append(LintIssue(
                    file=filename,
                    rule="MISSING_DESCRIPTION",
                    severity="WARNING",
                    message="Skill frontmatter does not define a 'description'."
                ))

            # 2. Market Regimes
            regimes = frontmatter.get("regimes") or frontmatter.get("regime")
            if regimes:
                reg_list = [r.strip().lower() for r in str(regimes).replace("[", "").replace("]", "").split(",") if r.strip()]
                for reg in reg_list:
                    if reg not in VALID_REGIMES:
                        issues.append(LintIssue(
                            file=filename,
                            rule="INVALID_REGIME",
                            severity="ERROR",
                            message=f"Unknown market regime '{reg}'. Valid: {sorted(VALID_REGIMES)}"
                        ))

        # Check headings
        lines = content.splitlines()
        has_h1 = any(line.strip().startswith("# ") for line in lines)
        if not has_h1:
            issues.append(LintIssue(
                file=filename,
                rule="MISSING_H1",
                severity="WARNING",
                message="Skill lacks a top-level H1 heading ('# Title')."
            ))

        # Check conversational bloat
        for idx, line in enumerate(lines, 1):
            line_lower = line.lower()
            for pattern in CONVERSATIONAL_BLOAT_PATTERNS:
                if re.search(pattern, line_lower):
                    issues.append(LintIssue(
                        file=filename,
                        rule="CONVERSATIONAL_BLOAT",
                        severity="ERROR",
                        message=f"Found conversational bloat matching '{pattern}'",
                        line=idx
                    ))

        return issues

    def lint_file(self, path: Path) -> List[LintIssue]:
        """Reads and lints a skill file from disk."""
        path = Path(path)
        if not path.exists():
            return [LintIssue(file=str(path), rule="FILE_NOT_FOUND", severity="ERROR", message="File does not exist")]
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return self.lint_skill(content, filename=path.name)
        except Exception as e:
            return [LintIssue(file=path.name, rule="READ_ERROR", severity="ERROR", message=str(e))]

    def lint_directory(self, dir_path: Path) -> Dict[str, List[LintIssue]]:
        """Lints all markdown skill files in a directory."""
        dir_path = Path(dir_path)
        results: Dict[str, List[LintIssue]] = {}
        if not dir_path.exists():
            return results

        for md_file in dir_path.glob("**/*.md"):
            # Skip hidden dirs like .archive
            if any(part.startswith(".") for part in md_file.parts):
                continue
            issues = self.lint_file(md_file)
            if issues:
                results[md_file.name] = issues

        return results

    def is_valid_skill(self, content: str, filename: str = "skill.md") -> Tuple[bool, List[str]]:
        """Convenience method returning (is_valid, error_messages)."""
        issues = self.lint_skill(content, filename=filename)
        errors = [str(iss) for iss in issues if iss.severity == "ERROR"]
        return len(errors) == 0, errors

    def _extract_frontmatter(self, content: str) -> Tuple[Optional[Dict[str, str]], str]:
        """Extracts YAML frontmatter if present (between --- markers)."""
        stripped = content.strip()
        if not stripped.startswith("---"):
            return None, content

        parts = stripped.split("---", 2)
        if len(parts) < 3:
            return None, content

        fm_text = parts[1]
        body = parts[2]
        data: Dict[str, str] = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip().lower()] = v.strip().strip("'\"")

        return data, body
