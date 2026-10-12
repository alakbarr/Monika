# ==============================================================================
# File: analysis/debate/exact_decimal_math.py
# Monika Exact Decimal Financial Arithmetic Engine (28-Digit Precision)
# ==============================================================================

"""
Exact Decimal Financial Arithmetic Engine.

Guarantees 28-digit decimal precision and AST-whitelisted arithmetic evaluation
to eliminate IEEE-754 binary floating-point drift in order level optimization,
risk/reward ratios, slippage calculations, and geometric constraints.
"""

from __future__ import annotations

import ast
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Union

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)

_AST_BINOPS = {
    ast.Add: _CTX.add,
    ast.Sub: _CTX.subtract,
    ast.Mult: _CTX.multiply,
    ast.Div: _CTX.divide,
    ast.Pow: _CTX.power,
    ast.Mod: _CTX.remainder,
}

_AST_UNARYOPS = {
    ast.UAdd: lambda d: d,
    ast.USub: lambda d: -d,
}


def to_exact_decimal(value: Any) -> Decimal:
    """
    Converts any numeric or string representation into an exact Decimal.
    Avoids float binary precision traps by stringifying floats first.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("Cannot convert None to Decimal")
    try:
        # Stringify to avoid IEEE-754 binary mantissa expansion (e.g. 0.1 -> 0.10000000000000000555)
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot convert {value!r} to exact Decimal") from exc


def _eval_ast_node(node: ast.AST) -> Decimal:
    """Recursively evaluates an arithmetic AST node in the 28-digit Decimal domain."""
    if isinstance(node, ast.Constant):
        # Reject booleans (subclass of int in Python)
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Disallowed constant: {node.value!r} (only numeric constants permitted)")
        return to_exact_decimal(node.value)

    if isinstance(node, ast.BinOp):
        op_fn = _AST_BINOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported binary operator in financial formula: {type(node.op).__name__}")
        left_val = _eval_ast_node(node.left)
        right_val = _eval_ast_node(node.right)
        try:
            return op_fn(left_val, right_val)
        except ZeroDivisionError as err:
            raise ZeroDivisionError("Division by zero in exact decimal evaluation") from err

    if isinstance(node, ast.UnaryOp):
        op_fn = _AST_UNARYOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_ast_node(node.operand))

    raise ValueError(f"Disallowed AST element in expression: {type(node).__name__}")


def safe_evaluate_math_expression(expression: str) -> Decimal:
    """
    Evaluates an arithmetic expression string safely in the exact-Decimal domain.
    
    Safe from arbitrary code execution:
    - Parses expression via ast.parse(mode='eval')
    - Only numeric constants and operators (+, -, *, /, **, %) are allowed.
    - Function calls, names, imports, attribute access, and loops are strictly forbidden.
    
    Example:
        safe_evaluate_math_expression("0.1 + 0.2") == Decimal("0.3")
    """
    clean_expr = expression.strip()
    if not clean_expr:
        raise ValueError("Empty math expression")
    try:
        tree = ast.parse(clean_expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Malformed arithmetic expression {expression!r}: {exc}") from exc
    return _eval_ast_node(tree.body)


def exact_rr_ratio(entry: Any, sl: Any, tp: Any) -> Decimal:
    """
    Calculates exact Risk:Reward ratio: abs(entry - tp) / abs(entry - sl).
    Raises ValueError if sl_dist is 0.
    """
    d_entry = to_exact_decimal(entry)
    d_sl = to_exact_decimal(sl)
    d_tp = to_exact_decimal(tp)

    sl_dist = abs(d_entry - d_sl)
    tp_dist = abs(d_entry - d_tp)

    if sl_dist == Decimal(0):
        raise ValueError("Stop loss distance is zero")

    return tp_dist / sl_dist


def exact_price_deviation_pct(current_price: Any, reference_price: Any) -> Decimal:
    """
    Calculates exact percentage deviation: abs(current - reference) / reference * 100.
    """
    d_curr = to_exact_decimal(current_price)
    d_ref = to_exact_decimal(reference_price)
    if d_ref <= Decimal(0):
        raise ValueError("Reference price must be positive")
    return (abs(d_curr - d_ref) / d_ref) * Decimal(100)
