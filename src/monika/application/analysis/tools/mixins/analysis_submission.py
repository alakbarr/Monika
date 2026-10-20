# ==============================================================================
# File: application/analysis/tools/mixins/analysis_submission.py
# ==============================================================================

"""
Asset Analysis Submission Mixin for ToolExecutor.
Encapsulates 14-factor confluence verification, monotonic risk checks,
database persistence of AssetAnalysis records, and execution triggering.
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
from monika.application.analysis.schemas.schemas import SubmitAssetAnalysisSchema
from monika.application.analysis.tools.mixins.base import (
    FACTOR_CONSISTENCY_TOLERANCE,
    FACTOR_POINT_MAP,
    FACTORS_WITH_VARIABLE_WEIGHT,
    _ToolExecutorMixinBase,
    logger,
)
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    COTReport,
    FundamentalBrief,
    PriceOHLCV,
    RiskState,
    SystemConfig,
    TechnicalIndicator,
    TradeTrigger,
    UserMarketIntel,
    VIXData,
)


class AssetAnalysisSubmissionMixin(_ToolExecutorMixinBase):
    """Mixin providing full AssetAnalysis validation, confluence scoring, and persistence."""

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

                    # Check: Stage 2 asset score jauh lebih tinggi dari Stage 1 macro score
                    if submitted_pi >= 8 and brief_pi_score <= 4 and decision in ("buy", "sell"):
                        if not (
                            priced_in_override
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
                        if priced_in_override and all(
                            priced_in_override.get(k)
                            for k in ["override_reason", "why_stage1_wrong", "post_event_evidence"]
                        ):
                            # Override diterima - log untuk audit
                            rationale = (
                                rationale
                                + f"\n\n[SYSTEM: Priced-in override accepted with explicit justification: {_j.dumps(priced_in_override)}]"
                            )
                        else:
                            errors.append(
                                f"PRICED-IN CONFLICT HARD BLOCKED: Stage 1 priced_in_score={brief_pi_score}. To override, you must fill priced_in_override_justification with all 3 required fields. Keyword-based justification in rationale is NOT accepted."
                            )

                    # IMP-6: Tighten gap tolerance 3 → 2
                    elif abs(brief_pi_score - submitted_pi) >= 2 and decision in ("buy", "sell"):
                        direction_of_conflict = "underestimating" if submitted_pi < brief_pi_score else "overestimating"
                        errors.append(
                            f"PRICED-IN ASSESSMENT CONFLICT: Stage 1 macro assessment={brief_pi_score}/10, "
                            f"your asset-specific assessment={submitted_pi}/10 (gap={abs(brief_pi_score - submitted_pi)}). "
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
                            and len(str(spec_adj.get("resolution_justification") or "").strip()) >= 40
                        )

                    if relevant_conf >= 0.55 and not has_valid_adjudication:
                        errors.append(
                            f"CONTRA_MACRO_HARD_REJECT: Keputusan {decision.upper()} untuk {symbol} secara langsung "
                            f"menentang bias makro Stage 1 ({contra_str}) dengan confidence ({relevant_conf:.2f} >= 0.55). "
                            f"Trading melawan makro dilarang kecuali Anda mengisi field 'specialist_adjudication' secara lengkap "
                            f"(conflict_detected=true, resolution_path in ('override_macro', 'cancel_setup', 'hedged_entry', 'scale_out'), "
                            f"dan justifikasi pembatalan level harga struktural minimal 40 karakter)."
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
                        _reconciled = any(
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

    async def _tool_submit_asset_analysis(self, inp: dict) -> dict:
        """Menyimpan analisis per aset dan memicu eksekusi."""
        inp.pop("submit_attempts", None)  # Toleransi tambahan argumen dari LLM

        if isinstance(inp, dict):
            for wrapper in ("input", "analysis", "data", "parameters", "args", "payload", "asset_analysis"):
                if wrapper in inp and isinstance(inp[wrapper], dict) and len(inp) == 1:
                    inp = inp[wrapper]
                    break
            self._resolve_symbol(inp)
            if not inp.get("symbol") and self.symbol:
                inp["symbol"] = self.symbol

        try:
            validated_data = SubmitAssetAnalysisSchema.model_validate(inp)
            inp = validated_data.model_dump(mode="json")  # Overwrite inp with clean coerced data
        except ValidationError as e:
            self.submit_attempts += 1
            error_msgs = [f"Field '{'.'.join(str(x) for x in err['loc'])}': {err['msg']}" for err in e.errors()]
            logger.warning(f"Pydantic validation failed for submit_asset_analysis: {error_msgs}")
            return {
                "status": "validation_failed",
                "errors": error_msgs,
                "error_classification": "SCHEMA_ERROR",
                "guidance": "Please fix the schema formatting errors above and call the tool again.",
            }

        symbol = str(self._resolve_symbol(inp) or inp.get("symbol") or "")
        decision = str(inp.get("decision") or "")
        confidence = float(inp.get("confidence", 0.5))
        rationale = inp.get("rationale", "")
        reeval_trigger = inp.get("reevaluation_trigger")
        entry_price: Optional[float] = None
        sl_price: Optional[float] = None
        tp_price: Optional[float] = None
        atr_value_for_validation: Optional[float] = None
        context_snapshot_id: Optional[str] = None
        context_cds_score: Optional[float] = None
        min_sl_from_atr: float = 0.0

        # Validation rules per spec §7.2
        errors = []

        # === AUTOMATED PRICED-IN ENFORCEMENT ===
        # Retrieve automated priced-in score from SystemConfig
        try:
            auto_pi_key = f"auto_pi_score_{symbol}"
            auto_pi_cfg = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == auto_pi_key))
            ).scalar_one_or_none()

            if auto_pi_cfg and auto_pi_cfg.value:
                import json

                auto_pi_data = json.loads(auto_pi_cfg.value)
                auto_pi_score = auto_pi_data.get("total_auto", 0)
                pi_freshness = auto_pi_data.get("computed_at")

                # Check freshness (must be within 2 hours)
                if pi_freshness:
                    computed_dt = datetime.fromisoformat(pi_freshness)
                    if computed_dt.tzinfo is None:
                        computed_dt = computed_dt.replace(tzinfo=timezone.utc)
                    age_minutes = (clock.now() - computed_dt).total_seconds() / 60

                    if age_minutes < 120:  # Fresh data
                        submitted_pi = inp.get("priced_in_score", 0) or 0

                        # Hard block: automated >= 8 means trade blocked regardless of AI assessment
                        if auto_pi_score >= 8 and decision in ("buy", "sell"):
                            errors.append(
                                f"AUTO-PI ENFORCEMENT BLOCK: Automated priced-in calculation "
                                f"scored {auto_pi_score}/9 (FedWatch+COT+Momentum). "
                                f"Score >= 8 indicates event is fully priced in. "
                                f"Decision must be WAIT. Cannot override without explicit "
                                f"priced_in_override_justification with all 3 fields."
                            )

                        # Soft warning: if model's score deviates > 3 from automated
                        elif abs(submitted_pi - auto_pi_score) > 3 and decision in ("buy", "sell"):
                            logger.warning(
                                f"[{symbol}] Priced-in score discrepancy: "
                                f"AI={submitted_pi}, Automated={auto_pi_score}. "
                                f"Gap > 3 recorded for audit."
                            )
        except Exception as pi_enforcement_err:
            logger.warning(f"Auto-PI enforcement check failed (non-fatal): {pi_enforcement_err}")

        # Require confluence_score and priced_in_score for actionable decisions
        if decision in ("buy", "sell"):
            # Enforce passing verification evidence from VerificationEvidenceLedger
            ledger = getattr(self, "verification_ledger", None)
            if ledger is not None and not ledger.has_passed_evidence(symbol):
                return {
                    "status": "rejected_verification_required",
                    "errors": [
                        f"TRADE VERIFICATION GATE BLOCKED: You recommended {decision.upper()} {symbol}, "
                        f"but no passing RiskGate or PositionSize verification evidence was recorded in this cycle. "
                        f"You MUST call 'calculate_position_size' or 'get_optimal_intraday_levels' to compute and verify "
                        f"lot sizing, stop-loss, and take-profit bounds before submitting analysis."
                    ],
                    "error_classification": "UNVERIFIED_TRADE_PROPOSAL",
                    "guidance": "Call 'calculate_position_size' now with exact parameters before calling submit_asset_analysis.",
                }

            conf_score = inp.get("confluence_score")
            if conf_score is None:
                errors.append(
                    "confluence_score REQUIRED for buy/sell. "
                    "Fill the CONFLUENCE SCORECARD in your system prompt "
                    "and submit the TOTAL RAW SCORE. This field is mandatory for auto-execute."
                )
            elif conf_score < 5:
                errors.append(
                    f"confluence_score {conf_score} is impossibly low for a buy/sell decision. "
                    f"Score < 5 should result in 'avoid' decision, not 'buy'/'sell'."
                )
            if inp.get("priced_in_score") is None:
                errors.append("priced_in_score is REQUIRED for buy/sell decision. Must provide a valid 1-10 score.")

            # Validasi confluence_factors (Fase 6 Task 3)
            factors = inp.get("confluence_factors", [])
            valid_factors = {
                "fundamental_bias",
                "dxy_confirms",
                "d1_trend",
                "rsi_neutral",
                "near_fvg",
                "near_order_block",
                "in_ote_zone",
                "near_sr_zone",
                "cot_aligned",
                "vix_ok",
                "post_event_entry",
                "session_prime",
                "liquidity_sweep_confirmed",
                "microstructure_ok",
                "microstructure_confirmed",
                "historical_pattern_consensus",
                "pattern_consensus",
                "quant_strategy_edge",
                "rr_ratio_bonus",
                "adr_target_bonus",
            }
            invalid_factors = [f for f in factors if f not in valid_factors]
            if invalid_factors:
                errors.append(
                    f"Invalid confluence_factors detected: {invalid_factors}. Only use exact IDs from the prompt."
                )

            if inp.get("confluence_factors") and inp.get("confluence_score") is not None:
                declared_factors = inp["confluence_factors"]
                effective_point_map = await self._get_effective_factor_point_map()
                expected_from_factors = sum((effective_point_map.get(f, 0) for f in declared_factors))
                claimed_score = inp["confluence_score"]
                gap = abs(claimed_score - expected_from_factors)
                effective_tolerance = FACTOR_CONSISTENCY_TOLERANCE
                if any(f in FACTORS_WITH_VARIABLE_WEIGHT for f in declared_factors):
                    effective_tolerance += 1
                # Widen tolerance for bonus factors that stack beyond core 14
                BONUS_FACTORS_BEYOND_CORE_14 = {
                    "liquidity_sweep_confirmed": 2,
                    "session_prime": 1,
                    "post_event_entry": 0,
                    "quant_strategy_edge": 1,
                    "rr_ratio_bonus": 1,
                    "adr_target_bonus": 1,
                }
                effective_tolerance += sum(v for f, v in BONUS_FACTORS_BEYOND_CORE_14.items() if f in declared_factors)
                if gap > effective_tolerance:
                    errors.append(
                        f"FACTOR_SCORE_MISMATCH: confluence_factors {declared_factors} secara matematis "
                        f"bernilai {expected_from_factors} poin, tapi confluence_score yang disubmit={claimed_score} "
                        f"(selisih {gap} > toleransi {FACTOR_CONSISTENCY_TOLERANCE}). Periksa ulang scorecard Anda — "
                        f"daftar confluence_factors harus mencerminkan skor yang Anda klaim."
                    )

        # === CONFLUENCE OVERLAP DETECTION ===
        factors = inp.get("confluence_factors") or []
        if factors and decision in ("buy", "sell"):
            zone_factors = {"near_fvg", "near_order_block", "in_ote_zone", "near_sr_zone"}
            active_zone_factors = set(factors) & zone_factors

            if len(active_zone_factors) >= 2:
                # Potential overlap: 2+ zone factors active simultaneously
                # These often describe the same physical zone
                zone_factor_score = sum(
                    [
                        2 if "near_fvg" in active_zone_factors else 0,
                        2 if "near_order_block" in active_zone_factors else 0,
                        1 if "in_ote_zone" in active_zone_factors else 0,
                        1 if "near_sr_zone" in active_zone_factors else 0,
                    ]
                )

                confluence_score = inp.get("confluence_score", 0) or 0
                effective_score = confluence_score

                if zone_factor_score >= 3:
                    # Proporsional cap: 1st zone full points, subsequent zones heavily discounted
                    effective_zone_contribution = min(
                        max(2, 2 + (len(active_zone_factors) - 1) * 0.5), zone_factor_score
                    )
                    # FIX: Cap deduction at -1 point (multiple zones = genuine confluence, not pure redundancy)
                    score_reduction = min(1, int(zone_factor_score - effective_zone_contribution))

                    if score_reduction > 0:
                        effective_score = confluence_score - score_reduction

                        logger.warning(
                            f"[{symbol}] Zone overlap cap applied: "
                            f"claimed={confluence_score}, effective={effective_score} "
                            f"(zone factors {active_zone_factors} likely describe same area, "
                            f"zone contribution capped at {effective_zone_contribution} pts)"
                        )

                        # Update the submitted score to effective score
                        inp["confluence_score"] = effective_score

                    # Check if effective score still meets threshold
                    min_confluence = (
                        getattr(self, "settings", {}).get("trading", {}).get("auto_execute_min_confluence", 7)
                    )
                    if effective_score < min_confluence:
                        errors.append(
                            f"Zone overlap correction: effective confluence score "
                            f"{effective_score} < threshold {min_confluence}. "
                            f"Multiple zone factors ({active_zone_factors}) likely describe "
                            f"the same price area. Capped contribution: "
                            f"{zone_factor_score} → {effective_zone_contribution} pts."
                        )

        if factors and "fundamental_bias" in factors and decision in ("buy", "sell"):
            try:
                from monika.application.protocol.context_coherence import SYMBOL_CURRENCY_MAP

                pair_info = SYMBOL_CURRENCY_MAP.get(symbol)
                if pair_info:
                    brief_row_check = (
                        await self.session.execute(
                            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                        )
                    ).scalar_one_or_none()
                    if brief_row_check and brief_row_check.structured_json:
                        import json

                        b_data_check = json.loads(brief_row_check.structured_json)
                        conf_map = b_data_check.get("currency_confidence", {})
                        base_conf = conf_map.get(pair_info["base"], 0.5)
                        quote_conf = conf_map.get(pair_info["quote"], 0.5)
                        relevant_conf = max(base_conf, quote_conf)
                        if relevant_conf < 0.55:
                            errors.append(
                                f"FUNDAMENTAL_BIAS_LOW_CONFIDENCE: Kamu klaim faktor 'fundamental_bias' "
                                f"(+2 poin) tapi currency_confidence Stage 1 hanya {relevant_conf:.2f} "
                                f"(< 0.55 threshold). Hapus faktor ini dari confluence_factors, atau berikan "
                                f"konfirmasi independen lain (DXY, teknikal) yang menggantikannya."
                            )
            except Exception as e:
                logger.debug(f"fundamental_bias confidence check failed (non-fatal): {e}")

        if "cot_aligned" in factors and decision in ("buy", "sell"):
            _SYMBOL_TO_COT_LOCAL = {
                "XAUUSD": "088691",
                "EURUSD": "099741",
                "GBPUSD": "096742",
                "USDJPY": "097741",
                "AUDUSD": "232741",
            }
            cot_code = _SYMBOL_TO_COT_LOCAL.get(symbol)
            if cot_code:
                cot_row = (
                    await self.session.execute(
                        select(COTReport)
                        .where(COTReport.market_code == cot_code)
                        .order_by(COTReport.report_date.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if not cot_row:
                    errors.append(
                        "COT_ALIGNED_NO_DATA: factor 'cot_aligned' diklaim (+1) tapi tidak ada data COT untuk simbol ini. Hapus faktor ini."
                    )
                else:
                    days_old = (
                        clock.now()
                        - (
                            cot_row.report_date.replace(tzinfo=timezone.utc)
                            if cot_row.report_date.tzinfo is None
                            else cot_row.report_date
                        )
                    ).days
                    if days_old > 10:
                        errors.append(
                            f"COT_ALIGNED_STALE: factor 'cot_aligned' diklaim (+1) tapi data COT berumur {days_old} hari (>10 hari, dianggap tidak reliable). Hapus faktor ini dari confluence_factors."
                        )

        if "vix_ok" in factors and decision in ("buy", "sell"):
            vix_row = (
                await self.session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
            ).scalar_one_or_none()
            if vix_row and vix_row.close >= 20:
                errors.append(
                    f"VIX_OK_INVALID: factor 'vix_ok' diklaim (+1) tapi VIX aktual={vix_row.close:.1f} (>=20, bukan kondisi 'ok'). Hapus faktor ini."
                )

        if "liquidity_sweep_confirmed" in factors and decision in ("buy", "sell"):
            try:
                from monika.application.analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep

                sweep_check = await detect_liquidity_sweep(self.session, symbol, self.settings)
                if not (sweep_check.get("structure_confirmed") and sweep_check.get("valid_for_direction") == decision):
                    errors.append(
                        "LIQUIDITY_SWEEP_UNCONFIRMED: factor claimed (+2) but deterministic check "
                        "does not confirm a validated sweep+structure-shift for this direction."
                    )
            except Exception as e:
                logger.warning(f"Liquidity sweep check failed (fail-open): {e}")

        try:
            edge_cfg = self.settings.get("trading", {}).get("edge_strategy", {})
            if edge_cfg.get("macro_bias", {}).get("enabled", True):
                from monika.application.analysis.calculators.macro_bias_filter import evaluate_macro_alignment

                macro_check = await evaluate_macro_alignment(self.session, symbol, decision, self.settings)
                if macro_check.get("strong_conflict"):
                    logger.warning(f"MACRO BIAS WARNING for {symbol}: {'; '.join(macro_check['reasons'])}")
            if edge_cfg.get("volatility_regime", {}).get("enabled", True):
                from monika.application.analysis.calculators.regime_classifier import compute_bollinger_donchian_chop

                chop = await compute_bollinger_donchian_chop(self.session, symbol, "H4", self.settings)
                if chop.get("chop_block"):
                    entry_cond = inp.get("entry_condition") or {}
                    cond_type = ""
                    cond_price = None
                    if isinstance(entry_cond, dict):
                        cond_type = str(entry_cond.get("type", "")).lower()
                        cond_price = (
                            entry_cond.get("price")
                            or entry_cond.get("entry_price")
                            or entry_cond.get("price_high")
                            or entry_cond.get("price_low")
                            or entry_cond.get("level")
                            or inp.get("entry_price")
                        )
                    elif isinstance(entry_cond, str):
                        cond_type = entry_cond.lower()
                        cond_price = inp.get("entry_price") or inp.get("stop_loss")

                    is_limit_type = any(
                        t in cond_type
                        for t in (
                            "limit",
                            "order_block",
                            "ob",
                            "fvg",
                            "pullback",
                            "pending",
                            "structural",
                            "rejection",
                            "breakout",
                            "sweep",
                        )
                    )
                    conf_score = int(inp.get("confluence_score", 0) or 0)
                    is_structural_limit = is_limit_type and bool(cond_price) and conf_score >= 6
                    if is_structural_limit:
                        logger.info(
                            f"[{symbol}] Volatility squeeze detected ({chop.get('reason')}), "
                            f"allowing structural entry ({cond_type}) with confluence {conf_score}."
                        )
                    else:
                        errors.append(
                            f"VOLATILITY REGIME GATE: {chop.get('reason')} — market order in squeeze is prone to chop. "
                            f"Specify a structural limit/pullback/breakout entry condition at a confirmed level (OB/FVG/sweep) or submit WAIT."
                        )
        except Exception as e:
            logger.warning(f"Mechanical gates failed (fail-open): {e}")

        if decision in ("buy", "sell"):
            if not inp.get("entry_condition"):
                errors.append("entry_condition is required for buy/sell decision")
            if inp.get("stop_loss") is None:
                errors.append("stop_loss is required for buy/sell decision")
            if inp.get("take_profit") is None:
                errors.append("take_profit is required for buy/sell decision")
            if not inp.get("invalidation"):
                errors.append(
                    "invalidation rule is required for buy/sell decision. Must specify precise price level and direction."
                )

            # TAMBAHKAN: Sanity check jarak SL/TP
            entry_zone = inp.get("entry_condition", {})
            sl_price = inp.get("stop_loss")
            tp_price = inp.get("take_profit")
            entry_price = None

            if isinstance(entry_zone, dict):
                entry_price = (
                    entry_zone.get("price")
                    or entry_zone.get("entry_price")
                    or entry_zone.get("level")
                    or entry_zone.get("price_high")
                    or entry_zone.get("price_low")
                )
            elif isinstance(entry_zone, (int, float)):
                entry_price = float(entry_zone)

            if not entry_price:
                raw_ep = inp.get("entry_price")
                if raw_ep is not None:
                    try:
                        entry_price = float(raw_ep)
                    except ValueError, TypeError:
                        pass

            if sl_price is not None and sl_price <= 0:
                errors.append("stop_loss MUST be greater than 0.")
            if tp_price is not None and tp_price <= 0:
                errors.append("take_profit MUST be greater than 0.")

            # Jika market order (entry_price None), ambil harga terakhir dari DB
            if entry_price is None and decision in ("buy", "sell"):
                try:
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
                        entry_price = last_bar.close
                except Exception:
                    pass  # Non-fatal, validasi dilewati jika tidak ada data

            if entry_price and sl_price and tp_price:
                sl_dist = abs(entry_price - sl_price)
                tp_dist = abs(entry_price - tp_price)

                # SL tidak boleh 0
                if sl_dist == 0:
                    errors.append("stop_loss distance cannot be 0")

                # RR minimal 1.0 untuk approval awal
                if sl_dist > 0 and tp_dist > 0:
                    rr = tp_dist / sl_dist if sl_dist else 0
                    from monika.application.analysis.prompt.risk_contract import build_risk_contract

                    risk_contract = build_risk_contract(symbol, getattr(self, "settings", {}))
                    min_rr = risk_contract.min_rr_ratio
                    if rr < min_rr:
                        breakeven_wr = 100.0 / (1.0 + min_rr)
                        req_tp_dist = sl_dist * min_rr
                        errors.append(
                            f"R:R ratio {rr:.2f} is below minimum {min_rr:.1f} required for positive expected value. "
                            f"For your SL distance of {sl_dist:.5f}, minimum required TP distance is {req_tp_dist:.5f}. "
                            f"Adjust TP further (within ADR band) or tighten SL to satisfy R:R >= {min_rr:.1f} "
                            f"(requires ~{breakeven_wr:.0f}% win rate for breakeven), or submit WAIT."
                        )

                # The static MIN_SL_DISTANCE check was removed. Dynamic ATR check is performed below.

                # === SANITY CHECK: TP not unrealistically far ===
                if entry_price > 0 and tp_dist / entry_price > 0.20:
                    errors.append(
                        f"TP ({tp_price}) is more than 20% from entry ({entry_price}). "
                        f"This appears to be an error. Review TP level."
                    )

            adr_ctx_for_validation = None
            if self.settings.get("trading", {}).get("risk", {}).get(
                "intraday_range_strategy_enabled", True
            ) and decision in ("buy", "sell"):
                try:
                    from monika.application.analysis.calculators.daily_range_calculator import (
                        compute_daily_range_context,
                    )

                    _adr_probe = await compute_daily_range_context(self.session, symbol, self.settings)
                    if "error" in _adr_probe:
                        logger.debug(f"[{symbol}] ADR context unavailable: {_adr_probe['error']}")
                    else:
                        adr_ctx_for_validation = _adr_probe
                except Exception as adr_probe_err:
                    logger.warning(
                        f"[{symbol}] ADR context fetch failed (non-fatal, ADR gating skipped this cycle): {adr_probe_err}"
                    )

            atr_value_for_validation = None
            try:
                atr_row = (
                    await self.session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == "H4")
                        .where(TechnicalIndicator.indicator_name == "ATR_14")
                        .where(TechnicalIndicator.timestamp <= clock.now())
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if atr_row:
                    import json as _json_atr

                    raw_atr = _json_atr.loads(atr_row.value_json)
                    if isinstance(raw_atr, dict):
                        atr_value_for_validation = float(raw_atr.get("atr", raw_atr.get("value", 0)) or 0)
                    else:
                        atr_value_for_validation = float(raw_atr or 0)
            except Exception as atr_err:
                logger.warning(f"ATR fetch failed for {symbol}: {atr_err}")
            if decision in ("buy", "sell"):
                _using_atr_fallback = False
                if atr_value_for_validation is None or atr_value_for_validation <= 0:
                    dynamic_fallback = await self._get_dynamic_atr_fallback(symbol)
                    if dynamic_fallback:
                        try:
                            atr_value_for_validation = float(dynamic_fallback)
                        except TypeError, ValueError:
                            atr_value_for_validation = None
                        if atr_value_for_validation:
                            logger.warning(
                                f"ATR_14 data unavailable for {symbol}/H4. Using 30-day average ATR fallback: {atr_value_for_validation:.5f}."
                            )
                            _using_atr_fallback = True
                    else:
                        errors.append(
                            f"ATR_14 data unavailable for {symbol}/H4 and 30-day average fallback also failed. Cannot validate stop-loss distance safely. Submit WAIT instead."
                        )
                else:
                    _using_atr_fallback = False
                if atr_value_for_validation and atr_value_for_validation > 0 and entry_price and sl_price:
                    try:
                        cfg = (
                            await self.session.execute(
                                select(SystemConfig).where(SystemConfig.key == "min_sl_atr_multiplier")
                            )
                        ).scalar_one_or_none()
                        if cfg and cfg.value:
                            import json

                            multipliers = json.loads(cfg.value)
                        else:
                            multipliers = (
                                getattr(self, "settings", {})
                                .get("trading", {})
                                .get("risk", {})
                                .get("min_sl_atr_multiplier_by_symbol", {})
                            )
                        base_multiplier = multipliers.get(symbol, multipliers.get("default", 1.0))
                    except Exception:
                        base_multiplier = 1.0
                    min_sl_multiplier = base_multiplier + 0.3 if _using_atr_fallback else base_multiplier
                    min_sl_from_atr = atr_value_for_validation * min_sl_multiplier
                    sl_dist = abs(entry_price - sl_price)

                    # Defensive reconciliation: if the ATR noise-floor for this cycle happens to
                    # exceed the ADR-based ceiling, the ATR floor alone would make EVERY trade on
                    # this symbol impossible under the intraday-range framework. Relax the floor
                    # instead of hard-blocking — the dedicated ADR ceiling check below still
                    # protects against an oversized stop.
                    if adr_ctx_for_validation is not None:
                        adr_sl_ceiling = adr_ctx_for_validation["target_sl_max_distance"]
                        if min_sl_from_atr > adr_sl_ceiling:
                            logger.warning(
                                f"[{symbol}] ATR noise-floor ({min_sl_from_atr:.5f}) exceeds ADR-based SL "
                                f"ceiling ({adr_sl_ceiling:.5f}) — relaxing ATR floor for this validation. "
                                f"Consider lowering min_sl_atr_multiplier_by_symbol['{symbol}']."
                            )
                            min_sl_from_atr = min(min_sl_from_atr, adr_sl_ceiling * 0.85)

                    if sl_dist < (min_sl_from_atr - 1e-4):
                        errors.append(
                            f"SL distance ({sl_dist:.5f}) is less than required minimum ({min_sl_multiplier}x ATR_14 or ADR-adjusted floor). {('[FALLBACK ATR USED]' if _using_atr_fallback else '')} Minimum required SL distance: {min_sl_from_atr:.5f}."
                        )

            # === INTRADAY RANGE (ADR) TP/SL BAND VALIDATION — HARD GATE ===
            if adr_ctx_for_validation is not None and entry_price and sl_price and tp_price:
                tol = adr_ctx_for_validation.get("band_tolerance_pct", 0.10)
                tp_dist_check = abs(tp_price - entry_price)
                sl_dist_check = abs(entry_price - sl_price)
                tp_min = adr_ctx_for_validation["target_tp_min_distance"] * (1 - tol)
                tp_max = adr_ctx_for_validation["target_tp_max_distance"] * (1 + tol)
                effective_sl_ceiling = (
                    max(adr_ctx_for_validation["target_sl_max_distance"], min_sl_from_atr * 1.25)
                    if min_sl_from_atr > 0
                    else adr_ctx_for_validation["target_sl_max_distance"]
                )
                sl_max = effective_sl_ceiling * (1 + tol)

                if tp_dist_check < tp_min:
                    errors.append(
                        f"TP too close for intraday-range strategy: distance={tp_dist_check:.5f} < minimum "
                        f"band {tp_min:.5f} (50% of {adr_ctx_for_validation['lookback_days']}-day "
                        f"ADR={adr_ctx_for_validation['adr']:.5f}, tolerance {tol:.0%}). Target band: "
                        f"[{adr_ctx_for_validation['target_tp_min_distance']:.5f}, "
                        f"{adr_ctx_for_validation['target_tp_max_distance']:.5f}]. Find a structural level "
                        f"further out within this band, or submit WAIT if none exists."
                    )
                elif tp_dist_check > tp_max:
                    errors.append(
                        f"TP too far for intraday-range strategy: distance={tp_dist_check:.5f} > maximum "
                        f"band {tp_max:.5f} (80% of ADR={adr_ctx_for_validation['adr']:.5f}, tolerance "
                        f"{tol:.0%}). Unlikely to resolve within one trading day. Target band: "
                        f"[{adr_ctx_for_validation['target_tp_min_distance']:.5f}, "
                        f"{adr_ctx_for_validation['target_tp_max_distance']:.5f}]. Move TP closer, or submit WAIT."
                    )

                if sl_dist_check > sl_max:
                    errors.append(
                        f"SL too wide for intraday-range strategy: distance={sl_dist_check:.5f} > maximum allowed {sl_max:.5f} (35% of ADR={adr_ctx_for_validation['adr']:.5f}). Find a tighter structural level, or submit WAIT if no valid tight stop exists."
                    )

                if self.settings.get("trading", {}).get("risk", {}).get("strict_structural_mapping", True):
                    errors.extend(
                        await self._validate_tp_structural_target(
                            symbol=symbol,
                            direction=decision,
                            tp_price=tp_price,
                            atr=atr_value_for_validation,
                            adr_ctx=adr_ctx_for_validation,
                        )
                    )

                if adr_ctx_for_validation.get("entry_allowed") is False:
                    room_pct = adr_ctx_for_validation.get("room_remaining_pct", 0) * 100
                    errors.append(
                        f"ENTRY BLOCKED: only {room_pct:.0f}% of today's typical ADR range remains "
                        f"(today_range_so_far={adr_ctx_for_validation['today_range_so_far']:.5f} of "
                        f"ADR={adr_ctx_for_validation['adr']:.5f}). Insufficient room for a fresh "
                        f"intraday target — submit WAIT and reassess next cycle."
                    )
                elif adr_ctx_for_validation.get("session_recommendation") == "reduced_target":
                    room_pct = adr_ctx_for_validation.get("room_remaining_pct", 0) * 100
                    rationale = rationale + (
                        f"\n\n[SYSTEM: Only {room_pct:.0f}% of today's typical ADR range "
                        f"remains. Confidence discounted for reduced room.]"
                    )
                    inp["rationale"] = rationale
                    confidence = round(min(confidence, 0.5), 3) if confidence else confidence
            # === END INTRADAY RANGE (ADR) VALIDATION ===

            # === MARKET PROXIMITY CHECK for LIMIT orders ===
            if decision in ("buy", "sell") and entry_zone:
                entry_type = entry_zone.get("type", "market") if isinstance(entry_zone, dict) else "market"
                specified_price = (
                    entry_zone.get("price")
                    if isinstance(entry_zone, dict)
                    else (float(entry_zone) if isinstance(entry_zone, (int, float)) else None)
                )

                if entry_type == "limit" and specified_price is not None:
                    # Check that limit price is within 3% of current market
                    try:
                        last_bar = (
                            await self.session.execute(
                                select(PriceOHLCV)
                                .where(PriceOHLCV.symbol == symbol)
                                .where(PriceOHLCV.timestamp <= clock.now())
                                .order_by(PriceOHLCV.timestamp.desc())
                                .limit(1)
                            )
                        ).scalar_one_or_none()

                        if last_bar and last_bar.close and last_bar.close > 0:
                            price_diff_pct = abs(specified_price - last_bar.close) / last_bar.close * 100

                            # Reject if limit price is more than 3% from current price
                            # (catches hallucinated price levels or stale levels)
                            if price_diff_pct > 3.0:
                                errors.append(
                                    f"Limit entry price ({specified_price}) is {price_diff_pct:.1f}% from "
                                    f"current price ({last_bar.close}). Maximum allowed deviation is 3%. "
                                    f"Either use market order or specify a realistic limit price. "
                                    f"Note: Current D1/H4 S/R zones must have a price within 3% of current market."
                                )
                    except Exception:
                        pass
            # === H4 INDICATOR STALENESS CHECK ===
            try:
                latest_indicator_ts = (
                    await self.session.execute(
                        select(TechnicalIndicator.timestamp)
                        .where(TechnicalIndicator.symbol == symbol)
                        .where(TechnicalIndicator.timeframe == "H4")
                        .where(TechnicalIndicator.timestamp <= clock.now())
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if latest_indicator_ts is None:
                    errors.append(
                        f"No H4 technical indicators found for {symbol}. "
                        f"Cannot assess RSI/MACD/ATR without data. Submit WAIT instead."
                    )
                else:
                    ind_ts = latest_indicator_ts
                    if ind_ts.tzinfo is None:
                        ind_ts = ind_ts.replace(tzinfo=timezone.utc)
                    indicator_age_hours = (clock.now() - ind_ts).total_seconds() / 3600
                    if indicator_age_hours > 10.0:
                        errors.append(
                            f"H4 technical indicators for {symbol} are {indicator_age_hours:.1f}h old "
                            f"(limit: 10.0h). RSI/MACD/ATR values are stale — MT5 may be disconnected. "
                            f"Submit WAIT until fresh data is available."
                        )
            except Exception as e:
                logger.warning(
                    f"[{symbol}] Could not verify H4 indicator freshness: {e}. Proceeding with analysis as a fallback."
                )

        elif decision == "wait":
            if not inp.get("reevaluation_trigger"):
                inp["reevaluation_trigger"] = {
                    "type": "time",
                    "symbol": symbol,
                    "hours": 4,
                    "detail": "Standard wait: re-evaluate on next 4-hour cycle",
                }
                reeval_trigger = inp["reevaluation_trigger"]

            # === WAIT QUALITY CHECK ===
            trigger = inp.get("reevaluation_trigger", {})
            trigger_detail = trigger.get("detail", "")
            trigger_type = trigger.get("type", "")

            # Reject vague triggers
            vague_phrases = [
                "in 6 hours",
                "next cycle",
                "tomorrow",
                "later",
                "re-evaluate in",
                "check later",
                "wait for update",
            ]
            is_vague = (
                len(trigger_detail) < 20
                or any(phrase in trigger_detail.lower() for phrase in vague_phrases)
                and trigger_type != "time"
            )

            if is_vague and trigger_type != "time":
                logger.warning(
                    f'[{symbol}] Vague WAIT trigger detected: "{trigger_detail[:80]}". '
                    f"AI should specify exact price level or event for re-evaluation."
                )
                # Don't block, but log for quality tracking
                rationale = rationale + (
                    f"\n[QUALITY NOTE: Reevaluation trigger could be more specific. "
                    f"Ideal: specific price level or named event.]"
                )
                inp["rationale"] = rationale

        if decision in ("buy", "sell"):
            if not inp.get("confluence_score"):
                errors.append("Ditolak: Confluence score kosong. Wajib diisi untuk trade buy/sell.")

        # SPECIALIST DISAGREEMENT CHECK
        if decision in ("buy", "sell"):
            try:
                import json as _j2

                disagreement_key = f"specialist_disagreement_{symbol}"
                disagreement_cfg = (
                    await self.session.execute(select(SystemConfig).where(SystemConfig.key == disagreement_key))
                ).scalar_one_or_none()
                if disagreement_cfg and disagreement_cfg.value:
                    dd = _j2.loads(disagreement_cfg.value)
                    flagged_at = datetime.fromisoformat(dd["flagged_at"])
                    if flagged_at.tzinfo is None:
                        flagged_at = flagged_at.replace(tzinfo=timezone.utc)
                    if (clock.now() - flagged_at).total_seconds() < 900:
                        adjudication = inp.get("specialist_adjudication")
                        if not adjudication or not adjudication.get("conflict_detected"):
                            errors.append(
                                f"SPECIALIST DISAGREEMENT UNRESOLVED: technical/sentiment/macro disagreed on "
                                f"direction ({dd['biases']}). You MUST explicitly fill the 'specialist_adjudication' "
                                f"field to resolve this conflict before submitting."
                            )
                        elif not adjudication.get("resolution_path") or not adjudication.get(
                            "resolution_justification"
                        ):
                            errors.append(
                                f"SPECIALIST DISAGREEMENT UNRESOLVED: You flagged the conflict but failed to provide "
                                f"'resolution_path' or 'resolution_justification' in 'specialist_adjudication'."
                            )
            except Exception as e:
                logger.debug(f"Specialist disagreement check failed (non-fatal): {e}")

        # UNIFIED THRESHOLD ENFORCEMENT
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

        # --- Cross-validate priced-in score, directional coherence, and SSVP with Stage 1 brief ---
        brief_row = None
        rationale, brief_row = await self._cross_validate_priced_in(
            symbol=symbol,
            decision=decision,
            rationale=rationale,
            inp=inp,
            errors=errors,
            brief_row=brief_row,
        )
        rationale = await self._cross_validate_directional_coherence(
            symbol=symbol,
            decision=decision,
            rationale=rationale,
            inp=inp,
            errors=errors,
            brief_row=brief_row,
        )
        context_snapshot_id, context_cds_score = await self._validate_ssvp_and_context_drift(
            symbol=symbol,
            decision=decision,
            rationale=rationale,
            inp=inp,
            errors=errors,
        )
        # Hard ceiling: non-deterministic uplift cap
        if decision in ("buy", "sell") and inp.get("confluence_score"):
            submitted_score = inp["confluence_score"]
            from monika.application.analysis.calculators.confluence_calculator import calculate_confluence

            det_calc = await calculate_confluence(
                self.session, symbol, decision, entry_price, sl_price, tp_price, settings=self.settings
            )
            det_score = det_calc.get("computed_score", 0)
            non_det_uplift = submitted_score - det_score
            # Skor deterministik dihitung ULANG di waktu submission dengan state pasar
            # real-time (sesi, RSI, dsb) yang bisa bergeser selama model bernalar
            # (15-18 tool turns). Toleransi dipisah jadi soft-warn vs hard-block agar
            # drift wajar tidak memicu rejection palsu, tapi skor yang jelas dikarang
            # tetap diblok.
            HARD_BLOCK_UPLIFT = 5  # FIX: sebelumnya 7 (hampir separuh skala 14, terlalu longgar)
            SOFT_WARN_UPLIFT = 3  # FIX: sebelumnya 5
            if non_det_uplift > HARD_BLOCK_UPLIFT:
                errors.append(
                    f"Non-deterministic score uplift EXTREME: reported={submitted_score}, verified_base={det_score} (recomputed at submission time), uplift={non_det_uplift} > hard-block threshold {HARD_BLOCK_UPLIFT}. This cannot be explained by normal session/indicator drift. Review each non-deterministic factor claim in your rationale."
                )
            elif non_det_uplift > SOFT_WARN_UPLIFT:
                effective_score = det_score + SOFT_WARN_UPLIFT
                logger.warning(
                    f"[{symbol}] Confluence uplift soft-warning: reported={submitted_score}, verified_base={det_score}, uplift={non_det_uplift}. Capping effective_score to {effective_score} for threshold re-validation."
                )
                try:
                    from monika.application.analysis.calculators.unified_threshold_calculator import (
                        compute_unified_confluence_threshold,
                    )

                    recheck_threshold, recheck_reason = await compute_unified_confluence_threshold(
                        self.session, symbol, self.settings
                    )
                    if effective_score < recheck_threshold:
                        errors.append(
                            f"Non-deterministic score uplift ({non_det_uplift}) capped effective_score to {effective_score}/14, which is BELOW the required threshold ({recheck_threshold}). Reported score {submitted_score} cannot be trusted at face value for this decision. Submit WAIT instead, or provide additional deterministic evidence."
                        )
                except Exception as e:
                    logger.debug(f"Unified threshold recheck for uplift cap failed (non-fatal): {e}")
                rationale = (
                    rationale
                    + f"\n\n[SYSTEM NOTE: Deterministic re-check at submission time scored {det_score}/14 vs reported {submitted_score}/14 (delta={non_det_uplift}). Effective score capped at {effective_score}/14 for threshold validation; flagged for audit.]"
                )
                inp["rationale"] = rationale
        if errors:
            attempts = self.submit_attempts + 1
            # Gunakan SystemConfig untuk counter persisten
            try:
                now_str = clock.now().strftime("%Y%m%d_%H")
                # Menggunakan tanggal_jam sebagai cycle proxy
                cfg_key = f"submit_attempt_{symbol}_{now_str}"
                cfg = (
                    await self.session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))
                ).scalar_one_or_none()

                if cfg and cfg.value is not None:
                    attempts = int(cfg.value) + 1
                    cfg.value = str(attempts)
                else:
                    attempts = 1
                    self.session.add(SystemConfig(key=cfg_key, value="1"))
                await self.session.commit()
            except Exception as e:
                logger.error(f"Failed to track submit attempts: {e}")
                self.submit_attempts += 1
                attempts = self.submit_attempts

            error_class = self._classify_validation_errors(errors)

            if error_class in ("GATE", "GATE_FATAL"):
                logger.info(f"[{symbol}] Mechanical risk gate blocked entry. Gracefully forcing WAIT. Errors: {errors}")
                decision = "wait"
                confidence = 0.0
                first_err = errors[0] if errors else "rule-based filter"
                rationale = f"Mechanical Risk Gate: Entry blocked by rule-based filter.\n" + "\n".join(errors)

                # Synthetic Trigger: ensure asset is monitored for condition resolution
                if not reeval_trigger and entry_price:
                    direction_str = "above" if inp.get("decision") == "buy" else "below"
                    reeval_trigger = {
                        "type": "price_level",
                        "symbol": symbol,
                        "price": float(entry_price),
                        "direction": direction_str,
                        "detail": f"Mechanical gate ({first_err[:40]}...) re-evaluation upon price reaching {entry_price}",
                    }
                elif not reeval_trigger:
                    reeval_trigger = {
                        "type": "time",
                        "symbol": symbol,
                        "hours": 2,
                        "detail": "Mechanical gate auto-reevaluate after 2 hours",
                    }
                errors = []
            elif error_class == "FATAL" or attempts >= 3:
                if error_class == "FATAL":
                    logger.error(f"[{symbol}] submit_asset_analysis failed validation (FATAL: {errors}). Forcing WAIT.")
                else:
                    logger.warning(
                        f"[{symbol}] submit_asset_analysis failed validation after max attempts ({attempts}): {errors}. Forcing WAIT."
                    )
                decision = "wait"
                confidence = 0.0
                rationale = (
                    f"System override: Forced WAIT due to {error_class} error or max attempts reached.\n"
                    + "\n".join(errors)
                )
                if not reeval_trigger:
                    reeval_trigger = {
                        "type": "time",
                        "symbol": symbol,
                        "hours": 2,
                        "detail": "Forced WAIT auto-reevaluate after 2 hours",
                    }
                errors = []
            else:
                logger.warning(f"submit_asset_analysis validation failed for {symbol} (Attempt {attempts}): {errors}")
                return {
                    "status": "validation_failed",
                    "errors": errors,
                    "error_classification": error_class,
                    "guidance": (
                        'Specialist conflict or SSVP discrepancy active: explicitly adjudicate in specialist_adjudication or rationale (e.g. "I trust price action because..."), or adjust entry/SL/TP, or submit WAIT.'
                        if any("adjudication" in e.lower() or "specialist disagreement" in e.lower() for e in errors)
                        else {
                            "STRUCTURAL": "Recalculate entry/SL/TP. Try different structural level.",
                            "GATE_FIXABLE": "Gate condition fixable: adjust entry type/zone (limit order at POC/VAH/VAL) or provide required override justification.",
                            "THRESHOLD": "Score insufficient. Submit WAIT with specific trigger.",
                            "GATE_FATAL": "Mechanical gate active. Submit WAIT.",
                            "GATE": "Mechanical gate active. Submit WAIT.",
                            "FATAL": "Submit WAIT immediately. Do not retry.",
                        }.get(error_class, "")
                    ),
                    "attempt": attempts,
                }

        import json as _json

        # Get most recent brief for FK
        brief = (
            await self.session.execute(
                select(FundamentalBrief.id).order_by(FundamentalBrief.generated_at.desc()).limit(1)
            )
        ).scalar_one_or_none()

        entry_cond = inp.get("entry_condition")
        reeval_trigger = reeval_trigger or inp.get("reevaluation_trigger")
        if reeval_trigger and not reeval_trigger.get("symbol"):
            reeval_trigger["symbol"] = symbol

        # EXTRACT NEW PRICED-IN AND NEWS FIELDS
        priced_in_score = inp.get("priced_in_score")
        priced_in_override_justification = inp.get("priced_in_override_justification")
        confluence_score = inp.get("confluence_score")
        confluence_factors = inp.get("confluence_factors")
        key_news_events_considered = inp.get("key_news_events_considered", [])
        news_impact_assessment = inp.get("news_impact_assessment", "")

        invalidation_price = inp.get("invalidation_price")
        invalidation_direction = inp.get("invalidation_direction")
        playbook_id = inp.get("playbook_id") or inp.get("source_strategy_id")
        if playbook_id:
            logger.info(f"[{symbol}] AssetAnalysis linked to empirical playbook: {playbook_id}")

        if decision in ("buy", "sell") and entry_price and atr_value_for_validation:
            proximity_warnings = await self._validate_smc_entry_proximity(
                symbol=symbol,
                entry_price=entry_price,
                direction=decision,
                stop_loss=float(inp["stop_loss"]) if inp.get("stop_loss") is not None else 0.0,
                atr=atr_value_for_validation,
            )
            if proximity_warnings:
                for w in proximity_warnings:
                    logger.warning(f"[{symbol}] {w}")
                rationale = rationale + "\n\n[SYSTEM VALIDATION WARNINGS]\n" + "\n".join(proximity_warnings)

        if "context_snapshot_id" not in locals():
            context_snapshot_id = None
            context_cds_score = None

        # Fetch specialist biases from system config (do not delete prematurely; lifecycle managed by per_asset_stage)
        specialist_biases_json = None
        try:
            key = f"pending_specialist_biases_{symbol}"
            cfg = (await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
            if cfg and cfg.value:
                specialist_biases_json = cfg.value
        except Exception as e:
            logger.debug(f"Failed to fetch staged specialist biases: {e}")

        # Idempotency guard for fallback LLM retries (prevent duplicate AssetAnalysis rows within SAME execution session)
        if self._submitted_analysis_id is not None:
            existing = await self.session.get(AssetAnalysis, self._submitted_analysis_id)
            if existing:
                logger.info(
                    f"Updating existing AssetAnalysis ID {existing.id} in current execution session for {symbol}"
                )
                existing.generated_at = clock.now()
                existing.brief_id = brief
                existing.decision = str(decision or "wait")
                existing.confidence = confidence
                existing.entry_zone = _json.dumps(entry_cond) if entry_cond else None
                existing.stop_loss = inp.get("stop_loss")
                existing.take_profit = inp.get("take_profit")
                existing.invalidation = (
                    _json.dumps(inp.get("invalidation"))
                    if isinstance(inp.get("invalidation"), dict)
                    else str(inp.get("invalidation"))
                    if inp.get("invalidation") is not None
                    else None
                )
                existing.invalidation_price = invalidation_price
                existing.invalidation_direction = invalidation_direction
                existing.reevaluation_trigger = _json.dumps(reeval_trigger) if reeval_trigger else None
                existing.rationale = rationale
                existing.priced_in_score = priced_in_score
                existing.priced_in_override_justification = priced_in_override_justification
                existing.confluence_score = confluence_score
                existing.confluence_factors_json = _json.dumps(confluence_factors) if confluence_factors else None
                if specialist_biases_json:
                    existing.specialist_biases_json = specialist_biases_json
                existing.context_snapshot_id = context_snapshot_id
                existing.ssvp_cds_score_at_analysis = context_cds_score
                existing.decision_source = "llm_stage2"
                if playbook_id:
                    existing.source_strategy_id = str(playbook_id).strip()
                existing_rationale = existing.rationale or ""
                if key_news_events_considered:
                    news_strs = [str(x).strip() for x in key_news_events_considered if str(x).strip()]
                    if news_strs:
                        existing_rationale += f"\n\nNews Events Considered: {', '.join(news_strs)}"
                if news_impact_assessment:
                    existing_rationale += f"\nNews Impact Assessment: {str(news_impact_assessment).strip()}"
                existing.rationale = existing_rationale
                await self.session.commit()
                return {
                    "status": "saved",
                    "analysis_id": existing.id,
                    "symbol": symbol,
                    "decision": existing.decision,
                    "message": "Analysis updated (idempotent retry in same session).",
                }

        analysis = AssetAnalysis(
            symbol=symbol,
            generated_at=clock.now(),
            brief_id=brief,
            decision=str(decision or "wait"),
            confidence=confidence,
            entry_zone=_json.dumps(entry_cond) if entry_cond else None,
            stop_loss=inp.get("stop_loss"),
            take_profit=inp.get("take_profit"),
            invalidation=_json.dumps(inp.get("invalidation"))
            if isinstance(inp.get("invalidation"), dict)
            else str(inp.get("invalidation"))
            if inp.get("invalidation") is not None
            else None,
            invalidation_price=invalidation_price,
            invalidation_direction=invalidation_direction,
            reevaluation_trigger=_json.dumps(reeval_trigger) if reeval_trigger else None,
            rationale=rationale,
            priced_in_score=priced_in_score,
            priced_in_override_justification=priced_in_override_justification,
            confluence_score=confluence_score,
            confluence_factors_json=_json.dumps(confluence_factors) if confluence_factors else None,
            specialist_biases_json=specialist_biases_json,
            context_snapshot_id=context_snapshot_id,
            ssvp_cds_score_at_analysis=context_cds_score,
            decision_source="llm_stage2",
            source_strategy_id=str(playbook_id).strip() if playbook_id else None,
        )

        # Ambil harga terkini saat AI menyimpan analisis
        try:
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
                analysis.price_at_analysis = last_bar.close
        except Exception as e:
            logger.warning(f"Failed to fetch price_at_analysis for {symbol}: {e}")

        # If DB model doesn't have key_news_events_considered, append to rationale
        analysis_rationale = analysis.rationale or ""
        if key_news_events_considered:
            news_strs = [str(x).strip() for x in key_news_events_considered if str(x).strip()]
            if news_strs:
                analysis_rationale += f"\n\nNews Events Considered: {', '.join(news_strs)}"
        if news_impact_assessment:
            analysis_rationale += f"\nNews Impact Assessment: {str(news_impact_assessment).strip()}"
        analysis.rationale = analysis_rationale
        self.session.add(analysis)
        await self.session.flush()  # get analysis.id before adding triggers
        self._submitted_analysis_id = analysis.id

        # Cancel any previous pending triggers for this symbol (superseded by new analysis)
        try:
            prev_pending_stmt = (
                select(TradeTrigger.id)
                .join(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
                .where(AssetAnalysis.symbol == symbol)
                .where(TradeTrigger.status == "pending")
                .where(TradeTrigger.asset_analysis_id != analysis.id)
            )
            prev_trigger_ids = (await self.session.execute(prev_pending_stmt)).scalars().all()
            if prev_trigger_ids:
                await self.session.execute(
                    update(TradeTrigger).where(TradeTrigger.id.in_(prev_trigger_ids)).values(status="cancelled")
                )
                logger.info(f"Cancelled {len(prev_trigger_ids)} superseded pending triggers for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to cancel superseded triggers for {symbol}: {e}")

        # Save trigger
        if reeval_trigger:
            raw_type = reeval_trigger.get("type", "time")
            norm_type = "price_level" if raw_type in ("price", "price_level") else raw_type
            trigger = TradeTrigger(
                asset_analysis_id=analysis.id,
                trigger_type=norm_type,
                condition_json=_json.dumps(reeval_trigger),
                status="pending",
            )
            self.session.add(trigger)

        await self.session.commit()
        conf_display = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)
        logger.info(f"Asset analysis saved: {symbol} → {decision} (confidence={conf_display})")

        msg = "Analysis saved successfully."
        if decision == "wait" and "System override: Forced WAIT" in rationale:
            msg = f"Analysis FORCEFULLY saved as WAIT due to validation errors. DO NOT RETRY. Errors: {rationale}"

        return {"status": "saved", "analysis_id": analysis.id, "symbol": symbol, "decision": decision, "message": msg}
