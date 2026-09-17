import math, logging
logger = logging.getLogger('TradingAgent.IndicatorSanitizer')

def safe_float(value, default: float | None = None, field_name: str = 'value') -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        logger.debug(f'Non-numeric indicator {field_name}={value!r} -> default={default}')
        return default
    if math.isnan(f) or math.isinf(f):
        logger.debug(f'NaN/Inf indicator {field_name}={value!r} -> default={default}')
        return default
    return f
