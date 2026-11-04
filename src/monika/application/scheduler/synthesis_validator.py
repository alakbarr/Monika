# ==============================================================================
# File: application/scheduler/synthesis_validator.py
# ==============================================================================

"""
AST Code Safety Validator, Security Scanner, and Delimiter/Indent Repair Engine.
Ensures dynamically synthesized trading strategies comply with quantitative security policies.
"""

from __future__ import annotations

import ast
import builtins
import logging
from pathlib import Path
import re
import shutil
import subprocess
import symtable
from typing import Any, Optional, Set

logger = logging.getLogger("TradingAgent.StrategySynthesis")

ALLOWED_MODULE_ROOTS = {
    "math",
    "numpy",
    "np",
    "pandas",
    "pd",
    "datetime",
    "typing",
    "dataclasses",
    "monika",
    "analysis",
    "sqlalchemy",
    "logging",
    "decimal",
    "collections",
    "enum",
    "itertools",
    "functools",
    "uuid",
    "re",
}

ALLOWED_DUNDER_ATTRS = {"__init__"}
ALLOWED_DUNDER_NAMES = {"__name__", "__doc__"}

DISALLOWED_CALL_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "breakpoint",
    "globals",
    "locals",
    "setattr",
    "delattr",
    "__import__",
    "exit",
    "quit",
    "help",
}

DISALLOWED_CALL_ATTRS = {
    "system",
    "popen",
    "spawn",
    "fork",
    "read",
    "write",
    "unlink",
    "rmdir",
    "mkdir",
    "connect",
    "remove",
    "rename",
}


