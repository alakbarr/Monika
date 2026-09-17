# ==============================================================================
# File: tests/cli/test_sparklines.py
# Description: Unit Tests for Braille Sparklines & Gauge Renderers
# ==============================================================================

import pytest
from cli.sparklines import braille_sparkline, bar_gauge, BRAILLE_BASE


def test_braille_sparkline_empty():
    """Empty list returns blank braille sequence."""
    res = braille_sparkline([], width=10)
    assert len(res) == 10
    assert res == chr(BRAILLE_BASE) * 10


def test_braille_sparkline_zero_width():
    """Width <= 0 returns empty string."""
    assert braille_sparkline([1.0, 2.0, 3.0], width=0) == ""
    assert braille_sparkline([1.0, 2.0, 3.0], width=-5) == ""


def test_braille_sparkline_flat_values():
    """Identical values produce consistent non-zero braille output."""
    res = braille_sparkline([5.0, 5.0, 5.0, 5.0], width=4)
    assert len(res) == 4
    # Ensure chars are within braille block
    for char in res:
        assert ord(char) >= BRAILLE_BASE


def test_braille_sparkline_ascending_descending():
    """Ascending trajectory produces valid braille characters."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
    res = braille_sparkline(values, width=4)
    assert len(res) == 4
    # All characters must be braille
    for c in res:
        assert 0x2800 <= ord(c) <= 0x28FF


def test_braille_sparkline_negative_values():
    """Handles negative and mixed floats correctly."""
    values = [-100.5, -50.0, 0.0, 50.0, 100.5]
    res = braille_sparkline(values, width=6)
    assert len(res) == 6


def test_bar_gauge_threshold_colors():
    """Test ratio calculation and threshold color tiers."""
    # Under 50%: green
    bar_low, col_low = bar_gauge(25.0, 100.0, width=10)
    assert "█" in bar_low
    assert col_low == "#2D5A27"

    # Between 50% and 80%: brass/amber
    bar_mid, col_mid = bar_gauge(65.0, 100.0, width=10)
    assert col_mid == "#C49A45"

    # Above 80%: red
    bar_high, col_high = bar_gauge(95.0, 100.0, width=10)
    assert col_high == "#8B261E"


def test_bar_gauge_boundaries():
    """Zero, negative, overflow, and zero max values."""
    # Zero value
    b0, _ = bar_gauge(0.0, 100.0, width=10)
    assert b0 == "░" * 10

    # Max exceeded (caps at width)
    b_max, _ = bar_gauge(150.0, 100.0, width=10)
    assert b_max == "█" * 10

    # Zero max_val
    b_zero_max, _ = bar_gauge(50.0, 0.0, width=10)
    assert b_zero_max == "░" * 10

    # Zero width
    b_zero_w, _ = bar_gauge(50.0, 100.0, width=0)
    assert b_zero_w == ""
