# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/post_verifications.py
# Description: Post-decision validation, grounding, and safety checks mixin
# ==============================================================================

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.stages.per_asset.runner_mixins.base import (
    _RunnerMixinBase,
    _get_clock,
)
from monika.infrastructure.database.models import AssetAnalysis, SystemConfig

logger = logging.getLogger("TradingAgent.PerAssetStage")


class PostProcessVerificationMixin(_RunnerMixinBase):
    """Mixin handling closed-loop validation, grounding checks, and safety penalties."""

    async def _post_process_analysis_verifications(
        self,
        session: AsyncSession,
        symbol: str,
        analysis: Optional[AssetAnalysis],
        decision: str,
        confidence: float,
        raw_bundle_data: Any,
        active_client: Any,
        effective_threshold: Any,
        specialist_biases: Dict[str, str],
        specialist_confidence: Dict[str, str],
        specialist_trust: Dict[str, float],
    ) -> Tuple[str, float]:
        """Post-decision closed-loop verification, grounding, and safety gates."""
        if not analysis:
            return decision, confidence

        # Track AI compliance: log when required fields are missing
        if analysis.decision in ("buy", "sell"):
            verified: Optional[Dict[str, Any]] = None
            # Post-Decision Closed-Loop Verification & Self-Correction (Harness Upgrade)
            try:
                from monika.application.analysis.validators.output_verifier import OutputVerifier

                verifier = OutputVerifier(self.settings)
                entry_payload = (
                    json.loads(analysis.entry_zone)
                    if isinstance(analysis.entry_zone, (str, bytes, bytearray))
                    else (analysis.entry_zone if isinstance(analysis.entry_zone, dict) else {})
                )
                if not entry_payload.get("price") and analysis.entry_price is not None:
                    try:
                        entry_payload["price"] = float(analysis.entry_price)
                    except TypeError, ValueError:
                        pass
                raw_payload = {
                    "decision": analysis.decision,
                    "entry_condition": entry_payload,
                    "stop_loss": analysis.stop_loss,
                    "take_profit": analysis.take_profit,
                    "confluence_score": analysis.confluence_score,
                    "priced_in_score": analysis.priced_in_score,
                    "reevaluation_trigger": json.loads(analysis.reevaluation_trigger)
                    if isinstance(analysis.reevaluation_trigger, (str, bytes, bytearray))
                    else (analysis.reevaluation_trigger if isinstance(analysis.reevaluation_trigger, dict) else {}),
                    "rationale": analysis.rationale,
                }
                verified, corrections = await verifier.verify_and_correct(
                    session=session,
                    settings=self.settings,
                    symbol=symbol,
                    raw_output=raw_payload,
                    context_data=raw_bundle_data if isinstance(raw_bundle_data, dict) else {},
                    client=active_client,
                    max_retries=1,
                )
                if verified and isinstance(verified, dict):
                    if verified.get("stop_loss"):
                        analysis.stop_loss = verified["stop_loss"]
                    if verified.get("take_profit"):
                        analysis.take_profit = verified["take_profit"]
                    if verified.get("confluence_score") is not None:
                        analysis.confluence_score = verified["confluence_score"]
                    if verified.get("priced_in_score") is not None:
                        analysis.priced_in_score = verified["priced_in_score"]
                    if verified.get("decision"):
                        analysis.decision = verified["decision"]
                        decision = verified["decision"]

                if corrections:
                    logger.info(f"[{symbol}] Post-decision self-correction applied: {corrections}")
                    curr_notes = analysis.execution_notes or ""
                    corr_note = f"[OutputVerifier] Corrected: {', '.join(corrections)}"
                    analysis.execution_notes = f"{curr_notes}\n{corr_note}".strip()

                if str(analysis.decision).lower() in ("wait", "avoid", "rejected"):
                    decision = "wait"
                    try:
                        from monika.application.benchmark.trade_trajectory_logger import TradeTrajectoryLogger

                        TradeTrajectoryLogger().log_trajectory(
                            symbol=symbol,
                            decision="REJECTED",
                            risk_decision={
                                "approved": False,
                                "reason": f"output_verifier: {corrections or (verified.get('verification_failures') if isinstance(verified, dict) else [])}",
                            },
                            execution_details={
                                "analysis_id": analysis.id,
                                "decision": "REJECTED",
                                "stage": "output_verifier",
                            },
                        )
                    except Exception as traj_err:
                        logger.debug(f"[{symbol}] OutputVerifier trajectory log error: {traj_err}")
                await session.commit()
            except Exception as e:
                logger.error(f"[{symbol}] Output verifier failed, demoting to wait (Fail-Closed): {e}")
                analysis.decision = "wait"
                decision = "wait"
                await session.commit()

            # In-Harness Grounding Validator (Extended PR-07: lot_size, spread, margin, equity)
            try:
                from monika.application.analysis.validators.in_harness_grounding import InHarnessGroundingValidator

                ez_parsed = (
                    json.loads(analysis.entry_zone)
                    if analysis.entry_zone and isinstance(analysis.entry_zone, str)
                    else (analysis.entry_zone if isinstance(analysis.entry_zone, dict) else {})
                )

                # Fetch live or paper account equity and margin for grounding
                acc_equity = None
                free_margin = None
                mt5_cli = getattr(self, "mt5_client", None)
                if mt5_cli is not None and callable(getattr(mt5_cli, "get_account_info", None)):
                    try:
                        import inspect

                        acc_fn = getattr(mt5_cli, "get_account_info")
                        if inspect.iscoroutinefunction(acc_fn):
                            acc = await acc_fn()
                        else:
                            acc = acc_fn()
                        if acc and isinstance(acc, dict):
                            acc_equity = float(acc.get("equity", 0.0)) or None
                            free_margin = float(acc.get("margin_free", 0.0)) or None
                    except Exception:
                        pass
                if acc_equity is None:
                    acc_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
                if free_margin is None:
                    free_margin = acc_equity * 0.95

                bundle_for_grounding = dict(raw_bundle_data) if isinstance(raw_bundle_data, dict) else {}
                bundle_for_grounding.setdefault("account_equity", acc_equity)
                bundle_for_grounding.setdefault("free_margin", free_margin)

                # Extract lot_size from verification ledger, tool evidence, or ez_parsed
                lot_size_val = getattr(analysis, "lot_size", None) or (
                    verified.get("lot_size") if isinstance(verified, dict) else None
                )
                if lot_size_val is None:
                    v_ledger = getattr(self, "verification_ledger", None)
                    if not v_ledger:
                        tool_exec = getattr(self, "tool_executor", None)
                        if tool_exec:
                            v_ledger = getattr(tool_exec, "verification_ledger", None)
                    if v_ledger and hasattr(v_ledger, "get_passed_records"):
                        passed_records = v_ledger.get_passed_records(symbol)
                        for prec in reversed(passed_records):
                            if prec.tool_name in ("calculate_position_size", "validate_risk_limits") and isinstance(
                                prec.details, dict
                            ):
                                lot_size_val = (
                                    prec.details.get("lot_size")
                                    or prec.details.get("lots")
                                    or prec.details.get("recommended_lot_size")
                                )
                                if lot_size_val is not None:
                                    break
                if lot_size_val is None and isinstance(ez_parsed, dict):
                    lot_size_val = ez_parsed.get("lot_size") or ez_parsed.get("lots")

                curr_payload = {
                    "decision": analysis.decision,
                    "entry_price": ez_parsed.get("price") or ez_parsed.get("price_high"),
                    "stop_loss": analysis.stop_loss,
                    "take_profit": analysis.take_profit,
                    "rationale": analysis.rationale,
                    "lot_size": float(lot_size_val) if lot_size_val is not None else None,
                    "account_equity": acc_equity,
                    "free_margin": free_margin,
                }
                is_grounded, ground_errors, ground_meta = InHarnessGroundingValidator.verify_grounding(
                    decision_payload=curr_payload,
                    data_bundle=bundle_for_grounding,
                    symbol=symbol,
                )
                if not is_grounded:
                    logger.warning(f"[{symbol}] InHarnessGrounding violations detected: {ground_errors}")
                    if any(
                        "too far" in err
                        or "too tight" in err
                        or "Ungrounded" in err
                        or "margin" in err.lower()
                        or "spread" in err.lower()
                        or "lot" in err.lower()
                        for err in ground_errors
                    ):
                        logger.warning(
                            f"[{symbol}] Demoting {analysis.decision.upper()} to WAIT due to grounding failure: {ground_errors}"
                        )
                        analysis.decision = "wait"
                        analysis.rationale = (
                            analysis.rationale or ""
                        ) + f" [GROUNDING REJECT: {'; '.join(ground_errors)}]"
                        await session.commit()
                        decision = "wait"
            except Exception as ground_err:
                logger.error(
                    f"[{symbol}] InHarnessGroundingValidator error, demoting to wait (Fail-Closed): {ground_err}"
                )
                if str(analysis.decision or "").lower() in ("buy", "sell"):
                    analysis.decision = "wait"
                    analysis.rationale = (analysis.rationale or "") + f" [GROUNDING ERROR REJECT: {ground_err}]"
                    await session.commit()
                    decision = "wait"

            # Cross-Timeframe Confirmation Gate (HTF Alignment Sentinel)
            try:
                if str(analysis.decision or "").lower() in ("buy", "sell"):
                    from monika.application.analysis.validators.cross_timeframe_gate import (
                        CrossTimeframeConfirmationGate,
                    )

                    is_aligned, htf_reason, htf_meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
                        decision=analysis.decision,
                        data_bundle=raw_bundle_data if isinstance(raw_bundle_data, dict) else {},
                        symbol=symbol,
                    )
                    if not is_aligned:
                        logger.warning(f"[{symbol}] CrossTimeframeGate REJECT: {htf_reason}")
                        analysis.decision = "wait"
                        analysis.rationale = (analysis.rationale or "") + f" [HTF MISALIGNMENT REJECT: {htf_reason}]"
                        await session.commit()
                        decision = "wait"
            except Exception as htf_err:
                logger.error(
                    f"[{symbol}] CrossTimeframeConfirmationGate error, demoting to wait (Fail-Closed): {htf_err}"
                )
                analysis.decision = "wait"
                decision = "wait"
                await session.commit()

            missing_fields = []
            if analysis.confluence_score is None:
                missing_fields.append("confluence_score")
            if analysis.priced_in_score is None:
                missing_fields.append("priced_in_score")
            if missing_fields:
                logger.warning(
                    f"[{symbol}] Model submitted {analysis.decision.upper()} without required fields: "
                    f"{missing_fields}. Auto-execute will be blocked. "
                    f"Review system prompt to reinforce mandatory scorecard requirements."
                )
                try:
                    key = f"ai_compliance_missing_fields_{symbol}"
                    existing = (
                        await session.execute(select(SystemConfig).where(SystemConfig.key == key))
                    ).scalar_one_or_none()
                    count = 1
                    if existing and existing.value:
                        try:
                            count = json.loads(existing.value).get("count", 0) + 1
                        except Exception:
                            pass
                    data = json.dumps(
                        {"count": count, "last_seen": _get_clock().now().isoformat(), "fields": missing_fields}
                    )
                    if existing:
                        existing.value = data
                    else:
                        session.add(SystemConfig(key=key, value=data))
                    await session.commit()
                except Exception as e:
                    logger.debug(f"Failed to track AI compliance: {e}")

        if analysis.decision in ("buy", "sell", "wait"):
            try:
                from monika.application.analysis.validators.adjudication_verifier import verify_adjudication

                target_biases = specialist_biases if specialist_biases else {}
                target_confidence = specialist_confidence if specialist_confidence else {}
                target_trust_weights = (
                    {k: round(specialist_trust.get(k, 1.0), 3) for k in target_biases} if specialist_trust else {}
                )

                if not target_biases and analysis.specialist_biases_json:
                    try:
                        _b_data = json.loads(analysis.specialist_biases_json)
                        target_biases = _b_data.get("biases", {})
                        target_confidence = _b_data.get("confidence", {})
                        target_trust_weights = _b_data.get("trust_weights_used", {})
                    except Exception:
                        pass

                if not target_biases:
                    try:
                        _biases_key = f"pending_specialist_biases_{symbol}"
                        _cfg = (
                            await session.execute(select(SystemConfig).where(SystemConfig.key == _biases_key))
                        ).scalar_one_or_none()
                        if _cfg and _cfg.value:
                            _b_data = json.loads(_cfg.value)
                            computed_at_str = _b_data.get("computed_at")
                            is_fresh = True
                            if computed_at_str:
                                try:
                                    c_dt = datetime.fromisoformat(computed_at_str)
                                    if c_dt.tzinfo is None:
                                        c_dt = c_dt.replace(tzinfo=timezone.utc)
                                    if (_get_clock().now() - c_dt).total_seconds() > 900:  # >15m old is stale
                                        is_fresh = False
                                except Exception:
                                    pass
                            if is_fresh:
                                target_biases = _b_data.get("biases", {})
                                target_confidence = _b_data.get("confidence", {})
                                target_trust_weights = _b_data.get("trust_weights_used", {})
                    except Exception:
                        pass

                if target_biases:
                    parsed_trigger = None
                    if analysis.reevaluation_trigger:
                        try:
                            parsed_trigger = (
                                json.loads(analysis.reevaluation_trigger)
                                if isinstance(analysis.reevaluation_trigger, str)
                                else analysis.reevaluation_trigger
                            )
                        except Exception:
                            parsed_trigger = {"raw": str(analysis.reevaluation_trigger)}

                    adj_check = await verify_adjudication(
                        self.settings,
                        symbol,
                        target_biases,
                        target_confidence,
                        analysis.decision,
                        analysis.rationale or "",
                        specialist_trust_weights=target_trust_weights,
                        confluence_score=int(analysis.confluence_score)
                        if analysis.confluence_score is not None
                        else None,
                        effective_threshold=int(effective_threshold) if effective_threshold is not None else None,
                        reeval_trigger=parsed_trigger if isinstance(parsed_trigger, dict) else None,
                    )
                    if adj_check.get("verdict") == "CONTRADICTS_OWN_FRAMEWORK":
                        logger.warning(
                            f"[{symbol}] Adjudication framework violation: {adj_check.get('mismatch_explanation')}"
                        )
                        analysis.rationale = (analysis.rationale or "") + (
                            f"\n\n[SYSTEM: Adjudication verifier flagged inconsistency between framework rules "
                            f"and actual decision. {adj_check.get('mismatch_explanation', '')}]"
                        )
                        if analysis.decision in ("buy", "sell"):
                            analysis.confidence = (analysis.confidence or 0.7) * 0.80
                        await session.commit()
                    elif adj_check.get("verdict") == "CONFIRM":
                        if adj_check.get("is_conditional_wait"):
                            logger.info(
                                f"[{symbol}] Adjudication confirmed: conditional WAIT aligned with specialist directional bias and execution timing."
                            )
                        else:
                            logger.debug(
                                f"[{symbol}] Adjudication confirmed: decision strictly aligned with framework."
                            )
                    elif adj_check.get("verdict") == "FLAG_FOR_REVIEW":
                        logger.info(
                            f"[{symbol}] Adjudication flagged for review: {adj_check.get('mismatch_explanation')}"
                        )
                    elif adj_check.get("verdict") == "UNVERIFIED":
                        logger.warning(
                            f"[{symbol}] Adjudication verification could not run (fail-closed): {adj_check.get('mismatch_explanation')}"
                        )
                        analysis.rationale = (analysis.rationale or "") + (
                            f"\n\n[SYSTEM: Adjudication verifier UNREACHABLE this cycle — decision NOT independently re-verified against the framework. Confidence discounted as a precaution.]"
                        )
                        if analysis.decision in ("buy", "sell"):
                            analysis.confidence = (analysis.confidence or 0.7) * 0.92
                        await session.commit()
            except Exception as e:
                logger.debug(f"[{symbol}] Adjudication verification failed (non-fatal): {e}")

        if analysis.decision in ("buy", "sell"):
            try:
                from monika.application.analysis.calculators.unified_threshold_calculator import (
                    compute_unified_confluence_threshold,
                )

                effective_threshold, _ = await compute_unified_confluence_threshold(
                    session=session,
                    symbol=symbol,
                    settings=self.settings,
                )
            except Exception as thr_err:
                logger.debug(f"[{symbol}] Failed computing unified threshold, using fallback: {thr_err}")
                effective_threshold = self.settings.get("trading", {}).get("auto_execute_min_confluence", 7)

            near_threshold = analysis.confluence_score and analysis.confluence_score <= effective_threshold + 1
            elevated_priced_in = analysis.priced_in_score and analysis.priced_in_score >= 6

            significant_disagreement_flag = False
            try:
                key = f"specialist_disagreement_{symbol}"
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                if cfg and cfg.value:
                    try:
                        flag_data = (
                            json.loads(cfg.value) if isinstance(cfg.value, str) and cfg.value.startswith("{") else {}
                        )
                        flagged_at_str = (
                            flag_data.get("flagged_at")
                            or flag_data.get("timestamp")
                            or (cfg.value if isinstance(cfg.value, str) and not cfg.value.startswith("{") else None)
                        )
                        flagged_at = datetime.fromisoformat(flagged_at_str) if isinstance(flagged_at_str, str) else None
                        if flagged_at:
                            if flagged_at.tzinfo is None:
                                flagged_at = flagged_at.replace(tzinfo=timezone.utc)
                            if (datetime.now(timezone.utc) - flagged_at).total_seconds() < 900:
                                significant_disagreement_flag = True
                            else:
                                await session.delete(cfg)
                        else:
                            significant_disagreement_flag = True
                    except Exception:
                        significant_disagreement_flag = False
            except Exception:
                pass

            recent_sl_streak = await self._get_symbol_sl_streak(session, symbol)

            if near_threshold or elevated_priced_in or significant_disagreement_flag or recent_sl_streak >= 2:
                sec_opinion = await self._run_second_opinion_check(session, symbol, analysis)
                if not sec_opinion.get("agree", True):
                    analysis.confidence = (analysis.confidence or 0.8) * 0.92
                    analysis.rationale = (analysis.rationale or "") + (
                        f"\n\n[SYSTEM: Secondary Model disagreed "
                        f"(category={sec_opinion.get('disagreement_category')}, "
                        f"reason={sec_opinion.get('reason')}). Confidence slightly adjusted.]"
                    )
                    confidence = analysis.confidence
                    await session.commit()
                elif recent_sl_streak >= 2:
                    analysis.rationale = (
                        (analysis.rationale or "")
                        + f"\n\n[SYSTEM: {recent_sl_streak} SL beruntun terdeteksi, second-opinion tetap setuju — tapi tetap waspada.]"
                    )
                    await session.commit()

        return decision, confidence
