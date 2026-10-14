# ==============================================================================
# File: application/analysis/tools/mixins/brief_submission.py
# ==============================================================================

"""
Fundamental Brief Submission and Validation Mixin for ToolExecutor.
Encapsulates anti-anchoring guards, DXY checks, COT verification, and brief persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from pydantic import ValidationError
from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.schemas.schemas import SubmitFundamentalBriefSchema
from monika.application.analysis.tools.mixins.base import _ToolExecutorMixinBase, logger
from monika.infrastructure.database.models import (
    COTReport,
    EconomicCalendar,
    FundamentalBrief,
    NewsItem,
    SystemConfig,
    VIXData,
)


class FundamentalBriefMixin(_ToolExecutorMixinBase):
    """Mixin providing fundamental brief validation and submission logic."""

    async def _validate_fundamental_brief_completeness(self, inp: dict) -> list[str]:
        """Check if fundamental brief contains all required analysis components."""
        errors = []
        narrative = inp.get("macro_narrative", "").lower()

        # Check DXY explicitly
        if "dxy" not in narrative and "dollar index" not in narrative and "usd" not in narrative:
            errors.append("MISSING_DXY_ANALYSIS: You must explicitly mention DXY and its implications.")
        if "get_dxy" not in self.effective_called_tools:
            dxy_uncertain = (
                "dxy uncertain" in narrative or "dxy unavailable" in narrative or "dollar uncertain" in narrative
            )
            if not dxy_uncertain:
                errors.append("MISSING_TOOL: You MUST call 'get_dxy' before submitting the fundamental brief.")

        # Check VIX explicitly
        if (
            "vix" not in narrative
            and "risk sentiment" not in narrative
            and "risk-on" not in narrative
            and "risk-off" not in narrative
        ):
            errors.append("MISSING_VIX_ANALYSIS: You must explicitly mention VIX or Risk Sentiment.")
        if "get_vix" not in self.effective_called_tools:
            vix_uncertain = (
                "vix uncertain" in narrative or "vix unavailable" in narrative or "sentiment uncertain" in narrative
            )
            if not vix_uncertain:
                errors.append("MISSING_TOOL: You MUST call 'get_vix' before submitting the fundamental brief.")

        # Check Currency Bias completeness
        bias = inp.get("currency_bias", {})
        required = ["USD", "EUR", "GBP", "JPY", "AUD", "XAU"]
        asset_universe = self.settings.get("trading", {}).get("asset_universe", [])
        if "XTIUSD" in asset_universe:
            required.append("OIL")
        if "BTCUSD" in asset_universe:
            required.append("BTC")
        missing_bias = [c for c in required if c not in bias]
        if missing_bias:
            errors.append(f"MISSING_CURRENCY_BIAS: Missing explicit bias for {', '.join(missing_bias)}.")

        non_neutral_currencies = [c for c, b in bias.items() if b != "neutral"]
        invalidation_map = inp.get("invalidation_conditions", {})
        missing_invalidation = [c for c in non_neutral_currencies if c not in invalidation_map]
        if missing_invalidation:
            errors.append(
                f"MISSING_INVALIDATION: currency dengan bias terarah (bukan neutral) WAJIB punya invalidation_conditions. Kurang untuk: {missing_invalidation}"
            )

        weak_invalidation = []
        for c in non_neutral_currencies:
            cond_text = str(invalidation_map.get(c, ""))
            has_number = any(ch.isdigit() for ch in cond_text)
            if cond_text and (len(cond_text) < 40 or not has_number):
                weak_invalidation.append(c)
        if weak_invalidation:
            errors.append(
                f"WEAK_INVALIDATION: invalidation_conditions untuk {weak_invalidation} terlalu generik "
                f"atau tidak mengandung level harga/angka spesifik (WAJIB >= 40 karakter dan memuat angka konkret). "
                f"Contoh baik: 'Bias {weak_invalidation[0]} bearish batal jika harga break di atas level 78.50 ATAU inventory draw > 3.5M barrels'."
            )

        confidence_map = inp.get("currency_confidence", {})
        missing_conf = [c for c in non_neutral_currencies if c not in confidence_map]
        if missing_conf:
            errors.append(
                f"MISSING_CONFIDENCE: currency dengan bias terarah WAJIB punya currency_confidence (0.0-1.0). Kurang untuk: {missing_conf}"
            )

        if not inp.get("strongest_counter_thesis"):
            errors.append("MISSING_COUNTER_THESIS: Anda WAJIB memberikan strongest_counter_thesis yang valid.")
        elif len(inp.get("strongest_counter_thesis", "")) < 50:
            errors.append(
                "WEAK_COUNTER_THESIS: strongest_counter_thesis terlalu pendek (WAJIB >= 50 karakter), sebutkan data/skenario makro spesifik yang bisa membatalkan tesis Anda."
            )

        # NEW P2-4: Check priced_in_assessment completeness
        pi = inp.get("priced_in_assessment", {})
        if not pi:
            errors.append(
                "MISSING_PRICED_IN: Field 'priced_in_assessment' tidak boleh kosong. Gunakan data aktual dari get_cot_report dan get_fedwatch_probabilities."
            )
        else:
            is_weekend = clock.now().weekday() >= 5
            has_cot = pi.get("cot_positioning_percentile") is not None
            has_retail = pi.get("retail_sentiment_percentile") is not None
            has_crypto_sentiment = (
                pi.get("funding_rate") is not None
                or pi.get("fear_greed_score") is not None
                or pi.get("crypto_sentiment") is not None
            )

            # If missing during weekday, attempt auto-fill from macro_priced_in_baseline
            if (
                not has_cot
                and not has_retail
                and not (is_weekend and (has_crypto_sentiment or pi.get("dominant_driver")))
            ):
                try:
                    from monika.application.analysis.calculators.macro_priced_in_calculator import (
                        calculate_macro_priced_in_baseline,
                    )

                    baseline = await calculate_macro_priced_in_baseline(self.session)
                    if baseline.get("cot_positioning_percentile") is not None:
                        pi["cot_positioning_percentile"] = baseline["cot_positioning_percentile"]
                        has_cot = True
                        logger.info(
                            f"Auto-filled cot_positioning_percentile={baseline['cot_positioning_percentile']} from baseline"
                        )
                except Exception as _pi_err:
                    logger.debug(f"Auto-fill baseline failed: {_pi_err}")

            if (
                not has_cot
                and not has_retail
                and not (is_weekend and (has_crypto_sentiment or pi.get("dominant_driver")))
            ):
                errors.append(
                    "INCOMPLETE_PRICED_IN: Harus mencantumkan metrik numerik nyata (misal cot_positioning_percentile atau retail_sentiment_percentile) hasil fetch tools."
                )
            if not pi.get("sell_the_news_risk"):
                errors.append("INCOMPLETE_PRICED_IN: 'sell_the_news_risk' wajib diisi (high/medium/low).")

            # P1: Phase 2.6 - Tempering currency_confidence saat priced-in tinggi
            if pi.get("priced_in_score", 0) >= 8:
                dominant_driver_text = (pi.get("dominant_driver") or "").upper()
                currency_conf = inp.get("currency_confidence", {})
                for cur, conf in currency_conf.items():
                    if cur in dominant_driver_text and conf > 0.65:
                        errors.append(
                            f"PRICED_IN_CONFIDENCE_MISMATCH: priced_in_score={pi.get('priced_in_score')} (fully priced in) untuk driver yang menyebut {cur}, tapi currency_confidence[{cur}]={conf} masih tinggi. Jika mayoritas ekspektasi sudah priced-in, conviction directional seharusnya lebih rendah (turunkan ke <=0.6) KECUALI kamu punya alasan spesifik kenapa masih ada ruang gerak (state di macro_narrative)."
                        )

        return errors

    async def _check_anchoring_and_require_justification(
        self, current_bias: dict, justification_map: dict
    ) -> list[str]:
        import json as _json

        # Fetch recent briefs with distinct hourly/cycle timestamps to avoid duplicate same-cycle records
        raw_briefs = (
            (
                await self.session.execute(
                    select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(20)
                )
            )
            .scalars()
            .all()
        )

        distinct_cycle_briefs = []
        last_time = None
        for b in raw_briefs:
            if b.generated_at:
                if last_time is None or (last_time - b.generated_at).total_seconds() > 1800:
                    distinct_cycle_briefs.append(b)
                    last_time = b.generated_at
            if len(distinct_cycle_briefs) == 4:
                break

        if len(distinct_cycle_briefs) < 4:
            return []

        parsed_biases = []
        for rb in distinct_cycle_briefs:
            cb = getattr(rb, "currency_bias", None)
            if isinstance(cb, dict) and cb:
                parsed_biases.append(cb)
            elif getattr(rb, "structured_json", None):
                try:
                    b_data = _json.loads(rb.structured_json)
                    if isinstance(b_data, dict):
                        parsed_biases.append(b_data.get("currency_bias", {}))
                except Exception:
                    pass
        if len(parsed_biases) < 4:
            return []

        is_weekend = clock.now().weekday() >= 5
        errors = []
        justification_map = justification_map or {}
        for currency, bias in current_bias.items():
            if bias == "neutral":
                continue
            is_anchored = all(pb.get(currency) == bias for pb in parsed_biases)
            if is_anchored:
                just = justification_map.get(currency, "")
                has_number = any(ch.isdigit() for ch in just)
                weekend_ref = is_weekend and any(
                    w in just.lower() for w in ["weekend", "tutup", "closed", "jumat", "friday"]
                )
                if currency not in justification_map or len(just) < 40 or (not has_number and not weekend_ref):
                    errors.append(
                        f"ANCHORING_RISK: Bias {currency} ('{bias}') sama selama >=4 siklus pasar berturut-turut. "
                        f"bias_continuity_justification untuk {currency} kosong/terlalu pendek/tidak mengandung "
                        f"data numerik baru (WAJIB >= 40 karakter dengan level harga, %, tanggal, atau basis poin). "
                        f'Contoh format: bias_continuity_justification={{"{currency}": "Bias {currency} {bias} dipertahankan karena data 2026-08-22 menunjukkan level 102.50 bertahan dan yield naik 5 bps"}}.'
                    )
        return errors

    async def _validate_key_data_points(self, inp: dict) -> list[str]:
        """
        Cross-check angka yang di-restate model terhadap data yang benar-benar di-fetch,
        menangkap salah baca/halusinasi data SEBELUM meracuni seluruh siklus.
        """
        errors = []
        kdp = inp.get("key_data_points_used", {})
        if not kdp:
            return ["MISSING_DATA_ANCHORS: key_data_points_used is required."]
        try:
            real_dxy = await self.execute("get_dxy", {})
            real_trend = str(real_dxy.get("trend_5d", "unknown")).lower()
            claimed_trend = str(kdp.get("dxy_trend_5d", "")).lower()
            if real_trend != "unknown":
                BULLISH_SET = {"bullish", "bull", "upward", "up", "uptrend", "strengthening", "rising", "positive"}
                BEARISH_SET = {"bearish", "bear", "downward", "down", "downtrend", "weakening", "falling", "negative"}
                NEUTRAL_SET = {"neutral", "flat", "sideways", "choppy", "mixed", "ranging"}

                real_is_bull = any(w in real_trend for w in BULLISH_SET)
                claimed_is_bull = any(w in claimed_trend for w in BULLISH_SET)
                real_is_bear = any(w in real_trend for w in BEARISH_SET)
                claimed_is_bear = any(w in claimed_trend for w in BEARISH_SET)
                real_is_neutral = any(w in real_trend for w in NEUTRAL_SET)
                claimed_is_neutral = any(w in claimed_trend for w in NEUTRAL_SET)

                match = (
                    (real_is_bull and claimed_is_bull)
                    or (real_is_bear and claimed_is_bear)
                    or (real_is_neutral and claimed_is_neutral)
                    or (real_trend in claimed_trend)
                )
                if not match:
                    errors.append(
                        f"DATA_MISMATCH: Kamu menyatakan DXY trend='{kdp.get('dxy_trend_5d')}' tapi data tool "
                        f"aktual menunjukkan trend_5d='{real_trend}'. Cek ulang output get_dxy() sebelum resubmit."
                    )
        except Exception:
            pass
        try:
            real_vix = await self.execute("get_vix", {})
            if not real_vix.get("error"):
                real_close = (real_vix.get("latest") or {}).get("close")
                claimed_close = kdp.get("vix_close")
                if real_close is not None and claimed_close is not None:
                    try:
                        rc = float(real_close)
                        cc = float(claimed_close)
                        if rc > 5.0 and abs(cc - rc) > 1.0:
                            errors.append(
                                f"DATA_MISMATCH: Kamu menyatakan VIX={claimed_close} tapi VIX close terbaru "
                                f"aktual={real_close}. Verifikasi nilai yang dibaca dari get_vix()."
                            )
                    except TypeError, ValueError:
                        pass
        except Exception:
            pass
        try:
            if kdp.get("fedwatch_dominant_pct") is not None:
                real_fw = await self.execute("get_fedwatch_probabilities", {})
                meetings = real_fw.get("meetings", [])
                if meetings:
                    all_meeting_dominant_probs = []
                    for m in meetings:
                        probs_raw = m.get("probabilities", {})
                        if isinstance(probs_raw, dict) and "probabilities" in probs_raw:
                            probs = probs_raw.get("probabilities", {})
                        elif isinstance(probs_raw, dict):
                            probs = probs_raw
                        else:
                            probs = {}

                        m_max = max(
                            (
                                float(v.get("probability", 0))
                                for v in probs.values()
                                if isinstance(v, dict) and "probability" in v
                            ),
                            default=None,
                        )
                        if m_max is not None:
                            all_meeting_dominant_probs.append(m_max)

                    if all_meeting_dominant_probs:
                        claimed = float(kdp.get("fedwatch_dominant_pct"))
                        min_diff = min(abs(claimed - p) for p in all_meeting_dominant_probs)
                        closest_prob = min(all_meeting_dominant_probs, key=lambda p: abs(claimed - p))
                        if min_diff > 8.0:
                            errors.append(
                                f"DATA_MISMATCH: Kamu menyatakan FedWatch dominant={claimed}% tapi data aktual "
                                f"terdekat={closest_prob}%. Verifikasi ulang output get_fedwatch_probabilities()."
                            )
        except Exception:
            pass
        try:
            if kdp.get("fedwatch_repricing_delta_pct") is not None:
                real_fw_comp = await self.execute("get_fedwatch_probabilities", {"compare_hours_ago": 24})
                comparisons = real_fw_comp.get("comparisons", [])
                if comparisons:
                    all_deltas = []
                    for c in comparisons:
                        for d_val in (c.get("deltas_pct") or {}).values():
                            all_deltas.append(float(d_val))
                    if all_deltas:
                        claimed_delta = float(kdp.get("fedwatch_repricing_delta_pct"))
                        min_diff = min(abs(claimed_delta - d) for d in all_deltas)
                        if min_diff > 8.0:
                            errors.append(
                                f"DATA_MISMATCH: Kamu menyatakan fedwatch_repricing_delta_pct={claimed_delta}% tapi delta aktual terdekat={min(all_deltas, key=lambda d: abs(claimed_delta - d))}%. Verifikasi output fedwatch.comparisons."
                            )
        except Exception:
            pass
        try:
            tol_yield_bp = (
                self.settings.get("data_quality", {}).get("key_data_tolerance", {}).get("treasury_10y_yield_bp", 15.0)
            )
            if tol_yield_bp is not None and kdp.get("treasury_10y_yield_pct") is not None:
                real_yields = await self.execute("get_treasury_yields", {})
                real_10y_list = real_yields.get("yields_by_tenor", {}).get("10Y", [])
                if real_10y_list:
                    real_10y = real_10y_list[0].get("yield_pct")
                    claimed_10y = float(kdp.get("treasury_10y_yield_pct"))
                    if real_10y is not None and abs(claimed_10y - real_10y) * 100 > float(tol_yield_bp):
                        errors.append(
                            f"DATA_MISMATCH: Kamu menyatakan yield 10Y={claimed_10y}% tapi data aktual={real_10y}%. "
                            f"Verifikasi ulang output get_treasury_yields()."
                        )
        except Exception:
            pass
        try:
            tol_cot_pct = self.settings.get("data_quality", {}).get("key_data_tolerance", {}).get("cot_leveraged_pct")
            if tol_cot_pct is not None and kdp.get("cot_leveraged_long_pct") is not None:
                claimed_cot = float(kdp["cot_leveraged_long_pct"])
                CURRENCY_COT_MAP = {
                    "EUR": "099741",
                    "GBP": "096742",
                    "JPY": "097741",
                    "AUD": "232741",
                    "XAU": "088691",
                    "OIL": "067651",
                    "BTC": "133741",
                    "USD": "099741",
                }
                target_code = kdp.get("cot_market_code")
                if not target_code and kdp.get("cot_currency"):
                    target_code = CURRENCY_COT_MAP.get(str(kdp["cot_currency"]).upper())
                if not target_code:
                    target_code = "099741"

                cot_query = (
                    select(COTReport)
                    .where(COTReport.market_code == target_code)
                    .order_by(COTReport.report_date.desc())
                    .limit(1)
                )
                latest_cot = (await self.session.execute(cot_query)).scalar_one_or_none()
                if latest_cot:
                    tot = (latest_cot.leveraged_long or 0) + (latest_cot.leveraged_short or 0)
                    if tot > 0:
                        actual_long_pct = ((latest_cot.leveraged_long or 0) / tot) * 100.0
                        if abs(claimed_cot - actual_long_pct) > tol_cot_pct:
                            errors.append(
                                f"Key data point 'cot_leveraged_long_pct' claimed {claimed_cot:.1f}%, "
                                f"but latest COT report for {target_code} shows {actual_long_pct:.1f}% (diff > tolerance {tol_cot_pct}%)."
                            )
        except Exception:
            pass
        return errors

    async def _cross_check_all_currencies_priced_in(self, inp: dict) -> list[str]:
        from monika.application.analysis.calculators.stage1_priced_in import calculate_stage1_priced_in_baseline

        warnings = []
        fedwatch_res = await self.execute("get_fedwatch_probabilities", {"compare_hours_ago": 24})
        fedwatch_prob = None
        fedwatch_delta = None
        if isinstance(fedwatch_res, dict) and fedwatch_res.get("meetings"):
            try:
                probs = fedwatch_res["meetings"][0]["probabilities"].get("probabilities", {})
                fedwatch_prob = max(
                    (v.get("probability", 0) for v in probs.values() if isinstance(v, dict)), default=None
                )
            except Exception:
                pass
            if fedwatch_res.get("comparisons"):
                try:
                    c0 = fedwatch_res["comparisons"][0]
                    deltas = c0.get("deltas_pct", {})
                    if deltas:
                        max_k = max(deltas.keys(), key=lambda k: abs(deltas[k]))
                        fedwatch_delta = deltas[max_k]
                except Exception:
                    pass

        CURRENCY_COT_MAP = {"EUR": "099741", "GBP": "096742", "JPY": "097741", "AUD": "232741", "XAU": "088691"}
        CURRENCY_PROXY_SYMBOL = {"EUR": "EURUSD", "GBP": "GBPUSD", "JPY": "USDJPY", "AUD": "AUDUSD", "XAU": "XAUUSD"}

        for ccy, cot_code in CURRENCY_COT_MAP.items():
            cot_row = (
                await self.session.execute(
                    select(COTReport)
                    .where(COTReport.market_code == cot_code)
                    .order_by(COTReport.report_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not cot_row or (cot_row.leveraged_long + cot_row.leveraged_short) <= 0:
                continue
            total = cot_row.leveraged_long + cot_row.leveraged_short
            percentile = cot_row.leveraged_long / total * 100
            proxy_symbol = CURRENCY_PROXY_SYMBOL.get(ccy)
            mom_res = (
                await self.execute("get_price_momentum", {"symbol": proxy_symbol, "timeframe": "H4", "period": 20})
                if proxy_symbol
                else {}
            )
            run_up = mom_res.get("run_up_vs_atr") if isinstance(mom_res, dict) else None
            baseline = calculate_stage1_priced_in_baseline(
                ccy,
                percentile,
                fedwatch_dominant_prob=fedwatch_prob,
                eurusd_run_up_vs_atr=run_up,
                fedwatch_repricing_delta=fedwatch_delta,
            )
            declared_bias = (inp.get("currency_bias", {}) or {}).get(ccy, "neutral")
            declared_pi = (inp.get("priced_in_assessment", {}) or {}).get("priced_in_score", 5)
            if baseline["is_priced_in"] and declared_pi <= 3 and declared_bias != "neutral":
                warnings.append(
                    f"[{ccy}] Deterministic baseline menunjukkan priced-in ({'; '.join(baseline['reasons'])}) tapi priced_in_score={declared_pi} rendah."
                )
        return warnings

    async def _tool_submit_fundamental_brief(self, inp: dict) -> dict:
        """Menyimpan narasi dan bias makro ke DB (menandai berakhirnya Tahap 1)."""
        inp.pop("submit_attempts", None)  # Toleransi tambahan argumen dari LLM

        if isinstance(inp, dict):
            for wrapper in ("input", "brief", "data", "parameters", "args", "payload"):
                if wrapper in inp and isinstance(inp[wrapper], dict) and len(inp) == 1:
                    inp = inp[wrapper]
                    break

        # Contamination guard
        stage2_tools = {
            "get_smc_zones",
            "get_technical_indicators",
            "get_swing_points",
            "get_fvg_zones",
            "get_order_blocks",
        }
        contaminated = stage2_tools.intersection(self.called_tools)
        if contaminated:
            logger.warning(f"Stage 1 contamination detected: {contaminated}. Blocking submission.")
            return {
                "status": "rejected",
                "errors": [f"You called Stage 2 tools ({', '.join(contaminated)}) during Stage 1."],
                "error_classification": "CONTAMINATION_ERROR",
                "guidance": "Stage 1 must ONLY use macro/fundamental tools. Do NOT call technical/SMC tools. Restart your reasoning focusing purely on fundamental drivers.",
            }

        # Deterministic priced-in check using EURUSD as a baseline proxy for USD
        try:
            warnings = await self._cross_check_all_currencies_priced_in(inp)
            if warnings:
                inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM WARNING: Deterministic Priced-In Check triggered.\n"
                    + "\n".join(warnings)
                    + f"\nStage 2 agents must exercise caution and increase confluence thresholds.]"
                )
        except Exception as e:
            logger.error(f"Deterministic priced-in check failed: {e}")

        try:
            validated_data = SubmitFundamentalBriefSchema.model_validate(inp)
            inp = validated_data.model_dump(mode="json")
        except ValidationError as e:
            error_msgs = [f"Field '{'.'.join(str(x) for x in err['loc'])}': {err['msg']}" for err in e.errors()]
            logger.warning(f"Pydantic validation failed for submit_fundamental_brief: {error_msgs}")
            return {
                "status": "validation_failed",
                "errors": error_msgs,
                "error_classification": "SCHEMA_ERROR",
                "guidance": "Please fix the schema formatting errors above and call the tool again.",
            }

        # Validate Completeness
        completeness_errors = await self._validate_fundamental_brief_completeness(inp)
        data_anchor_errors = await self._validate_key_data_points(inp)
        completeness_errors.extend(data_anchor_errors)

        merged_justifications = {
            **inp.get("bias_change_justification", {}),
            **inp.get("bias_continuity_justification", {}),
        }
        anchoring_errors = await self._check_anchoring_and_require_justification(
            inp.get("currency_bias", {}), merged_justifications
        )
        if anchoring_errors:
            completeness_errors.extend(anchoring_errors)

        non_neutral_currencies = [c for c, b in inp.get("currency_bias", {}).items() if b != "neutral"]
        invalidation_map = inp.get("invalidation_conditions", {})
        missing_invalidation = [
            c for c in non_neutral_currencies if c not in invalidation_map or not invalidation_map.get(c, "").strip()
        ]
        if missing_invalidation:
            completeness_errors.append(
                f"MISSING_INVALIDATION: Currency berikut punya bias non-neutral tapi tidak "
                f"punya invalidation_conditions: {missing_invalidation}. Setiap bias directional "
                f"WAJIB punya kondisi falsifiable."
            )

        # Checklist verification
        checklist = inp.get("checklist", {})
        if checklist.get("contradiction_existed"):
            counter_thesis = inp.get("strongest_counter_thesis", "")
            if not counter_thesis:
                completeness_errors.append(
                    "CONTRADICTION_UNRESOLVED: You marked contradiction_existed=True in the checklist, but did not provide the strongest_counter_thesis. You must detail the counter-thesis."
                )
            elif not any(ch.isdigit() for ch in counter_thesis):
                completeness_errors.append(
                    "CONTRADICTION_UNRESOLVED_NO_EVIDENCE: contradiction_existed=True tapi strongest_counter_thesis tidak mengandung bukti numerik konkret (level harga/%/tanggal/basis poin) sebagai dasar resolusi kontradiksi."
                )

        # Ceiling check
        try:
            from monika.core.analytics.agent_performance_monitor import get_currency_confidence_ceiling

            ceilings = await get_currency_confidence_ceiling(self.session)
            currency_conf = inp.get("currency_confidence", {})
            for cur, conf in currency_conf.items():
                ceiling = ceilings.get(cur, 0.95)
                if conf > ceiling:
                    completeness_errors.append(
                        f"CONFIDENCE_CEILING_EXCEEDED: Your confidence for {cur} ({conf}) exceeds the historical accuracy ceiling ({ceiling}). "
                        f"Please lower your confidence to max {ceiling}."
                    )
        except Exception as e:
            logger.error(f"Error checking confidence ceilings: {e}")

        if completeness_errors:
            self.submit_attempts += 1
            if self.submit_attempts <= 2:
                logger.warning(f"Brief rejected (incomplete): {completeness_errors}")
                return {
                    "status": "rejected",
                    "errors": completeness_errors,
                    "error_classification": "INCOMPLETE_ANALYSIS",
                    "guidance": "Your brief is incomplete. Fix the errors above and resubmit. Do NOT ignore this.",
                }
            else:
                logger.warning(
                    f"Brief accepted with unresolved errors after {self.submit_attempts} attempts: {completeness_errors}"
                )
                inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM FLAG: Brief force-accepted with unresolved errors: "
                    f"{'; '.join(completeness_errors)}. Stage 2 MUST escalate if this affects the trading decision.]"
                )
                inp["confidence"] = min(float(inp.get("confidence", 0.5)), 0.35)
                inp["_data_quality_degraded"] = True
                inp["_degradation_reasons"] = completeness_errors

        from monika.application.protocol.brief_contamination_guard import BriefContaminationGuard

        brief_data_for_check = {
            "currency_bias": inp.get("currency_bias", {}),
            "risk_sentiment": inp.get("risk_sentiment", "mixed"),
            "confidence": inp.get("confidence", 0.5),
        }
        is_safe, contamination_issues, contamination_risk = await BriefContaminationGuard.validate_brief_integrity(
            self.session, brief_data_for_check, self.settings
        )
        CONTAMINATION_HARD_BLOCK_THRESHOLD = 0.4  # FIX P2-1: turunkan dari 0.5 ke 0.4

        if not is_safe and contamination_risk >= CONTAMINATION_HARD_BLOCK_THRESHOLD:
            self.submit_attempts += 1
            if self.submit_attempts <= 2:
                logger.warning(f"Brief REJECTED (contamination_risk={contamination_risk:.2f}): {contamination_issues}")
                return {
                    "status": "rejected",
                    "errors": contamination_issues,
                    "error_classification": "INTERNAL_CONTRADICTION",
                    "guidance": (
                        "Brief Anda mengandung kontradiksi internal yang belum diselesaikan "
                        "(lihat errors di atas). Anda WAJIB secara eksplisit menyatakan di "
                        "macro_narrative: sumber mana yang Anda percaya dan MENGAPA, sebelum "
                        "submit ulang. Jangan hanya menyebut kedua sisi tanpa memilih."
                    ),
                }
            else:
                logger.warning(
                    f"Brief accepted despite contamination_risk={contamination_risk:.2f} "
                    f"(max retries reached): {contamination_issues}"
                )
                inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM FLAG: Brief disimpan meski contamination_risk={contamination_risk:.2f} "
                    f"setelah {self.submit_attempts} percobaan. Isu belum terselesaikan: "
                    f"{'; '.join(contamination_issues)}. Stage 2 harus ekstra hati-hati.]"
                )
        elif not is_safe:
            inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                f"\n\n[SYSTEM NOTE: contamination_risk={contamination_risk:.2f} (warning zone). "
                f"Issues: {'; '.join(contamination_issues)}]"
            )

        # === NEW: Enforce priced_in_assessment when major events exist ===
        priced_in = inp.get("priced_in_assessment")
        if not priced_in:
            # Check if there are major events within 48h
            now = clock.now()
            result = await self.session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact == "high")
                .where(EconomicCalendar.event_time >= now)
                .where(EconomicCalendar.event_time <= now + timedelta(hours=48))
                .limit(1)
            )
            upcoming_major = result.scalar_one_or_none()

            if upcoming_major:
                logger.warning(
                    f"Brief rejected: missing priced_in_assessment when high-impact event '{upcoming_major.event_name}' is within 48h."
                )
                return {
                    "status": "rejected",
                    "errors": [f"Missing 'priced_in_assessment' field."],
                    "error_classification": "INCOMPLETE_ANALYSIS",
                    "guidance": f"A high-impact event ('{upcoming_major.event_name}') is scheduled within the next 48h. You MUST provide the 'priced_in_assessment' field to evaluate how much this event is already priced in by the market.",
                }

        # ── DETERMINISTIC CONFIDENCE CEILING (menegakkan CHECKPOINT 3 secara kode) ──
        try:
            declared_confidence = float(inp.get("confidence", 0.7))
            ceiling_reasons = []
            hard_ceiling = 1.0

            if contamination_risk >= 0.35:
                hard_ceiling = min(hard_ceiling, 0.65)
                ceiling_reasons.append(f"contamination_risk={contamination_risk:.2f}")

            vix_row = (
                await self.session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
            ).scalar_one_or_none()
            if vix_row and vix_row.close >= 28:
                hard_ceiling = min(hard_ceiling, 0.70)
                ceiling_reasons.append(f"vix={vix_row.close:.1f}>=28")

            from datetime import timedelta as _td

            upcoming_2h = (
                (
                    await self.session.execute(
                        select(EconomicCalendar)
                        .where(EconomicCalendar.impact == "high")
                        .where(EconomicCalendar.event_time >= clock.now())
                        .where(EconomicCalendar.event_time <= clock.now() + _td(hours=2))
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            if upcoming_2h:
                event_currencies = set()
                for ev in upcoming_2h:
                    if ev.currency:
                        event_currencies.add(ev.currency.upper())
                inp["_upcoming_event_currencies"] = list(event_currencies)
                hard_ceiling = min(hard_ceiling, 0.70)
                ev_names = ", ".join(str(e.event_name)[:25] for e in upcoming_2h[:3])
                ceiling_reasons.append(f"high_impact_event_within_2h({ev_names})")

            if declared_confidence > hard_ceiling:
                logger.warning(
                    f"[ConfidenceCeiling] Stage1 confidence clamped {declared_confidence:.2f} -> {hard_ceiling:.2f}. Reasons: {ceiling_reasons}"
                )
                inp["confidence"] = hard_ceiling
                inp["macro_narrative"] = (
                    inp.get("macro_narrative", "")
                    + f"\n\n[SYSTEM: Confidence auto-capped to {hard_ceiling:.2f} (declared {declared_confidence:.2f}) due to: {', '.join(ceiling_reasons)}.]"
                )
        except Exception as e:
            logger.debug(f"Deterministic confidence ceiling check failed (non-fatal): {e}")
        # ── END CONFIDENCE CEILING ──

        import json as _json

        now = clock.now()
        validity = self.settings.get("data_quality", {}).get("brief_validity_hours", 12.0)
        valid_until = now + timedelta(hours=validity)

        # Task 2.3: Validation for priced_in_assessment
        priced_in = inp.get("priced_in_assessment")
        if priced_in:
            pi_score = priced_in.get("priced_in_score")
            if pi_score is not None:
                try:
                    pi_score = int(pi_score)
                    if not 1 <= pi_score <= 10:
                        pi_score = max(1, min(10, pi_score))
                        logger.warning(
                            f"priced_in_score {priced_in.get('priced_in_score')} out of range, clamped to {pi_score}"
                        )
                except ValueError, TypeError:
                    logger.warning(f"priced_in_score invalid type: {type(pi_score)}, setting to 5")
                    pi_score = 5
                priced_in["priced_in_score"] = pi_score

                # Sanity check for priced_in_score
                if pi_score <= 3:
                    from sqlalchemy import func, or_

                    now_utc = clock.now()
                    recent_high_news = (
                        await self.session.execute(
                            select(func.count(NewsItem.id))
                            .where(NewsItem.fetched_at >= now_utc - timedelta(hours=24))
                            .where(or_(NewsItem.title.ilike("%BREAKING%"), NewsItem.title.ilike("%URGENT%")))
                        )
                    ).scalar() or 0

                    recent_high_econ = (
                        await self.session.execute(
                            select(func.count(EconomicCalendar.id))
                            .where(EconomicCalendar.event_time >= now_utc - timedelta(hours=24))
                            .where(EconomicCalendar.event_time <= now_utc)
                            .where(EconomicCalendar.impact == "high")
                        )
                    ).scalar() or 0

                    total_high_events = recent_high_news + recent_high_econ
                    if total_high_events >= 5:
                        logger.warning(
                            f"Sanity Check Failed: pi_score={pi_score} but {total_high_events} high/breaking news found."
                        )
                        inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                            f"\n\n[SYSTEM WARNING: priced_in_score is low ({pi_score}) despite {total_high_events} recent "
                            f"HIGH/BREAKING events. The market may have already priced these in! Stage 2 should exercise caution.]"
                        )

            valid_risks = ["high", "medium", "low", "not_applicable"]
            current_risk = priced_in.get("sell_the_news_risk")
            pi_score = priced_in.get("priced_in_score", 5)
            if pi_score >= 8:
                priced_in["sell_the_news_risk"] = "high"
            elif pi_score in (5, 6, 7):
                if current_risk not in ("medium", "high"):
                    priced_in["sell_the_news_risk"] = "medium"
            elif pi_score in (3, 4):
                if current_risk not in ("low", "medium"):
                    priced_in["sell_the_news_risk"] = "low"
            else:
                if current_risk not in ("not_applicable", "low"):
                    priced_in["sell_the_news_risk"] = "not_applicable"
            inp["priced_in_assessment"] = priced_in

        brief = FundamentalBrief(
            generated_at=now,
            valid_until=valid_until,
            content_markdown=inp.get("macro_narrative", ""),
            structured_json=_json.dumps(
                {
                    "generated_at": now.isoformat(),
                    "macro_narrative": inp.get("macro_narrative", ""),
                    "key_drivers": inp.get("key_drivers", []),
                    "currency_bias": inp.get("currency_bias", {}),
                    "currency_confidence": inp.get("currency_confidence", {}),
                    "invalidation_conditions": inp.get("invalidation_conditions", {}),
                    "per_asset_macro_matrix": inp.get("per_asset_macro_matrix", {}),
                    "asset_priced_in_scores": inp.get("asset_priced_in_scores", {}),
                    "yield_curve_regime": inp.get("yield_curve_regime", None),
                    "systemic_liquidity_trend": inp.get("systemic_liquidity_trend", None),
                    "strongest_counter_thesis": inp.get("strongest_counter_thesis", ""),
                    "key_upcoming_risks": inp.get("key_upcoming_risks", []),
                    "risk_sentiment": inp.get("risk_sentiment", "mixed"),
                    "macro_regime": inp.get("macro_regime", "mixed"),
                    "confidence": inp.get("confidence", 0.5),
                    "priced_in_assessment": inp.get("priced_in_assessment", None),
                    "key_data_points_used": inp.get("key_data_points_used", {}),
                    "checklist": inp.get("checklist", {}),
                    "bias_continuity_justification": inp.get("bias_continuity_justification", {}),
                    "_data_quality_degraded": inp.get("_data_quality_degraded", False),
                    "_degradation_reasons": inp.get("_degradation_reasons", []),
                }
            ),
            confidence=inp.get("confidence", 0.5),
            risk_sentiment=inp.get("risk_sentiment", "mixed"),
        )
        self.session.add(brief)
        await self.session.commit()
        await self.session.refresh(brief)
        saved_brief_id = brief.id

        # Macro Regime Shift Auto-Recording to MarketChronicle
        try:
            from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

            prev_brief = (
                await self.session.execute(
                    select(FundamentalBrief)
                    .where(FundamentalBrief.id != brief.id)
                    .order_by(FundamentalBrief.generated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if prev_brief:
                await ChronicleWriter(self.settings).maybe_record_regime_shift(self.session, brief, prev_brief)
        except Exception as chronicle_err:
            logger.debug(f"Failed to record chronicle regime shift (non-fatal): {chronicle_err}")

        priced_in = inp.get("priced_in_assessment")
        priced_in_summary = (
            (
                f", priced_in_score={priced_in.get('priced_in_score')}, "
                f"sell_news_risk={priced_in.get('sell_the_news_risk')}"
            )
            if priced_in
            else ""
        )

        logger.info(
            f"Fundamental brief saved (id={saved_brief_id}, sentiment={inp.get('risk_sentiment')}{priced_in_summary})"
        )

        try:
            recent_briefs = (
                (
                    await self.session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(6)
                    )
                )
                .scalars()
                .all()
            )
            streak_warnings = []
            flip_flop_warnings = []
            new_bias = inp.get("currency_bias", {})
            for currency, bias in new_bias.items():
                if bias == "neutral":
                    continue
                history = []
                for prev in recent_briefs[1:4]:
                    if not prev.structured_json:
                        continue
                    try:
                        pb = _json.loads(prev.structured_json).get("currency_bias", {}).get(currency, "neutral")
                        history.append(pb)
                    except Exception:
                        pass

                # FIX (P1): Flip-Flop Bias Detector
                if len(history) >= 2:
                    if bias != "neutral" and history[0] != "neutral" and bias != history[0] and bias == history[1]:
                        flip_flop_warnings.append(
                            f"{currency} flip-flop detected: {history[1]} -> {history[0]} -> {bias}"
                        )

                streak = 1
                for prev in recent_briefs[1:]:
                    if not prev.structured_json:
                        break
                    try:
                        prev_bias = _json.loads(prev.structured_json).get("currency_bias", {}).get(currency)
                    except Exception:
                        break
                    if prev_bias == bias:
                        streak += 1
                    else:
                        break
                if streak >= 4:
                    streak_warnings.append(f"{currency}={bias} unchanged for {streak} consecutive briefs")

            alerts = []
            if streak_warnings:
                alerts.extend(streak_warnings)
            if flip_flop_warnings:
                alerts.extend(
                    [
                        f"[FLIP-FLOP WARNING] {w} — Jika bias bolak-balik tiap siklus tanpa breakout makro baru, ini akan menyebabkan whipsaw loss. WAJIB justifikasi kuat atau gunakan NEUTRAL."
                        for w in flip_flop_warnings
                    ]
                )

            if alerts:
                key = f"anchoring_streak_alert_{clock.now().strftime('%Y%m%d_%H')}"
                existing = (
                    await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))
                ).scalar_one_or_none()
                if existing:
                    existing.value = _json.dumps(alerts)
                else:
                    self.session.add(SystemConfig(key=key, value=_json.dumps(alerts)))
                await self.session.commit()
        except Exception as e:
            try:
                await self.session.rollback()
            except Exception:
                pass
            logger.debug(f"Anti-anchoring streak check failed (non-fatal): {e}")

        return {
            "status": "saved",
            "brief_id": saved_brief_id,
            "valid_until": valid_until.isoformat(),
        }
