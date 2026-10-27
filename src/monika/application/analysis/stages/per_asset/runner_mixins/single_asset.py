# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/single_asset.py
# Description: Single asset analysis execution mixin for PerAssetRunner
# ==============================================================================

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.stages.per_asset.context_builder import SYMBOL_TO_COT
from monika.application.analysis.stages.per_asset.runner_mixins.base import (
    _RunnerMixinBase,
    _get_clock,
)
from monika.application.analysis.stages.per_asset.runner_mixins.single_asset_helpers import (
    compute_prompt_invariants,
    extract_entry_price_from_analysis,
    handle_billing_fallback,
)
from monika.application.analysis.stages.preflight_gate import PreFlightTurnGate
from monika.application.analysis.tools.tools_definitions import (
    ASSET_RESTRICTED_TOOLS,
    minify_tool_definitions,
)
from monika.infrastructure.database.models import ActivityLog, AssetAnalysis

logger = logging.getLogger("TradingAgent.PerAssetStage")


class SingleAssetAnalysisMixin(_RunnerMixinBase):
    """Mixin implementing full single-asset analysis execution lifecycle (run_one)."""

    async def run_one(
        self,
        session: AsyncSession,
        symbol: str,
        extra_context: Optional[str] = None,
        skip_cooldown: bool = False,
        is_secondary: bool = False,
        bypass_prescreen: bool = False,
        use_session_trigger_client: bool = False,
        stage1_confidence: float | None = None,
    ) -> dict:
        """Mengeksekusi analisis lengkap (SMC, teknikal, makro) untuk satu simbol tunggal."""
        logger.info(f"Starting per-asset analysis for {symbol}...")
        start_time = _get_clock().now()
        active_client = (
            self.session_trigger_client
            if use_session_trigger_client
            else self.secondary_client
            if is_secondary
            else self.primary_client
        )

        # Cooldown check (only for non-forced reruns)
        if not skip_cooldown:
            last_run = self._last_analysis_time.get(symbol)
            if last_run:
                elapsed_minutes = (start_time - last_run).total_seconds() / 60
                if elapsed_minutes < self._min_reanalysis_minutes:
                    logger.info(
                        f"[{symbol}] Cooldown active: last analysis {elapsed_minutes:.0f}min ago "
                        f"(cooldown={self._min_reanalysis_minutes}min). Skipping."
                    )
                    return {
                        "success": True,
                        "symbol": symbol,
                        "decision": "skip",
                        "confidence": 0.0,
                        "analysis_id": None,
                        "rationale": f"Cooldown: last analysis {elapsed_minutes:.0f}min ago.",
                        "elapsed_seconds": 0,
                        "skipped_by_cooldown": True,
                    }
        # Pre-flight Turn Gate (Zero-token rejection on unviable market conditions)
        if self.settings.get("analysis", {}).get("enable_preflight_gate", True) and not getattr(
            self, "_skip_preflight", False
        ):
            preflight_ok, preflight_reason = await PreFlightTurnGate.evaluate_preconditions(
                session=session,
                symbol=symbol,
                settings=self.settings,
                mt5_client=getattr(self, "mt5_client", None),
                override_time=start_time,
            )
            if not preflight_ok:
                logger.info(f"[{symbol}] PreFlightTurnGate REJECT: {preflight_reason}")
                return {
                    "success": True,
                    "symbol": symbol,
                    "decision": "wait",
                    "confidence": 0.0,
                    "analysis_id": None,
                    "rationale": f"PreFlightGate: {preflight_reason}",
                    "elapsed_seconds": (_get_clock().now() - start_time).total_seconds(),
                    "skipped_by_preflight": True,
                }

        # Check brief freshness and quality
        early_brief_res, brief_check, initial_context_blocks = await self._check_brief_freshness_and_quality(
            session, symbol, start_time
        )
        if early_brief_res:
            return early_brief_res

        # SSVP Context Coherence Check
        coherence_injection = await self._compute_ssvp_coherence(session, symbol, brief_check)

        # Phase 4: Dynamic Threshold calculation
        from monika.application.analysis.calculators.adaptive_policy import AdaptiveRiskPolicy

        adaptive_policy = AdaptiveRiskPolicy(self.settings)
        effective_threshold, threshold_reason = await adaptive_policy.get_effective_threshold(session, symbol)
        self._last_threshold_reason = threshold_reason  # Store for debugging if needed
        logger.info(f"[{symbol}] Adaptive Threshold: {effective_threshold}/14 ({threshold_reason})")

        # Fetch bundle DULU (sebelum skill compose)
        from monika.domain.market.instrument_identity import resolve_instrument_identity

        ident = resolve_instrument_identity(symbol)
        cot_code = ident.cot_code or SYMBOL_TO_COT.get(ident.canonical_symbol, "")
        data_bundle, raw_bundle_data, bundle_success, tool_order_guidance = await self._fetch_stage2_bundle(
            session, symbol, cot_code
        )

        # Compute Zero-Arithmetic Invariants (SOTA Grounding)
        curr_px, atr_f, adr_f = await compute_prompt_invariants(
            self.settings, symbol, raw_bundle_data, initial_context_blocks, session=session
        )

        # TimesFM 3.0 Quantile Skewness Alpha Injection
        try:
            from monika.application.analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator
            from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

            tfm_engine = TimesFMEngine(self.settings)
            tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe="H1", max_age_hours=8.0)
            if tfm_fc and tfm_fc.get("quantiles"):
                alpha_res = TimesFMAlphaCalculator.calculate_skew_from_quantiles(
                    tfm_fc["quantiles"], current_price=float(curr_px) if curr_px is not None else None
                )
                if alpha_res.get("valid"):
                    tfm_prompt_block = TimesFMAlphaCalculator.format_for_prompt(alpha_res)
                    initial_context_blocks.append(("TIMESFM 3.0 PROBABILISTIC SKEW ALPHA", tfm_prompt_block))
        except Exception as tfm_alpha_err:
            logger.debug(f"[{symbol}] TimesFM alpha prompt injection non-fatal: {tfm_alpha_err}")

        # Initialize WorkingScratchpad for symbol
        try:
            from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad

            WorkingScratchpad.clear(symbol)
            seed_data = {}
            if atr_f is not None:
                seed_data["h4_atr"] = float(atr_f)
            if adr_f is not None:
                seed_data["daily_adr"] = float(adr_f)
            WorkingScratchpad.update_scratchpad(symbol, seed_data)
        except Exception as ws_err:
            logger.debug(f"[{symbol}] WorkingScratchpad init non-fatal: {ws_err}")

        # Extract detected regime and active playbook from bundle data or classify
        detected_regime = ""
        active_playbook = ""
        if isinstance(raw_bundle_data, dict):
            active_playbook = str(raw_bundle_data.get("active_playbook_id", "") or "")
            mr = raw_bundle_data.get("market_regime")
            if isinstance(mr, dict):
                sym_reg = mr.get(symbol)
                if isinstance(sym_reg, dict):
                    detected_regime = sym_reg.get("regime", "")
                elif isinstance(sym_reg, str):
                    detected_regime = sym_reg
                else:
                    detected_regime = mr.get("regime", "")
        if not detected_regime:
            try:
                from monika.application.analysis.calculators.regime_classifier import classify_market_regime

                rc = await classify_market_regime(session, symbol, self.settings)
                detected_regime = rc.get("final_regime") or rc.get("label") or ""
            except Exception as e:
                logger.debug(f"[{symbol}] Regime classification fallback non-fatal: {e}")

        # Compose system prompt
        system_prompt, abort_prompt_res = self._compose_stage2_system_prompt(
            symbol,
            cot_code,
            effective_threshold,
            tool_order_guidance,
            detected_regime=detected_regime,
            active_playbook=active_playbook,
        )
        if abort_prompt_res:
            return abort_prompt_res

        core_instructions = self._build_user_message(symbol)

        # Build context blocks
        context_blocks = initial_context_blocks + await self._build_stage2_context_blocks(
            session, symbol, brief_check, start_time, extra_context, stage1_confidence, coherence_injection or ""
        )

        data_ok, data_reason = await self._check_minimum_data_quality(session, symbol)
        if not data_ok:
            logger.warning(f"[{symbol}] Data quality gate failed: {data_reason}")
            return {
                "success": True,
                "symbol": symbol,
                "decision": "wait",
                "confidence": 0.0,
                "rationale": f"Insufficient data quality: {data_reason}",
                "analysis_id": None,
                "elapsed_seconds": 0,
                "skipped_by_data_quality": True,
            }

        # Task 4.1: Data coherence check
        cost_mode = self.settings.get("trading", {}).get("cost_mode", "standard")
        if cost_mode != "lite":
            is_coherent, coh_msg = await self._check_data_coherence_for_analysis(session, symbol)
            if not is_coherent:
                logger.warning(f"[{symbol}] Data coherence gate failed: {coh_msg}")
                return {
                    "success": True,
                    "symbol": symbol,
                    "decision": "wait",
                    "confidence": 0.0,
                    "rationale": f"Data coherence failed: {coh_msg}",
                    "analysis_id": None,
                    "elapsed_seconds": 0,
                    "skipped_by_data_quality": True,
                }
        else:
            logger.info(f"[{symbol}] Data coherence gate BYPASSED (lite mode)")

        # Pre-screen dengan Haiku sebelum menggunakan Sonnet 5 yang lebih mahal
        if bypass_prescreen:
            should_analyze, screen_reason = True, "bypassed via trigger"
        else:
            should_analyze, screen_reason = await self._run_prescreen(session, symbol)

        try:
            from sqlalchemy import select as _psel

            from monika.infrastructure.database.models import PrescreenLog, PriceOHLCV

            last_price = (
                await session.execute(
                    _psel(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == symbol)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            session.add(
                PrescreenLog(
                    symbol=symbol,
                    decision=("analyze" if should_analyze else "skip"),
                    reason=screen_reason[:500],
                    price_at_check=last_price,
                )
            )
            await session.commit()
        except Exception as e:
            logger.debug(f"Failed to log prescreen outcome: {e}")

        # Melacak keputusan prescreen untuk evaluasi akurasi
        try:
            session.add(
                ActivityLog(
                    category="analysis",
                    description=(
                        f"Haiku prescreen {symbol}: {'ANALYZE' if should_analyze else 'SKIP'} — {screen_reason[:100]}"
                    ),
                    actor="haiku_prescreen",
                )
            )
            await session.commit()
        except Exception:
            pass

        if not should_analyze:
            logger.info(f"[{symbol}] Pre-screen SKIP: {screen_reason}")
            await self._log(session, f"Haiku pre-screen skip {symbol}: {screen_reason}")
            return {
                "success": True,
                "symbol": symbol,
                "decision": "skip",
                "confidence": 0.0,
                "rationale": f"Haiku pre-screen: {screen_reason}",
                "analysis_id": None,
                "tool_calls_made": 1,
                "turns": 1,
                "elapsed_seconds": (_get_clock().now() - start_time).total_seconds(),
                "skipped_by_prescreen": True,
            }

        # Mark analysis start time now that prescreen has passed
        self._last_analysis_time[symbol] = start_time

        # === ASSEMBLE FINAL MESSAGE ===
        message_parts = [core_instructions]

        if context_blocks:
            message_parts.append("\n\n--- ADDITIONAL CONTEXT (Read before executing tools) ---")
            for label, content in context_blocks:
                message_parts.append(f"\n[{label}]\n{content}")

        user_message = "\n".join(message_parts)

        # Bundling data teknikal untuk mengurangi panggilan tool
        if bundle_success:
            trimmed_msg = self._build_trimmed_user_message(symbol)
            user_message = f"{trimmed_msg}\n\n[PRE-FETCHED DATA]\n{data_bundle or ''}"
            if context_blocks:
                user_message += "\n\n" + "\n".join(f"[{label}]\n{content}" for label, content in context_blocks)
            logger.info(
                f"[{symbol}] Data bundle injected ({len(data_bundle or '')} chars), verbose instructions removed"
            )
        else:
            logger.warning(f"[{symbol}] Data bundle empty — AI will call all tools manually")

        # Task 2.2: Verify data freshness right before sending to AI
        is_fresh, fresh_msg = await self._verify_data_currency(session, symbol)
        if not is_fresh:
            logger.info(f"[{symbol}] Data staleness check failed: {fresh_msg}")
            return {
                "success": True,
                "symbol": symbol,
                "decision": "wait",
                "confidence": 0.0,
                "analysis_id": None,
                "skipped_by_data_quality": True,
                "rationale": fresh_msg,
                "elapsed_seconds": (_get_clock().now() - start_time).total_seconds(),
            }

        precomputed_context = await self._fetch_precomputed_data(session, symbol)
        if precomputed_context:
            user_message += f"\n\n--- PRE-COMPUTED MACRO SIGNALS (for context) ---\n{precomputed_context}"

        try:
            from monika.application.analysis.calculators.regime_classifier import classify_market_regime

            regime_res = await classify_market_regime(session, symbol, self.settings)
            if regime_res and regime_res.get("regime"):
                user_message += (
                    f"\n\n[MARKET REGIME DETECTED]: {regime_res['regime'].upper()} "
                    f"(Quality: {regime_res.get('composite_quality', 'NORMAL')}). Adjust strategy accordingly."
                )
        except Exception as e:
            logger.debug(f"Failed to fetch market regime for prompt injection: {e}")

        # SOTA Frozen Tool Selection: Deterministic pinned tools preserving 100% KV-Cache prefix hit rate
        dynamic_tools = minify_tool_definitions(ASSET_RESTRICTED_TOOLS)

        ineffective_factors_note = ""
        try:
            from monika.core.analytics.analysis_tracker import compute_factor_effectiveness

            eff = await compute_factor_effectiveness(session, days_back=30)
            dropped_factors = eff.get("dropped_factors", [])
            if dropped_factors:
                ineffective_factors_note = (
                    f"\n[NOTE: Statistically ineffective factors to avoid: {', '.join(dropped_factors)}]\n"
                )
        except Exception as e:
            logger.debug(f"Failed to filter ineffective factors: {e}")

        # Injeksi AI Decision Memory
        extra_context_str = ineffective_factors_note
        try:
            from monika.application.analysis.memory.decision_log import DecisionLogger

            lessons = await DecisionLogger.get_recent_lessons(session, symbol, limit=3)
            global_lessons = await DecisionLogger.get_global_lessons(session, exclude_symbol=symbol, limit=2)
            if lessons["real_trades"] or lessons["paper_whatifs"]:
                extra_context_str = "--- AI Decision Memory (Recent Lessons) ---\n"
                if lessons["real_trades"]:
                    extra_context_str += "Real Trades Outcome:\n"
                    for r in lessons["real_trades"]:
                        adj_str = f" | Next Adjustment: {r['next_adjustment']}" if r.get("next_adjustment") else ""
                        extra_context_str += (
                            f"- Decision: {r['decision']} | Profitable: {r['profitable']} | Tags: {r['tags']}{adj_str}\n"
                            f"  Specific Lesson: {r.get('specific_lesson', r['reflection'])}\n"
                        )
                if lessons["paper_whatifs"]:
                    extra_context_str += "Paper What-Ifs (Dodged/Missed):\n"
                    for r in lessons["paper_whatifs"]:
                        adj_str = f" | Next Adjustment: {r['next_adjustment']}" if r.get("next_adjustment") else ""
                        extra_context_str += (
                            f"- Blocked Decision: {r['decision']} (Reason: {r['reason_rejected']}) | "
                            f"Direction Correct: {r['direction_correct']} | Tags: {r['tags']}{adj_str}\n"
                            f"  Specific Lesson: {r.get('specific_lesson', r['reflection'])}\n"
                        )
            if global_lessons:
                if not extra_context_str:
                    extra_context_str = "--- AI Decision Memory (Recent Lessons) ---\n"
                extra_context_str += "\nCross-Symbol Structural Lessons (may generalize):\n"
                for gl in global_lessons:
                    extra_context_str += f"- [{gl['symbol']}] {gl['lesson']}\n"

            if isinstance(raw_bundle_data, dict):
                raw_bundle_data["recent_lessons"] = {"symbol_lessons": lessons, "global_lessons": global_lessons}

            try:
                from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

                c_writer = ChronicleWriter(self.settings)
                chronicle_ctx = await c_writer.get_chronicle_for_symbol(session, symbol, days_back=30, limit=5)
                if not chronicle_ctx or "No specific macro chronicle" in chronicle_ctx:
                    chronicle_ctx = await c_writer.get_chronicle_context(session, days_back=30, limit=5)
                if chronicle_ctx:
                    if not extra_context_str:
                        extra_context_str = ""
                    extra_context_str += f"\n{chronicle_ctx}\n"
                    if isinstance(raw_bundle_data, dict):
                        raw_bundle_data["market_chronicle"] = chronicle_ctx
            except Exception as e:
                logger.debug(f"Failed to load chronicle context: {e}")

            compressed_query = (
                select(ActivityLog)
                .where(ActivityLog.category == "compressed_memory")
                .order_by(ActivityLog.timestamp.desc())
                .limit(2)
            )
            compressed_logs = (await session.execute(compressed_query)).scalars().all()
            if compressed_logs:
                if not extra_context_str:
                    extra_context_str = "--- AI Decision Memory (Recent Lessons) ---\n"
                extra_context_str += "\n--- LONG-TERM AI COMPRESSED MEMORY ---\n"
                for clog in compressed_logs:
                    extra_context_str += f"{clog.description}\n"
        except Exception as e:
            logger.debug(f"Failed to load memory context: {e}")

        # Specialist Agent Decomposition
        specialist_biases: dict[str, str] = {}
        specialist_confidence: dict[str, str] = {}
        specialist_trust: dict[str, float] = {}
        use_specialists = self.settings.get("agent_architecture", {}).get("specialist_decomposition", True)
        if use_specialists and not bundle_success:
            logger.warning(
                f"[{symbol}] Specialist decomposition skipped — pre-fetch data bundle failed; "
                f"running specialists without context could mislead the adjudicator with false 'NEUTRAL' signals."
            )
            use_specialists = False

        # Conditional Specialist Gate: Skip 3 LLM calls if asset is confirmed flat/ranging with low momentum
        if use_specialists and isinstance(raw_bundle_data, dict):
            f_brief = raw_bundle_data.get("get_fundamental_brief", {})
            s1_conf = stage1_confidence or (f_brief.get("confidence") if isinstance(f_brief, dict) else 0.5)
            r_data = raw_bundle_data.get("get_volatility_regime", {})
            regime_name = str(r_data.get("regime") or raw_bundle_data.get("regime") or "").lower()
            adx_val = None
            tech_ind = raw_bundle_data.get("get_technical_indicators", {})
            if isinstance(tech_ind, dict):
                adx_val = tech_ind.get("adx") or tech_ind.get("ADX")

            if (s1_conf is not None and s1_conf < 0.40) or (
                adx_val is not None and adx_val < 18.0 and regime_name in ("range", "squeeze_consolidation", "ranging")
            ):
                logger.info(
                    f"[{symbol}] Skipping specialist pipeline (ADX={adx_val}, regime={regime_name}, s1_conf={s1_conf}) — "
                    f"zero LLM tokens burned for flat/ranging asset"
                )
                use_specialists = False

        if use_specialists:
            (
                spec_extra_ctx,
                specialist_biases,
                specialist_confidence,
                specialist_trust,
            ) = await self._execute_specialist_debate_pipeline(session, symbol, raw_bundle_data)
            extra_context_str += spec_extra_ctx

        # Compute prefetch_satisfied_tools from raw_bundle_data
        prefetch_satisfied_tools = set()
        if isinstance(raw_bundle_data, dict):
            for k, v in raw_bundle_data.items():
                is_valid = False
                if isinstance(v, dict):
                    is_valid = bool(v) and not v.get("error")
                elif isinstance(v, list):
                    is_valid = bool(v)
                elif v is not None:
                    is_valid = True

                if is_valid:
                    prefetch_satisfied_tools.add(k)
                    # Normalize to base tool name for inspection guards matching
                    if k.startswith("get_"):
                        base_k = re.sub(r"_(?:M15|M30|H1|H4|D1|W1|MN|recent)$", "", k)
                        prefetch_satisfied_tools.add(base_k)
                    elif k.startswith("price_history_"):
                        prefetch_satisfied_tools.add("get_price_history")
                    elif k.startswith("smc_zones_"):
                        prefetch_satisfied_tools.add("get_smc_zones")
                    elif k.startswith("structure_breaks_"):
                        prefetch_satisfied_tools.add("get_structure_breaks")
                    elif k.startswith("swing_points_"):
                        prefetch_satisfied_tools.add("get_swing_points")
                    elif k.startswith("technical_indicators_"):
                        prefetch_satisfied_tools.add("get_technical_indicators")

        # Rate limiting
        try:
            from monika.infrastructure.llm.rate_limiting.claude_rate_limiter import ClaudeRateLimiter

            await ClaudeRateLimiter.acquire_session_slot(model_name=active_client.model)
        except Exception as e:
            logger.debug(f"Rate limiter error (non-fatal): {e}")

        # Wire in Per-Symbol Adaptive Thinking Budget
        try:
            from monika.infrastructure.llm.adaptive_thinking import PerSymbolAdaptiveThinkingAllocator

            vix_val = None
            regime_val = None
            if isinstance(raw_bundle_data, dict):
                v_data = raw_bundle_data.get("get_vix")
                if isinstance(v_data, dict):
                    vix_val = v_data.get("vix") or v_data.get("close")
                f_data = raw_bundle_data.get("get_fundamental_brief")
                if isinstance(f_data, dict):
                    regime_val = f_data.get("macro_narrative") or f_data.get("risk_sentiment")

            adaptive_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
                symbol=symbol,
                context={
                    "vix": vix_val,
                    "confluence_score": (stage1_confidence * 14.0) if stage1_confidence else None,
                    "regime": regime_val,
                },
            )
            # Smart Confluence Gate: low confidence (<0.45) caps budget
            if stage1_confidence is not None and stage1_confidence < 0.45:
                adaptive_budget = min(adaptive_budget, 4096)
                logger.info(
                    f"[{symbol}] Adaptive thinking budget capped to 4096 due to low Stage 1 confidence ({stage1_confidence:.2f})"
                )

            if hasattr(active_client, "set_thinking_budget"):
                active_client.set_thinking_budget(adaptive_budget)
            elif hasattr(active_client, "thinking_budget"):
                active_client.thinking_budget = adaptive_budget
            logger.info(f"[{symbol}] Adaptive reasoning budget dynamically set to {adaptive_budget} tokens")
        except Exception as e:
            logger.debug(f"[{symbol}] Adaptive thinking budget allocation error (non-fatal): {e}")

        # Multimodal Vision Chart Snapshot (Wave 2)
        vision_image = raw_bundle_data.get("user_chart_vision_image") if isinstance(raw_bundle_data, dict) else None
        multimodal_images = [vision_image] if isinstance(vision_image, dict) and vision_image.get("data") else None

        # Pre-inject deterministic Volatility Regime Gate status
        edge_cfg = (self.settings.get("trading") or {}).get("edge_strategy") or {}
        vol_cfg = edge_cfg.get("volatility_regime") or {}
        if vol_cfg.get("enabled", True):
            try:
                from monika.application.analysis.calculators.regime_classifier import (
                    compute_bollinger_donchian_chop,
                )

                chop = await compute_bollinger_donchian_chop(session, symbol, "H4", self.settings)
                if chop and chop.get("chop_block"):
                    chop_reason = chop.get("reason") or "range squeeze"
                    user_message += (
                        f"\n\n[VOLATILITY REGIME GATE — ACTIVE (deterministic)]\n"
                        f"Reason: {chop_reason}. "
                        "Market-order BUY/SELL will be rejected. "
                        "The only acceptable submissions are a structural limit/pullback/breakout entry "
                        "at a confirmed level (OB/FVG/sweep) with explicit entry price and confluence_score >= 5, "
                        "or decision='wait'."
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[{symbol}] Volatility regime gate pre-check failed (non-fatal): {e}")

        result = await active_client.run_agent(
            session=session,
            system_prompt=system_prompt,
            user_message=user_message,
            tools=dynamic_tools,
            stage_name=f"per_asset_{symbol}",
            extra_context=extra_context_str if extra_context_str else None,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            multimodal_images=multimodal_images,
        )
        elapsed = (_get_clock().now() - start_time).total_seconds()

        if not result["success"]:
            result = await handle_billing_fallback(
                runner=self,
                session=session,
                symbol=symbol,
                result=result,
                active_client=active_client,
                system_prompt=system_prompt,
                user_message=user_message,
                dynamic_tools=dynamic_tools,
            )

            if not result["success"]:
                msg = f"Per-asset analysis FAILED for {symbol}: {result.get('error')}"
                logger.error(msg)
                await self._log(session, msg, category="error")
                return {**result, "symbol": symbol, "elapsed_seconds": elapsed}

        # Pastikan analisis benar-benar tersimpan pada siklus/sesi saat ini
        now_ts = _get_clock().now()
        analysis = (
            await session.execute(
                select(AssetAnalysis)
                .where(AssetAnalysis.symbol == symbol)
                .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
                .where(AssetAnalysis.generated_at <= now_ts + timedelta(minutes=1))
                .order_by(AssetAnalysis.generated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if analysis:
            m = re.search(r"Market Regime:\s*([^\n]+)", extra_context or "")
            if m:
                analysis.market_regime_at_analysis = m.group(1).strip()
                await session.commit()

        analysis_id = analysis.id if analysis else None

        if analysis_id is None:
            logger.warning(
                f"Analysis for {symbol} completed but no AssetAnalysis found in DB. "
                "LLM may not have called submit_asset_analysis. Initiating multi-tier recovery..."
            )
            analysis = await self._recover_missing_analysis(
                session=session,
                symbol=symbol,
                user_message=user_message,
                result=result,
                active_client=active_client,
                system_prompt=system_prompt,
                dynamic_tools=dynamic_tools,
                start_time=start_time,
            )
            if analysis:
                analysis_id = analysis.id

        decision = analysis.decision if analysis else "UNKNOWN"
        confidence = analysis.confidence if analysis else 0.0

        decision, confidence = await self._post_process_analysis_verifications(
            session=session,
            symbol=symbol,
            analysis=analysis,
            decision=decision,
            confidence=confidence,
            raw_bundle_data=raw_bundle_data,
            active_client=active_client,
            effective_threshold=effective_threshold,
            specialist_biases=specialist_biases,
            specialist_confidence=specialist_confidence,
            specialist_trust=specialist_trust,
        )

        msg = (
            f"Per-asset analysis complete: {symbol} → {decision} "
            f"(conf={confidence:.2f}, {result['tool_calls_made']} tools, "
            f"{result['turns']} turns, {elapsed:.1f}s)"
        )
        logger.info(msg)
        await self._log(session, msg)

        try:
            from monika.infrastructure.database.event_store import TradingEventStore

            await TradingEventStore.emit(
                session=session,
                event_type="analysis.stage2.completed",
                payload={
                    "symbol": symbol,
                    "analysis_id": analysis_id,
                    "decision": decision,
                    "confidence": confidence,
                    "elapsed_seconds": elapsed,
                    "tool_calls_made": result.get("tool_calls_made", 0),
                    "turns": result.get("turns", 0),
                },
                correlation_id=f"cycle_stage2_{symbol}_{analysis_id or clock.now().strftime('%Y%m%d%H%M%S')}",
                actor="per_asset_stage",
            )
        except Exception as es_err:
            logger.debug(f"Event store emit analysis.stage2.completed error: {es_err}")

        # Clean up temporary pending specialist biases
        try:
            from monika.infrastructure.database.models import SystemConfig

            _biases_key = f"pending_specialist_biases_{symbol}"
            _cfg = (
                await session.execute(select(SystemConfig).where(SystemConfig.key == _biases_key))
            ).scalar_one_or_none()
            if _cfg:
                await session.delete(_cfg)
                await session.commit()
        except Exception:
            pass

        entry_price_val = extract_entry_price_from_analysis(analysis)

        if analysis and hasattr(analysis, "decision") and analysis.decision is not None:
            decision = analysis.decision

        def _safe_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except ValueError, TypeError:
                return None

        def _safe_int(val: Any) -> Optional[int]:
            if val is None:
                return None
            try:
                return int(val)
            except ValueError, TypeError:
                return None

        result.update(
            {
                "symbol": symbol,
                "analysis_id": analysis_id,
                "decision": decision,
                "confidence": confidence,
                "entry_price": entry_price_val,
                "stop_loss": _safe_float(analysis.stop_loss) if analysis else None,
                "take_profit": _safe_float(analysis.take_profit) if analysis else None,
                "confluence_score": _safe_int(analysis.confluence_score) if analysis else None,
                "elapsed_seconds": elapsed,
            }
        )
        return result
