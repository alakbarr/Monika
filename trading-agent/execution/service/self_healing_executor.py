"""
File: execution/service/self_healing_executor.py
Autonomous self-healing execution harness for MetaTrader 5 orders.
Intercepts broker rejections (stops_level violation, requotes, volume snapping)
and performs zero-token deterministic micro-repairs without dropping trades.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.Execution.SelfHealing")


class MT5SelfHealingExecutor:
    """
    Closed-loop autonomous executor that repairs recoverable broker errors.
    Deterministic mathematical healing ensures high-probability setups are not dropped.
    """

    MAX_HEALING_ATTEMPTS: int = 3

    def __init__(self, broker_adapter: Any, mt5_client: Optional[Any] = None):
        self.broker_adapter = broker_adapter
        self.mt5_client = mt5_client or getattr(broker_adapter, "mt5_client", None)

    async def heal_and_reexecute(
        self,
        order: Any,
        mt5_result: Dict[str, Any],
        sl: Optional[float],
        tp: Optional[float],
        comment: str,
        max_spread_multiplier: Optional[float] = None,
        atr: Optional[float] = None,
        decision: str = "buy",
    ) -> Dict[str, Any]:
        """
        Attempts up to MAX_HEALING_ATTEMPTS deterministic micro-repairs upon broker rejection.
        Returns the updated mt5_result dict (success=True if healed and filled).
        """
        if mt5_result.get("success"):
            return mt5_result

        symbol = getattr(order, "symbol", "")
        current_sl = sl
        current_tp = tp
        curr_volume = float(getattr(order, "requested_volume", 0.01) or 0.01)
        direction = (decision or getattr(order, "order_type", "buy")).lower()
        is_buy = "buy" in direction

        for attempt in range(1, self.MAX_HEALING_ATTEMPTS + 1):
            retcode = mt5_result.get("retcode", -1)
            err_msg = str(mt5_result.get("error", "")).lower()

            logger.info(
                f"[SelfHealingMT5] Attempt {attempt}/{self.MAX_HEALING_ATTEMPTS} for {symbol}: "
                f"Retcode={retcode}, Error='{err_msg}'"
            )

            # ── 1. Retcode 10016: TRADE_RETCODE_INVALID_STOPS ──
            if retcode == 10016 or "invalid stops" in err_msg or "stops" in err_msg:
                healed_stops = await self._heal_stops(symbol, current_sl, current_tp, is_buy)
                if healed_stops:
                    new_sl, new_tp = healed_stops
                    logger.warning(
                        f"[SelfHealingMT5] {symbol} Stop levels healed: "
                        f"SL: {current_sl} -> {new_sl}, TP: {current_tp} -> {new_tp}"
                    )
                    current_sl, current_tp = new_sl, new_tp
                    mt5_result = await self.broker_adapter.submit_order(
                        order=order,
                        sl=current_sl,
                        tp=current_tp,
                        comment=f"{comment[:24]}|heal_sl",
                        max_spread_multiplier=max_spread_multiplier,
                    )
                    if mt5_result.get("success"):
                        logger.info(f"[SelfHealingMT5] {symbol} Order successfully FILLED after stops repair!")
                        return mt5_result
                    continue

            # ── 2. Retcode 10014: TRADE_RETCODE_INVALID_VOLUME ──
            if retcode == 10014 or "invalid volume" in err_msg or "volume" in err_msg:
                snapped_vol = await self._snap_volume(symbol, curr_volume)
                if snapped_vol and snapped_vol != curr_volume:
                    logger.warning(
                        f"[SelfHealingMT5] {symbol} Volume healed: {curr_volume} -> {snapped_vol}"
                    )
                    curr_volume = snapped_vol
                    order.requested_volume = curr_volume
                    mt5_result = await self.broker_adapter.submit_order(
                        order=order,
                        sl=current_sl,
                        tp=current_tp,
                        comment=f"{comment[:24]}|heal_vol",
                        max_spread_multiplier=max_spread_multiplier,
                    )
                    if mt5_result.get("success"):
                        logger.info(f"[SelfHealingMT5] {symbol} Order successfully FILLED after volume repair!")
                        return mt5_result
                    continue

            # ── 3. Retcode 10004 / 10015: REQUOTE or INVALID_PRICE ──
            if retcode in (10004, 10015, 10021) or "requote" in err_msg or "price" in err_msg:
                can_reprice = await self._check_reprice_tolerance(symbol, order, is_buy, atr)
                if can_reprice:
                    logger.warning(f"[SelfHealingMT5] {symbol} Re-pricing order within ATR tolerance buffer...")
                    mt5_result = await self.broker_adapter.submit_order(
                        order=order,
                        sl=current_sl,
                        tp=current_tp,
                        comment=f"{comment[:24]}|heal_prc",
                        max_spread_multiplier=max_spread_multiplier,
                    )
                    if mt5_result.get("success"):
                        logger.info(f"[SelfHealingMT5] {symbol} Order successfully FILLED after re-pricing!")
                        return mt5_result
                    continue

            # Non-recoverable error (e.g. 10019 NO_MONEY, 10027 AUTOTRADING_DISABLED)
            logger.error(f"[SelfHealingMT5] {symbol} Encountered non-recoverable error ({retcode}): {err_msg}")
            break

        return mt5_result

    async def _heal_stops(
        self, symbol: str, sl: Optional[float], tp: Optional[float], is_buy: bool
    ) -> Optional[tuple[float, float]]:
        """Calculates deterministic SL/TP offset outside broker stops_level zone."""
        try:
            import MetaTrader5 as mt5
            info = mt5.symbol_info(symbol)
            if not info:
                return None

            point = info.point or 0.00001
            digits = info.digits or 5
            stops_level = max(getattr(info, "trade_stops_level", 10), 10)
            spread = getattr(info, "spread", 20)

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return None

            # In MT5, Buy positions close at Bid, Sell positions close at Ask
            curr_price = tick.bid if is_buy else tick.ask
            min_buffer_pts = stops_level + spread + 10  # 10 point extra buffer
            min_dist = min_buffer_pts * point

            new_sl = sl
            new_tp = tp

            if is_buy:
                # For Buy: SL must be below curr_price by at least min_dist
                if sl is not None:
                    max_allowed_sl = curr_price - min_dist
                    if sl >= max_allowed_sl:
                        new_sl = round(max_allowed_sl - (2 * point), digits)
                # For Buy: TP must be above curr_price by at least min_dist
                if tp is not None:
                    min_allowed_tp = curr_price + min_dist
                    if tp <= min_allowed_tp:
                        new_tp = round(min_allowed_tp + (5 * point), digits)
            else:
                # For Sell: SL must be above curr_price by at least min_dist
                if sl is not None:
                    min_allowed_sl = curr_price + min_dist
                    if sl <= min_allowed_sl:
                        new_sl = round(min_allowed_sl + (2 * point), digits)
                # For Sell: TP must be below curr_price by at least min_dist
                if tp is not None:
                    max_allowed_tp = curr_price - min_dist
                    if tp >= max_allowed_tp:
                        new_tp = round(max_allowed_tp - (5 * point), digits)

            return (new_sl if new_sl is not None else 0.0, new_tp if new_tp is not None else 0.0)
        except Exception as e:
            logger.debug(f"[SelfHealingMT5] Error calculating healed stops: {e}")
            return None

    async def _snap_volume(self, symbol: str, volume: float) -> Optional[float]:
        """Snaps lot volume to valid broker min, max, and volume_step."""
        try:
            import MetaTrader5 as mt5
            info = mt5.symbol_info(symbol)
            if not info:
                return None

            vol_min = getattr(info, "volume_min", 0.01) or 0.01
            vol_max = getattr(info, "volume_max", 100.0) or 100.0
            vol_step = getattr(info, "volume_step", 0.01) or 0.01

            # Snap to step
            steps = round(volume / vol_step)
            snapped = round(steps * vol_step, 2)
            snapped = max(vol_min, min(vol_max, snapped))
            return snapped
        except Exception as e:
            logger.debug(f"[SelfHealingMT5] Error snapping volume: {e}")
            return None

    async def _check_reprice_tolerance(
        self, symbol: str, order: Any, is_buy: bool, atr: Optional[float]
    ) -> bool:
        """Verifies if fresh tick price is within safe ATR drift tolerance (<= 0.20 * ATR)."""
        try:
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return False

            fresh_price = tick.ask if is_buy else tick.bid
            old_price = float(getattr(order, "planned_entry_price", 0.0) or fresh_price)

            if atr and atr > 0:
                drift = abs(fresh_price - old_price)
                max_allowed_drift = 0.20 * atr
                if drift > max_allowed_drift:
                    logger.warning(
                        f"[SelfHealingMT5] Price drift {drift:.5f} exceeds ATR buffer {max_allowed_drift:.5f}. "
                        f"Skipping re-pricing to prevent slippage violation."
                    )
                    return False

            # Update planned entry price
            order.planned_entry_price = fresh_price
            return True
        except Exception as e:
            logger.debug(f"[SelfHealingMT5] Error checking reprice tolerance: {e}")
            return False
