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
    AssetAnalysis,
    COTReport,
    FundamentalBrief,
    RiskState,
    TradeTrigger,
    UserMarketIntel,
    VIXData,
)
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
                    f"SMC PROXIMITY FAIL: Entry {entry_price:.5f} is NOT within 0.5Ã—ATR ({proximity_threshold:.5f}) of any active H1/H4 FVG or Order Block. "
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
        AND fall inside the ADR band â€” mathematical band membership alone is insufficient."""
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

    async def _cross_validate_priced_in(
        self,
        symbol: str,
        decision: str,
        rationale: str,
        inp: dict,
        errors: list[str],
        brief_row: Any,
    ) -> tuple[str, Any]:
        """Cross-validate priced-in score with Stage 1 brief."""
        try:
            if not brief_row:
                brief_row = (
                    await self.session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()

            if brief_row and brief_row.structured_json:
                import json as _j

                brief_data = _j.loads(brief_row.structured_json)
                brief_priced_in = brief_data.get("priced_in_assessment", {})
                brief_pi_score = brief_priced_in.get("priced_in_score") if brief_priced_in else None
                asset_pi_map = brief_data.get("asset_priced_in_scores", {})
                if isinstance(asset_pi_map, dict) and symbol in asset_pi_map and asset_pi_map[symbol] is not None:
                    brief_pi_score = asset_pi_map[symbol]

                submitted_pi = inp.get("priced_in_score")

                if brief_pi_score is not None and submitted_pi is not None:
                    priced_in_override = inp.get("priced_in_override_justification")

                    # Check: Stage 2 asset score is significantly higher than Stage 1 macro score
                    if submitted_pi >= 8 and brief_pi_score <= 4 and decision in ("buy", "sell"):
                        if not (
                            isinstance(priced_in_override, dict)
                            and all(
                                priced_in_override.get(k)
                                for k in ["override_reason", "why_stage1_wrong", "post_event_evidence"]
                            )
                        ):
                            errors.append(
                                f"PRICED-IN CONFLICT (REVERSE): Your asset-specific score={submitted_pi} "
                                f"contradicts Stage 1 macro score={brief_pi_score}. "
                                f"Stage 1 says market not priced in, but you say asset is fully priced in. "
                                f"Provide priced_in_override_justification with all 3 required fields, "
                                f"or align your assessment with macro context."
                            )

                    if brief_pi_score >= 8 and submitted_pi <= 4 and decision in ("buy", "sell"):
                        if isinstance(priced_in_override, dict) and all(
                            priced_in_override.get(k)
                            for k in ["override_reason", "why_stage1_wrong", "post_event_evidence"]
                        ):
                            # Override accepted - log for audit trail
                            rationale = (
                                rationale
                                + f"\n\n[SYSTEM: Priced-in override accepted with explicit justification: {_j.dumps(priced_in_override)}]"
                            )
                        else:
                            errors.append(
                                f"PRICED-IN CONFLICT HARD BLOCKED: Stage 1 priced_in_score={brief_pi_score}. To override, you must fill priced_in_override_justification with all 3 required fields. Keyword-based justification in rationale is NOT accepted."
                            )

                    # IMP-6 / Fix: Allow gap tolerance of 2 if explicitly justified in rationale
                    elif abs(brief_pi_score - submitted_pi) >= 2 and decision in ("buy", "sell"):
                        gap = abs(brief_pi_score - submitted_pi)
                        rat_lower = (rationale or "").lower()
                        has_rationale_justification = any(
                            k in rat_lower
                            for k in [
                                "priced-in gap justification",
                                "priced_in",
                                "priced in",
                                "justification for",
                                "macro divergence",
                                "stage 1",
                                "idiosyncratic",
                                "independent justification",
                                "discount",
                                "premium",
                                "technical",
                                "structure",
                                "order block",
                                "fvg",
                            ]
                        )
                        if gap == 2 and has_rationale_justification:
                            rationale = (
                                rationale
                                + f"\n\n[SYSTEM: Priced-in gap ({gap}) acknowledged and accepted based on rationale context.]"
                            )
                        elif gap >= 3 and isinstance(priced_in_override, dict) and any(priced_in_override.values()):
                            rationale = (
                                rationale
                                + f"\n\n[SYSTEM: Priced-in gap ({gap}) accepted with override: {_j.dumps(priced_in_override)}]"
                            )
                        elif gap >= 2 and not has_rationale_justification:
                            direction_of_conflict = (
                                "underestimating" if submitted_pi < brief_pi_score else "overestimating"
                            )
                            errors.append(
                                f"PRICED-IN ASSESSMENT CONFLICT: Stage 1 macro assessment={brief_pi_score}/10, "
                                f"your asset-specific assessment={submitted_pi}/10 (gap={gap}). "
                                f"You appear to be {direction_of_conflict} priced-in risk. "
                                f"Either explicitly justify this gap in rationale, or re-evaluate your score. "
                                f"Unresolved 2+ point gaps suggest analysis inconsistency."
                            )

                    # IMP-6: Mid-range 5-7 now a THRESHOLD warning (not just a note)
                    elif 5 <= submitted_pi <= 7 and decision in ("buy", "sell"):
                        rationale = rationale + (
                            f"\n\n[SYSTEM: Mid-range priced-in score ({submitted_pi}/10) detected. "
                            f"If major event occurs within 12h and result meets expectations, "
                            f"consider immediate re-evaluation for potential counter-trend opportunity.]"
                        )

                    # IMP-6: High score (8+) without override should force 'wait'
                    if submitted_pi >= 8 and decision in ("buy", "sell") and not priced_in_override:
                        errors.append(
                            f"PRICED-IN HIGH SCORE BLOCK: Asset priced_in_score={submitted_pi}/10 >= 8. "
                            f"Must use priced_in_override_justification to proceed with buy/sell, "
                            f"or set decision to wait."
                        )
        except Exception as e:
            logger.debug(f"Stage 1/2 priced-in cross-validation failed (non-fatal): {e}")

        return rationale, brief_row

    async def _cross_validate_directional_coherence(
        self,
        symbol: str,
        decision: str,
        rationale: str,
        inp: dict,
        errors: list[str],
        brief_row: Any,
    ) -> str:
        """Cross-validate trade directional coherence against Stage 1 macro brief."""
        if decision not in ("buy", "sell"):
            return rationale

        try:
            import json as _json

            from monika.application.protocol.context_coherence import SYMBOL_CURRENCY_MAP
            from monika.domain.market.bias_utils import normalize_bias

            pair_info = SYMBOL_CURRENCY_MAP.get(symbol)

            # Retrieve brief if not already retrieved
            if not brief_row:
                brief_row = (
                    await self.session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()

            if pair_info and brief_row and brief_row.structured_json:
                _b_data = _json.loads(brief_row.structured_json)
                _currency_bias = _b_data.get("currency_bias", {})
                base_curr = pair_info["base"]
                quote_curr = pair_info["quote"]
                base_bias = normalize_bias(_currency_bias.get(base_curr, "neutral"))
                quote_bias = normalize_bias(_currency_bias.get(quote_curr, "neutral"))

                # 1. Base & Quote Directional Coherence Check (with per_asset_macro_matrix priority)
                contradictions = []
                matrix = _b_data.get("per_asset_macro_matrix", {})
                clean_sym = symbol.upper().replace("/", "")
                asset_ctx = matrix.get(clean_sym) or matrix.get(symbol.upper())
                asset_bias = ""
                asset_conf = 0.5
                if isinstance(asset_ctx, dict):
                    asset_bias = normalize_bias(asset_ctx.get("directional_bias", "neutral"))
                    try:
                        asset_conf = float(asset_ctx.get("confidence", 0.70))
                    except ValueError, TypeError:
                        asset_conf = 0.70

                if asset_bias and asset_bias != "neutral":
                    if decision == "buy" and asset_bias == "bearish":
                        contradictions.append(f"{symbol}='{asset_bias}' (matrix)")
                    elif decision == "sell" and asset_bias == "bullish":
                        contradictions.append(f"{symbol}='{asset_bias}' (matrix)")
                else:
                    if decision == "buy":
                        if base_bias == "bearish":
                            contradictions.append(f"{base_curr}='{base_bias}'")
                        if quote_bias == "bullish":
                            contradictions.append(f"{quote_curr}='{quote_bias}'")
                    elif decision == "sell":
                        if base_bias == "bullish":
                            contradictions.append(f"{base_curr}='{base_bias}'")
                        if quote_bias == "bearish":
                            contradictions.append(f"{quote_curr}='{quote_bias}'")

                _reconciliation_keywords = [
                    "trust price action",
                    "trust brief",
                    "trust the brief",
                    "trust macro",
                    "contradicts brief",
                    "despite brief",
                    "brief is stale",
                    "overriding brief",
                    "post-event",
                    "brief may be wrong",
                    "narrative shift",
                    "technical overrides macro",
                    "price action contradicts",
                    "macro-technical conflict",
                    "brief conflict",
                    "coherence warning",
                    "divergence closed",
                    "pre-event positioning",
                    "divergence",
                    "ssvp",
                    "discrepancy",
                    "unresolved",
                ]

                if contradictions:
                    contra_str = ", ".join(contradictions)
                    conf_map = _b_data.get("currency_confidence", {})
                    base_conf = float(conf_map.get(base_curr, 0.5)) if isinstance(conf_map, dict) else 0.5
                    quote_conf = float(conf_map.get(quote_curr, 0.5)) if isinstance(conf_map, dict) else 0.5
                    relevant_conf = max(
                        base_conf if any(base_curr in c for c in contradictions) else 0.0,
                        quote_conf if any(quote_curr in c for c in contradictions) else 0.0,
                        asset_conf if any(symbol in c for c in contradictions) else 0.0,
                    )

                    spec_adj = inp.get("specialist_adjudication")
                    has_valid_adjudication = False
                    if isinstance(spec_adj, dict):
                        has_valid_adjudication = (
                            bool(spec_adj.get("conflict_detected"))
                            and spec_adj.get("resolution_path")
                            in ("override_macro", "cancel_setup", "hedged_entry", "scale_out")
                            and len(str(spec_adj.get("resolution_justification") or "").strip()) >= 15
                        )

                    if relevant_conf >= 0.55 and not has_valid_adjudication:
                        errors.append(
                            f"CONTRA_MACRO_HARD_REJECT: Decision {decision.upper()} for {symbol} directly "
                            f"opposes Stage 1 macro bias ({contra_str}) with conviction ({relevant_conf:.2f} >= 0.55). "
                            f"Trading against the macro bias is prohibited unless you complete the 'specialist_adjudication' object "
                            f"(conflict_detected=true, resolution_path in ('override_macro', 'cancel_setup', 'hedged_entry', 'scale_out'), "
                            f"and provide structural level invalidation justification >= 15 characters)."
                        )
                    else:
                        _rationale_lower = (rationale or "").lower()
                        _has_reconciliation = (
                            any(kw in _rationale_lower for kw in _reconciliation_keywords) or has_valid_adjudication
                        )

                        if not _has_reconciliation:
                            logger.warning(
                                f"[{symbol}] DIRECTIONAL COHERENCE FLAG: "
                                f"{decision.upper()} submitted but Stage 1 brief indicates {contra_str}. "
                                f"No explicit reconciliation found in rationale. Appending coherence flag."
                            )
                            rationale = rationale + (
                                f"\n\n[SYSTEM COHERENCE FLAG: {decision.upper()} submitted "
                                f"despite Stage 1 brief indicating {contra_str}. "
                                f"This creates a macro-technical conflict. "
                                f"Human reviewer: verify that rationale above explicitly "
                                f"addresses WHY technical analysis overrides macro bias.]"
                            )
                            inp["rationale"] = rationale
        except Exception as _dcc_err:
            logger.debug(f"Directional coherence check failed (non-fatal): {_dcc_err}")

        return rationale

    async def _validate_ssvp_and_context_drift(
        self,
        symbol: str,
        decision: str,
        rationale: str,
        inp: dict,
        errors: list[str],
    ) -> tuple[Optional[str], Optional[float]]:
        """Validate Context Discrepancy Score (SSVP/CDS) against system thresholds."""
        if decision not in ("buy", "sell"):
            return None, None

        context_snapshot_id: Optional[str] = None
        context_cds_score: Optional[float] = None
        try:
            import json as _j

            from monika.application.protocol.context_snapshot import compute_context_snapshot_id

            context_snapshot_id, _ = await compute_context_snapshot_id(self.session)
            now_str = clock.now().strftime("%Y%m%d_%H")
            mon_key = f"context_drift_{symbol}_{now_str}"
            mon_cfg = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == mon_key))
            ).scalar_one_or_none()
            if mon_cfg and mon_cfg.value:
                mon_data = _j.loads(mon_cfg.value)
                context_cds_score = mon_data.get("cds_score")
                if context_cds_score is not None:
                    cds_block_threshold = (
                        self.settings.get("ssvp", {}).get("cds_thresholds", {}).get("block_buysell", 0.65)
                        if self.settings
                        else 0.65
                    )
                    cds_warn_threshold = (
                        self.settings.get("ssvp", {}).get("cds_thresholds", {}).get("warning", 0.35)
                        if self.settings
                        else 0.35
                    )
                    if context_cds_score >= cds_block_threshold:
                        errors.append(
                            f"SSVP BLOCKED: Context Discrepancy Score ({context_cds_score:.2f}) >= {cds_block_threshold:.2f}. "
                            f'You MUST submit a "wait" decision until context drift is resolved.'
                        )
                    elif context_cds_score >= cds_warn_threshold:
                        _rationale_lower = (rationale or "").lower()
                        adj_obj = inp.get("specialist_adjudication") or {}
                        adj_text = (
                            str(adj_obj.get("resolution_justification", ""))
                            + " "
                            + str(adj_obj.get("conflict_reason", ""))
                        ).lower()
                        combined_text = _rationale_lower + " " + adj_text
                        _has_substantive_adj = len(adj_text.strip()) >= 30 or (
                            len(_rationale_lower.strip()) >= 120
                            and any(
                                token in _rationale_lower
                                for token in (
                                    "price action",
                                    "structure",
                                    "discount",
                                    "premium",
                                    "order block",
                                    "absorption",
                                    "divergence",
                                    "fvg",
                                    "cvd",
                                    "brief",
                                    "specialist",
                                    "macro",
                                    "sentiment",
                                    "catalyst",
                                    "momentum",
                                    "trend",
                                    "reversal",
                                    "liquidity",
                                )
                            )
                        )
                        _reconciled = _has_substantive_adj or any(
                            kw in combined_text
                            for kw in [
                                "trust price action",
                                "trust brief",
                                "trust the brief",
                                "trust macro",
                                "divergence",
                                "pre-event positioning",
                                "ssvp",
                                "discrepancy",
                                "unresolved",
                                "contradicts brief",
                                "despite brief",
                                "overriding brief",
                                "technical overrides macro",
                                "override_macro",
                                "price action overrides",
                                "macro overrides",
                                "override",
                                "reconcile",
                                "adjudicat",
                            ]
                        )
                        if not _reconciled:
                            errors.append(
                                f"SSVP ADJUDICATION REQUIRED: CDS is {context_cds_score:.2f} (Warning Level >= {cds_warn_threshold:.2f}). "
                                f"You must explicitly acknowledge and adjudicate the conflicting context in your "
                                f'rationale (e.g. "I trust price action because..." or "I trust the brief because...") '
                                f"before submitting {decision.upper()}."
                            )
        except Exception as ssvp_err:
            logger.debug(f"SSVP data retrieval failed (non-fatal): {ssvp_err}")

        return context_snapshot_id, context_cds_score

    async def _resolve_adopted_bracket(self, inp: dict) -> bool:
        """Resolves adopted_bracket from pre-computed or dynamic bracket options."""
        adopted = inp.get("adopted_bracket")
        if not adopted and isinstance(inp.get("entry_condition"), dict):
            adopted = inp["entry_condition"].get("adopted_bracket")
        if not adopted:
            return False

        adopted_norm = str(adopted).strip().upper()
        inp["adopted_bracket"] = adopted_norm

        from monika.application.analysis.calculators.invariant_calculator import resolve_bracket_choice

        sym_lookup = str(inp.get("symbol") or getattr(self, "symbol", "") or "")
        inst_dict = getattr(self, "__dict__", {})
        bracket_opts = inst_dict.get("bracket_options")
        if not bracket_opts and sym_lookup:
            sym_map = getattr(self, "_symbol_bracket_options", None)
            if isinstance(sym_map, dict):
                bracket_opts = sym_map.get(sym_lookup)
        if not bracket_opts:
            bracket_opts = getattr(self, "bracket_options", None)
        if not bracket_opts:
            sess_state = getattr(self, "_session_state", None)
            if isinstance(sess_state, dict):
                bracket_opts = sess_state.get("bracket_options") or sess_state.get("brackets")
        resolved = resolve_bracket_choice(adopted_norm, bracket_opts)
        if not resolved and isinstance(bracket_opts, dict):
            cand = bracket_opts.get(adopted_norm) or bracket_opts.get(adopted_norm.lower())
            if isinstance(cand, dict):
                resolved = cand
        if not resolved and inp.get("symbol"):
            try:
                from monika.application.analysis.calculators.invariant_calculator import (
                    generate_concrete_bracket_options,
                )

                sym_c = str(inp.get("symbol") or "")
                last_px_val = None
                last_bar_c = (
                    await self.session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == sym_c)
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if last_bar_c:
                    last_px_val = float(last_bar_c.close)
                atr_r = (
                    await self.session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == sym_c)
                        .where(TechnicalIndicator.timeframe == "H4")
                        .where(TechnicalIndicator.indicator_name == "ATR_14")
                        .where(TechnicalIndicator.timestamp <= clock.now())
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                atr_raw_val = None
                if atr_r and atr_r.value_json:
                    import json as _jb_json

                    try:
                        parsed_atr = _jb_json.loads(atr_r.value_json)
                        if isinstance(parsed_atr, dict):
                            atr_raw_val = parsed_atr.get("atr", parsed_atr.get("value"))
                        elif isinstance(parsed_atr, (int, float)):
                            atr_raw_val = parsed_atr
                    except Exception:
                        pass
                atr_v = (
                    float(atr_raw_val)
                    if atr_raw_val is not None and float(atr_raw_val) > 0
                    else (last_px_val * 0.005 if last_px_val else 1.0)
                )
                if last_px_val and sym_c:
                    reg_c = (
                        inst_dict.get("regime_classification")
                        or getattr(self, "regime_classification", None)
                        or getattr(self, "market_regime", None)
                    )
                    imp_c = inst_dict.get("h4_impulse_atr") or getattr(self, "h4_impulse_atr", None)
                    bracket_opts = generate_concrete_bracket_options(
                        symbol=sym_c,
                        current_price=last_px_val,
                        atr=atr_v,
                        adr_5d=atr_v * 2.5,
                        regime_classification=str(reg_c) if reg_c else None,
                        h4_impulse_atr=float(imp_c) if imp_c is not None else None,
                    )
                    self.bracket_options = bracket_opts
                    resolved = resolve_bracket_choice(adopted_norm, bracket_opts)
            except Exception as _b_err:
                logger.debug(f"Dynamic bracket resolution notice: {_b_err}")

        if resolved:
            b_name = str(resolved.get("name") or adopted_norm).strip().upper()
            b_entry = resolved.get("entry")
            b_sl = resolved.get("stop_loss") if resolved.get("stop_loss") is not None else resolved.get("sl")
            b_tp = resolved.get("take_profit") if resolved.get("take_profit") is not None else resolved.get("tp")
            inp["decision"] = resolved.get(
                "direction",
                inp.get("decision", "buy" if "LONG" in b_name else "sell"),
            )
            if b_sl is not None:
                inp["stop_loss"] = b_sl
            if b_tp is not None:
                inp["take_profit"] = b_tp
            if not inp.get("entry_condition") or not isinstance(inp.get("entry_condition"), dict):
                inp["entry_condition"] = {
                    "type": resolved.get("entry_type", "market"),
                    "price": b_entry,
                    "detail": f"Adopted verified bracket {b_name}",
                    "adopted_bracket": b_name,
                }
            else:
                if b_entry is not None:
                    inp["entry_condition"]["price"] = b_entry
                if not inp["entry_condition"].get("type"):
                    inp["entry_condition"]["type"] = resolved.get("entry_type", "market")
                if not inp["entry_condition"].get("detail"):
                    inp["entry_condition"]["detail"] = f"Adopted verified bracket {b_name}"
                inp["entry_condition"]["adopted_bracket"] = b_name
            if not inp.get("invalidation_price") and b_sl is not None:
                inp["invalidation_price"] = b_sl
            if not inp.get("invalidation_direction"):
                inp["invalidation_direction"] = "below" if inp["decision"] == "buy" else "above"
            return True

        if isinstance(inp.get("entry_condition"), dict):
            inp["entry_condition"]["adopted_bracket"] = adopted_norm
        elif inp.get("entry_condition") is None and adopted_norm in ("LONG_OPTION_A", "SHORT_OPTION_B"):
            inp["entry_condition"] = {
                "type": "market",
                "price": inp.get("entry_price"),
                "detail": f"Adopted verified bracket {adopted_norm}",
                "adopted_bracket": adopted_norm,
            }
        return adopted_norm in ("LONG_OPTION_A", "SHORT_OPTION_B")

    async def _auto_verify_position_sizing(self, symbol: str, decision: str, inp: dict) -> None:
        """Auto-calculates verified position sizing on the fly if evidence is not yet recorded."""
        ledger = getattr(self, "verification_ledger", None)
        harness_obj = getattr(self, "_harness", None) or getattr(self, "harness", None)
        harness_ledger = getattr(harness_obj, "verification_ledger", None) if harness_obj is not None else None
        active_ledger = ledger or harness_ledger
        if active_ledger is None or active_ledger.has_passed_evidence(symbol):
            return

        raw_entry = (
            inp.get("entry_price")
            or inp.get("entry")
            or (inp.get("entry_condition", {}).get("price") if isinstance(inp.get("entry_condition"), dict) else None)
        )
        raw_sl = inp.get("stop_loss") or inp.get("sl")
        raw_tp = inp.get("take_profit") or inp.get("tp")
        if raw_sl is None:
            return

        try:
            from monika.domain.risk.position_sizing import calculate_lot_size

            entry_val = float(raw_entry) if raw_entry is not None else None
            if entry_val is None:
                last_bar = (
                    await self.session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if last_bar:
                    entry_val = float(last_bar.close)

            if entry_val is not None:
                sizing_res = await calculate_lot_size(
                    symbol=symbol,
                    entry_price=entry_val,
                    stop_loss=float(raw_sl),
                    direction=decision,
                    session=self.session,
                    settings=self.settings,
                )
                if sizing_res and sizing_res.get("is_valid", True):
                    payload_ev = {
                        "symbol": symbol,
                        "entry_price": entry_val,
                        "stop_loss": float(raw_sl),
                        "take_profit": float(raw_tp) if raw_tp is not None else None,
                        "lot_size": sizing_res.get("recommended_lots"),
                    }
                    active_ledger.record_tool_execution("calculate_position_size", payload_ev, sizing_res)
                    if harness_ledger is not None and harness_ledger is not active_ledger:
                        harness_ledger.record_tool_execution("calculate_position_size", payload_ev, sizing_res)
                    logger.info(
                        f"[{symbol}] submit_asset_analysis auto-calculated verified position size: "
                        f"Lots={sizing_res.get('recommended_lots')}, Risk=${sizing_res.get('risk_amount_usd')}"
                    )
        except Exception as auto_sz_err:
            logger.warning(f"[{symbol}] Auto-sizing in submit_asset_analysis non-fatal error: {auto_sz_err}")

    async def _enforce_specialist_and_threshold_checks(
        self, symbol: str, decision: str, rationale: str, inp: dict, errors: list[str]
    ) -> None:
        if decision in ("buy", "sell"):
            if not inp.get("confluence_score"):
                errors.append("Rejected: Missing confluence_score. Must be provided for actionable buy/sell decisions.")
            try:
                import json as _j2

                disagreement_key = f"specialist_disagreement_{symbol}"
                disagreement_cfg = (
                    await self.session.execute(select(SystemConfig).where(SystemConfig.key == disagreement_key))
                ).scalar_one_or_none()
                should_auto_adjudicate = False
                auto_reason_tag = "institutional structural verification"
                if disagreement_cfg and disagreement_cfg.value:
                    dd = _j2.loads(disagreement_cfg.value)
                    flagged_at = datetime.fromisoformat(dd["flagged_at"])
                    if flagged_at.tzinfo is None:
                        flagged_at = flagged_at.replace(tzinfo=timezone.utc)
                    if (clock.now() - flagged_at).total_seconds() < 900:
                        should_auto_adjudicate = True
                        auto_reason_tag = f"specialist split ({dd.get('biases')})"

                adopted_val = (
                    str(inp.get("adopted_bracket") or (inp.get("entry_condition") or {}).get("adopted_bracket") or "")
                    .strip()
                    .upper()
                )
                rat_zone_text = (str(rationale or "") + " " + str(inp.get("dealing_range_zone") or "")).lower()
                factors_list = inp.get("confluence_factors") or []
                if adopted_val in ("LONG_OPTION_A", "SHORT_OPTION_B"):
                    should_auto_adjudicate = True
                    auto_reason_tag = f"adopted pre-verified bracket {adopted_val}"
                elif (
                    "uncrowded_institutional_synergy" in factors_list
                    or "uncrowded_institutional_synergy" in rat_zone_text
                ):
                    should_auto_adjudicate = True
                    auto_reason_tag = "Uncrowded Institutional Synergy (Tech == Macro)"
                elif (
                    decision == "buy"
                    and ("discount_accumulation_zone" in rat_zone_text or "accumulation zone" in rat_zone_text)
                ) or (
                    decision == "sell"
                    and ("premium_distribution_zone" in rat_zone_text or "distribution zone" in rat_zone_text)
                ):
                    should_auto_adjudicate = True
                    auto_reason_tag = "H4 Dealing Range extreme value zone"

                if should_auto_adjudicate:
                    adjudication = inp.get("specialist_adjudication")
                    if (
                        not adjudication
                        or not isinstance(adjudication, dict)
                        or not adjudication.get("conflict_detected")
                    ):
                        inp["specialist_adjudication"] = {
                            "conflict_detected": True,
                            "resolution_path": "override_macro" if decision in ("buy", "sell") else "cancel_setup",
                            "resolution_justification": f"Auto-adjudicated {decision.upper()} to proceed to Dialectical Debate based on {auto_reason_tag}.",
                        }
                        logger.info(
                            f"[{symbol}] Auto-populated specialist_adjudication to preserve trade thesis ({auto_reason_tag})."
                        )
                    elif not adjudication.get("resolution_path") or not adjudication.get("resolution_justification"):
                        adjudication["resolution_path"] = adjudication.get("resolution_path") or "override_macro"
                        adjudication["resolution_justification"] = (
                            adjudication.get("resolution_justification")
                            or f"Adjudicated {decision.upper()} setup through {auto_reason_tag}."
                        )
                        inp["specialist_adjudication"] = adjudication
            except Exception as e:
                logger.debug(f"Specialist disagreement check failed (non-fatal): {e}")

        try:
            from monika.application.analysis.calculators.unified_threshold_calculator import (
                compute_unified_confluence_threshold,
            )

            final_threshold, threshold_reason = await compute_unified_confluence_threshold(
                self.session, symbol, self.settings
            )

            conf_score_val = inp.get("confluence_score")
            if conf_score_val is not None:
                if conf_score_val < final_threshold and decision in ["buy", "sell"]:
                    errors.append(
                        f"Confluence score ({conf_score_val}) is below the mandatory unified threshold ({final_threshold}) for {symbol}. "
                        f"You MUST change decision to 'wait'. Reason: {threshold_reason}"
                    )
        except Exception as e:
            logger.debug(f"Unified threshold enforcement failed: {e}")
