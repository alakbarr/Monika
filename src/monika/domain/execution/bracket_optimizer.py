"""
Deterministic Bracket Optimizer and Alignment Engine.

Snaps and harmonizes proposed trade execution brackets (Entry, Stop Loss, Take Profit)
to ensure they satisfy structural invariants, ATR noise floors, ADR target bands,
and minimum Risk-to-Reward hurdles without arbitrarily overriding high-conviction
proposals into Forced WAIT.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional

from monika.core.config.risk_defaults import DEFAULT_MIN_RR_RATIO
from monika.domain.market.instrument_identity import resolve_instrument_identity

logger = logging.getLogger("TradingAgent.BracketOptimizer")


def get_symbol_decimals(symbol: str) -> int:
    """Derives standard price display/order decimals for a given symbol."""
    try:
        ident = resolve_instrument_identity(symbol)
        pts = f"{ident.point_size:.8f}".rstrip("0")
        if "." in pts:
            return len(pts.split(".")[1])
    except Exception:
        pass
    sym_upper = symbol.upper()
    if "JPY" in sym_upper:
        return 3
    if any(k in sym_upper for k in ("XAU", "XTI", "XBR", "BTC")):
        return 2
    return 5


@dataclass(frozen=True)
class OptimizedBrackets:
    """Represents normalized, mathematically aligned trade brackets."""

    symbol: str
    direction: str  # "buy" or "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    reward_distance: float
    rr_ratio: float
    adjusted: bool
    adjustments: List[str] = field(default_factory=list)


class BracketOptimizer:
    """
    Deterministic bracket optimizer.
    Pre-flight aligns Entry, Stop Loss, and Take Profit before validation,
    eliminating preventable 'Forced WAIT' rejections.
    """

    def __init__(self, default_min_rr: float = DEFAULT_MIN_RR_RATIO) -> None:
        self.default_min_rr = float(default_min_rr)

    def optimize(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        atr: Optional[float] = None,
        adr_ctx: Optional[Dict[str, Any]] = None,
        min_rr: Optional[float] = None,
        min_sl_atr_multiplier: float = 1.0,
    ) -> OptimizedBrackets:
        """
        Calculates optimized brackets respecting ATR noise floors, ADR bands,
        and minimum R:R constraints.
        """
        dir_clean = str(direction).lower().strip()
        if dir_clean not in ("buy", "sell"):
            raise ValueError(f"Invalid direction '{direction}', expected 'buy' or 'sell'")

        if entry_price <= 0:
            raise ValueError(f"Invalid entry_price {entry_price}, must be strictly positive")

        decimals = get_symbol_decimals(symbol)
        adjustments: List[str] = []
        is_buy = dir_clean == "buy"

        target_min_rr = float(min_rr if min_rr is not None and min_rr > 0 else self.default_min_rr)

        # 1. Geometry Correction (prevent inverted SL/TP)
        cur_sl = float(stop_loss) if stop_loss > 0 else 0.0
        cur_tp = float(take_profit) if take_profit > 0 else 0.0

        if is_buy:
            if cur_sl >= entry_price:
                inverted_dist = abs(cur_sl - entry_price)
                cur_sl = entry_price - (inverted_dist if inverted_dist > 0 else 0.001)
                adjustments.append(f"Inverted BUY SL flipped below entry to {cur_sl:.{decimals}f}")
            if cur_tp > 0 and cur_tp <= entry_price:
                inverted_tp_dist = abs(entry_price - cur_tp)
                cur_tp = entry_price + (inverted_tp_dist if inverted_tp_dist > 0 else 0.002)
                adjustments.append(f"Inverted BUY TP flipped above entry to {cur_tp:.{decimals}f}")
        else:
            if cur_sl > 0 and cur_sl <= entry_price:
                inverted_dist = abs(entry_price - cur_sl)
                cur_sl = entry_price + (inverted_dist if inverted_dist > 0 else 0.001)
                adjustments.append(f"Inverted SELL SL flipped above entry to {cur_sl:.{decimals}f}")
            if cur_tp >= entry_price:
                inverted_tp_dist = abs(cur_tp - entry_price)
                cur_tp = entry_price - (inverted_tp_dist if inverted_tp_dist > 0 else 0.002)
                adjustments.append(f"Inverted SELL TP flipped below entry to {cur_tp:.{decimals}f}")

        # 2. Stop Loss Floor Alignment (ATR Floor)
        raw_sl_dist = abs(entry_price - cur_sl) if cur_sl > 0 else 0.0
        effective_atr = float(atr) if atr is not None and atr > 0 else None

        min_sl_dist = 0.0
        if effective_atr is not None:
            min_sl_dist = effective_atr * max(0.5, float(min_sl_atr_multiplier))

        # Check ADR ceiling for SL if available
        adr_sl_ceiling: Optional[float] = None
        if adr_ctx and "target_sl_max_distance" in adr_ctx:
            try:
                adr_sl_ceiling = float(adr_ctx["target_sl_max_distance"])
            except TypeError, ValueError:
                adr_sl_ceiling = None

        if adr_sl_ceiling is not None and min_sl_dist > 0:
            effective_sl_ceiling = max(adr_sl_ceiling, min_sl_dist * 1.25)
            min_sl_dist = min(min_sl_dist, effective_sl_ceiling * 0.85)

        target_sl_dist = raw_sl_dist
        if min_sl_dist > 0 and target_sl_dist < min_sl_dist:
            target_sl_dist = min_sl_dist
            adjustments.append(
                f"SL distance expanded from {raw_sl_dist:.{decimals}f} to ATR floor {target_sl_dist:.{decimals}f}"
            )
        elif adr_sl_ceiling is not None and target_sl_dist > (adr_sl_ceiling * 1.10):
            target_sl_dist = adr_sl_ceiling
            adjustments.append(
                f"SL distance capped from {raw_sl_dist:.{decimals}f} to ADR ceiling {target_sl_dist:.{decimals}f}"
            )

        if target_sl_dist <= 0:
            fallback_atr = effective_atr if effective_atr else (entry_price * 0.005)
            target_sl_dist = fallback_atr * 1.2
            adjustments.append(f"SL synthesized from ATR fallback to {target_sl_dist:.{decimals}f}")

        # Calculate aligned SL price
        aligned_sl = (entry_price - target_sl_dist) if is_buy else (entry_price + target_sl_dist)
        aligned_sl = round(aligned_sl, decimals)
        final_sl_dist = round(abs(entry_price - aligned_sl), decimals)

        # 3. Take Profit Alignment (R:R & ADR Band)
        required_min_tp_dist = final_sl_dist * target_min_rr
        raw_tp_dist = abs(cur_tp - entry_price) if cur_tp > 0 else 0.0

        target_tp_dist = raw_tp_dist
        if target_tp_dist < required_min_tp_dist:
            target_tp_dist = required_min_tp_dist
            adjustments.append(
                f"TP distance expanded from {raw_tp_dist:.{decimals}f} to meet R:R >= {target_min_rr:.2f} ({target_tp_dist:.{decimals}f})"
            )

        # Harmonize with ADR Target Band if available
        if adr_ctx and "target_tp_min_distance" in adr_ctx and "target_tp_max_distance" in adr_ctx:
            try:
                adr_tp_min = float(adr_ctx["target_tp_min_distance"])
                adr_tp_max = float(adr_ctx["target_tp_max_distance"])
                tol = float(adr_ctx.get("band_tolerance_pct", 0.10))

                eff_tp_min = adr_tp_min * (1.0 - tol)
                eff_tp_max = adr_tp_max * (1.0 + tol)

                if target_tp_dist < eff_tp_min:
                    target_tp_dist = max(eff_tp_min, required_min_tp_dist)
                    adjustments.append(f"TP snapped to ADR min target band {eff_tp_min:.{decimals}f}")
                elif target_tp_dist > eff_tp_max:
                    if eff_tp_max >= required_min_tp_dist:
                        target_tp_dist = eff_tp_max
                        adjustments.append(f"TP capped to ADR max target band {eff_tp_max:.{decimals}f}")
            except TypeError, ValueError:
                pass

        aligned_tp = (entry_price + target_tp_dist) if is_buy else (entry_price - target_tp_dist)
        aligned_tp = round(aligned_tp, decimals)
        final_tp_dist = round(abs(aligned_tp - entry_price), decimals)

        final_rr = (final_tp_dist / final_sl_dist) if final_sl_dist > 0 else 0.0

        adjusted = len(adjustments) > 0 or aligned_sl != stop_loss or aligned_tp != take_profit

        return OptimizedBrackets(
            symbol=symbol,
            direction=dir_clean,
            entry_price=round(entry_price, decimals),
            stop_loss=aligned_sl,
            take_profit=aligned_tp,
            risk_distance=final_sl_dist,
            reward_distance=final_tp_dist,
            rr_ratio=round(final_rr, 2),
            adjusted=adjusted,
            adjustments=adjustments,
        )
