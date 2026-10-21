"""Pure position-math helpers shared by risk checks and paper accounting.

Phase 0 contract (fail closed): a stop loss that is missing, non-finite,
non-positive, or on the wrong side of the entry price is not a risk anchor.
Callers must treat ``None`` as "risk unknown" and refuse to size, gate, or
account with it instead of falling back to a permissive default.
"""

from __future__ import annotations

import math


def validated_stop_distance(
    direction: str,
    entry_price: float | None,
    stop_loss: float | None,
) -> float | None:
    """Return the entry-to-stop distance on the loss side, or ``None`` when invalid.

    BUY  requires ``stop_loss < entry_price``.
    SELL requires ``stop_loss > entry_price``.

    Any other direction, a non-finite/zero/negative price, or a stop on the
    wrong side of entry returns ``None``. This is the single replacement for
    the historical ``abs(entry - stop)`` calls that turned a trailing stop
    moved past entry into a fresh, larger risk denominator.
    """
    if entry_price is None or stop_loss is None:
        return None
    try:
        entry = float(entry_price)
        stop = float(stop_loss)
    except TypeError, ValueError:
        return None
    if not math.isfinite(entry) or not math.isfinite(stop) or entry <= 0.0 or stop <= 0.0:
        return None

    normalized = (direction or "").strip().lower()
    if normalized == "buy":
        distance = entry - stop
    elif normalized == "sell":
        distance = stop - entry
    else:
        return None

    if not math.isfinite(distance) or distance <= 0.0:
        return None
    return distance
