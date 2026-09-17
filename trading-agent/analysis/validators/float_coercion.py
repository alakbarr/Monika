import re
from typing import Any, Optional


def coerce_optional_float(value: Any) -> Optional[float]:
    """Defensively coerce LLM-generated values into clean floats.
    
    Strips currency symbols ($ € £ ¥), commas, percentage signs, and whitespace.
    Returns None if value represents null or is unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    val_str = str(value).strip()
    if not val_str or val_str.lower() in ("n/a", "none", "null", "-", "nan", "nil", "undefined"):
        return None

    cleaned = re.sub(r'[$€£¥,]', '', val_str).strip()
    cleaned = re.sub(r'\s*%\s*$', '', cleaned).strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def coerce_float(value: Any, default: float = 0.0) -> float:
    """Coerce value to float with a safe fallback default."""
    res = coerce_optional_float(value)
    return res if res is not None else default
