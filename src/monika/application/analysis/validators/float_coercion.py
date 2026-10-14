import math
import re
from typing import Any, Optional


def coerce_optional_float(value: Any) -> Optional[float]:
    """Defensively coerce LLM-generated values into clean floats.

    Strips currency symbols ($ € £ ¥), handles thousands/decimal commas, percentage signs, and whitespace.
    Returns None if value represents null, NaN, Inf, or is unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f_val = float(value)
        if math.isnan(f_val) or math.isinf(f_val):
            return None
        return f_val

    val_str = str(value).strip()
    if not val_str or val_str.lower() in ("n/a", "none", "null", "-", "nan", "nil", "undefined", "inf", "-inf"):
        return None

    cleaned = re.sub(r"[$€£¥]", "", val_str).strip()
    cleaned = re.sub(r"\s*%\s*$", "", cleaned).strip()

    # Handle comma/dot formatting
    if "," in cleaned and "." in cleaned:
        # Both present: determine which is decimal based on the last occurrence
        if cleaned.rfind(".") > cleaned.rfind(","):
            # Format: 1,234.56 -> remove commas
            cleaned = cleaned.replace(",", "")
        else:
            # Format: 1.234,56 -> remove dots, replace comma with dot
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # Only comma present. E.g. "1,0850", "0,75", "1,234", "1,000,000"
        if re.match(r"^\d{1,3}(?:,\d{3})+$", cleaned):
            # Standard integer with thousands separator: e.g. "1,000", "1,000,000"
            cleaned = cleaned.replace(",", "")
        else:
            # European decimal comma: e.g. "1,0850", "0,75", "155,20"
            cleaned = cleaned.replace(",", ".")

    try:
        res = float(cleaned)
        if math.isnan(res) or math.isinf(res):
            return None
        return res
    except ValueError, TypeError:
        return None


def coerce_float(value: Any, default: float = 0.0) -> float:
    """Coerce value to float with a safe fallback default."""
    res = coerce_optional_float(value)
    return res if res is not None else default
