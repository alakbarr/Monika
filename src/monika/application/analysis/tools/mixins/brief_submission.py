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
from monika.application.analysis.schemas import SubmitFundamentalBriefSchema
from monika.application.analysis.tools.mixins.base import _ToolExecutorMixinBase, logger
from monika.infrastructure.database.models import (
    COTReport,
    EconomicCalendar,
    FundamentalBrief,
    NewsItem,
    SystemConfig,
    VIXData,
)

VALID_MACRO_REGIMES: Set[str] = {
    "reflation",
    "stagflation",
    "disinflation",
    "goldilocks",
    "transition",
    "transitional",
    "mixed",
    "risk-on",
    "risk-off",
    "risk_on",
    "risk_off",
    "neutral",
    "ranging",
}

_REGIME_PUNCT_STRIP: str = " \t\n\r,.;:-_ /|[]{}\"'()"
_NARRATIVE_REGIME_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("stagflation", "stagflation"),
    ("goldilocks", "goldilocks"),
    ("reflation", "reflation"),
    ("disinflation", "disinflation"),
    ("risk-off", "risk-off"),
    ("risk_off", "risk-off"),
    ("risk-on", "risk-on"),
    ("risk_on", "risk-on"),
)

STANDARD_FX_PAIRS_BASE_QUOTE: Dict[str, tuple[str, str]] = {
    "USDJPY": ("USD", "JPY"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "XAUUSD": ("XAU", "USD"),
}
_FX_BASE_QUOTE = STANDARD_FX_PAIRS_BASE_QUOTE
_BIAS_TO_SIGN: Dict[str, int] = {
    "bullish": 1,
    "bearish": -1,
    "neutral": 0,
    "mixed": 0,
}


def sanitize_macro_regime(raw_regime: Any, macro_narrative: Optional[str] = None) -> str:
    """Strip punctuation (',.;:-_ /|[]{}\"\'()') from macro_regime; infer from narrative or default to 'transition' if invalid."""
    if isinstance(raw_regime, str):
        cleaned = raw_regime.strip(_REGIME_PUNCT_STRIP).lower()
        alpha_count = sum(1 for ch in cleaned if ch.isalpha())
        if len(cleaned) >= 3 and alpha_count >= 3:
            if (
                cleaned in VALID_MACRO_REGIMES
                or cleaned.replace("_", "-") in VALID_MACRO_REGIMES
                or cleaned.replace("-", "_") in VALID_MACRO_REGIMES
            ):
                return cleaned
            for kw, canonical in _NARRATIVE_REGIME_KEYWORDS:
                if kw in cleaned:
                    return canonical

    if isinstance(macro_narrative, str) and macro_narrative.strip():
        narr_lower = macro_narrative.lower()
        for kw, canonical in _NARRATIVE_REGIME_KEYWORDS:
            if kw in narr_lower:
                return canonical
        return "transitional"

    return "transition"


def _resolve_bias_sign(bias_str: str) -> Optional[int]:
    if bias_str in _BIAS_TO_SIGN:
        return _BIAS_TO_SIGN[bias_str]
    if "bull" in bias_str:
        return 1
    if "bear" in bias_str:
        return -1
    if "neut" in bias_str or "mix" in bias_str or "flat" in bias_str:
        return 0
    return None


def reconcile_fx_pair_macro_matrix(currency_bias: Any, per_asset_macro_matrix: Any) -> Dict[str, Any]:
    """Ensure FX pair directional_bias in per_asset_macro_matrix matches currency_bias[BASE] - currency_bias[QUOTE]."""
    matrix: Dict[str, Any] = dict(per_asset_macro_matrix) if isinstance(per_asset_macro_matrix, dict) else {}
    if not isinstance(currency_bias, dict):
        return matrix

    norm_cb: Dict[str, str] = {
        str(k).upper().strip(): str(v).lower().strip() for k, v in currency_bias.items() if k is not None
    }

    for pair, (base_ccy, quote_ccy) in STANDARD_FX_PAIRS_BASE_QUOTE.items():
        if pair not in matrix or not isinstance(matrix[pair], dict):
            continue
        if pair == "XAUUSD":
            if base_ccy not in norm_cb or quote_ccy not in norm_cb:
                continue
        elif base_ccy not in norm_cb and quote_ccy not in norm_cb:
            continue

        base_str = norm_cb.get(base_ccy, "neutral")
        quote_str = norm_cb.get(quote_ccy, "neutral")
        b_sign = _resolve_bias_sign(base_str)
        q_sign = _resolve_bias_sign(quote_str)
        if b_sign is None or q_sign is None:
            continue

        diff = b_sign - q_sign
        expected_direction: Optional[str] = None
        if diff > 0:
            expected_direction = "bullish"
        elif diff < 0:
            expected_direction = "bearish"

        if expected_direction is not None:
            orig_dir_raw = str(matrix[pair].get("directional_bias", "")).strip()
            current_dir = orig_dir_raw.lower()
            if expected_direction[:4] not in current_dir:
                logger.info(
                    f"[AlgebraicFXReconciliation] Reconciled {pair} directional_bias "
                    f"from '{current_dir}' to '{expected_direction}' ({base_ccy}={base_str}, {quote_ccy}={quote_str})."
                )
                matrix[pair]["directional_bias"] = (
                    expected_direction.upper() if (orig_dir_raw and orig_dir_raw.isupper()) else expected_direction
                )
                reconcile_note = f"[AUTO-RECONCILED: {base_ccy}={base_str} vs {quote_ccy}={quote_str} -> {pair}={expected_direction}]"
                existing_kd = matrix[pair].get("key_driver")
                if isinstance(existing_kd, str) and existing_kd.strip():
                    if "[AUTO-RECONCILED:" not in existing_kd:
                        matrix[pair]["key_driver"] = f"{existing_kd.strip()} {reconcile_note}"
                else:
                    matrix[pair]["key_driver"] = reconcile_note
                existing_sd = matrix[pair].get("structural_driver")
                if isinstance(existing_sd, str) and existing_sd.strip() and "[AUTO-RECONCILED:" not in existing_sd:
                    matrix[pair]["structural_driver"] = f"{existing_sd.strip()} {reconcile_note}"
    return matrix


def _extract_priced_in_baseline_score(automated_priced_in: Any, sym: Optional[str] = None) -> Optional[int]:
    """Extract numeric baseline score from automated_priced_in structure."""
    if isinstance(automated_priced_in, bool) or automated_priced_in is None:
        return None
    if isinstance(automated_priced_in, (int, float)):
        return int(automated_priced_in)
    if isinstance(automated_priced_in, dict):
        if sym and sym in automated_priced_in:
            sym_entry = automated_priced_in[sym]
            if isinstance(sym_entry, (int, float)) and not isinstance(sym_entry, bool):
                return int(sym_entry)
            if isinstance(sym_entry, dict):
                for key in ("total_score", "total_auto", "score", "baseline"):
                    val = sym_entry.get(key)
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        return int(val)
        for key in ("total_score", "total_auto", "score", "baseline"):
            val = automated_priced_in.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return int(val)
    return None


def cap_empirical_priced_in_scores(
    asset_priced_in_scores: Any,
    automated_priced_in: Any,
    has_imminent_high_impact: bool = False,
) -> Dict[str, int]:
    """Cap asset_priced_in_scores[sym] to min(submitted_score, baseline + 2) when baseline <= 4 and no imminent event."""
    scores: Dict[str, int] = dict(asset_priced_in_scores) if isinstance(asset_priced_in_scores, dict) else {}
    if not scores or has_imminent_high_impact:
        return scores
    if not isinstance(automated_priced_in, (dict, int, float)) or isinstance(automated_priced_in, bool):
        return scores

    for sym, submitted_val in list(scores.items()):
        baseline_val = _extract_priced_in_baseline_score(automated_priced_in, sym=sym)
        if baseline_val is not None and baseline_val <= 4:
            try:
                sub_int = int(submitted_val)
                capped = min(sub_int, int(baseline_val) + 2)
                if capped != sub_int:
                    logger.info(
                        f"[EmpiricalPricedInCap] Capped {sym} priced_in_score from {sub_int} to {capped} "
                        f"(automated baseline={baseline_val})."
                    )
                scores[sym] = capped
            except ValueError, TypeError:
                pass
    return scores


def format_macro_intelligence_dossier(inp: dict, now: datetime, valid_until: Optional[datetime] = None) -> str:
    """
    Synthesizes a complete, institutional Macro Intelligence Dossier for storage in
    FundamentalBrief.content_markdown, presenting all Stage 1 dimensions clearly for
    the Dashboard (BriefTab) and Telegram (/brief).
    """
    ts_str = now.strftime("%Y-%m-%d %H:%M UTC")
    valid_str = valid_until.strftime("%Y-%m-%d %H:%M UTC") if valid_until else "12 hours"
    regime = (
        sanitize_macro_regime(inp.get("macro_regime", "mixed"), inp.get("macro_narrative")).upper().replace("-", "_")
    )
    sentiment = str(inp.get("risk_sentiment", "mixed")).upper()
    conf = float(inp.get("confidence", 0.5) or 0.5)
    conf_str = f"{conf:.0%}"
    liquidity = str(inp.get("systemic_liquidity_trend", "neutral") or "neutral").upper()
    yield_curve = str(inp.get("yield_curve_regime", "neutral") or "neutral").upper()

    doc = [
        "# 🏛️ MONIKA MACRO INTELLIGENCE DOSSIER // STAGE 1 BRIEF",
        f"**Session Timestamp**: `{ts_str}` | **Validity**: Until `{valid_str}`",
        f"**Macro Regime**: `{regime}` | **Risk Sentiment**: `{sentiment}` | **Overall Confidence**: `{conf_str}`",
        f"**Systemic Net Liquidity**: `{liquidity}` | **Yield Curve Regime**: `{yield_curve}`",
        "",
        "---",
        "",
        "## 1. Executive Macroeconomic Narrative & Causality Transmission",
        (inp.get("macro_narrative") or "(No narrative recorded)").strip(),
        "",
        "---",
        "",
    ]

    bias_map = inp.get("currency_bias") or {}
    conf_map = inp.get("currency_confidence") or {}
    inval_map = inp.get("invalidation_conditions") or {}
    if bias_map and isinstance(bias_map, dict):
        doc.append("## 2. Currency Bias & Attractiveness Matrix")
        doc.append("| Currency | Directional Bias | Confidence | Invalidation Trigger Level |")
        doc.append("| :--- | :---: | :---: | :--- |")
        priority_order = ["USD", "EUR", "GBP", "JPY", "AUD", "XAU", "OIL", "BTC"]
        seen_ccy = set()
        for ccy in priority_order:
            if ccy in bias_map:
                seen_ccy.add(ccy)
                b_val = str(bias_map[ccy]).upper()
                c_val = f"{float(conf_map.get(ccy, conf)):.0%}" if ccy in conf_map else "N/A"
                i_val = str(inval_map.get(ccy, "-"))
                doc.append(f"| **{ccy}** | `{b_val}` | {c_val} | {i_val} |")
        for ccy, b in bias_map.items():
            if ccy not in seen_ccy:
                b_val = str(b).upper()
                c_val = f"{float(conf_map.get(ccy, conf)):.0%}" if ccy in conf_map else "N/A"
                i_val = str(inval_map.get(ccy, "-"))
                doc.append(f"| **{ccy}** | `{b_val}` | {c_val} | {i_val} |")
        doc.append("")
        doc.append("---")
        doc.append("")

    matrix = inp.get("per_asset_macro_matrix") or {}
    pi_scores = inp.get("asset_priced_in_scores") or {}
    if matrix and isinstance(matrix, dict):
        doc.append("## 3. Per-Asset Macro Transmission Matrix")
        doc.append("| Asset | Bias | Priced-In | Structural Driver | Tactical Catalyst | Invalidation Level |")
        doc.append("| :--- | :---: | :---: | :--- | :--- | :--- |")
        for sym, item in matrix.items():
            if isinstance(item, dict):
                d_bias = str(item.get("directional_bias", "neutral")).upper()
                pi_s = f"{pi_scores.get(sym)}/10" if sym in pi_scores else "-"
                struct = str(item.get("structural_driver", "-"))
                tact = str(item.get("tactical_catalyst", "-"))
                inval = str(item.get("invalidation_level", "-"))
                doc.append(f"| **{sym}** | `{d_bias}` | {pi_s} | {struct} | {tact} | {inval} |")
        doc.append("")
        doc.append("---")
        doc.append("")

    priced_in = inp.get("priced_in_assessment") or {}
    if priced_in and isinstance(priced_in, dict):
        doc.append("## 4. Market Pricing, Expectations & Positioning")
        if priced_in.get("dominant_driver"):
            doc.append(f"- **Dominant Market Driver**: {priced_in['dominant_driver']}")
        p_score = priced_in.get("priced_in_score", "N/A")
        stn_risk = str(priced_in.get("sell_the_news_risk", "N/A")).upper()
        doc.append(f"- **Priced-In Composite**: `{p_score}/10` | **Sell-The-News Exhaustion Risk**: `{stn_risk}`")
        if priced_in.get("fedwatch_shift_summary"):
            doc.append(f"- **FedWatch Trajectory Shift**: {priced_in['fedwatch_shift_summary']}")
        cot_p = priced_in.get("cot_positioning_percentile")
        ret_p = priced_in.get("retail_sentiment_percentile")
        if cot_p is not None or ret_p is not None:
            doc.append(
                f"- **Positioning Percentiles**: COT Non-Commercial: `{cot_p if cot_p is not None else 'N/A'}%` | "
                f"Retail Sentiment: `{ret_p if ret_p is not None else 'N/A'}%`"
            )
        if priced_in.get("upcoming_event_context"):
            doc.append(f"- **Upcoming Catalyst Context**: {priced_in['upcoming_event_context']}")
        doc.append("")
        doc.append("---")
        doc.append("")

    counter_thesis = inp.get("strongest_counter_thesis")
    if counter_thesis:
        doc.append("## 5. Strongest Counter-Thesis & Falsification Conditions")
        doc.append(f"> ⚠️ **Falsification Argument**:  \n> {str(counter_thesis).strip()}")
        doc.append("")

    return "\n".join(doc)


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
            errors.append(
                f"MISSING_CURRENCY_BIAS: Parameter 'currency_bias' must be a JSON object with explicit "
                f"'bullish', 'bearish', or 'neutral' values for all 8 single-code keys. "
                f"Missing keys: {', '.join(missing_bias)}."
            )

        non_neutral_currencies = [c for c, b in bias.items() if b != "neutral"]
        neutral_currencies = [c for c, b in bias.items() if b == "neutral"]
        invalidation_map = inp.get("invalidation_conditions", {})
        missing_invalidation = [c for c in non_neutral_currencies if c not in invalidation_map]
        if missing_invalidation:
            errors.append(
                f"MISSING_INVALIDATION: Directional currencies (non-neutral) MUST specify explicit invalidation_conditions. Missing conditions for: {missing_invalidation}."
            )
        is_weekend_now = clock.now().weekday() >= 5
        if not is_weekend_now and len(neutral_currencies) >= 6:
            missing_neutral_inv = [c for c in neutral_currencies if c not in invalidation_map]
            if len(missing_neutral_inv) > 2:
                errors.append(
                    f"LAZY_NEUTRAL_BIAS_EVASION: Classified >= 6 currencies as 'neutral' ({neutral_currencies}) "
                    f"without specifying invalidation_conditions (range breakout thresholds) for {missing_neutral_inv}. "
                    f"A neutral stance is not a shortcut to bypass boundary validation: provide explicit range parameters in invalidation_conditions."
                )

        weak_invalidation = []
        for c in non_neutral_currencies:
            cond_text = str(invalidation_map.get(c, ""))
            has_number = any(ch.isdigit() for ch in cond_text)
            if cond_text and (len(cond_text) < 40 or not has_number):
                weak_invalidation.append(c)
        if weak_invalidation:
            errors.append(
                f"WEAK_INVALIDATION: invalidation_conditions for {weak_invalidation} are too generic "
                f"or lack specific price levels/numerical data (REQUIRED: >= 40 characters with concrete numerical anchors). "
                f"Institutional standard example: 'Bearish {weak_invalidation[0]} bias invalidated if price breaks above 78.50 OR inventory draw exceeds 3.5M barrels'."
            )

        confidence_map = inp.get("currency_confidence", {})
        missing_conf = [c for c in non_neutral_currencies if c not in confidence_map]
        if missing_conf:
            errors.append(
                f"MISSING_CONFIDENCE: Directional currencies MUST specify currency_confidence (0.0-1.0). Missing for: {missing_conf}."
            )

        if not inp.get("strongest_counter_thesis"):
            errors.append("MISSING_COUNTER_THESIS: A substantiated strongest_counter_thesis is REQUIRED.")
        elif len(inp.get("strongest_counter_thesis", "")) < 50:
            errors.append(
                "WEAK_COUNTER_THESIS: strongest_counter_thesis is too brief (REQUIRED: >= 50 characters). Detail specific macro data catalysts and falsifiable risk scenarios that would invalidate your thesis."
            )

        # NEW P2-4: Check priced_in_assessment completeness
        pi = inp.get("priced_in_assessment", {})
        if not pi:
            errors.append(
                "MISSING_PRICED_IN: Parameter 'priced_in_assessment' cannot be empty. Ground analysis in empirical data from get_cot_report and get_fedwatch_probabilities."
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
                    "INCOMPLETE_PRICED_IN: Must include verified quantitative positioning metrics (e.g. cot_positioning_percentile or retail_sentiment_percentile) retrieved from analytical tools."
                )
            if not pi.get("sell_the_news_risk"):
                errors.append(
                    "INCOMPLETE_PRICED_IN: Parameter 'sell_the_news_risk' is required ('high', 'medium', 'low', or 'not_applicable')."
                )

            # Phase 2.6: Temper currency_confidence when market is heavily priced in
            if pi.get("priced_in_score", 0) >= 8:
                dominant_driver_text = (pi.get("dominant_driver") or "").upper()
                currency_conf = inp.get("currency_confidence", {})
                for cur, conf in currency_conf.items():
                    if cur in dominant_driver_text and conf > 0.65:
                        errors.append(
                            f"PRICED_IN_CONFIDENCE_MISMATCH: priced_in_score={pi.get('priced_in_score')} (fully priced in) for driver citing {cur}, but currency_confidence[{cur}]={conf} remains elevated. When market expectations are largely priced in, directional conviction must be tempered (<= 0.60) UNLESS explicitly justified by an unpriced catalyst in macro_narrative."
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
                if currency not in justification_map or len(just) < 15 or (not has_number and not weekend_ref):
                    errors.append(
                        f"ANCHORING_RISK: {currency} bias ('{bias}') has persisted across >= 4 consecutive cycles. "
                        f"bias_continuity_justification for {currency} is missing, too brief, or lacks updated numerical evidence "
                        f"(REQUIRED: >= 15 characters citing price levels, %, dates, or yield basis points). "
                        f'Example: bias_continuity_justification={{"{currency}": "{currency} {bias} bias maintained as 2026-08-22 print confirms 102.50 support holding and yields up 5 bps"}}.'
                    )
        return errors

    async def _validate_key_data_points(self, inp: dict) -> list[str]:
        """Cross-checks quantitative figures restated by the model against empirical tool outputs,

        preempting data misreads and hallucinations before propagation across the pipeline.
        """
        errors = []
        kdp = inp.get("key_data_points_used", {})
        if not kdp:
            return ["MISSING_DATA_ANCHORS: key_data_points_used is required."]
        try:
            real_dxy = await self.execute("get_dxy", {"force_refresh": True})
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
                        f"DATA_MISMATCH: Restated DXY trend='{kdp.get('dxy_trend_5d')}', but verified empirical tool "
                        f"output indicates trend_5d='{real_trend}'. Re-verify get_dxy() output before resubmission."
                    )
        except Exception:
            pass
        try:
            real_vix = await self.execute("get_vix", {"force_refresh": True})
            if not real_vix.get("error"):
                real_close = (real_vix.get("latest") or {}).get("close")
                claimed_close = kdp.get("vix_close")
                if real_close is not None and claimed_close is not None:
                    try:
                        rc = float(real_close)
                        cc = float(claimed_close)
                        if rc > 5.0 and abs(cc - rc) > 1.0:
                            errors.append(
                                f"DATA_MISMATCH: Claimed VIX={claimed_close}, but latest verified VIX "
                                f"close={real_close}. Re-verify reading from get_vix()."
                            )
                    except TypeError, ValueError:
                        pass
        except Exception:
            pass
        try:
            if kdp.get("fedwatch_dominant_pct") is not None:
                real_fw = await self.execute("get_fedwatch_probabilities", {"force_refresh": True})
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
                                f"DATA_MISMATCH: Kamu menyatakan FedWatch dominant={claimed}% (Claimed FedWatch dominant={claimed}%), "
                                f"but nearest verified empirical probability terdekat={closest_prob}%. Re-verify get_fedwatch_probabilities() output."
                            )
        except Exception:
            pass
        try:
            if kdp.get("fedwatch_repricing_delta_pct") is not None:
                real_fw_comp = await self.execute(
                    "get_fedwatch_probabilities", {"compare_hours_ago": 24, "force_refresh": True}
                )
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
                                f"DATA_MISMATCH: Claimed fedwatch_repricing_delta_pct={claimed_delta}%, but nearest empirical delta={min(all_deltas, key=lambda d: abs(claimed_delta - d))}%. Re-verify output from fedwatch.comparisons."
                            )
        except Exception:
            pass
        try:
            tol_yield_bp = (
                self.settings.get("data_quality", {}).get("key_data_tolerance", {}).get("treasury_10y_yield_bp", 15.0)
            )
            if tol_yield_bp is not None and kdp.get("treasury_10y_yield_pct") is not None:
                real_yields = await self.execute("get_treasury_yields", {"force_refresh": True})
                real_10y_list = real_yields.get("yields_by_tenor", {}).get("10Y", [])
                if real_10y_list:
                    real_10y = real_10y_list[0].get("yield_pct")
                    claimed_10y = float(kdp.get("treasury_10y_yield_pct"))
                    if real_10y is not None and abs(claimed_10y - real_10y) * 100 > float(tol_yield_bp):
                        errors.append(
                            f"DATA_MISMATCH: Claimed 10Y yield={claimed_10y}%, but verified empirical yield={real_10y}%. "
                            f"Re-verify reading from get_treasury_yields()."
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
        fedwatch_res = await self.execute(
            "get_fedwatch_probabilities", {"compare_hours_ago": 24, "force_refresh": True}
        )
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
                await self.execute(
                    "get_price_momentum",
                    {"symbol": proxy_symbol, "timeframe": "H4", "period": 20, "force_refresh": True},
                )
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
                    f"[{ccy}] Quantitative baseline indicates priced-in condition ({'; '.join(baseline['reasons'])}), but declared priced_in_score={declared_pi} is subdued."
                )
        return warnings

    async def _tool_submit_fundamental_brief(self, inp: dict) -> dict:
        """Persists institutional macro narrative and currency biases to DB (marking completion of Stage 1)."""
        inp.pop("submit_attempts", None)  # Tolerate supplementary LLM arguments

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

        raw_auto_pi = inp.get("automated_priced_in") if isinstance(inp, dict) else None
        has_raw_regime = isinstance(inp, dict) and "macro_regime" in inp
        raw_narr = inp.get("macro_narrative") if isinstance(inp, dict) else None
        sanitized_regime = (
            sanitize_macro_regime(inp.get("macro_regime"), raw_narr)
            if has_raw_regime
            else sanitize_macro_regime("mixed", raw_narr)
        )
        if isinstance(inp, dict) and has_raw_regime:
            inp["macro_regime"] = sanitized_regime

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

        inp["macro_regime"] = (
            sanitized_regime
            if has_raw_regime
            else sanitize_macro_regime(inp.get("macro_regime"), inp.get("macro_narrative"))
        )
        inp["per_asset_macro_matrix"] = reconcile_fx_pair_macro_matrix(
            inp.get("currency_bias", {}),
            inp.get("per_asset_macro_matrix", {}),
        )

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
                f"MISSING_INVALIDATION: The following currencies carry directional biases but lack "
                f"invalidation_conditions: {missing_invalidation}. Every directional thesis "
                f"MUST establish a falsifiable invalidation boundary."
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
                    "CONTRADICTION_UNRESOLVED_NO_EVIDENCE: contradiction_existed=True, but strongest_counter_thesis lacks verifiable numerical evidence (price levels, percentages, dates, basis points) resolving the contradiction."
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
            logger.warning(f"Brief rejected (incomplete, attempt {self.submit_attempts}): {completeness_errors}")
            return {
                "status": "rejected",
                "errors": completeness_errors,
                "error_classification": "INCOMPLETE_ANALYSIS",
                "attempt": self.submit_attempts,
                "guidance": (
                    "Your brief is incomplete and CANNOT be force-accepted. "
                    "Fix EVERY listed error above and resubmit via submit_fundamental_brief."
                ),
            }

        from monika.application.protocol.brief_contamination_guard import BriefContaminationGuard

        brief_data_for_check = {
            "currency_bias": inp.get("currency_bias", {}),
            "risk_sentiment": inp.get("risk_sentiment", "mixed"),
            "confidence": inp.get("confidence", 0.5),
        }
        is_safe, contamination_issues, contamination_risk = await BriefContaminationGuard.validate_brief_integrity(
            self.session, brief_data_for_check, self.settings
        )
        CONTAMINATION_HARD_BLOCK_THRESHOLD = 0.4  # Hard block ceiling lowered from 0.5 to 0.4 for strict risk isolation

        if not is_safe and contamination_risk >= CONTAMINATION_HARD_BLOCK_THRESHOLD:
            self.submit_attempts += 1
            logger.warning(
                f"Brief REJECTED (contamination_risk={contamination_risk:.2f}, attempt {self.submit_attempts}): "
                f"{contamination_issues}"
            )
            return {
                "status": "rejected",
                "errors": contamination_issues,
                "error_classification": "INTERNAL_CONTRADICTION",
                "attempt": self.submit_attempts,
                "guidance": (
                    "The brief contains unresolved internal contradictions (see errors above) "
                    "and cannot be accepted (fail-closed safety constraint). "
                    "You MUST harmonize currency_bias with risk_sentiment or explicitly articulate "
                    "in macro_narrative which data source is authoritative and WHY before resubmitting."
                ),
            }
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

        # ── DETERMINISTIC CONFIDENCE CEILING (Programmatic enforcement of Checkpoint 3) ──
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

        # Empirical Priced-In Cap when automated_priced_in baseline is available and <= 4 without imminent event
        auto_pi_source = raw_auto_pi
        if auto_pi_source is None:
            cand_self = getattr(self, "automated_priced_in", None)
            if isinstance(cand_self, (dict, int, float)) and not isinstance(cand_self, bool):
                auto_pi_source = cand_self
        if auto_pi_source is None:
            ctx_d = getattr(self, "context_data", None)
            if isinstance(ctx_d, dict):
                cand_ctx = ctx_d.get("automated_priced_in")
                if isinstance(cand_ctx, (dict, int, float)) and not isinstance(cand_ctx, bool):
                    auto_pi_source = cand_ctx
        if auto_pi_source is not None:
            has_imminent_2h = bool(inp.get("_upcoming_event_currencies"))
            inp["asset_priced_in_scores"] = cap_empirical_priced_in_scores(
                inp.get("asset_priced_in_scores", {}),
                auto_pi_source,
                has_imminent_high_impact=has_imminent_2h,
            )

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

        dossier_markdown = format_macro_intelligence_dossier(inp, now=now, valid_until=valid_until)

        brief = FundamentalBrief(
            generated_at=now,
            valid_until=valid_until,
            content_markdown=dossier_markdown,
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
                    "macro_regime": sanitize_macro_regime(inp.get("macro_regime", "mixed"), inp.get("macro_narrative")),
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
                        f"[FLIP-FLOP WARNING] {w} — Rapidly reversing directional bias cycle-to-cycle without fresh macroeconomic catalysts risks whipsaw losses. Provide robust institutional justification or maintain a NEUTRAL stance."
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
