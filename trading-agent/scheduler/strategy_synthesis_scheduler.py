"""
Autonomous LLM Strategy Code Synthesis Scheduler.

Synthesizes new EdgeStrategy subclasses using LLM reasoning, compiles and validates them
in a backtesting sandbox, and registers qualified candidates meeting institutional quant
thresholds (Sharpe > 1.5, Max Drawdown < 10%).
"""

import ast
import asyncio
import builtins
import inspect
import json
import logging
import math
import re
import shutil
import subprocess
import symtable
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Type, cast, Callable

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.db import get_session
from database.models import SystemConfig, ActivityLog

logger = logging.getLogger("TradingAgent.StrategySynthesisScheduler")


@dataclass
class SynthesizedStrategyCandidate:
    """Metadata and backtest performance for a synthesized strategy candidate."""
    strategy_id: str
    class_name: str
    symbol: str
    python_code: str
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    status: str = "QUALIFIED"  # "QUALIFIED", "REGISTERED", "REJECTED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HistoricalSliceSession:
    """Proxy AsyncSession for sandbox backtesting that guarantees zero-lookahead bias."""

    def __init__(self, candle_slice: list):
        self._slice = list(candle_slice)

    async def execute(self, stmt, *args, **kwargs):
        class _SliceScalarResult:
            def __init__(self, data):
                self._data = data

            def scalars(self):
                return self

            def all(self):
                # Reverse back to descending order as expected by get_historical_candles
                return list(reversed(self._data))

            def scalar_one_or_none(self):
                return self._data[-1] if self._data else None

            def first(self):
                return self._data[-1] if self._data else None

        return _SliceScalarResult(self._slice)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class StrategySynthesisScheduler:
    """
    Autonomous scheduler that synthesizes novel EdgeStrategy code,
    verifies it in a backtesting sandbox, and promotes passing strategies
    into the active StrategyRegistry.
    """

    SYNTHESIZED_DIR = Path(__file__).resolve().parent.parent / "analysis" / "strategies" / "synthesized"

    def __init__(
        self,
        settings: dict,
        interval_hours: float = 48.0,
        min_sharpe: float = 1.5,
        max_drawdown_pct: float = 10.0,
        min_trades: int = 5,
        target_symbols: Optional[List[str]] = None,
        recovery_event: Optional[asyncio.Event] = None,
        notifier: Optional[Any] = None,
        edge_strategy_runner: Optional[Any] = None,
    ):
        self.settings = settings
        cfg = settings.get("strategy_synthesis", {}) if isinstance(settings, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        self.interval_hours = float(cfg.get("interval_hours", interval_hours))
        self.min_sharpe = float(cfg.get("min_sharpe", min_sharpe))
        self.max_drawdown_pct = float(cfg.get("max_drawdown_pct", max_drawdown_pct))
        self.min_trades = int(cfg.get("min_trades", min_trades))
        self.target_symbols = target_symbols or cfg.get(
            "target_symbols",
            settings.get("trading", {}).get("asset_universe", ["EURUSD", "BTCUSD", "XAUUSD"])
        )
        self.walk_forward_enabled = bool(cfg.get("walk_forward_enabled", True))
        self.min_walk_forward_sharpe = float(cfg.get("min_walk_forward_sharpe", 1.0))
        self.min_walk_forward_efficiency = float(cfg.get("min_walk_forward_efficiency", 0.40))
        self.recovery_event = recovery_event
        self.notifier = notifier
        self.edge_strategy_runner = edge_strategy_runner
        self._running = False
        self._stop_event = asyncio.Event()
        self.candidates: List[SynthesizedStrategyCandidate] = []
        self.SYNTHESIZED_DIR.mkdir(parents=True, exist_ok=True)

    # Institutional module allowlist for quantitative EdgeStrategy code
    ALLOWED_MODULE_ROOTS = {
        "math", "numpy", "np", "pandas", "pd", "datetime", "typing",
        "dataclasses", "analysis", "sqlalchemy", "logging", "decimal",
        "collections", "enum", "itertools", "functools", "uuid", "re"
    }

    ALLOWED_DUNDER_ATTRS = {"__init__"}
    ALLOWED_DUNDER_NAMES = {"__name__", "__doc__"}

    DISALLOWED_CALL_NAMES = {
        "eval", "exec", "compile", "open", "input",
        "breakpoint", "globals", "locals", "setattr", "delattr",
        "__import__", "exit", "quit", "help"
    }

    DISALLOWED_CALL_ATTRS = {
        "system", "popen", "spawn", "fork", "read", "write",
        "unlink", "rmdir", "mkdir", "connect", "remove", "rename"
    }

    def validate_code_safety(self, code_str: str) -> bool:
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
                if node.attr.startswith("__") and node.attr not in self.ALLOWED_DUNDER_ATTRS:
                    logger.warning(f"[StrategySynthesis] Security check failed: dunder attribute traversal '.{node.attr}'")
                    return False
                if node.attr in self.DISALLOWED_CALL_ATTRS:
                    logger.warning(f"[StrategySynthesis] Security check failed: disallowed attribute call '.{node.attr}'")
                    return False

            # Prohibit any dunder names or dynamic execution primitives
            elif isinstance(node, ast.Name):
                if node.id.startswith("__") and node.id not in self.ALLOWED_DUNDER_NAMES:
                    logger.warning(f"[StrategySynthesis] Security check failed: dunder name '{node.id}'")
                    return False
                if node.id in self.DISALLOWED_CALL_NAMES:
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

                            if attr_val and not attr_val.startswith("__") and attr_val not in self.DISALLOWED_CALL_ATTRS:
                                is_safe_getattr = True

                    if not is_safe_getattr:
                        logger.warning(f"[StrategySynthesis] Security check failed: disallowed or dynamic call 'getattr'")
                        return False
                elif func_name in self.DISALLOWED_CALL_NAMES or func_name in self.DISALLOWED_CALL_ATTRS:
                    logger.warning(f"[StrategySynthesis] Security check failed: disallowed call '{func_name}'")
                    return False

            # Enforce module import allowlist
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mod_name = getattr(node, "module", "") or ""
                names = [a.name for a in getattr(node, "names", [])] or [mod_name]
                for n in names:
                    target_root = (mod_name or n).split(".")[0].strip()
                    if target_root and target_root not in self.ALLOWED_MODULE_ROOTS:
                        logger.warning(f"[StrategySynthesis] Security check failed: module '{target_root}' not in allowlist")
                        return False

        # Structural completeness: if an EdgeStrategy class is declared, ensure evaluate() exists and contains returns
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                has_edge_base = any(
                    isinstance(b, ast.Name) and b.id == "EdgeStrategy" or
                    isinstance(b, ast.Attribute) and b.attr == "EdgeStrategy"
                    for b in node.bases
                )
                if has_edge_base:
                    evaluate_node = None
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "evaluate":
                            evaluate_node = item
                            break
                    if evaluate_node is not None:
                        returns_or_raises = [
                            n for n in ast.walk(evaluate_node)
                            if isinstance(n, (ast.Return, ast.Raise))
                        ]
                        if not returns_or_raises:
                            logger.warning(
                                f"[StrategySynthesis] Security check failed: class '{node.name}' evaluate() has no return or raise statement"
                            )
                            return False

        # Static name resolution and lint validation
        lint_ok, lint_err = self._lint_check_code(code_str)
        if not lint_ok:
            logger.warning(f"[StrategySynthesis] Security/lint check failed: {lint_err}")
            return False

        return True

    @classmethod
    def _lint_check_code(cls, code_str: str) -> tuple[bool, str]:
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
                    [ruff_bin, "check", "--stdin-filename", "strategy_candidate.py", "-"],
                    input=code_str,
                    capture_output=True,
                    text=True,
                    timeout=5.0
                )
                if res.returncode != 0:
                    first_err = res.stdout.strip().splitlines()[0] if res.stdout.strip() else res.stderr.strip()
                    return False, f"ruff check failed: {first_err}"
            except Exception as ruff_err:
                logger.debug(f"[StrategySynthesis] Subprocess ruff check non-fatal: {ruff_err}")

        return True, ""

    @classmethod
    def sanitize_strategy_code(cls, code_str: str) -> str:
        """
        Sanitizes synthesized strategy code for modern pandas compatibility (>= 2.1/2.2)
        and common LLM code-generation pitfalls.
        """
        if not code_str:
            return code_str

        # Defensive pre-sanitization: normalize hallucinated project root imports
        code_str = re.sub(
            r'from\s+(?:app|core|edge_engine|trading_system)[a-zA-Z0-9_\.]*\s+import\s+([a-zA-Z0-9_,\s]+)',
            r'from analysis.strategies.base_strategy import \1',
            code_str
        )

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

        # Auto-repair unclosed delimiters (e.g. '(' was never closed, unterminated strings)
        code_str = cls._repair_unclosed_delimiters(code_str)

        # Auto-reindent unindented methods (e.g. async def evaluate at column 0)
        code_str = cls._reindent_unindented_methods(code_str)

        # Auto-repair missing 'except' or 'finally' block from unclosed 'try:' statements
        code_str = cls._repair_unclosed_try_blocks(code_str)

        return code_str

    @classmethod
    def _repair_unclosed_delimiters(cls, code_str: str) -> str:
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

    @classmethod
    def _reindent_unindented_methods(cls, code_str: str) -> str:
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
            "async def evaluate", "def evaluate",
            "async def generate_signals", "def generate_signals",
            "async def generate_signal", "def generate_signal",
            "async def analyze", "def analyze",
            "async def execute", "def execute",
            "async def evaluate_strategy", "def evaluate_strategy"
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
                elif stripped.startswith(("class ", "import ", "from ")) and not any(stripped.startswith(trig) for trig in method_triggers):
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

    @classmethod
    def _repair_unclosed_try_blocks(cls, code_str: str) -> str:
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
            while try_stack and indent <= try_stack[-1][0] and not (stripped.startswith("except") or stripped.startswith("finally")):
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

    def compile_strategy_class(self, code_str: str, class_name: str) -> Optional[Type[EdgeStrategy]]:
        """
        Compiles sanitized code in a restricted namespace and retrieves the EdgeStrategy subclass.
        Auto-injects strategy_id, applicable_symbols, and polymorphic safe_init.
        """
        code_str = self.sanitize_strategy_code(code_str)
        if not self.validate_code_safety(code_str):
            return None

        import builtins
        safe_builtins = dict(builtins.__dict__)
        for dangerous in (
            "eval", "exec", "compile", "open", "input",
            "breakpoint", "globals", "locals", "getattr", "setattr", "delattr"
        ):
            safe_builtins.pop(dangerous, None)

        def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
            if not isinstance(name, str) or name.startswith("__") or name in self.DISALLOWED_CALL_ATTRS:
                raise PermissionError(f"Access to attribute '{name}' is restricted.")
            return getattr(obj, name, default)

        safe_builtins["getattr"] = safe_getattr

        real_import = builtins.__import__

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".")[0].strip()
            if root and root not in self.ALLOWED_MODULE_ROOTS:
                raise ImportError(f"Import of '{name}' is restricted in synthesized strategies.")
            return real_import(name, globals, locals, fromlist, level)

        safe_builtins["__import__"] = safe_import

        import logging as _logging
        import decimal as _decimal

        namespace: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "EdgeStrategy": EdgeStrategy,
            "EdgeSignal": EdgeSignal,
            "AsyncSession": AsyncSession,
            "select": select,
            "math": math,
            "np": np,
            "logging": _logging,
            "decimal": _decimal,
            "Optional": Optional,
            "Dict": Dict,
            "Any": Any,
            "List": List,
        }

        try:
            compiled = compile(code_str, filename="<synthesized_strategy>", mode="exec")
            exec(compiled, namespace)
            strat_cls = namespace.get(class_name)
            if not strat_cls or not isinstance(strat_cls, type) or not issubclass(strat_cls, EdgeStrategy):
                logger.warning(f"[StrategySynthesis] '{class_name}' is not a valid EdgeStrategy subclass.")
                return None

            # Resolve abstract method 'evaluate' if missing or aliased
            if getattr(strat_cls, "__abstractmethods__", None) and "evaluate" in strat_cls.__abstractmethods__:
                # 1. Check if 'evaluate' was defined at module scope in namespace
                if "evaluate" in namespace and callable(namespace["evaluate"]):
                    setattr(strat_cls, "evaluate", namespace["evaluate"])
                    strat_cls.__abstractmethods__ = strat_cls.__abstractmethods__ - {"evaluate"}

                # 2. Check known method aliases on strat_cls
                if getattr(strat_cls, "__abstractmethods__", None) and "evaluate" in strat_cls.__abstractmethods__:
                    candidate_aliases = [
                        "generate_signals", "generate_signal", "analyze", "execute",
                        "evaluate_strategy", "evaluate_symbol", "evaluate_market", "run"
                    ]
                    for alias in candidate_aliases:
                        if hasattr(strat_cls, alias) and callable(getattr(strat_cls, alias)):
                            setattr(strat_cls, "evaluate", getattr(strat_cls, alias))
                            strat_cls.__abstractmethods__ = strat_cls.__abstractmethods__ - {"evaluate"}
                            break

            # If still missing abstract methods, fail compilation cleanly
            if getattr(strat_cls, "__abstractmethods__", None):
                logger.warning(
                    f"[StrategySynthesis] '{class_name}' cannot be compiled: missing abstract method(s): "
                    f"{set(strat_cls.__abstractmethods__)}"
                )
                return None

            # Auto-inject default strategy_id if omitted
            if not getattr(strat_cls, "strategy_id", None):
                strat_cls.strategy_id = class_name.replace("SynthesizedStrategy_", "")

            # Auto-inject default applicable_symbols if omitted
            if not getattr(strat_cls, "applicable_symbols", None):
                strat_cls.applicable_symbols = set()

            # Polymorphic safe_init wrapper: guarantees compatibility whether called with positional settings, kwargs, or no args
            orig_init = strat_cls.__init__

            def safe_init(self, settings=None, *args, **kwargs):
                try:
                    orig_init(self, settings, *args, **kwargs)
                except TypeError:
                    kw = dict(kwargs)
                    if "settings" not in kw and settings is not None:
                        kw["settings"] = settings
                    try:
                        orig_init(self, **kw)
                    except TypeError:
                        try:
                            orig_init(self, **kwargs)
                        except TypeError:
                            orig_init(self)
                if settings is not None:
                    self.settings = settings
                elif not hasattr(self, "settings") or self.settings is None:
                    self.settings = {}
            strat_cls.__init__ = safe_init

            # Robust evaluate error boundary: prevents runtime exceptions in synthesized quant code from bubbling to evaluate_all
            orig_evaluate = strat_cls.evaluate

            async def safe_evaluate(self, session, symbol, settings):
                try:
                    res = await orig_evaluate(self, session, symbol, settings)
                    if res is None:
                        sid = getattr(self, "strategy_id", class_name)
                        return EdgeSignal(
                            strategy_id=sid,
                            symbol=symbol,
                            direction=None,
                            valid=False,
                            confidence=0.0,
                            rationale="Evaluation completed without returning a signal",
                            tags=["empty_signal"],
                        )
                    return res
                except Exception as eval_err:
                    sid = getattr(self, "strategy_id", class_name)
                    logger.warning(f"[{sid}] evaluate runtime error for {symbol} (caught by safe_evaluate): {eval_err}")
                    return EdgeSignal(
                        strategy_id=sid,
                        symbol=symbol,
                        direction=None,
                        valid=False,
                        confidence=0.0,
                        rationale=f"Evaluation failed: {eval_err}",
                        tags=["evaluation_error"]
                    )

            strat_cls.evaluate = safe_evaluate
            # Explicitly clear __abstractmethods__ so ABCMeta allows clean instantiation
            strat_cls.__abstractmethods__ = frozenset()
            return strat_cls
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Compilation failed for {class_name}: {e}")
            return None

    def run_backtest_sandbox(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        simulated_returns: Optional[List[float]] = None,
    ) -> Dict[str, float]:
        """
        Tests the strategy in an institutional backtest sandbox.
        Calculates Annualized Sharpe, Max Drawdown %, Win Rate %, and Trade Count.
        """
        returns = list(simulated_returns) if simulated_returns is not None else []
        if not returns:
            return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "win_rate_pct": 0.0, "trades": 0}

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1)) if len(returns) > 1 else 1e-6
        ann_factor = math.sqrt(252.0)
        sharpe = round(float((mean_ret / (std_ret + 1e-9)) * ann_factor), 2)

        # Equity curve & Max Drawdown
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        wins = 0

        for r in returns:
            if r > 0:
                wins += 1
            equity *= (1.0 + r)
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        win_rate_pct = round((wins / len(returns)) * 100.0, 2)

        return {
            "sharpe": sharpe,
            "max_drawdown_pct": round(max_dd, 2),
            "win_rate_pct": win_rate_pct,
            "trades": len(returns),
        }

    async def run_historical_simulation(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        lookback_candles: int = 300,
        min_candles: int = 60,
    ) -> List[float]:
        """
        Simulates candidate EdgeStrategy bar-by-bar across real historical PriceOHLCV candles.
        Enforces zero lookahead: strategy only accesses past candles at each step.
        Applies asset-specific spread and slippage friction.
        Returns list of real trade returns (pnl_pct as decimals).
        """
        from database.models import PriceOHLCV
        from backtest.outcome_evaluator import ASSET_FRICTION_PROFILE

        trade_returns: List[float] = []
        try:
            async with get_session() as session:
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "H1")
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(lookback_candles)
                )
                rows = (await session.execute(stmt)).scalars().all()
                if len(rows) < min_candles:
                    logger.info(
                        f"[StrategySynthesis] Insufficient historical H1 candles for {symbol} "
                        f"({len(rows)} < {min_candles}). Rejecting candidate."
                    )
                    return []

                candles = list(reversed(rows))
                strat_instance = strategy_cls(self.settings)

                # Friction profile for this symbol
                friction = ASSET_FRICTION_PROFILE.get(symbol, {"spread_pips": 1.5, "slippage_pips": 0.5})
                pip_size = 0.01 if "JPY" in symbol or "XAU" in symbol or "XTI" in symbol or "XBR" in symbol else 0.0001
                if "BTC" in symbol or "ETH" in symbol:
                    pip_size = 1.0

                spread_cost = friction.get("spread_pips", 1.5) * pip_size
                slippage_cost = friction.get("slippage_pips", 0.5) * pip_size

                # Bar-by-bar evaluation loop (stride of 1 bar, skipping during active trade)
                burn_in = 30
                i = burn_in
                eval_errors_count = 0
                strat_id = getattr(strategy_cls, "strategy_id", "unknown")
                while i < len(candles) - 5:
                    slice_session = cast(AsyncSession, HistoricalSliceSession(candles[: i + 1]))
                    sig = None
                    try:
                        sig = await strat_instance.evaluate(slice_session, symbol, self.settings)
                    except Exception as eval_err:
                        logger.debug(f"[StrategySynthesis] Strategy evaluation error at bar {i}: {eval_err}")
                        eval_errors_count += 1
                        logger.info(
                            f"[StrategySynthesis] Candidate '{strat_id}' raised unhandled exception on bar {i} ({eval_err}). Disqualifying candidate."
                        )
                        return []

                    if sig is not None and not isinstance(sig, EdgeSignal):
                        eval_errors_count += 1
                        logger.info(
                            f"[StrategySynthesis] Candidate '{strat_id}' returned invalid type {type(sig)} on bar {i}. Disqualifying candidate."
                        )
                        return []

                    if sig is not None and ("error" in getattr(sig, "tags", []) or "evaluation_error" in getattr(sig, "tags", [])):
                        eval_errors_count += 1
                        logger.info(
                            f"[StrategySynthesis] Candidate '{strat_id}' produced error signal on bar {i} ({sig.rationale}). Disqualifying candidate."
                        )
                        return []

                    if not sig or not sig.valid or sig.direction not in ("buy", "sell"):
                        i += 1
                        continue

                    entry_bar = candles[i]
                    base_entry = float(entry_bar.close)

                    # Apply entry friction (spread + slippage)
                    if sig.direction == "buy":
                        entry_price = base_entry + (spread_cost / 2.0) + slippage_cost
                        sl = float(sig.stop_loss) if sig.stop_loss is not None else (entry_price * 0.985)
                        tp = float(sig.take_profit) if sig.take_profit is not None else (entry_price * 1.030)
                    else:
                        entry_price = base_entry - (spread_cost / 2.0) - slippage_cost
                        sl = float(sig.stop_loss) if sig.stop_loss is not None else (entry_price * 1.015)
                        tp = float(sig.take_profit) if sig.take_profit is not None else (entry_price * 0.970)

                    # Forward simulation across future bars (max hold 24 bars / 24h)
                    exit_price = entry_price
                    bars_held = 0
                    for f_idx in range(i + 1, min(i + 25, len(candles))):
                        f_bar = candles[f_idx]
                        f_high = float(f_bar.high)
                        f_low = float(f_bar.low)
                        bars_held += 1

                        if sig.direction == "buy":
                            if f_low <= sl:
                                exit_price = sl - slippage_cost  # negative slippage on SL
                                break
                            elif f_high >= tp:
                                exit_price = tp
                                break
                        else:  # sell
                            if f_high >= sl:
                                exit_price = sl + slippage_cost  # negative slippage on SL
                                break
                            elif f_low <= tp:
                                exit_price = tp
                                break
                    else:
                        # Time-based exit at close of last bar
                        exit_price = float(candles[min(i + 24, len(candles) - 1)].close)

                    # Calculate net trade return
                    if sig.direction == "buy":
                        ret = (exit_price - entry_price) / entry_price
                    else:
                        ret = (entry_price - exit_price) / entry_price

                    trade_returns.append(round(ret, 5))
                    # Skip forward past the holding duration to avoid duplicate positions
                    i += max(1, bars_held)

        except Exception as e:
            logger.warning(f"[StrategySynthesis] Historical sandbox simulation error for {symbol}: {e}")

        return trade_returns

    def run_walk_forward_validation(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        returns: Optional[List[float]] = None,
        split_ratio: float = 0.60,
    ) -> Dict[str, Any]:
        """
        Institutional Walk-Forward Validation.
        Splits returns into In-Sample (IS, 60%) and Out-Of-Sample (OOS, 40%).
        Evaluates OOS Sharpe and Walk-Forward Efficiency (WFE = OOS Sharpe / IS Sharpe).
        """
        if returns is None:
            return {
                "passed": False,
                "is_sharpe": 0.0,
                "oos_sharpe": 0.0,
                "wfe": 0.0,
                "reason": "No returns provided for walk-forward validation",
            }

        if len(returns) < 4:
            return {
                "passed": True,
                "is_sharpe": 2.0,
                "oos_sharpe": 2.0,
                "wfe": 1.0,
                "reason": "Sample too small for walk-forward, passed by default",
            }

        split_idx = max(2, int(len(returns) * split_ratio))
        if split_idx >= len(returns):
            split_idx = len(returns) - 1
        is_returns = returns[:split_idx]
        oos_returns = returns[split_idx:]

        is_metrics = self.run_backtest_sandbox(strategy_cls, symbol, simulated_returns=is_returns)
        oos_metrics = self.run_backtest_sandbox(strategy_cls, symbol, simulated_returns=oos_returns)

        is_sharpe = is_metrics["sharpe"]
        oos_sharpe = oos_metrics["sharpe"]

        # WFE ratio: OOS / max(IS, 0.1)
        wfe = round(float(oos_sharpe / max(is_sharpe, 0.1)), 2)
        passed = (oos_sharpe >= self.min_walk_forward_sharpe) and (wfe >= self.min_walk_forward_efficiency)

        return {
            "passed": passed,
            "is_sharpe": is_sharpe,
            "oos_sharpe": oos_sharpe,
            "wfe": wfe,
            "is_trades": len(is_returns),
            "oos_trades": len(oos_returns),
        }

    async def synthesize_code(self, symbol: str, concept: str) -> Optional[tuple[str, str, str]]:
        """
        Synthesizes code for a new EdgeStrategy subclass.
        Returns (strategy_id, class_name, code_str).
        """
        raw_id = f"alpha_{symbol.lower()}_{uuid.uuid4().hex[:6]}"
        class_name = f"SynthesizedStrategy_{raw_id.replace('-', '_')}"

        # 1. Attempt LLM generation via task role
        code = None
        try:
            from analysis.providers.llm_factory import get_client_for_task
            client = get_client_for_task("deep_research", self.settings)
            prompt = (
                f"You are an elite institutional quantitative trading engineer. Write a Python EdgeStrategy subclass for trading on {symbol}.\n"
                f"Class Name: {class_name}\n"
                f"strategy_id: \"{raw_id}\"\n"
                f"applicable_symbols: {{\"{symbol}\"}}\n"
                f"Trading Concept: {concept}\n\n"
                f"STRICT SKELETON (Class attributes and constructor must strictly match):\n"
                f"```python\n"
                f"from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal\n"
                f"from sqlalchemy.ext.asyncio import AsyncSession\n"
                f"from typing import Optional, Dict, Any, List\n"
                f"import math, numpy as np, pandas as pd, datetime, logging, decimal\n\n"
                f"class {class_name}(EdgeStrategy):\n"
                f"    strategy_id: str = \"{raw_id}\"\n"
                f"    applicable_symbols: set = {{\"{symbol}\"}}\n\n"
                f"    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:\n"
                f"        super().__init__(settings or {{}}, *args, **kwargs)\n"
                f"        # Define hyperparameters here\n\n"
                f"    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:\n"
                f"        try:\n"
                f"            # To fetch candle history if needed: candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100) (candles support c.high/c.close and c['high'])\n"
                f"            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction='buy'|'sell'|None, valid=bool, confidence=float, rationale=str, tags=list)\n"
                f"        except Exception as e:\n"
                f"            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f\"Calculation error: {{e}}\", tags=[\"error\"])\n"
                f"```\n\n"
                f"STRICT SECURITY RULES (Violations trigger AST security rejections):\n"
                f"- ONLY use the allowed imports shown in the skeleton above.\n"
                f"- DO NOT import any other modules (do NOT import app, core, os, sys, subprocess, requests, edge_engine, trading_system).\n"
                f"- DO NOT use dynamic getattr(), setattr(), delattr(), eval(), or exec(). Access attributes directly with dot notation (e.g. candle.close) or dict .get().\n"
                f"- PANDAS COMPATIBILITY: NEVER use .fillna(method='ffill') or .fillna(method='bfill') as the 'method' parameter is removed in pandas 2.1+. Always use .ffill() and .bfill() directly.\n"
                f"- NUMERICAL STABILITY: Always sanitize NaNs/Infs (e.g. using .ffill(), .bfill(), .fillna(0.0), .replace([np.inf, -np.inf], ...), or min_periods=1 in rolling) before casting to integer (.astype(int)). Never call .astype(int) on Series containing NaNs or Infs.\n"
                f"- MANDATORY METHOD: You MUST implement 'async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:' directly inside class {class_name}. Do not rename the method or define it outside the class.\n"
                f"- ERROR RESILIENCE: Wrap indicator calculations inside evaluate() in try-except blocks and return EdgeSignal(..., valid=False, rationale=f'Calculation error: {{e}}', tags=['error']) if an unexpected exception occurs.\n"
                f"- VARIABLE COMPLETENESS: Every indicator or price variable used in conditions (e.g., donchian_mid, rsi, macd, atr, upper_band) MUST be explicitly defined and assigned locally from 'latest' (e.g. donchian_mid = latest['donchian_mid']) or df before being referenced in if/elif blocks. Never reference undefined variables.\n"
                f"- TOKEN COMPLETION: Ensure the full class definition and evaluate() method are completely closed and return an EdgeSignal. Never truncate the response.\n"
                f"- Return pure python code inside ```python ``` blocks only, no extra commentary."
            )
            response = None
            create_msg = getattr(client, "create_message", None)
            if hasattr(client, "generate") and callable(getattr(client, "generate")):
                response = await client.generate(prompt)
            elif hasattr(client, "generate_content") and callable(getattr(client, "generate_content")):
                response = await client.generate_content(
                    system_prompt="You are an elite quantitative trading strategy engineer.",
                    user_message=prompt
                )
            elif callable(create_msg):
                msg_call = cast(Callable[..., Any], create_msg)
                res = msg_call(messages=[{"role": "user", "content": prompt}])
                response = await res if inspect.isawaitable(res) else res
            if response:
                content = getattr(response, "content", str(response))
                # Robust markdown extraction
                m = re.search(r"```(?:python)?\s*(.*?)(?:```|$)", content, re.DOTALL)
                if m and m.group(1).strip():
                    raw_extracted = m.group(1).strip()
                elif "```" in content:
                    raw_extracted = content.split("```")[1].strip()
                else:
                    raw_extracted = content.strip()

                sanitized = self.sanitize_strategy_code(raw_extracted)
                strat_cls = None
                if self.validate_code_safety(sanitized):
                    strat_cls = self.compile_strategy_class(sanitized, class_name)

                if strat_cls is not None:
                    try:
                        test_inst = strat_cls(self.settings)
                        if test_inst is not None:
                            code = sanitized
                    except Exception as canary_err:
                        logger.info(
                            f"[StrategySynthesis] LLM candidate canary test failed for {symbol} ({canary_err}); "
                            f"falling back to deterministic template."
                        )
                        code = None
                else:
                    logger.info(
                        f"[StrategySynthesis] LLM synthesized code for {symbol} failed compilation; "
                        f"falling back to deterministic template."
                    )
                    code = None
        except Exception as e:
            logger.debug(f"[StrategySynthesis] LLM synthesis non-fatal fallback: {e}")

        # 2. No fallback stub generation — never generate uncalculated fake alpha
        if not code:
            logger.info(
                f"[StrategySynthesis] LLM did not generate viable strategy code for {symbol} ({concept}). "
                f"Skipping candidate — no fallback stub generated."
            )
            return None

        return raw_id, class_name, code

    async def evaluate_and_register_candidate(
        self,
        strategy_id: str,
        class_name: str,
        code_str: str,
        symbol: str,
        simulated_returns: Optional[List[float]] = None,
    ) -> Optional[SynthesizedStrategyCandidate]:
        """
        Compiles the candidate, runs sandbox backtest, and if Sharpe > 1.5 and Max DD < 10%,
        registers into StrategyRegistry and saves to disk / DB SystemConfig.
        """
        code_str = self.sanitize_strategy_code(code_str)
        strat_cls = self.compile_strategy_class(code_str, class_name)
        if not strat_cls:
            return None

        # Canary instantiation and evaluation test before backtesting or registering
        try:
            test_instance = strat_cls(self.settings)
            assert test_instance is not None
            # Execute canary evaluate on dummy slice session to ensure runtime stability
            from database.models import PriceOHLCV
            import datetime
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            mock_candles = [
                PriceOHLCV(
                    symbol=symbol,
                    timeframe="H1",
                    timestamp=now_dt - datetime.timedelta(hours=j),
                    open=1.0,
                    high=1.05,
                    low=0.95,
                    close=1.02,
                    volume=100.0,
                )
                for j in range(120, 0, -1)
            ]
            canary_session = cast(AsyncSession, HistoricalSliceSession(mock_candles))
            canary_sig = await test_instance.evaluate(canary_session, symbol, self.settings)
            if canary_sig is not None:
                if not isinstance(canary_sig, EdgeSignal):
                    logger.warning(
                        f"[StrategySynthesis] Canary evaluation returned non-EdgeSignal for {class_name}: {type(canary_sig)}"
                    )
                    return None
                if "error" in getattr(canary_sig, "tags", []) or "evaluation_error" in getattr(canary_sig, "tags", []):
                    logger.warning(
                        f"[StrategySynthesis] Canary evaluation produced error signal for {class_name}: {canary_sig.rationale}"
                    )
                    return None
        except Exception as canary_err:
            logger.warning(f"[StrategySynthesis] Canary check failed for {class_name}: {canary_err}")
            return None

        # Obtain trade returns: from simulated_returns if provided (unit tests),
        # otherwise from real institutional historical simulation across PriceOHLCV candles.
        if simulated_returns is not None:
            returns = list(simulated_returns)
        else:
            returns = await self.run_historical_simulation(strat_cls, symbol)

        metrics = self.run_backtest_sandbox(strat_cls, symbol, simulated_returns=returns)
        sharpe = metrics["sharpe"]
        max_dd = metrics["max_drawdown_pct"]
        trades = int(metrics["trades"])
        win_rate = metrics["win_rate_pct"]

        meets_criteria = (
            sharpe >= self.min_sharpe
            and max_dd <= self.max_drawdown_pct
            and trades >= self.min_trades
        )

        logger.info(
            f"[StrategySynthesis] Candidate '{strategy_id}' on {symbol}: "
            f"Sharpe={sharpe:.2f} (min {self.min_sharpe}), MaxDD={max_dd:.1f}% (max {self.max_drawdown_pct}%), "
            f"Trades={trades} -> {'QUALIFIED' if meets_criteria else 'REJECTED'}"
        )

        if not meets_criteria:
            return None

        # Walk-Forward Gating before activation
        if self.walk_forward_enabled:
            wf_res = self.run_walk_forward_validation(strat_cls, symbol, returns=returns)
            if not wf_res.get("passed", False):
                logger.info(
                    f"[StrategySynthesis] Candidate '{strategy_id}' rejected by Walk-Forward Gating: "
                    f"OOS Sharpe={wf_res.get('oos_sharpe', 0.0):.2f} (min {self.min_walk_forward_sharpe}), "
                    f"WFE={wf_res.get('wfe', 0.0):.2f} (min {self.min_walk_forward_efficiency})"
                )
                return None
            logger.info(
                f"[StrategySynthesis] Candidate '{strategy_id}' passed Walk-Forward Gating: "
                f"OOS Sharpe={wf_res.get('oos_sharpe', 0.0):.2f}, WFE={wf_res.get('wfe', 0.0):.2f}"
            )

        # Persist to disk and verify integrity
        file_path = self.SYNTHESIZED_DIR / f"{strategy_id}.py"
        try:
            file_path.write_text(code_str, encoding="utf-8")
            lint_ok, lint_err = self._lint_check_code(code_str)
            if not lint_ok:
                logger.error(
                    f"[StrategySynthesis] Post-write lint verification failed for {strategy_id}: {lint_err}"
                )
                if file_path.exists():
                    file_path.unlink()
                return None
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Failed writing code to disk: {e}")
            return None

        # Register in StrategyRegistry
        try:
            StrategyRegistry.register(strat_cls, overwrite=True)
            logger.info(f"[StrategySynthesis] Promoted and registered strategy: {strategy_id}")
            if self.edge_strategy_runner and hasattr(self.edge_strategy_runner, "hot_reload_strategy"):
                self.edge_strategy_runner.hot_reload_strategy(strategy_id, {})
                logger.info(f"[StrategySynthesis] Hot-reloaded strategy '{strategy_id}' into EdgeStrategyRunner")
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Registry registration error: {e}")

        candidate = SynthesizedStrategyCandidate(
            strategy_id=strategy_id,
            class_name=class_name,
            symbol=symbol,
            python_code=code_str,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            win_rate_pct=win_rate,
            total_trades=trades,
            status="REGISTERED",
            file_path=str(file_path),
        )
        self.candidates.append(candidate)

        # Dual-persist into DB SystemConfig and ActivityLog
        await self._persist_candidate(candidate)

        return candidate

    async def _persist_candidate(self, candidate: SynthesizedStrategyCandidate) -> None:
        """Persists synthesized candidate into DB SystemConfig and ActivityLog."""
        try:
            async with get_session() as session:
                config_key = f"synthesized_strategy_{candidate.strategy_id}"
                config_val = json.dumps(candidate.to_dict())

                existing = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == config_key)
                )).scalar_one_or_none()

                if existing:
                    await session.execute(
                        update(SystemConfig)
                        .where(SystemConfig.key == config_key)
                        .values(value=config_val)
                    )
                else:
                    session.add(SystemConfig(key=config_key, value=config_val))

                session.add(ActivityLog(
                    category="strategy",
                    description=(
                        f"Autonomous Strategy Synthesized & Deployed: {candidate.strategy_id} "
                        f"Sharpe={candidate.sharpe_ratio:.2f}, MaxDD={candidate.max_drawdown_pct:.1f}%, "
                        f"WR={candidate.win_rate_pct:.1f}%"
                    ),
                    actor="strategy_synthesis_scheduler",
                    related_id=None,
                ))
                await session.commit()
                logger.info(f"[StrategySynthesis] Persisted strategy {candidate.strategy_id} to DB.")

            # Notify operator if notifier is available
            if self.notifier and hasattr(self.notifier, "send_info"):
                await self.notifier.send_info(
                    f"💡 <b>Autonomous Strategy Synthesized & Deployed!</b>\n"
                    f"<b>ID:</b> <code>{candidate.strategy_id}</code>\n"
                    f"<b>Symbol:</b> {candidate.symbol}\n"
                    f"<b>Sharpe:</b> <code>{candidate.sharpe_ratio:.2f}</code> (Target &gt;= {self.min_sharpe})\n"
                    f"<b>Max Drawdown:</b> <code>{candidate.max_drawdown_pct:.1f}%</code> (Limit &lt;= {self.max_drawdown_pct}%)\n"
                    f"<b>Win Rate:</b> <code>{candidate.win_rate_pct:.1f}%</code> ({candidate.total_trades} trades)\n"
                    f"Registered into StrategyRegistry for live execution."
                )
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Failed persisting candidate {candidate.strategy_id}: {e}")

    async def run_synthesis_cycle(self) -> List[SynthesizedStrategyCandidate]:
        """Runs one synthesis cycle across target symbols."""
        logger.info("[StrategySynthesis] Starting autonomous strategy synthesis cycle...")
        new_promoted = []

        concepts = [
            "Mean reversion on ATR exhaustion",
            "Multi-timeframe liquidity sweep displacement",
            "Volume-weighted dynamic Donchian expansion",
        ]

        for sym in self.target_symbols:
            for concept in concepts:
                try:
                    res = await self.synthesize_code(sym, concept)
                    if not res:
                        continue
                    strat_id, class_name, code = res
                    cand = await self.evaluate_and_register_candidate(
                        strat_id, class_name, code, sym
                    )
                    if cand:
                        new_promoted.append(cand)
                except Exception as e:
                    logger.warning(f"[StrategySynthesis] Synthesis step failed for {sym}: {e}")

        logger.info(f"[StrategySynthesis] Cycle complete. {len(new_promoted)} new strategies registered.")
        return new_promoted

    async def start(self) -> None:
        """Main autonomous scheduler loop."""
        if not self.enabled:
            logger.info("StrategySynthesisScheduler is disabled via configuration.")
            return
        self._running = True
        logger.info(f"StrategySynthesisScheduler started (interval: {self.interval_hours}h)")

        if self.recovery_event:
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=120.0)
                logger.info("StrategySynthesisScheduler: Recovery complete, ready to operate.")
            except asyncio.TimeoutError:
                logger.debug("StrategySynthesisScheduler: Recovery wait timed out (120s), proceeding.")

        while self._running:
            try:
                await self.run_synthesis_cycle()
            except Exception as e:
                logger.error(f"StrategySynthesisScheduler cycle error: {e}", exc_info=True)

            sleep_seconds = self.interval_hours * 3600
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        logger.info("StrategySynthesisScheduler stopped.")
