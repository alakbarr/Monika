# ==============================================================================
# File: cli/sparklines.py
# Description: Terminal Braille Sparklines & Gauge Renderers
# ==============================================================================

"""
Terminal charting utilities for Monika AI Trading Agent.

Pure Python braille sparklines and bar gauges with zero third-party dependencies.
Renders PnL trends, VIX curves, equity trajectories, and context window gauges.
"""

from typing import List, Tuple, Sequence

BRAILLE_BASE = 0x2800
# (left_dot, right_dot) for rows from top (row 3) down to bottom (row 0)
# Dot 1 & 4 (top), Dot 2 & 5 (upper-mid), Dot 3 & 6 (lower-mid), Dot 7 & 8 (bottom)
BRAILLE_DOTS: Tuple[Tuple[int, int], ...] = (
    (0x01, 0x08),  # Row 3 (top)
    (0x02, 0x10),  # Row 2
    (0x04, 0x20),  # Row 1
    (0x40, 0x80),  # Row 0 (bottom)
)


def braille_sparkline(values: Sequence[float], width: int = 20) -> str:
    """
    Render values as a braille sparkline.

    Each braille character provides 2 horizontal columns and 4 vertical levels.
    Supports padding when fewer values than required, truncating when more.

    Args:
        values: Sequence of numeric values.
        width: Number of terminal character columns to render.

    Returns:
        String of braille characters of length `width`.
    """
    if width <= 0:
        return ""
    if not values:
        return chr(BRAILLE_BASE) * width

    vals = [float(v) for v in values]
    mn, mx = min(vals), max(vals)
    rng = mx - mn
    if rng <= 0.0:
        rng = 1.0

    target = width * 2
    norm = [int((v - mn) / rng * 3.99) for v in vals]

    if len(norm) > target:
        norm = norm[-target:]
    elif len(norm) < target:
        norm = [0] * (target - len(norm)) + norm

    chars: List[str] = []
    for i in range(0, len(norm), 2):
        left = norm[i]
        right = norm[i + 1] if i + 1 < len(norm) else 0
        code = BRAILLE_BASE
        for row in range(4):
            if row <= left:
                code |= BRAILLE_DOTS[3 - row][0]
            if row <= right:
                code |= BRAILLE_DOTS[3 - row][1]
        chars.append(chr(code))

    return "".join(chars)


def bar_gauge(
    value: float,
    max_val: float,
    width: int = 20,
    thresholds: Tuple[float, float] = (0.5, 0.8),
    colors: Tuple[str, str, str] = ("#2D5A27", "#C49A45", "#8B261E"),
) -> Tuple[str, str]:
    """
    Render a horizontal text bar gauge with threshold-based coloring.

    Args:
        value: Current numeric value.
        max_val: Maximum expected value.
        width: Total character width of the gauge.
        thresholds: (warn_threshold, critical_threshold) as ratios 0.0 - 1.0.
        colors: (ok_color, warn_color, critical_color) hex codes.

    Returns:
        (bar_string, color_hex) tuple.
    """
    if width <= 0:
        return "", colors[0]

    ratio = min(max(value / max_val, 0.0), 1.0) if max_val > 0 else 0.0
    filled = int(round(ratio * width))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)

    if ratio < thresholds[0]:
        color = colors[0]
    elif ratio < thresholds[1]:
        color = colors[1]
    else:
        color = colors[2]

    return bar, color
