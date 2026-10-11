# ==============================================================================
# File: graph/nodes/risk/level_synthesizer.py
# Monika Order Level Synthesis & Geometry Repair Engine
# ==============================================================================

"""
Order level synthesizer and invariant geometry validator.
Resolves entry price from multiple price sources and derives institutional
stop loss and take profit levels using structural levels and ATR fallback.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.Graph.Risk.LevelSynthesizer")


def _safe_num(val: Any, default: float = 0.0) -> float:
    """Sanitizes numerical inputs, stripping currency symbols and handling mocks/NaNs."""
    if val is None or hasattr(val, "_mock_name") or hasattr(val, "_mock_return_value"):
        return default
    try:
        if isinstance(val, str):
            val = re.sub(r'[$€£¥,]', '', val).strip()
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


async def resolve_and_repair_levels(
    session: Any,
    scheduler: Any,
    symbol: str,
    r: Dict[str, Any],
    ana: Any = None,
    state_asset_analyses: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, float]:
    """
    Single-pass level resolution and geometry repair.
    Resolves entry_price, validates BUY/SELL geometry, computes optimal levels,
    and falls back to ATR percentage heuristics if necessary.
    Synchronizes results back into `r` dictionary and `ana` DB record.
    """
    from database.models import PriceOHLCV
    from sqlalchemy import select

    dec_u = str(r.get("decision", "")).upper()
    entry_p = _safe_num(r.get("entry_price"))

    # 1. Resolve entry_price if missing
    if entry_p <= 0.0 and ana:
        entry_p = _safe_num(getattr(ana, "entry_price", None))
        if entry_p <= 0.0 and getattr(ana, "entry_zone", None) and not hasattr(ana.entry_zone, "_mock_name"):
            try:
                ez = json.loads(ana.entry_zone) if isinstance(ana.entry_zone, str) else ana.entry_zone
                if isinstance(ez, dict):
                    entry_p = _safe_num(ez.get("price"))
            except Exception:
                pass
        if entry_p <= 0.0:
            entry_p = _safe_num(getattr(ana, "price_at_analysis", None))

    if entry_p <= 0.0 and state_asset_analyses and isinstance(state_asset_analyses.get(symbol), dict):
        raw_aa = state_asset_analyses[symbol]
        entry_p = _safe_num(raw_aa.get("entry_price"))

    if entry_p <= 0.0 and hasattr(scheduler, "mt5") and scheduler.mt5:
        try:
            info = await scheduler.mt5.get_symbol_info(symbol)
            if isinstance(info, dict):
                entry_p = _safe_num(info.get("ask" if dec_u == "BUY" else "bid") or info.get("price"))
        except Exception:
            pass

    if entry_p <= 0.0:
        try:
            bar_close = (await session.execute(
                select(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol).order_by(PriceOHLCV.timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            if bar_close and float(bar_close) > 0.0:
                entry_p = float(bar_close)
        except Exception:
            pass

    if entry_p > 0.0:
        r["entry_price"] = entry_p

    # 2. Resolve SL and TP if missing or geometrically invalid
    sl_p = _safe_num(r.get("stop_loss"))
    if sl_p <= 0.0 and ana:
        sl_p = _safe_num(getattr(ana, "stop_loss", None))
    tp_p = _safe_num(r.get("take_profit"))
    if tp_p <= 0.0 and ana:
        tp_p = _safe_num(getattr(ana, "take_profit", None))

    if sl_p > 0.0:
        r["stop_loss"] = sl_p
    if tp_p > 0.0:
        r["take_profit"] = tp_p

    levels_invalid = (
        sl_p <= 0.0 or tp_p <= 0.0
        or (dec_u == "BUY" and (sl_p >= entry_p or tp_p <= entry_p))
        or (dec_u == "SELL" and (sl_p <= entry_p or tp_p >= entry_p))
    )

    if levels_invalid and entry_p > 0.0:
        # Try IntradayLevelOptimizer first
        try:
            from analysis.calculators.intraday_level_optimizer import compute_optimal_levels
            calc_res = await compute_optimal_levels(
                session=session,
                symbol=symbol,
                direction=dec_u.lower(),
                entry_price=entry_p,
                settings=scheduler.settings,
                existing_sl=sl_p if sl_p > 0.0 else None,
                existing_tp=tp_p if tp_p > 0.0 else None,
            )
            if calc_res:
                top_sl = calc_res.get("top_sl_candidates")
                top_tp = calc_res.get("top_tp_candidates")
                if top_sl and (sl_p <= 0.0 or (dec_u == "BUY" and sl_p >= entry_p) or (dec_u == "SELL" and sl_p <= entry_p)):
                    sl_p = float(top_sl[0]["price"])
                    r["stop_loss"] = sl_p
                if top_tp and (tp_p <= 0.0 or (dec_u == "BUY" and tp_p <= entry_p) or (dec_u == "SELL" and tp_p >= entry_p)):
                    tp_p = float(top_tp[0]["price"])
                    r["take_profit"] = tp_p
                logger.info(f"[LevelSynthesizer] Computed structural levels for arbitrated {symbol} ({dec_u}): SL={sl_p}, TP={tp_p}")
        except Exception as opt_err:
            logger.debug(f"[LevelSynthesizer] Level optimizer failed for {symbol}: {opt_err}")

        # Fallback to ATR-based calculation if structural calculation failed or levels still invalid
        if (
            sl_p <= 0.0 or tp_p <= 0.0
            or (dec_u == "BUY" and (sl_p >= entry_p or tp_p <= entry_p))
            or (dec_u == "SELL" and (sl_p <= entry_p or tp_p >= entry_p))
        ):
            atr_val = _safe_num(r.get("atr") or r.get("atr_14"))
            if atr_val <= 0.0 and ana and getattr(ana, "indicators", None) and not hasattr(ana.indicators, "_mock_name"):
                try:
                    inds = json.loads(ana.indicators) if isinstance(ana.indicators, str) else ana.indicators
                    if isinstance(inds, dict):
                        atr_val = _safe_num(inds.get("atr_14") or inds.get("atr") or inds.get("ATR"))
                except Exception:
                    pass
            if atr_val <= 0.0:
                sym_u = symbol.upper()
                if "BTC" in sym_u or "ETH" in sym_u or "CRYPTO" in sym_u:
                    atr_val = entry_p * 0.02
                elif "XAU" in sym_u or "OIL" in sym_u or "XTI" in sym_u or "XBR" in sym_u:
                    atr_val = entry_p * 0.01
                else:
                    atr_val = entry_p * 0.005

            if dec_u == "BUY":
                sl_p = round(max(0.0001, entry_p - (1.5 * atr_val)), 5)
                tp_p = round(entry_p + (3.0 * atr_val), 5)
            else:
                sl_p = round(entry_p + (1.5 * atr_val), 5)
                tp_p = round(max(0.0001, entry_p - (3.0 * atr_val)), 5)

            r["stop_loss"] = sl_p
            r["take_profit"] = tp_p
            logger.info(f"[LevelSynthesizer] Applied ATR fallback levels for {symbol} ({dec_u}): SL={sl_p}, TP={tp_p}")

    # Synchronize to ana if available
    if ana:
        if r.get("entry_price") is not None:
            ana.entry_price = r["entry_price"]
        if r.get("stop_loss") is not None:
            ana.stop_loss = r["stop_loss"]
        if r.get("take_profit") is not None:
            ana.take_profit = r["take_profit"]

    return entry_p, sl_p, tp_p
