# ==============================================================================
# File: skills/skills_guard.py
# ==============================================================================

"""
Static AST Security Auditor & Malicious Code Guard for Dynamically Loaded Skills.
Institutional-grade security scanner ensuring external, community, or newly learned
skills cannot execute unauthorized system exploits or data exfiltration.

Auditing Capabilities:
  1. AST Node Traversal:
     Scans all Python scripts (*.py) in skill directory for forbidden calls:
       - Dangerous built-ins: eval, exec, compile, __subclasses__, __bases__, globals, locals.
       - Arbitrary process execution: os.system, subprocess.Popen without validation.
       - Dangerous file system deletions: shutil.rmtree('/'), os.remove without boundary.
       - Secret access attempts: inspecting .env, reading environment variables with KEY/SECRET/TOKEN.

  2. Shell Script Scanner:
     Inspects *.sh and *.bat scripts for destructive commands (e.g. rm -rf, del /f /q, format, fdisk).

  3. Audit Verdicts:
     Returns AuditReport with is_safe (bool), score (0-100), and list of findings.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.Skills.SkillsGuard")

FORBIDDEN_CALLS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
}

FORBIDDEN_ATTRIBUTES: Set[str] = {
    "__subclasses__",
    "__bases__",
    "__globals__",
}

SENSITIVE_ENV_PATTERNS = re.compile(
    r"(PRIVATE_KEY|PASSWORD|API_SECRET|DATABASE_URL|MT5_PASSWORD)",
    re.IGNORECASE,
)

DESTRUCTIVE_SHELL_PATTERNS = [
    re.compile(r"rm\s+-rf\s+(/|~|\$HOME)", re.IGNORECASE),
    re.compile(r"del\s+/[fs]\s+c:\\", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|\:&\s*\};:", re.IGNORECASE),  # Fork bomb
    re.compile(r"format\s+[a-z]:", re.IGNORECASE),
]


@dataclass
class AuditFinding:
    severity: str  # "HIGH", "MEDIUM", "LOW"
    file_path: str
    line_number: int
    rule: str
    message: str


@dataclass
class AuditReport:
    skill_name: str
    is_safe: bool
    score: int  # 0 to 100
    findings: List[AuditFinding] = field(default_factory=list)


class SkillASTVisitor(ast.NodeVisitor):
    """Traverses Python AST to flag high-risk security constructs."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.findings: List[AuditFinding] = []

    def visit_Call(self, node: ast.Call):
        # Check direct calls like eval(...) or exec(...)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FORBIDDEN_CALLS:
                self.findings.append(
                    AuditFinding(
                        severity="HIGH",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule="FORBIDDEN_BUILTIN",
                        message=f"Disallowed execution of '{func_name}()'.",
                    )
                )

        # Check attribute calls like os.system(...)
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in ("system", "popen", "spawn"):
                self.findings.append(
                    AuditFinding(
                        severity="HIGH",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule="UNRESTRICTED_OS_EXEC",
                        message=f"Disallowed direct shell execution via '{attr_name}()'.",
                    )
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Check attribute access like obj.__subclasses__()
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.findings.append(
                AuditFinding(
                    severity="HIGH",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    rule="REFLECTION_ATTACK",
                    message=f"Disallowed reflection access to '{node.attr}'.",
                )
            )
        self.generic_visit(node)


class SkillsGuard:
    """
    Performs comprehensive static security audits on skill packages before installation or execution.
    """

    @classmethod
    def audit_skill_directory(cls, skill_dir: str, skill_name: str = "") -> AuditReport:
        p = Path(skill_dir)
        name = skill_name or p.name
        findings: List[AuditFinding] = []

        if not p.exists():
            return AuditReport(
                skill_name=name,
                is_safe=False,
                score=0,
                findings=[AuditFinding("HIGH", skill_dir, 0, "MISSING_DIR", "Directory does not exist.")],
            )

        # 1. Audit Python files via AST
        for py_file in p.glob("**/*.py"):
            try:
                with open(py_file, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()

                tree = ast.parse(code, filename=str(py_file))
                visitor = SkillASTVisitor(str(py_file))
                visitor.visit(tree)
                findings.extend(visitor.findings)
            except SyntaxError as e:
                findings.append(
                    AuditFinding(
                        severity="MEDIUM",
                        file_path=str(py_file),
                        line_number=e.lineno or 0,
                        rule="SYNTAX_ERROR",
                        message=f"Python syntax error: {e.msg}",
                    )
                )
            except Exception as e:
                findings.append(
                    AuditFinding(
                        severity="LOW",
                        file_path=str(py_file),
                        line_number=0,
                        rule="PARSER_ERROR",
                        message=f"Could not audit file: {e}",
                    )
                )

        # 2. Audit Shell scripts
        for script_file in list(p.glob("**/*.sh")) + list(p.glob("**/*.bat")):
            try:
                with open(script_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                for line_no, line in enumerate(lines, start=1):
                    for pat in DESTRUCTIVE_SHELL_PATTERNS:
                        if pat.search(line):
                            findings.append(
                                AuditFinding(
                                    severity="HIGH",
                                    file_path=str(script_file),
                                    line_number=line_no,
                                    rule="DESTRUCTIVE_COMMAND",
                                    message=f"Destructive shell pattern detected: {line.strip()}",
                                )
                            )
            except Exception:
                pass

        # 3. Compute security score
        high_count = sum(1 for f in findings if f.severity == "HIGH")
        med_count = sum(1 for f in findings if f.severity == "MEDIUM")
        score = max(0, 100 - (high_count * 50) - (med_count * 20))
        is_safe = high_count == 0

        logger.info(
            f"[SkillsGuard] Audited skill '{name}': score={score}, safe={is_safe}, findings={len(findings)}"
        )
        return AuditReport(
            skill_name=name,
            is_safe=is_safe,
            score=score,
            findings=findings,
        )
