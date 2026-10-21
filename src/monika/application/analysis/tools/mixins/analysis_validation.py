# ==============================================================================
# File: application/analysis/tools/mixins/analysis_validation.py
# ==============================================================================

"""
Asset Analysis Structural & Risk Validation Mixin for ToolExecutor.
Encapsulates SMC proximity validation, TP structural targets, dynamic ATR fallbacks,
and error classification.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.mixins.base import _ToolExecutorMixinBase, logger
from monika.infrastructure.database.models import (
    FVGZone,
    LiquidityZone,
    OrderBlock,
    PriceOHLCV,
    SRZone,
    StructureBreak,
    SwingPoint,
    SystemConfig,
    TechnicalIndicator,
)


class AssetAnalysisValidationMixin(_ToolExecutorMixinBase):
    """Mixin providing structural and proximity validation for AssetAnalysis."""

    def _format_smc_data(self, zones_data: dict, current_price: Optional[float] = None) -> dict:
        """Helper to trim SMC data to save tokens, prioritized by proximity to current price."""
        formatted = {}
        for key in ["order_blocks", "fvg_zones", "liquidity_zones", "sr_zones"]:
            items = list(zones_data.get(key, []))
            if current_price and items:
                for item in items:
                    h = item.get("price_high") or item.get("zone_high") or item.get("gap_high") or item.get("high", 0.0)
                    l = item.get("price_low") or item.get("zone_low") or item.get("gap_low") or item.get("low", 0.0)
                    mid = (h + l) / 2.0 if (h and l) else (h or l or 0.0)
                    item["_dist"] = abs(mid - current_price) if mid else float("inf")
                items.sort(key=lambda x: x.get("_dist", float("inf")))

            trimmed = []
            for item in items[:3]:  # Max 3
                # Remove verbose fields
                trimmed_item = {
                    k: v
                    for k, v in item.items()
                    if k not in ("id", "symbol", "timeframe", "filled_at", "mitigated_at", "_dist")
                }
                trimmed.append(trimmed_item)
            formatted[key] = trimmed
        return formatted

    async def _get_precomputed_data(self, key: str) -> dict:
        cfg = (
            (
                await self.session.execute(
                    select(SystemConfig).where(
                        SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"])
                    )
                )
            )
            .scalars()
            .first()
        )
        if not cfg or not cfg.value:
            return {"error": "No pre-computed data available"}
        import json

        try:
            data = json.loads(cfg.value)
            return data.get(key, {})
        except Exception as e:
            return {"error": f"Failed to parse pre-computed data: {e}"}

    # Backward compatibility alias
    _get_gemini_precomputed = _get_precomputed_data

    async def _validate_smc_entry_proximity(
        self,
        symbol: str,
        entry_price: float,
        direction: str,
        stop_loss: float,
        atr: float,
        confluence_factors: Optional[list[str]] = None,
    ) -> list[str]:
        warnings = []
        if not entry_price or not atr or atr <= 0:
            return warnings

        # TIGHTENED: Use 0.5x ATR instead of 2.0x ATR
        # Entry should be WITHIN or at the boundary of an FVG/OB, not just "nearby"
        proximity_threshold = atr * 0.5

        fvgs = (
            (
                await self.session.execute(
                    select(FVGZone)
                    .where(FVGZone.symbol == symbol)
                    .where(FVGZone.timeframe.in_(["H1", "H4"]))
                    .where(FVGZone.filled_at.is_(None))
                    .order_by(FVGZone.formed_at.desc())
                    .limit(15)
                )
            )
            .scalars()
            .all()
        )

        near_fvg = False
        inside_fvg = False
        for fvg in fvgs:
            # Check if entry is INSIDE the FVG (ideal)
            if fvg.gap_low <= entry_price <= fvg.gap_high:
                inside_fvg = True
                near_fvg = True
                break
            # Check if entry is within 0.5 ATR of FVG boundary
            fvg_mid = (fvg.gap_high + fvg.gap_low) / 2
            if abs(entry_price - fvg_mid) <= proximity_threshold:
                near_fvg = True
                break

        obs = (
            (
                await self.session.execute(
                    select(OrderBlock)
                    .where(OrderBlock.symbol == symbol)
                    .where(OrderBlock.timeframe.in_(["H1", "H4"]))
                    .where(OrderBlock.mitigated_at.is_(None))
                    .order_by(OrderBlock.formed_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

        near_ob = False
        inside_ob = False
        for ob in obs:
            # Check if entry is INSIDE the OB (ideal)
            if ob.price_low <= entry_price <= ob.price_high:
                inside_ob = True
                near_ob = True
                break
            ob_mid = (ob.price_high + ob.price_low) / 2
            if abs(entry_price - ob_mid) <= proximity_threshold:
                near_ob = True
                break

        is_breakout = bool(
            confluence_factors
            and any(
                f in confluence_factors
                for f in ("breakout_expansion", "volume_expansion", "trend_continuation", "momentum_expansion")
            )
        )
        if not near_fvg and not near_ob:
            if is_breakout:
                matched_factors = [
                    f
                    for f in (confluence_factors or [])
                    if f in ("breakout_expansion", "volume_expansion", "trend_continuation", "momentum_expansion")
                ]
                warnings.append(
                    f"BREAKOUT EXPANSION NOTE: Entry {entry_price:.5f} is an active momentum/breakout setup "
                    f"(confirmed by {matched_factors}). Evaluated on expansion criteria rather than pullback zone."
                )
            else:
                warnings.append(
                    f"SMC PROXIMITY FAIL: Entry {entry_price:.5f} is NOT within 0.5×ATR ({proximity_threshold:.5f}) of any active H1/H4 FVG or Order Block. "
                    f'Entry appears to be "chasing" price rather than waiting for pullback to institutional zone. '
                    f"Consider WAIT until price returns to a zone."
                )
        elif not inside_fvg and not inside_ob and (near_fvg or near_ob):
            warnings.append(
                f"SMC PROXIMITY NOTE: Entry is near but not inside an FVG/OB zone. "
                f"Ideal entry would be within the zone boundary itself. Confidence slightly reduced."
            )

        # SL validation remains the same
        if direction == "buy":
            swing_lows = (
                (
                    await self.session.execute(
                        select(SwingPoint)
                        .where(SwingPoint.symbol == symbol)
                        .where(SwingPoint.timeframe.in_(["H1", "H4"]))
                        .where(SwingPoint.type == "low")
                        .where(SwingPoint.price <= entry_price)
                        .order_by(SwingPoint.price.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            sl_beyond_swing = any(sl.price >= stop_loss for sl in swing_lows) if swing_lows else True
        else:
            swing_highs = (
                (
                    await self.session.execute(
                        select(SwingPoint)
                        .where(SwingPoint.symbol == symbol)
                        .where(SwingPoint.timeframe.in_(["H1", "H4"]))
                        .where(SwingPoint.type == "high")
                        .where(SwingPoint.price >= entry_price)
                        .order_by(SwingPoint.price.asc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            sl_beyond_swing = any(sh.price <= stop_loss for sh in swing_highs) if swing_highs else True

        if not sl_beyond_swing:
            warnings.append(
                f"SL STRUCTURE FAIL: Stop loss {stop_loss:.5f} does not appear to be BEYOND a significant swing point. "
                f"SL must be placed on the other side of a structural level to be valid."
            )

        return warnings

    async def _validate_tp_structural_target(
        self,
        symbol: str,
        direction: str,
        tp_price: Optional[float],
        atr: Optional[float],
        adr_ctx: Optional[dict] = None,
    ) -> list[str]:
        """TP must anchor to a real structural target (SR/FVG/OB/swing/liquidity/round-number)
        AND fall inside the ADR band — mathematical band membership alone is insufficient."""
        errors = []
        if not tp_price or not atr or atr <= 0:
            return errors
        tol_mult = self.settings.get("trading", {}).get("risk", {}).get("structural_snap_tolerance_atr_mult", 0.4)
        tolerance = atr * tol_mult
        found, basis = (False, "")

        sr_zones = (
            (
                await self.session.execute(
                    select(SRZone).where(SRZone.symbol == symbol).where(SRZone.timeframe.in_(["H4", "D1"]))
                )
            )
            .scalars()
            .all()
        )
        for sr in sr_zones:
            if sr.price_low - tolerance <= tp_price <= sr.price_high + tolerance:
                found, basis = True, f"SR zone {sr.price_low:.5f}-{sr.price_high:.5f}"
                break
        if not found:
            fvgs = (
                (
                    await self.session.execute(
                        select(FVGZone)
                        .where(FVGZone.symbol == symbol)
                        .where(FVGZone.timeframe.in_(["H1", "H4"]))
                        .where(FVGZone.filled_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for fvg in fvgs:
                edge = fvg.gap_low if direction == "sell" else fvg.gap_high
                if abs(tp_price - edge) <= tolerance:
                    found, basis = True, f"{fvg.direction} FVG edge {edge:.5f}"
                    break
        if not found:
            obs = (
                (
                    await self.session.execute(
                        select(OrderBlock)
                        .where(OrderBlock.symbol == symbol)
                        .where(OrderBlock.timeframe.in_(["H1", "H4"]))
                        .where(OrderBlock.mitigated_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for ob in obs:
                edge = ob.price_low if direction == "sell" else ob.price_high
                if abs(tp_price - edge) <= tolerance:
                    found, basis = True, f"{ob.direction} OB edge {edge:.5f}"
                    break
        if not found:
            swings = (
                (
                    await self.session.execute(
                        select(SwingPoint)
                        .where(SwingPoint.symbol == symbol)
                        .where(SwingPoint.timeframe.in_(["H1", "H4"]))
                        .order_by(SwingPoint.timestamp.desc())
                        .limit(15)
                    )
                )
                .scalars()
                .all()
            )
            for sw in swings:
                if abs(tp_price - sw.price) <= tolerance:
                    found, basis = True, f"swing {sw.type} @ {sw.price:.5f}"
                    break
        if not found:
            liqs = (
                (
                    await self.session.execute(
                        select(LiquidityZone)
                        .where(LiquidityZone.symbol == symbol)
                        .where(LiquidityZone.timeframe.in_(["H1", "H4"]))
                    )
                )
                .scalars()
                .all()
            )
            for lz in liqs:
                if lz.zone_low - tolerance <= tp_price <= lz.zone_high + tolerance:
                    found, basis = True, f"liquidity zone {lz.type}"
                    break
        if not found:
            round_increments = {
                "XAUUSD": 10.0,
                "XTIUSD": 1.0,
                "XBRUSD": 1.0,
                "BTCUSD": 1000.0,
                "USDJPY": 0.20,
                "EURUSD": 0.0050,
                "GBPUSD": 0.0050,
                "AUDUSD": 0.0050,
                "USDCAD": 0.0050,
                "USDCHF": 0.0050,
                "NZDUSD": 0.0050,
            }
            incr = round_increments.get(symbol)
            if incr:
                nearest = round(tp_price / incr) * incr
                if abs(tp_price - nearest) <= tolerance:
                    found, basis = True, f"round number {nearest:.5f}"

        if not found and adr_ctx:
            min_dist = float(adr_ctx.get("target_tp_min_distance", 0) or 0)
            max_dist = float(adr_ctx.get("target_tp_max_distance", 0) or 0)
            tol = float(adr_ctx.get("band_tolerance_pct", 0.15) or 0.15)
            if min_dist > 0 and max_dist > 0:
                found, basis = (
                    True,
                    f"ADR expansion target band [{min_dist * (1 - tol):.5f}, {max_dist * (1 + tol):.5f}]",
                )

        if not found:
            adr_info = adr_ctx or {}
            min_dist = float(adr_info.get("target_tp_min_distance", 0) or 0)
            max_dist = float(adr_info.get("target_tp_max_distance", 0) or 0)
            adr_band_str = (
                f"inside the ADR band [{min_dist:.5f}, {max_dist:.5f}]" if adr_ctx else "matching market structure"
            )
            errors.append(
                f"TP STRUCTURAL MAPPING FAIL: take_profit={tp_price:.5f} is not within {tolerance:.5f} "
                f"({tol_mult}x ATR) of any known SR/FVG/OB/swing/liquidity/round-number target {adr_band_str}. "
                f"Call get_optimal_intraday_levels to find a validated structural TP, or submit WAIT."
            )
        else:
            logger.debug(f"[{symbol}] TP structural mapping OK: {basis}")
        return errors

    async def _get_dynamic_atr_fallback(self, symbol: str) -> Optional[float]:
        """
        ATR fallback yang market-aware, bukan hardcoded.
        Priority: 30d avg > recent range-based estimate > hardcoded minimum
        """
        try:
            # Method 1: 30-day average ATR (existing, tapi improved)
            rows = (
                (
                    await self.session.execute(
                        select(TechnicalIndicator.value_json)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == "H4")
                        .where(TechnicalIndicator.indicator_name == "ATR_14")
                        .where(TechnicalIndicator.timestamp >= clock.now() - timedelta(days=30))
                        .where(TechnicalIndicator.timestamp <= clock.now())
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(30)  # Kurangi limit, cukup 30 bars
                    )
                )
                .scalars()
                .all()
            )

            if len(rows) >= 5:  # Minimum 5 data points untuk average yang valid
                values = []
                for row in rows:
                    try:
                        import json

                        v = json.loads(row)
                        atr = v.get("atr", v.get("value")) if isinstance(v, dict) else float(v)
                        if atr and 0 < atr < 1000:  # Sanity check
                            values.append(float(atr))
                    except Exception:
                        pass

                if values:
                    # Gunakan median, bukan mean, untuk robustness terhadap outlier
                    values.sort()
                    median_atr = values[len(values) // 2]
                    return round(median_atr, 5)

            # Method 2: Recent candle range estimate
            last_bars = (
                (
                    await self.session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timeframe == "H4")
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(14)
                    )
                )
                .scalars()
                .all()
            )

            if len(last_bars) >= 5:
                ranges = [abs(b.high - b.low) for b in last_bars]
                return round(sum(ranges) / len(ranges), 5)

            # Method 3: Dynamic minimum berdasarkan current price (tidak hardcoded)
            last_bar = last_bars[0] if last_bars else None
            if last_bar and last_bar.close:
                price = last_bar.close
                # ATR minimum biasanya 0.1-0.3% dari price untuk liquid instruments
                SYMBOL_MIN_ATR_PCT = {
                    "XAUUSD": 0.003,  # 0.3% - $6+ pada harga $2000
                    "BTCUSD": 0.015,  # 1.5%
                    "EURUSD": 0.0005,  # 5 pips
                    "GBPUSD": 0.0006,
                    "USDJPY": 0.004,
                    "AUDUSD": 0.0004,
                    "XTIUSD": 0.005,  # 0.5%
                }
                pct = SYMBOL_MIN_ATR_PCT.get(symbol, 0.001)
                return round(price * pct, 5)

            return None

        except Exception as e:
            logger.debug(f"Dynamic ATR fallback failed for {symbol}: {e}")
            return None

    @staticmethod
    def _classify_validation_errors(errs: list[str]) -> str:
        """Classify submit_asset_analysis validation errors into GATE, GATE_FIXABLE, STRUCTURAL, THRESHOLD, or FATAL."""
        GATE_FATAL_ERRORS = [
            "macro bias gate",
            "entry blocked: only",
            "adr range remains",
            "priced-in conflict hard blocked",
            "context discrepancy score",
        ]

        GATE_FIXABLE_ERRORS = [
            "volatility regime gate",
            "volatility squeeze",
            "price inside value area",
            "liquidity sweep",
            "priced-in conflict (reverse)",
        ]

        FATAL_ERRORS = [
            "no h4 technical indicators found",
            "technical indicators found",
            "stale — mt5 may be disconnected",
            "data unavailable",
            "symbol is required",
            "direction must be",
        ]

        THRESHOLD_ERRORS = [
            "confluence_score",
            "priced_in_score",
            "adaptive threshold",
            "below the required threshold",
            "score insufficient",
            "score uplift",
        ]

        STRUCTURAL_ERRORS = [
            "stop_loss",
            "take_profit",
            "tp structural mapping",
            "structural",
            "r:r ratio",
            "risk-to-reward",
            "risk is zero",
            "sl distance",
            "tp distance",
            "tp too",
            "sl too",
            "limit entry price",
            "entry_condition",
            "entry_price",
            "invalidation",
            "invalid confluence_factors",
            "fundamental_bias",
            "cot_aligned",
            "vix_ok",
            "adjudication",
            "specialist disagreement",
            "reevaluation_trigger",
        ]

        for err in errs:
            err_l = err.lower()
            for g_fatal in GATE_FATAL_ERRORS:
                if g_fatal in err_l:
                    return "GATE"
        for err in errs:
            err_l = err.lower()
            for g_fix in GATE_FIXABLE_ERRORS:
                if g_fix in err_l:
                    return "GATE_FIXABLE"
        for err in errs:
            err_l = err.lower()
            for fatal in FATAL_ERRORS:
                if fatal in err_l:
                    return "FATAL"
        for err in errs:
            err_l = err.lower()
            for threshold in THRESHOLD_ERRORS:
                if threshold in err_l:
                    return "THRESHOLD"
        for err in errs:
            err_l = err.lower()
            for structural in STRUCTURAL_ERRORS:
                if structural in err_l:
                    return "STRUCTURAL"
        return "STRUCTURAL"

    async def _validate_manual_order_structural(
        self,
        symbol: str,
        direction: str,
        entry_price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> list[str]:
        """
        Lightweight structural validation specifically for manual orders via Telegram chat.
        Checks:
        1. Required fields: symbol, direction, entry_price, stop_loss, take_profit
        2. Valid direction ('buy', 'sell')
        3. Price alignment:
           - For BUY: stop_loss < entry_price < take_profit
           - For SELL: take_profit < entry_price < stop_loss
        4. Minimum Risk-to-Reward ratio (default >= 1.3)
        5. ADR Band check: Take profit distance <= 80% ADR
        """
        errors = []
        if not symbol:
            errors.append("symbol is required")
        if direction not in ("buy", "sell"):
            errors.append(f"direction must be 'buy' or 'sell', got '{direction}'")
        if entry_price is None or entry_price <= 0:
            errors.append("entry_price must be a positive number")
        if stop_loss is None or stop_loss <= 0:
            errors.append("stop_loss must be a positive number")
        if take_profit is None or take_profit <= 0:
            errors.append("take_profit must be a positive number")

        if errors or entry_price is None or stop_loss is None or take_profit is None:
            return errors

        # Price alignment & R:R
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)

        if direction == "buy":
            if stop_loss >= entry_price:
                errors.append(f"For BUY, stop_loss ({stop_loss}) must be BELOW entry_price ({entry_price})")
            if take_profit <= entry_price:
                errors.append(f"For BUY, take_profit ({take_profit}) must be ABOVE entry_price ({entry_price})")
        elif direction == "sell":
            if stop_loss <= entry_price:
                errors.append(f"For SELL, stop_loss ({stop_loss}) must be ABOVE entry_price ({entry_price})")
            if take_profit >= entry_price:
                errors.append(f"For SELL, take_profit ({take_profit}) must be BELOW entry_price ({entry_price})")

        min_rr = self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5)
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio < min_rr:
                errors.append(f"Risk-to-Reward ratio {rr_ratio:.2f} is below minimum required {min_rr:.2f}")
        else:
            errors.append("Risk is zero (entry equals stop_loss)")

        # ADR Band check (TP distance <= 80% ADR)
        try:
            adr_res = await self.execute("get_adr", {"symbol": symbol, "lookback_days": 20})
            adr_val = adr_res.get("adr_20") or adr_res.get("adr")
            if adr_val and float(adr_val) > 0:
                max_tp_dist = float(adr_val) * 0.80
                if reward > max_tp_dist:
                    errors.append(
                        f"Take profit distance ({reward:.5f}) exceeds 80% of 20-day ADR ({max_tp_dist:.5f}). "
                        f"Intraday range strategy requires TP to stay within achievable daily range."
                    )
        except Exception as adr_err:
            logger.debug(f"ADR check in manual order validation failed (non-fatal): {adr_err}")

        return errors
