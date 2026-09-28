# ==============================================================================
# File: analysis/memory/skill_ast_audit.py
# ==============================================================================

"""
Static AST Security Audit and Structural Linter for Skills & Playbooks.
Institutional-grade engine turn protection architecture.

Performs deterministic, non-executing AST security scanning on generated Python code,
trading strategies, and dynamic skills before promotion to the active portfolio.
Enforces structural sanity, complexity bounds, forbidden modules, and dangerous builtins.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Memory.SkillAstAudit")

DANGEROUS_IMPORTS = frozenset({
    "ctypes",
    "subprocess",
    "shutil",
    "pty",
    "winreg",
    "_winapi",
    "multiprocessing",
    "webbrowser",
    "socketserver",
})

DANGEROUS_CALLS = frozenset({
    "compile",
    "eval",
    "exec",
    "__import__",
    "globals",
    "locals",
})

DANGEROUS_ATTR_CALLS = frozenset({
    ("os", "system"),
    ("os", "popen"),
    ("os", "spawn"),
    ("os", "spawnl"),
    ("os", "spawnv"),
    ("os", "kill"),
    ("os", "killpg"),
    ("shutil", "rmtree"),
    ("shutil", "move"),
})

MAX_ALLOWED_CYCLOMATIC_COMPLEXITY = 25
MAX_ALLOWED_NESTING_DEPTH = 6


@dataclass
class AstAuditViolation:
    line_number: int
    rule_id: str
    message: str
    severity: str  # 'critical', 'warning'


@dataclass
class AstAuditReport:
    is_clean: bool
    violations: List[AstAuditViolation] = field(default_factory=list)
    complexity_score: int = 1
    max_nesting_depth: int = 1
    warnings: List[str] = field(default_factory=list)

    @property
    def has_critical_violations(self) -> bool:
        return any(v.severity == "critical" for v in self.violations)


class _ComplexityAndSecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations: List[AstAuditViolation] = []
        self.complexity: int = 1
        self.current_depth: int = 0
        self.max_depth: int = 0

    def generic_visit(self, node: ast.AST):
        # Track block nesting depth
        is_block = isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.For, ast.AsyncFor, ast.While, ast.If, ast.Try),
        )
        if is_block:
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.max_depth = self.current_depth

        super().generic_visit(node)

        if is_block:
            self.current_depth -= 1

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root_mod = alias.name.split(".")[0].lower()
            if root_mod in DANGEROUS_IMPORTS:
                self.violations.append(AstAuditViolation(
                    line_number=node.lineno,
                    rule_id="SEC_001_DANGEROUS_IMPORT",
                    message=f"Import of forbidden dangerous module '{root_mod}' is prohibited.",
                    severity="critical",
                ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root_mod = node.module.split(".")[0].lower()
            if root_mod in DANGEROUS_IMPORTS:
                self.violations.append(AstAuditViolation(
                    line_number=node.lineno,
                    rule_id="SEC_001_DANGEROUS_IMPORT",
                    message=f"Import from forbidden dangerous module '{root_mod}' is prohibited.",
                    severity="critical",
                ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in DANGEROUS_CALLS:
                self.violations.append(AstAuditViolation(
                    line_number=node.lineno,
                    rule_id="SEC_002_DANGEROUS_CALL",
                    message=f"Direct invocation of hazardous builtin '{func_name}' is prohibited.",
                    severity="critical",
                ))
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod_name = node.func.value.id
            attr_name = node.func.attr
            if (mod_name, attr_name) in DANGEROUS_ATTR_CALLS:
                self.violations.append(AstAuditViolation(
                    line_number=node.lineno,
                    rule_id="SEC_002_DANGEROUS_CALL",
                    message=f"Invocation of hazardous function '{mod_name}.{attr_name}' is prohibited.",
                    severity="critical",
                ))
        self.generic_visit(node)

    # Cyclomatic complexity branch points
    def visit_If(self, node: ast.If):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        # Each 'and' or 'or' adds a branch
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


class SkillAstAuditor:
    """Performs static syntax and security checks on skill code snippets."""

    def __init__(
        self,
        max_complexity: int = MAX_ALLOWED_CYCLOMATIC_COMPLEXITY,
        max_depth: int = MAX_ALLOWED_NESTING_DEPTH,
    ):
        self.max_complexity = max_complexity
        self.max_depth = max_depth

    def audit_code(self, code_str: str) -> AstAuditReport:
        """
        Audit a python string. Returns AstAuditReport.
        """
        if not code_str or not code_str.strip():
            return AstAuditReport(is_clean=True, complexity_score=0, max_nesting_depth=0)

        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return AstAuditReport(
                is_clean=False,
                violations=[AstAuditViolation(
                    line_number=e.lineno or 0,
                    rule_id="SYNTAX_ERROR",
                    message=f"SyntaxError in code: {e}",
                    severity="critical",
                )],
            )

        visitor = _ComplexityAndSecurityVisitor()
        visitor.visit(tree)

        warnings = []
        if visitor.complexity > self.max_complexity:
            visitor.violations.append(AstAuditViolation(
                line_number=1,
                rule_id="COMPLEXITY_EXCEEDED",
                message=f"Cyclomatic complexity ({visitor.complexity}) exceeds threshold ({self.max_complexity}).",
                severity="warning",
            ))
            warnings.append(f"High cyclomatic complexity: {visitor.complexity}")

        if visitor.max_depth > self.max_depth:
            visitor.violations.append(AstAuditViolation(
                line_number=1,
                rule_id="NESTING_DEPTH_EXCEEDED",
                message=f"Nesting depth ({visitor.max_depth}) exceeds maximum ({self.max_depth}).",
                severity="warning",
            ))
            warnings.append(f"Deep block nesting: {visitor.max_depth}")

        is_clean = not any(v.severity == "critical" for v in visitor.violations)
        return AstAuditReport(
            is_clean=is_clean,
            violations=visitor.violations,
            complexity_score=visitor.complexity,
            max_nesting_depth=visitor.max_depth,
            warnings=warnings,
        )
