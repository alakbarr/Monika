import logging

logger = logging.getLogger("TradingAgent.SwapEstimator")

FALLBACK_SWAP = {
    "EURUSD": {"long": -6.5, "short": 1.2},
    "GBPUSD": {"long": -4.8, "short": -0.5},
    "USDJPY": {"long": 3.1, "short": -8.2},
    "AUDUSD": {"long": -2.0, "short": -1.0},
    "XAUUSD": {"long": -8.0, "short": -3.0},
    "BTCUSD": {"long": -15.0, "short": -15.0},
    "XTIUSD": {"long": -5.0, "short": -2.0},
    "XBRUSD": {"long": -5.0, "short": -2.0},
}

from datetime import datetime, timedelta
from typing import Optional


async def estimate_swap_cost(
    symbol: str,
    direction: str,
    lots: float,
    holding_hours: float,
    start_time: Optional[datetime] = None,
    mt5_client=None,
) -> float:
    if holding_hours < 24.0 and not start_time:
        return 0.0

    # Calculate effective rollover days (Wednesday = 3x swap)
    effective_nights = 0.0
    if start_time:
        end_dt = start_time + timedelta(hours=holding_hours)
        # Find first rollover (21:00 UTC) strictly after start_time
        first_roll = start_time.replace(hour=21, minute=0, second=0, microsecond=0)
        if first_roll <= start_time:
            first_roll += timedelta(days=1)
        cur_roll = first_roll
        while cur_roll <= end_dt:
            # Wednesday rollover (weekday == 2) incurs 3x swap
            multiplier = 3.0 if cur_roll.weekday() == 2 else 1.0
            effective_nights += multiplier
            cur_roll += timedelta(days=1)
    else:
        effective_nights = float(max(0, int(holding_hours // 24)))

    if effective_nights == 0.0:
        return 0.0

    per_night = None
    dir_clean = (direction or "").lower()
    is_buy = dir_clean in ("buy", "long")

    if mt5_client:
        try:
            info = await mt5_client.get_symbol_info(symbol)
            if info:
                raw_swap = info.get("swap_long") if is_buy else info.get("swap_short")
                swap_mode = info.get("swap_mode", 1)  # 1 = by points, 2 = in symbol currency
                point = info.get("point")
                tick_value = info.get("trade_tick_value")
                tick_size = info.get("trade_tick_size")

                if raw_swap is not None:
                    if swap_mode == 1:  # in points
                        if point is not None and tick_value is not None and tick_size is not None:
                            point_val = (
                                (float(tick_value) / float(tick_size) * float(point)) if float(tick_size) > 0 else 0.1
                            )
                        else:
                            # In points mode without full broker tick specs, 1 point represents 0.1 pip ($0.10)
                            point_val = 0.1
                        per_night = float(raw_swap) * point_val
                    else:
                        per_night = float(raw_swap)
        except Exception as e:
            logger.warning(f"Failed to fetch live swap for {symbol}: {e}")

    if per_night is None:
        per_night = FALLBACK_SWAP.get(symbol, {}).get("long" if is_buy else "short", -3.0)

    return round(float(per_night) * lots * effective_nights, 2)