def validate_code_safety(code_str: str) -> bool:
    """
    Institutional-grade AST validation:
    1. Verifies valid Python syntax.
    2. Prohibits any unauthorized double-underscore traversal (__class__, __subclasses__, __globals__, etc.),
       while allowing standard constructor chaining (.__init__).
    3. Restricts imports strictly to quantitative allowlist (math, numpy, pandas, logging, decimal, etc.).
    4. Prohibits dynamic evaluation and dangerous introspection primitives (eval, exec, unsafe getattr, etc.).
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        logger.warning(f"[StrategySynthesis] Syntax error in synthesized code: {e}")
        return False

    for node in ast.walk(tree):
        # Prohibit unauthorized private / dunder attribute traversal (e.g., .__subclasses__, .__class__, .__globals__)
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr not in ALLOWED_DUNDER_ATTRS:
                logger.warning(f"[StrategySynthesis] Security check failed: dunder attribute traversal '.{node.attr}'")
                return False
            if node.attr in DISALLOWED_CALL_ATTRS:
                logger.warning(f"[StrategySynthesis] Security check failed: disallowed attribute call '.{node.attr}'")
                return False

        # Prohibit any dunder names or dynamic execution primitives
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id not in ALLOWED_DUNDER_NAMES:
                logger.warning(f"[StrategySynthesis] Security check failed: dunder name '{node.id}'")
                return False
            if node.id in DISALLOWED_CALL_NAMES:
                logger.warning(f"[StrategySynthesis] Security check failed: disallowed primitive '{node.id}'")
                return False

        # Prohibit dangerous call expressions
        elif isinstance(node, ast.Call):
            func = node.func
            func_name = getattr(func, "id", getattr(func, "attr", ""))
            if func_name == "getattr":
                # Allow safe getattr with clean string literal attribute: getattr(obj, "literal_attr", default)
                is_safe_getattr = False
                if len(node.args) >= 2:
                    target = node.args[0]
                    attr_arg = node.args[1]
                    target_id = getattr(target, "id", None)
                    if target_id != "__builtins__":
                        attr_val = None
                        if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                            attr_val = attr_arg.value
                        elif isinstance(attr_arg, getattr(ast, "Str", type(None))):
                            attr_val = getattr(attr_arg, "s", None)

                        if attr_val and not attr_val.startswith("__") and attr_val not in DISALLOWED_CALL_ATTRS:
                            is_safe_getattr = True

                if not is_safe_getattr:
                    logger.warning(f"[StrategySynthesis] Security check failed: disallowed or dynamic call 'getattr'")
                    return False
            elif func_name in DISALLOWED_CALL_NAMES or func_name in DISALLOWED_CALL_ATTRS:
                logger.warning(f"[StrategySynthesis] Security check failed: disallowed call '{func_name}'")
                return False

        # Enforce module import allowlist
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod_name = getattr(node, "module", "") or ""
            names = [a.name for a in getattr(node, "names", [])] or [mod_name]
            for n in names:
                target_root = (mod_name or n).split(".")[0].strip()
                if target_root and target_root not in ALLOWED_MODULE_ROOTS:
                    logger.warning(
                        f"[StrategySynthesis] Security check failed: module '{target_root}' not in allowlist"
                    )
                    return False

    # Structural completeness: if an EdgeStrategy class is declared, ensure evaluate() exists and contains returns
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_edge_base = any(
                isinstance(b, ast.Name)
                and b.id == "EdgeStrategy"
                or isinstance(b, ast.Attribute)
                and b.attr == "EdgeStrategy"
                for b in node.bases
            )
            if has_edge_base:
                evaluate_node = None
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "evaluate":
                        evaluate_node = item
                        break
                if evaluate_node is not None:
                    returns_or_raises = [n for n in ast.walk(evaluate_node) if isinstance(n, (ast.Return, ast.Raise))]
                    if not returns_or_raises:
                        logger.warning(
                            f"[StrategySynthesis] Security check failed: class '{node.name}' evaluate() has no return or raise statement"
                        )
                        return False

    # Static name resolution and lint validation
    lint_ok, lint_err = lint_check_code(code_str)
    if not lint_ok:
        logger.warning(f"[StrategySynthesis] Security/lint check failed: {lint_err}")
        return False

    return True


def lint_check_code(code_str: str) -> tuple[bool, str]:
    """
    Static verification using symtable (stdlib) and ruff (if available).
    Guarantees 0 undefined variables (F821) and clean syntax across all scopes.
    """
    # 1. Symtable check for unresolved global/free symbols
    try:
        tbl = symtable.symtable(code_str, "<synthesized_strategy>", "exec")
        mod_syms = set(tbl.get_identifiers())

        def _find_unresolved(table, module_symbols, parent_symbols=None):
            unresolved = []
            scope_symbols = set(module_symbols)
            if parent_symbols:
                scope_symbols.update(parent_symbols)
            local_defs = set(table.get_identifiers())

            for s in table.get_symbols():
                name = s.get_name()
                if name.startswith("__"):
                    continue
                if s.is_global() or s.is_free():
                    if name not in scope_symbols and name not in dir(builtins):
                        unresolved.append((name, table.get_name()))

            for child in table.get_children():
                unresolved.extend(_find_unresolved(child, module_symbols, local_defs))
            return unresolved

        unresolved = _find_unresolved(tbl, mod_syms)
        if unresolved:
            err_details = ", ".join(f"'{name}' in {scope}" for name, scope in unresolved)
            return False, f"Undefined symbol(s): {err_details}"
    except Exception as e:
        return False, f"symtable inspection error: {e}"

    # 2. Ruff check if ruff binary is available in venv or PATH
    ruff_bin = shutil.which("ruff")
    if not ruff_bin:
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "venv" / "Scripts" / "ruff.exe",
            Path(__file__).resolve().parent.parent / "venv" / "bin" / "ruff",
            Path(__file__).resolve().parent.parent.parent / "venv" / "Scripts" / "ruff.exe",
        ]
        for cp in candidate_paths:
            if cp.exists():
                ruff_bin = str(cp)
                break

    if ruff_bin:
        try:
            res = subprocess.run(
                [ruff_bin, "check", "--select", "E9,F821", "--stdin-filename", "strategy_candidate.py", "-"],
                input=code_str,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
            )
            if res.returncode == 1:
                first_err = (
                    res.stdout.strip().splitlines()[0]
                    if res.stdout.strip()
                    else (
                        res.stderr.strip().splitlines()[0] if res.stderr.strip() else "syntax or name resolution error"
                    )
                )
                return False, f"ruff check failed: {first_err}"
            elif res.returncode != 0:
                tool_err = res.stderr.strip().splitlines()[0] if res.stderr.strip() else f"exit code {res.returncode}"
                logger.debug(f"[StrategySynthesis] Subprocess ruff check non-fatal (tool warning): {tool_err}")
        except Exception as ruff_err:
            logger.debug(f"[StrategySynthesis] Subprocess ruff check non-fatal: {ruff_err}")

    return True, ""


def sanitize_strategy_code(code_str: str) -> str:
    """
    Sanitizes synthesized strategy code for modern pandas compatibility (>= 2.1/2.2)
    and common LLM code-generation pitfalls.
    """
    if not code_str:
        return code_str

    # Defensive pre-sanitization: normalize hallucinated project root imports
    code_str = re.sub(
        r"from\s+(?:app|core|edge_engine|trading_system)[a-zA-Z0-9_\.]*\s+import\s+([a-zA-Z0-9_,\s]+)",
        r"from monika.application.analysis.strategies.base_strategy import \1",
        code_str,
    )

    # Auto-repair dunder attribute traversal on candles / dicts (e.g. c.__dict__ -> c)
    code_str = re.sub(r"\b([a-zA-Z0-9_]+)\s*\.\s*__dict__", r"\1", code_str)
    # Auto-repair vars(c) -> c
    code_str = re.sub(r"\bvars\s*\(\s*([a-zA-Z0-9_]+)\s*\)", r"\1", code_str)

    # Pattern 1: .fillna(method='ffill'|'bfill', inplace=True|False)
    def _sub_method_first(m):
        method = m.group(1).lower()
        inplace = m.group(2)
        fn = "ffill" if method == "ffill" else "bfill"
        return f".{fn}(inplace={inplace})" if inplace else f".{fn}()"

    code_str = re.sub(
        r"\.fillna\s*\(\s*method\s*=\s*['\"](ffill|bfill)['\"]\s*(?:,\s*inplace\s*=\s*(True|False))?\s*\)",
        _sub_method_first,
        code_str,
        flags=re.IGNORECASE,
    )

    # Pattern 2: .fillna(inplace=True|False, method='ffill'|'bfill')
    def _sub_inplace_first(m):
        inplace = m.group(1)
        method = m.group(2).lower()
        fn = "ffill" if method == "ffill" else "bfill"
        return f".{fn}(inplace={inplace})"

    code_str = re.sub(
        r"\.fillna\s*\(\s*inplace\s*=\s*(True|False)\s*,\s*method\s*=\s*['\"](ffill|bfill)['\"]\s*\)",
        _sub_inplace_first,
        code_str,
        flags=re.IGNORECASE,
    )

    # Auto-repair invalid pandas .replace([inf, -inf], <non_scalar>) resulting in mismatched replacement lists
    code_str = repair_invalid_replace_calls(code_str)

    # Auto-repair unclosed delimiters (e.g. '(' was never closed, unterminated strings)
    code_str = repair_unclosed_delimiters(code_str)

    # Auto-reindent unindented methods (e.g. async def evaluate at column 0)
    code_str = reindent_unindented_methods(code_str)

    # Auto-repair missing 'except' or 'finally' block from unclosed 'try:' statements
    code_str = repair_unclosed_try_blocks(code_str)

    # Map legacy imports from pre-refactor top-level 'analysis' module to 'monika.application.analysis'
    code_str = re.sub(r"\bfrom\s+analysis\.", "from monika.application.analysis.", code_str)
    code_str = re.sub(r"\bimport\s+analysis\.", "import monika.application.analysis.", code_str)

    return code_str


def repair_invalid_replace_calls(code_str: str) -> str:
    """
    Auto-repairs invalid pandas .replace([inf, -inf], <non_scalar>) calls.
    Pandas requires the replacement value for a list target to be either a scalar
    or an equal-length list. Passing a Series, DataFrame, or method call results in:
    ValueError: Replacement lists must match in length. Expecting 2 got <N>.
    """
    if not code_str:
        return code_str

    inf_item = r"(?:-?float\(['\"]-?inf['\"]\)|-?(?:np\.|math\.)?inf)"
    target_pattern = rf"\[\s*{inf_item}(?:\s*,\s*{inf_item})*\s*\]"
    call_matches = list(re.finditer(rf"\.replace\s*\(\s*({target_pattern})\s*,\s*", code_str))

    for m in reversed(call_matches):
        target_str = m.group(1)
        val_start = m.end()
        paren_depth = 1
        i = val_start
        while i < len(code_str) and paren_depth > 0:
            if code_str[i] == "(":
                paren_depth += 1
            elif code_str[i] == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    break
            i += 1

        if paren_depth == 0:
            val_expr = code_str[val_start:i].strip()
            is_scalar = bool(
                re.match(
                    r"^(?:(?:np\.|math\.)?nan|float\(['\"]nan['\"]\)|None|-?\d+(?:\.\d+)?)(?:\s*,\s*inplace\s*=\s*(?:True|False))?$",
                    val_expr,
                    re.IGNORECASE,
                )
            )
            if not is_scalar:
                inplace_match = re.search(r",\s*inplace\s*=\s*(True|False)", val_expr, re.IGNORECASE)
                if inplace_match and inplace_match.group(1).lower() == "true":
                    replacement = f".replace({target_str}, np.nan, inplace=True)"
                else:
                    replacement = f".replace({target_str}, np.nan).ffill().bfill()"
                code_str = code_str[: m.start()] + replacement + code_str[i + 1 :]

    return code_str


def repair_unclosed_delimiters(code_str: str) -> str:
    """
    Repairs unclosed parentheses '(', brackets '[', braces '{', and string literals
    often caused by LLM token truncation or missing closing delimiters on nested calls.
    """
    if not code_str:
        return code_str

    for _ in range(15):
        try:
            ast.parse(code_str)
            return code_str
        except SyntaxError as err:
            msg = str(err).lower()
            if not any(k in msg for k in ("was never closed", "unclosed", "unterminated", "unexpected eof")):
                return code_str

            lineno = err.lineno
            lines = code_str.splitlines()

            # 1. Handle unterminated string literals
            if "string literal" in msg:
                if lineno and 1 <= lineno <= len(lines):
                    target_idx = lineno - 1
                    target_line = lines[target_idx]
                    if "triple" in msg:
                        quote = '"""' if '"""' in target_line else "'''"
                    else:
                        quote = '"' if '"' in target_line else "'"
                    lines[target_idx] = target_line + quote
                    code_str = "\n".join(lines) + "\n"
                    continue

            # 2. Handle unclosed delimiters: '(', '[', '{'
            closing_char = ")"
            if "[" in msg or "bracket" in msg:
                closing_char = "]"
            elif "{" in msg or "brace" in msg:
                closing_char = "}"

            if not lineno or not (1 <= lineno <= len(lines)):
                if lines:
                    lines[-1] += closing_char
                code_str = "\n".join(lines) + "\n"
                continue

            target_idx = lineno - 1
            line = lines[target_idx]

            # Find the statement boundary: either current line or where indent drops
            curr_indent = len(line) - len(line.lstrip())
            last_line_of_stmt = target_idx
            for next_idx in range(target_idx + 1, len(lines)):
                nl = lines[next_idx]
                n_strip = nl.strip()
                if not n_strip or n_strip.startswith("#"):
                    continue
                n_indent = len(nl) - len(nl.lstrip())
                if n_indent <= curr_indent:
                    break
                last_line_of_stmt = next_idx

            lines[last_line_of_stmt] = lines[last_line_of_stmt] + closing_char
            code_str = "\n".join(lines) + "\n"

    return code_str


def reindent_unindented_methods(code_str: str) -> str:
    """
    Detects methods like 'async def evaluate' or 'def evaluate' (or common aliases)
    that were placed at module scope (column 0) after a class definition,
    and re-indents them into the class body.
    """
    if not code_str:
        return code_str

    lines = code_str.splitlines()
    in_class = False
    class_indent = 0
    new_lines = []
    reindent_active = False

    method_triggers = (
        "async def evaluate",
        "def evaluate",
        "async def generate_signals",
        "def generate_signals",
        "async def generate_signal",
        "def generate_signal",
        "async def analyze",
        "def analyze",
        "async def execute",
        "def execute",
        "async def evaluate_strategy",
        "def evaluate_strategy",
    )

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        indent = len(line) - len(line.lstrip())

        if stripped.startswith("class ") and "(EdgeStrategy" in stripped:
            in_class = True
            class_indent = indent
            reindent_active = False
            new_lines.append(line)
            continue

        if in_class and indent <= class_indent:
            if any(stripped.startswith(trig) for trig in method_triggers):
                reindent_active = True
            elif stripped.startswith(("class ", "import ", "from ")) and not any(
                stripped.startswith(trig) for trig in method_triggers
            ):
                reindent_active = False

        if reindent_active:
            new_lines.append("    " + line)
        else:
            new_lines.append(line)

    repaired = "\n".join(new_lines) + "\n"
    try:
        ast.parse(repaired)
        return repaired
    except SyntaxError:
        return code_str


def repair_unclosed_try_blocks(code_str: str) -> str:
    """
    Repairs unclosed try statements (e.g. expected 'except' or 'finally' block)
    often caused by LLM omitting the closing except block or output token cutoffs.
    """
    try:
        ast.parse(code_str)
        return code_str
    except SyntaxError as err:
        err_msg = str(err).lower()
        if "except" not in err_msg and "finally" not in err_msg:
            return code_str

    lines = code_str.splitlines()
    new_lines = []
    try_stack = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        indent = len(line) - len(line.lstrip())
        indent_str = line[:indent]

        # Check if open try block at deeper or equal indent was abandoned before this line
        while (
            try_stack
            and indent <= try_stack[-1][0]
            and not (stripped.startswith("except") or stripped.startswith("finally"))
        ):
            t_indent, t_indent_str = try_stack.pop()
            inner_indent = t_indent_str + "    "
            new_lines.append(f"{t_indent_str}except Exception:")
            new_lines.append(f"{inner_indent}pass")

        if stripped.startswith("try:") or stripped == "try":
            try_stack.append((indent, indent_str))
        elif stripped.startswith("except") or stripped.startswith("finally"):
            if try_stack and try_stack[-1][0] == indent:
                try_stack.pop()

        new_lines.append(line)

    # Close any remaining try blocks at EOF
    while try_stack:
        t_indent, t_indent_str = try_stack.pop()
        inner_indent = t_indent_str + "    "
        new_lines.append(f"{t_indent_str}except Exception as e:")
        new_lines.append(
            f"{inner_indent}return EdgeSignal(strategy_id=getattr(self, 'strategy_id', 'unknown'), symbol=getattr(self, 'symbol', 'unknown'), direction=None, valid=False, confidence=0.0, rationale=f'Calculation error: {{e}}', tags=['error'])"
        )

    repaired = "\n".join(new_lines) + "\n"
    try:
        ast.parse(repaired)
        return repaired
    except SyntaxError:
        return code_str


# Compatibility aliases
_lint_check_code = lint_check_code
_repair_invalid_replace_calls = repair_invalid_replace_calls
_repair_unclosed_delimiters = repair_unclosed_delimiters
_reindent_unindented_methods = reindent_unindented_methods
_repair_unclosed_try_blocks = repair_unclosed_try_blocks
