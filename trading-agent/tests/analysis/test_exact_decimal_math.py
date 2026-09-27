# ==============================================================================
# File: tests/analysis/test_exact_decimal_math.py
# Monika Exact Decimal Math Test Suite
# ==============================================================================

from decimal import Decimal
import pytest

from analysis.debate.exact_decimal_math import (
    to_exact_decimal,
    safe_evaluate_math_expression,
    exact_rr_ratio,
    exact_price_deviation_pct,
)


def test_to_exact_decimal():
    assert to_exact_decimal(10) == Decimal("10")
    assert to_exact_decimal(0.1) == Decimal("0.1")
    assert to_exact_decimal("123.456") == Decimal("123.456")
    assert to_exact_decimal(Decimal("42.0")) == Decimal("42.0")

    with pytest.raises(ValueError, match="Cannot convert None"):
        to_exact_decimal(None)

    with pytest.raises(ValueError, match="Cannot convert"):
        to_exact_decimal("invalid_number")


def test_safe_evaluate_math_expression_precision():
    # IEEE-754 binary floating point produces 0.30000000000000004
    # Exact Decimal must produce exact 0.3
    res = safe_evaluate_math_expression("0.1 + 0.2")
    assert res == Decimal("0.3")

    complex_res = safe_evaluate_math_expression("(100.50 * 2) - (15.2 / 2) + (3 ** 2)")
    # 201.0 - 7.6 + 9 = 202.4
    assert complex_res == Decimal("202.4")


def test_safe_evaluate_math_expression_security_rejection():
    # Disallowed function calls and injections
    with pytest.raises(ValueError):
        safe_evaluate_math_expression("__import__('os').system('dir')")

    with pytest.raises(ValueError):
        safe_evaluate_math_expression("exec('x=1')")

    with pytest.raises(ValueError):
        safe_evaluate_math_expression("abs(-5)")

    with pytest.raises(ValueError):
        safe_evaluate_math_expression("x + 5")

    with pytest.raises(ValueError):
        safe_evaluate_math_expression("True + 1")

    with pytest.raises(ValueError):
        safe_evaluate_math_expression("")


def test_safe_evaluate_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        safe_evaluate_math_expression("100 / 0")


def test_exact_rr_ratio():
    # Long trade: Entry 2000.0, SL 1990.0, TP 2030.0 -> SL dist = 10, TP dist = 30 -> RR = 3.0
    rr = exact_rr_ratio(2000.0, 1990.0, 2030.0)
    assert rr == Decimal("3")

    # Short trade: Entry 1.0850, SL 1.0870, TP 1.0800 -> SL dist = 0.0020, TP dist = 0.0050 -> RR = 2.5
    rr_short = exact_rr_ratio("1.0850", "1.0870", "1.0800")
    assert rr_short == Decimal("2.5")

    # Zero distance SL raises
    with pytest.raises(ValueError, match="Stop loss distance is zero"):
        exact_rr_ratio(2000.0, 2000.0, 2030.0)


def test_exact_price_deviation_pct():
    dev = exact_price_deviation_pct(2020.0, 2000.0)
    assert dev == Decimal("1.0")

    with pytest.raises(ValueError, match="Reference price must be positive"):
        exact_price_deviation_pct(2020.0, 0.0)

    with pytest.raises(ValueError, match="Reference price must be positive"):
        exact_price_deviation_pct(2020.0, -100.0)
