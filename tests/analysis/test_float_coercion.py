import pytest
from analysis.validators.float_coercion import coerce_float, coerce_optional_float


def test_coerce_optional_float_none_and_empty():
    assert coerce_optional_float(None) is None
    assert coerce_optional_float("") is None
    assert coerce_optional_float("   ") is None


def test_coerce_optional_float_null_representations():
    null_values = ["N/A", "n/a", "none", "None", "NULL", "null", "-", "NaN", "nan", "nil", "undefined"]
    for val in null_values:
        assert coerce_optional_float(val) is None
        assert coerce_optional_float(f"  {val}  ") is None


def test_coerce_optional_float_numeric_primitives():
    assert coerce_optional_float(42) == 42.0
    assert coerce_optional_float(42.5) == 42.5
    assert coerce_optional_float(-10.25) == -10.25
    assert coerce_optional_float(0) == 0.0


def test_coerce_optional_float_currency_symbols():
    assert coerce_optional_float("$100.50") == 100.50
    assert coerce_optional_float("€ 45.20") == 45.20
    assert coerce_optional_float("£1,234.50") == 1234.50
    assert coerce_optional_float("¥ 5000") == 5000.0


def test_coerce_optional_float_percentages():
    assert coerce_optional_float("15.5%") == 15.5
    assert coerce_optional_float("  99.9 % ") == 99.9
    assert coerce_optional_float("-3.2%") == -3.2


def test_coerce_optional_float_commas():
    assert coerce_optional_float("1,234,567.89") == 1234567.89
    assert coerce_optional_float("$2,500.00") == 2500.0


def test_coerce_optional_float_invalid_strings():
    assert coerce_optional_float("unknown") is None
    assert coerce_optional_float("invalid_number") is None
    assert coerce_optional_float("foo$bar") is None


def test_coerce_float_default():
    assert coerce_float(None) == 0.0
    assert coerce_float("invalid") == 0.0
    assert coerce_float("invalid", default=5.5) == 5.5
    assert coerce_float("$12.34", default=1.0) == 12.34
    assert coerce_float(42, default=0.0) == 42.0
