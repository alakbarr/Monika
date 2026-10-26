# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/prescreen.py
# Description: Fast pre-screening filter mixin for PerAssetRunner
# ==============================================================================

import logging
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.stages.per_asset.runner_mixins.base import (
    _RunnerMixinBase,
    _get_clock,
)

logger = logging.getLogger("TradingAgent.PerAssetStage")


class PrescreenMixin(_RunnerMixinBase):
    """Mixin handling fast LLM pre-screening and price-action momentum filters."""

    async def _run_prescreen(self, session: AsyncSession, symbol: str) -> Tuple[bool, str]:
        """
        Penyaringan (prescreen) kilat via Haiku. Menghemat token jika setup sangat tidak layak.
        Returns: (should_analyze: bool, alasan: str)
        """
        vix_row = None  # NEW: always initialized regardless of branch taken
        adx_val = None  # NEW
        skip_qual: dict = {}
        risk_state: dict = {}
        # === NEW: FORCE-ANALYZE ON PRICE MOVEMENT ===
        try:
            from sqlalchemy import select

            from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator

            last_analysis_time = self._last_analysis_time.get(symbol)
            if last_analysis_time:
                price_now = (
                    await session.execute(
                        select(PriceOHLCV.close)
                        .where(PriceOHLCV.symbol == symbol)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                price_then = (
                    await session.execute(
                        select(PriceOHLCV.close)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timestamp <= last_analysis_time)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                atr_row = (
                    await session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == "H4")
                        .where(TechnicalIndicator.indicator_name == "ATR_14")
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if price_now and price_then and atr_row:
                    import json as _j

                    atr_raw = _j.loads(atr_row.value_json)
                    atr_val = (
                        atr_raw.get("atr", atr_raw.get("value", 0)) if isinstance(atr_raw, dict) else float(atr_raw)
                    )
                    if atr_val and abs(price_now - price_then) / atr_val >= 0.75:
                        return (
                            True,
                            f"Pergerakan harga signifikan sejak analisis terakhir "
                            f"({abs(price_now - price_then) / atr_val:.2f}x ATR) — force ANALYZE",
                        )
        except Exception as e:
            logger.debug(f"Price-move prescreen check failed: {e}")

        # === NEW (Phase 3B): SMART RE-ANALYSIS GATE / FLAT-MARKET CHECK ===
        try:
            from datetime import timezone

            from sqlalchemy import select

            from monika.infrastructure.database.models import (
                AssetAnalysis,
                Position,
                PriceOHLCV,
                TechnicalIndicator,
            )

            open_pos = (
                await session.execute(
                    select(Position).where(Position.symbol == symbol).where(Position.status == "open").limit(1)
                )
            ).scalar_one_or_none()

            # If open_pos is not None: do NOT skip via flat-market check (always allow analysis to monitor/manage open position).
            if open_pos is None:
                last_analysis = (
                    await session.execute(
                        select(AssetAnalysis)
                        .where(AssetAnalysis.symbol == symbol)
                        .order_by(AssetAnalysis.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if last_analysis and last_analysis.decision and str(last_analysis.decision).lower() == "wait":
                    now_u = _get_clock().now()
                    raw_created = getattr(last_analysis, "created_at", None)
                    if raw_created is None:
                        raw_created = getattr(last_analysis, "generated_at", None)
                    if raw_created is not None:
                        created_at = (
                            raw_created.replace(tzinfo=timezone.utc) if raw_created.tzinfo is None else raw_created
                        )
                        age_minutes = (now_u - created_at).total_seconds() / 60.0
                        if 0 <= age_minutes < 60.0:
                            price_now = (
                                await session.execute(
                                    select(PriceOHLCV.close)
                                    .where(PriceOHLCV.symbol == symbol)
                                    .order_by(PriceOHLCV.timestamp.desc())
                                    .limit(1)
                                )
                            ).scalar_one_or_none()

                            ref_price = getattr(last_analysis, "price_at_analysis", None) or price_now
                            if price_now is not None and ref_price is not None:
                                atr_row = (
                                    await session.execute(
                                        select(TechnicalIndicator)
                                        .where(TechnicalIndicator.symbol == symbol)
                                        .where(TechnicalIndicator.timeframe == "H4")
                                        .where(TechnicalIndicator.indicator_name.in_(["ATR_14", "ATR"]))
                                        .order_by(TechnicalIndicator.timestamp.desc())
                                        .limit(1)
                                    )
                                ).scalar_one_or_none()
                                if atr_row is None:
                                    atr_row = (
                                        await session.execute(
                                            select(TechnicalIndicator)
                                            .where(TechnicalIndicator.symbol == symbol)
                                            .where(TechnicalIndicator.timeframe == "H1")
                                            .where(TechnicalIndicator.indicator_name.in_(["ATR_14", "ATR"]))
                                            .order_by(TechnicalIndicator.timestamp.desc())
                                            .limit(1)
                                        )
                                    ).scalar_one_or_none()

                                if atr_row:
                                    import json as _j

                                    atr_raw = (
                                        _j.loads(atr_row.value_json)
                                        if isinstance(atr_row.value_json, str)
                                        else atr_row.value_json
                                    )
                                    atr_val = (
                                        float(atr_raw.get("atr", atr_raw.get("value", 0)))
                                        if isinstance(atr_raw, dict)
                                        else float(atr_raw)
                                    )
                                    if atr_val and atr_val > 0:
                                        price_delta = abs(float(price_now) - float(ref_price))
                                        if price_delta / atr_val < 0.25:
                                            return (
                                                False,
                                                f"Quick flat-market check: price moved only {price_delta / atr_val:.2f}x ATR (<0.25x) since WAIT posture {int(age_minutes)}m ago — reusing WAIT posture",
                                            )
        except Exception as e:
            logger.debug(f"Flat-market prescreen check failed: {e}")

        # === QUICK LOCAL PRE-CHECK (no API call) ===
        try:
            from monika.core.calibration.prescreen_calibrator import compute_prescreen_skip_quality

            skip_qual = await compute_prescreen_skip_quality(session)

            local_quality = skip_qual.get("local_heuristic", {})
            local_false_skip_rate = (
                local_quality.get("false_skip_rate_pct", 0) if isinstance(local_quality, dict) else 0
            )

            # If false skip rate is >35%, we disable local deterministic gates so we don't miss trades
            if local_false_skip_rate <= 35:
                import json as _j

                from sqlalchemy import select

                from monika.infrastructure.database.models import TechnicalIndicator, VIXData

                # Quick VIX check (system-level pause threshold)
                vix_row = (
                    await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
                ).scalar_one_or_none()

                SAFE_HAVEN_SYMBOLS = {"XAUUSD", "USDJPY"}
                clean_sym = str(symbol).strip().upper().replace("/", "")
                if vix_row and vix_row.close >= 35 and clean_sym not in SAFE_HAVEN_SYMBOLS:
                    return (False, f"Quick local check: VIX={vix_row.close:.1f} >= 35 (non-safe-haven pause)")

                # Quick ADX check — extreme ranging
                adx_row = (
                    await session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == "D1")
                        .where(TechnicalIndicator.indicator_name == "ADX_14")
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if adx_row:
                    adx_data = _j.loads(adx_row.value_json)
                    adx_val = adx_data.get("adx", 25) if isinstance(adx_data, dict) else float(adx_data)
                    if adx_val < 10:  # Extremely flat
                        return (False, f"Quick local check: ADX={adx_val:.1f} < 10 (dead market, no signal value)")
            else:
                logger.info(
                    f"[{symbol}] Local prescreen gates bypassed due to high false-skip rate ({local_false_skip_rate}%)"
                )
        except Exception as e:
            logger.debug(f"Quick local pre-check failed (non-fatal): {e}")

        # === NEW P1 (Phase 2.7): Quick Calendar Prescreen ===
        try:
            from datetime import timedelta as _td

            from sqlalchemy import select as _sel_cal

            from monika.domain.market.currency_utils import get_symbol_currencies
            from monika.infrastructure.database.models import EconomicCalendar

            sym_currencies = get_symbol_currencies(symbol)
            upcoming_cal = (
                await session.execute(
                    _sel_cal(EconomicCalendar)
                    .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
                    .where(EconomicCalendar.currency.in_(list(sym_currencies)))
                    .where(EconomicCalendar.event_time >= _get_clock().now())
                    .where(EconomicCalendar.event_time <= _get_clock().now() + _td(minutes=15))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if upcoming_cal:
                # Force skip if major news < 15m (harmonized with PreFlightTurnGate)
                return (
                    False,
                    f"Quick local check: High-impact event '{upcoming_cal.event_name}' in < 15m. Avoiding entry.",
                )
        except Exception as e:
            logger.debug(f"Prescreen calendar check failed: {e}")

        if not self._haiku_client:
            return True, "prescreen disabled - no client"

        # Risk state check - lightweight
        try:
            from monika.application.analysis.tools.tool_executor import ToolExecutor

            executor = ToolExecutor(session, settings=self.settings, symbol=symbol)
            risk_state = await executor.execute("get_risk_state", {})
            if risk_state.get("trading_paused"):
                return False, f"Risk state: trading paused ({risk_state.get('pause_reason', 'unknown')})"
        except Exception:
            pass

        # Get minimal context for AI decision
        now_utc = _get_clock().now()
        weekday = now_utc.weekday()
        hour = now_utc.hour

        if weekday >= 5 and symbol not in self.always_open_assets:
            return False, "Market closed (weekend, non-crypto)"

        bias_note = ""
        try:
            llm_quality = skip_qual.get("llm_prescreen", {}) if skip_qual else {}
            llm_false_skip_rate = llm_quality.get("false_skip_rate_pct", 0) if isinstance(llm_quality, dict) else 0
            if llm_false_skip_rate > 35:
                bias_note = (
                    "\nNOTE: Recent calibration shows this prescreen has been too conservative (missing real "
                    "moves). When uncertain, lean YES."
                )
        except Exception as e:
            logger.debug(f"Prescreen calibration extraction failed: {e}")

        bias_note_default = (
            "\nEVALUATION MANDATE: Balance opportunity capture against pipeline computational cost. "
            "Return YES if price is within 1.0x H4 ATR of an active structural level (OB/FVG/SR) or has active trend/momentum. "
            "Return NO if market is in dead consolidation, far from structural levels, or lacks directional catalyst."
        )
        bias_note = bias_note if bias_note else bias_note_default

        # --- NEW: Extract nearest_zone_note ---
        nearest_zone_note = "active market structure"
        try:
            from sqlalchemy import select

            from monika.infrastructure.database.models import PriceOHLCV, SRZone, SwingPoint

            last_close = (
                await session.execute(
                    select(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == symbol)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_close:
                zones = (
                    (
                        await session.execute(
                            select(SRZone).where(SRZone.symbol == symbol).where(SRZone.timeframe == "H4")
                        )
                    )
                    .scalars()
                    .all()
                )
                if zones:
                    nearest = min(
                        zones, key=lambda z: min(abs(z.price_high - last_close), abs(z.price_low - last_close))
                    )
                    dist_pct = (
                        min(abs(nearest.price_high - last_close), abs(nearest.price_low - last_close))
                        / last_close
                        * 100
                    )
                    nearest_zone_note = f"{dist_pct:.2f}% from nearest S/R zone (strength={nearest.strength})"
                else:
                    swings = (
                        (
                            await session.execute(
                                select(SwingPoint)
                                .where(SwingPoint.symbol == symbol)
                                .where(SwingPoint.timeframe == "H4")
                                .order_by(SwingPoint.timestamp.desc())
                                .limit(4)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if swings:
                        nearest_sw = min(swings, key=lambda s: abs(s.price - last_close))
                        dist_pct = abs(nearest_sw.price - last_close) / last_close * 100
                        nearest_zone_note = f"{dist_pct:.2f}% from nearest H4 swing {nearest_sw.type}"
                    else:
                        nearest_zone_note = "S/R in calculation; volatility active (H4 ATR ready)"
        except Exception as e:
            logger.debug(f"Prescreen nearest zone check failed: {e}")
        # --- END NEW ---

        PRESCREEN_SCHEMA = {
            "type": "object",
            "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]}, "reason": {"type": "string"}},
            "required": ["decision", "reason"],
        }

        prompt = f"""Quick trading opportunity check for {symbol}. Evaluate whether we should proceed with full Stage 2 analysis.

Context:
- UTC time: {hour}:00, Day: {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][weekday]}
- Asset type: {"24/7 crypto" if symbol in self.always_open_assets else "forex/commodity"}
- VIX: {"normal" if not vix_row else (str(round(vix_row.close, 1)) + (" HIGH" if vix_row.close > 22 else " NORMAL"))}
- ADX: {"ranging" if adx_val is not None and adx_val < 15 else ("trending" if adx_val is not None and adx_val > 25 else "weak")}
- Risk state: {"PAUSED" if risk_state and risk_state.get("trading_paused") else "ACTIVE"}
- Proximity: {nearest_zone_note}

Rule:
- Return YES if price is within 1.0% of a strong S/R zone (strength>=3) OR within 1.0x ATR H4 OR standard risk/vix conditions hold.
- Return NO if: Risk paused OR market closed OR ADX dead (<12) OR VIX extreme (>35).{bias_note}
"""

        try:
            if hasattr(self._haiku_client, "thinking_budget"):
                self._haiku_client.thinking_budget = 0
            if hasattr(self._haiku_client, "thinking_level"):
                self._haiku_client.thinking_level = "none"
            from monika.core.primitives.jev_primitives import build_prescreen_questions

            prescreen_jev_q = build_prescreen_questions(symbol)
            resp = await self._haiku_client.classify_json(
                prompt=prompt, schema=PRESCREEN_SCHEMA, jev_questions=prescreen_jev_q, temperature=0.0
            )
            if resp and "reason" not in resp and "opportunity_score" in resp:
                resp["reason"] = f"opportunity_score={resp['opportunity_score']}"
            if resp and resp.get("decision") == "YES":
                return True, resp.get("reason", "")[:80]
            elif resp and resp.get("decision") == "NO":
                # --- NEW: BYPASS PRESCREEN ONLY IF FRESH BREAKING CATALYST OR EXPLICIT MACRO DRIVER ---
                try:
                    from datetime import timedelta

                    from sqlalchemy import select

                    from monika.application.protocol.context_coherence import SYMBOL_CURRENCY_MAP
                    from monika.infrastructure.database.models import FundamentalBrief, NewsItem

                    pair_info = SYMBOL_CURRENCY_MAP.get(symbol, {})
                    base_c, quote_c = pair_info.get("base"), pair_info.get("quote")
                    if base_c and quote_c:
                        recent_breaking = (
                            await session.execute(
                                select(NewsItem)
                                .where(NewsItem.fetched_at >= _get_clock().now() - timedelta(minutes=60))
                                .where(NewsItem.impact.in_(["BREAKING", "HIGH"]))
                                .where(
                                    NewsItem.currency_tags.like(f"%{base_c}%")
                                    | NewsItem.currency_tags.like(f"%{quote_c}%")
                                )
                                .limit(1)
                            )
                        ).scalar_one_or_none()
                        if recent_breaking:
                            logger.info(
                                f"[{symbol}] Prescreen returned NO, but bypassing due to recent BREAKING news catalyst"
                            )
                            return True, "forced_by_macro_override_breaking_news"

                    brief = (
                        await session.execute(
                            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                        )
                    ).scalar_one_or_none()
                    if brief and brief.confidence and brief.confidence >= 0.85:
                        matrix = getattr(brief, "per_asset_macro_matrix", None)
                        if not matrix and brief.structured_json:
                            try:
                                import json

                                b_data = json.loads(brief.structured_json)
                                matrix = b_data.get("per_asset_macro_matrix", {})
                            except Exception:
                                matrix = {}
                        matrix = matrix or {}
                        sym_entry = matrix.get(symbol) or matrix.get(symbol.replace("/", ""))
                        if sym_entry and sym_entry.get("tactical_catalyst"):
                            logger.info(
                                f"[{symbol}] Prescreen returned NO, but bypassing due to high conviction macro catalyst ({brief.confidence:.2f})"
                            )
                            return True, "forced_by_macro_override_tactical_catalyst"
                except Exception as e:
                    logger.debug(f"[{symbol}] Override check failed: {e}")
                # --- END NEW ---
                return False, resp.get("reason", "")[:80]
            else:
                return True, "prescreen ambiguous - defaulting to allow"
        except Exception as e:
            return True, f"prescreen error - defaulting to allow: {str(e)[:40]}"
