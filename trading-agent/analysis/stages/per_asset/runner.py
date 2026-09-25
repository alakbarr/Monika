# ==============================================================================
# File: analysis/stages/per_asset/runner.py
# ==============================================================================

import asyncio
import logging
import json
import sys
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

from analysis.providers.llm_factory import get_client_for_task, create_client
from analysis.tools.tools_definitions import (
    STAGE2_TOOLS, STAGE2_TOOLS_V2, STAGE2_PRESCREEN_TOOLS,
    STAGE2_ESSENTIAL_TOOLS, STAGE2_FROZEN_TOOLS
)
from analysis.stages.preflight_gate import PreFlightTurnGate
from database.models import ActivityLog

from analysis.stages.per_asset.context_builder import (
    ContextBuilderMixin, ContextBuilder, SYMBOL_TO_COT, SYSTEM_PROMPT_TEMPLATE,
    _flatten_system_prompt, _render_specialist_prompt
)
from analysis.stages.per_asset.specialist_pipeline import SpecialistPipelineMixin, SpecialistPipeline
from analysis.stages.per_asset.verifiers import VerifiersMixin, VerifierService, _get_symbol_sl_streak

logger = logging.getLogger("TradingAgent.PerAssetStage")

def _get_asyncio():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "asyncio"):
        return pas.asyncio
    return asyncio

def _get_clock():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "clock"):
        return pas.clock
    return clock

class PerAssetRunner(ContextBuilderMixin, SpecialistPipelineMixin, VerifiersMixin):
    """Eksekutor utama Tahap 2 yang mengorkestrasi analisis seluruh aset."""

    def __init__(self, settings: dict, mt5_client: Optional[object] = None) -> None:
        """
        Args:
            settings: Dictionary pengaturan lengkap.
            mt5_client: Optional MT5 client instance for preflight quote checks and execution.
        """
        self.settings = settings
        self.mt5_client = mt5_client
        # Composition over Inheritance (H-1)
        self.context_builder = ContextBuilder(settings)
        self.specialist_pipeline = SpecialistPipeline(settings, runner=self)
        self.verifiers = VerifierService(settings, runner=self)

        self._specialist_weights_cache = {'weights': None, 'ts': None}
        analysis_cfg = settings.get("analysis", {}) or settings.get("claude", {})
        
        # Batas turn tool dikurangi karena data sudah dibundel (pre-bundled)
        stage2_tool_turns = analysis_cfg.get("stage2_max_tool_turns", 8)
        
        self.primary_client = get_client_for_task("stage2_per_asset_primary", settings)
        self.session_trigger_client = get_client_for_task("stage2_session_trigger", settings)

        try:
            self.secondary_client = get_client_for_task("stage2_per_asset_secondary", settings)
        except Exception:
            self.secondary_client = self.primary_client

        # Pre-screener opsional (Haiku)
        prescreen_task = settings.get("llm", {}).get("task_roles", {}).get("stage2_prescreen", {})
        prescreen_model = prescreen_task.get("primary", "")
        try:
            self._haiku_client = get_client_for_task("stage2_prescreen", settings) if prescreen_model else None
        except Exception:
            self._haiku_client = None
        trading_cfg = settings.get("trading", {})
        self.asset_universe: list[str] = trading_cfg.get("asset_universe", ["XAUUSD", "EURUSD"])
        self.always_open_assets = set(trading_cfg.get("24_7_assets", ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]))
        self.run_parallel: bool = trading_cfg.get("parallel_asset_analysis", False)
        
        self._last_analysis_time: dict[str, datetime] = {}
        self._min_reanalysis_minutes: int = int(
            trading_cfg.get('schedule', {}).get('min_reanalysis_minutes', 30)
        )
        self.consent_callback: Optional[Callable[..., Any]] = None
        self.is_fallback_always_approved: Optional[Callable[[], bool]] = None

    async def _fetch_stage1_confidence(self, session: AsyncSession) -> float:
        """P2-2: Fetch stage1 confidence fresh per-call instead of caching on shared instance.
        Fixes race condition where NewsWatcher/TriggerChecker/PositionExitReviewer call
        run_one() concurrently on the same instance and read stale cross-cycle values.
        """
        from database.models import FundamentalBrief
        from sqlalchemy import select
        from utils.calibration.confidence_calibrator import get_calibrated_confidence
        try:
            brief = (await session.execute(
                select(FundamentalBrief)
                .order_by(FundamentalBrief.generated_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            raw_conf = brief.confidence if (brief and brief.confidence is not None) else 0.50
            return await get_calibrated_confidence(session, raw_conf)
        except Exception:
            return 0.50

    async def run_all(
        self,
        session_factory: Any,
        symbols: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        per_symbol_contexts: Optional[dict] = None,
        is_secondary: bool = False,
        use_session_trigger_client: bool = False,
        skip_cooldown: bool = False,
        user_market_intel: Optional[list] = None,
    ) -> dict[str, dict]:
        """Menjalankan siklus analisis untuk daftar simbol (bisa berurutan atau paralel)."""
        
        from sqlalchemy import select

        def _format_intel_for_symbol(sym: str, intel_list: Optional[list]) -> str:
            if not intel_list:
                return ""
            relevant = []
            sym_clean = sym.upper().replace('/', '')
            for item in intel_list:
                raw_aff = item.get("affected_symbols") or []
                if isinstance(raw_aff, str):
                    aff_list = [s.strip() for s in raw_aff.split(",") if s.strip()]
                else:
                    aff_list = list(raw_aff)
                aff = [s.upper().replace('/', '') for s in aff_list]
                if not aff or "ALL" in aff or sym_clean in aff:
                    relevant.append(item)
            if not relevant:
                return ""
            lines = ["[OPERATOR MARKET INTELLIGENCE & DIRECTIVES FOR THIS ASSET]"]
            for it in relevant:
                lines.append(f"• ID #{it.get('id')} [{it.get('intel_type', '').upper()}]: {it.get('title')}")
                lines.append(f"  Directive: {it.get('directive', 'neutral')} | Target Cycle: {it.get('target_cycle', 'continuous')}")
                lines.append(f"  Summary: {it.get('summary')}")
                if it.get("full_content"):
                    lines.append(f"  Details: {it.get('full_content')[:400]}")
            return "\n".join(lines)
        
        targets = symbols or self.asset_universe
        logger.info(f"Running per-asset analysis for {len(targets)} symbols: {targets}")
        try:
            from analysis.event_broadcaster import emit_analysis_event
            emit_analysis_event("analysis_step_start", {"step": "prefetch_data", "symbols": targets})
        except Exception:
            pass
        
        # Ambil nilai confidence dari brief Tahap 1 untuk menyesuaikan agresivitas Tahap 2
        stage1_confidence = 0.50
        try:
            from database.models import FundamentalBrief
            async with session_factory() as session:
                brief = (await session.execute(
                    select(FundamentalBrief)
                    .order_by(FundamentalBrief.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if brief and brief.confidence is not None:
                    stage1_confidence = brief.confidence
        except Exception as e:
            logger.debug(f"Stage1 confidence fetch failed (non-fatal): {e}")

        if self.run_parallel:
            # Limit concurrent API calls untuk menghindari rate limiting & provider congestion
            from asyncio import Semaphore
            max_concurrency = int(self.settings.get("trading", {}).get("parallel_max_concurrency", 2))
            sem = Semaphore(max(1, max_concurrency))
            
            async def run_one_with_session_and_sem(symbol):
                async with sem:
                    async with session_factory() as session:
                        symbol_context = (per_symbol_contexts or {}).get(symbol, '')
                        intel_context = _format_intel_for_symbol(symbol, user_market_intel)
                        combined_context = '\n\n'.join(filter(None, [extra_context, symbol_context, intel_context]))
                        return symbol, await self.run_one(
                            session, symbol, combined_context or None, 
                            skip_cooldown=skip_cooldown, is_secondary=is_secondary, 
                            use_session_trigger_client=use_session_trigger_client,
                            stage1_confidence=stage1_confidence
                        )
            
            tasks = [run_one_with_session_and_sem(sym) for sym in targets]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            results = {}
            for item in results_list:
                if isinstance(item, BaseException):
                    logger.error(f"Per-asset parallel error: {item}")
                else:
                    sym, res = item
                    results[sym] = res
            for sym in targets:
                if sym not in results:
                    results[sym] = {
                        "success": False,
                        "decision": "error",
                        "symbol": sym,
                        "error": "Unhandled exception during parallel execution",
                    }
            return results
        else:
            # Berurutan
            results = {}
            for symbol in targets:
                async with session_factory() as session:
                    symbol_context = (per_symbol_contexts or {}).get(symbol, '')
                    intel_context = _format_intel_for_symbol(symbol, user_market_intel)
                    combined_context = '\n\n'.join(filter(None, [extra_context, symbol_context, intel_context]))
                    try:
                        result = await self.run_one(
                            session, symbol, combined_context or None,
                            skip_cooldown=skip_cooldown, is_secondary=is_secondary,
                            use_session_trigger_client=use_session_trigger_client,
                            stage1_confidence=stage1_confidence
                        )
                    except Exception as e:
                        logger.error(f'[{symbol}] run_one raised unhandled exception — isolating: {e}', exc_info=True)
                        result = {
                            'success': False, 'symbol': symbol, 'decision': 'error',
                            'error': str(e), 'elapsed_seconds': 0
                        }
                    results[symbol] = result
                    await _get_asyncio().sleep(1)

            try:
                from analysis.event_broadcaster import emit_analysis_event
                total_in = sum(r.get("input_tokens", 0) for r in results.values() if isinstance(r, dict))
                total_out = sum(r.get("output_tokens", 0) for r in results.values() if isinstance(r, dict))
                emit_analysis_event("analysis_step_complete", {
                    "step": "prefetch_data",
                    "symbols": targets,
                    "input_tokens": total_in,
                    "output_tokens": total_out,
                })
            except Exception:
                pass

            return results

    async def _recover_missing_analysis(
        self,
        session: AsyncSession,
        symbol: str,
        user_message: str,
        result: dict,
        active_client: Any,
        system_prompt: Any,
        dynamic_tools: list,
        start_time: datetime,
    ) -> Optional[Any]:
        """Multi-tier recovery jika LLM selesai tanpa memanggil submit_asset_analysis."""
        final_text = result.get("final_text", "")
        analysis = None
        from database.models import AssetAnalysis
        from datetime import timedelta

        # --- TIER 1: Targeted Recovery Nudge Turn ---
        try:
            recovery_nudge = (
                f"CRITICAL SYSTEM RECOVERY INSTRUCTION: You finished your turns without calling the required 'submit_asset_analysis' tool. "
                f"You MUST call 'submit_asset_analysis' NOW with 'symbol': '{symbol}', 'decision' (buy/sell/wait/avoid), "
                f"'confidence' (0.0 to 1.0), and 'rationale' based on your previous findings. Do not respond with plain text."
            )
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": final_text or "Analysis completed."},
                {"role": "user", "content": recovery_nudge}
            ]
            if hasattr(active_client, 'run_agent_from_messages'):
                rec_result = await active_client.run_agent_from_messages(
                    session=session,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=dynamic_tools,
                    max_tool_turns=3,
                    stage_name=f"per_asset_{symbol}"
                )
                if rec_result.get("success"):
                    analysis = (await session.execute(
                        select(AssetAnalysis)
                        .where(AssetAnalysis.symbol == symbol)
                        .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
                        .order_by(AssetAnalysis.generated_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()
        except Exception as rec_err:
            logger.warning(f"[{symbol}] Tier 1 recovery nudge failed: {rec_err}")

        # --- TIER 2: Heuristic Text Extraction Fallback ---
        if not analysis and final_text:
            try:
                import re
                import re
                text_lower = final_text.lower()
                extracted_decision = None
                
                # Use strict pattern matching to avoid false positives on words like "wait for pullback"
                m_dec = re.search(r'\b(?:decision|action)\s*[:=]\s*["\']?\*?\*?(buy|sell|avoid|wait)\*?\*?["\']?', text_lower)
                if m_dec:
                    extracted_decision = m_dec.group(1)
                elif '"decision": "buy"' in text_lower or "'decision': 'buy'" in text_lower or "**decision**: buy" in text_lower:
                    extracted_decision = "buy"
                elif '"decision": "sell"' in text_lower or "'decision': 'sell'" in text_lower or "**decision**: sell" in text_lower:
                    extracted_decision = "sell"
                elif '"decision": "avoid"' in text_lower or "'decision': 'avoid'" in text_lower or "**decision**: avoid" in text_lower:
                    extracted_decision = "avoid"
                elif '"decision": "wait"' in text_lower or "'decision': 'wait'" in text_lower or "**decision**: wait" in text_lower:
                    extracted_decision = "wait"

                if extracted_decision:
                    logger.info(f"[{symbol}] Tier 2 heuristic extracted decision '{extracted_decision}' from final text.")
                    fallback_payload = {
                        "symbol": symbol,
                        "decision": extracted_decision,
                        "confidence": 0.5,
                        "rationale": final_text[:1000] if final_text else f"Extracted from model final text ({extracted_decision})",
                        "invalidation": "Extracted via heuristic text recovery",
                    }
                    if extracted_decision in ("buy", "sell"):
                        fallback_payload["entry_condition"] = {"type": "market", "detail": "Extracted market entry"}
                        # Try extracting numerical SL and TP from text if available
                        m_sl = re.search(r'(?:stop[-_\s]*loss|sl)\s*[:=]\s*([0-9.]+)', text_lower)
                        m_tp = re.search(r'(?:take[-_\s]*profit|tp)\s*[:=]\s*([0-9.]+)', text_lower)
                        if m_sl and m_tp:
                            try:
                                fallback_payload["stop_loss"] = float(m_sl.group(1))
                                fallback_payload["take_profit"] = float(m_tp.group(1))
                            except ValueError:
                                fallback_payload["stop_loss"] = None
                                fallback_payload["take_profit"] = None
                    
                    from analysis.tools.tool_executor import ToolExecutor
                    executor = ToolExecutor(session, settings=self.settings, model_name=active_client.model, symbol=symbol)
                    submit_res = await executor._tool_submit_asset_analysis(fallback_payload)
                    if submit_res.get("status") in ("recorded", "success") or "id" in submit_res:
                        analysis = (await session.execute(
                            select(AssetAnalysis)
                            .where(AssetAnalysis.symbol == symbol)
                            .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
                            .order_by(AssetAnalysis.generated_at.desc())
                            .limit(1)
                        )).scalar_one_or_none()
            except Exception as ext_err:
                logger.warning(f"[{symbol}] Tier 2 text extraction fallback failed: {ext_err}")

        # --- TIER 3: Deterministic Fallback WAIT Record ---
        if not analysis:
            try:
                logger.warning(f"[{symbol}] Tier 3 inserting deterministic WAIT AssetAnalysis record.")
                fallback_record = AssetAnalysis(
                    symbol=symbol,
                    decision="wait",
                    confidence=0.0,
                    rationale=f"Fallback record: LLM completed without invoking submit_asset_analysis. Raw text snippet: {final_text[:400]}",
                    invalidation="N/A",
                    execution_status="completed",
                    generated_at=_get_clock().now()
                )
                session.add(fallback_record)
                await session.commit()
                analysis = fallback_record
            except Exception as tier3_err:
                logger.error(f"[{symbol}] Tier 3 record insertion failed: {tier3_err}")

        return analysis

    async def run_one(self, session: AsyncSession, symbol: str, extra_context: Optional[str] = None, skip_cooldown: bool = False, is_secondary: bool = False, bypass_prescreen: bool = False, use_session_trigger_client: bool = False, stage1_confidence: float | None = None) -> dict:
        """Mengeksekusi analisis lengkap (SMC, teknikal, makro) untuk satu simbol tunggal."""
        from sqlalchemy import select
        logger.info(f"Starting per-asset analysis for {symbol}...")
        start_time = _get_clock().now()
        active_client = (
            self.session_trigger_client if use_session_trigger_client
            else self.secondary_client if is_secondary
            else self.primary_client
        )
        
        # Cooldown check (only for non-forced reruns)
        if not skip_cooldown:
            last_run = self._last_analysis_time.get(symbol)
            if last_run:
                elapsed_minutes = (start_time - last_run).total_seconds() / 60
                if elapsed_minutes < self._min_reanalysis_minutes:
                    logger.info(
                        f'[{symbol}] Cooldown active: last analysis {elapsed_minutes:.0f}min ago '
                        f'(cooldown={self._min_reanalysis_minutes}min). Skipping.'
                    )
                    return {
                        'success': True, 'symbol': symbol, 'decision': 'skip',
                        'confidence': 0.0, 'analysis_id': None,
                        'rationale': f'Cooldown: last analysis {elapsed_minutes:.0f}min ago.',
                        'elapsed_seconds': 0, 'skipped_by_cooldown': True
                    }
        # Pre-flight Turn Gate (Zero-token rejection on unviable market conditions)
        if self.settings.get("analysis", {}).get("enable_preflight_gate", True) and not getattr(self, "_skip_preflight", False):
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
                    'success': True,
                    'symbol': symbol,
                    'decision': 'wait',
                    'confidence': 0.0,
                    'analysis_id': None,
                    'rationale': f"PreFlightGate: {preflight_reason}",
                    'elapsed_seconds': (_get_clock().now() - start_time).total_seconds(),
                    'skipped_by_preflight': True,
                }

        # Check brief freshness and quality
        early_brief_res, brief_check, initial_context_blocks = await self._check_brief_freshness_and_quality(session, symbol, start_time)
        if early_brief_res:
            return early_brief_res
        
        # SSVP Context Coherence Check
        coherence_injection = await self._compute_ssvp_coherence(session, symbol, brief_check)

        # Phase 4: Dynamic Threshold calculation
        from analysis.calculators.adaptive_policy import AdaptiveRiskPolicy
        adaptive_policy = AdaptiveRiskPolicy(self.settings)
        effective_threshold, threshold_reason = await adaptive_policy.get_effective_threshold(session, symbol)
        self._last_threshold_reason = threshold_reason  # Store for debugging if needed
        logger.info(f"[{symbol}] Adaptive Threshold: {effective_threshold}/14 ({threshold_reason})")

        # Fetch bundle DULU (sebelum skill compose)
        from utils.market.instrument_identity import resolve_instrument_identity
        ident = resolve_instrument_identity(symbol)
        cot_code = ident.cot_code or SYMBOL_TO_COT.get(ident.canonical_symbol, "")
        data_bundle, raw_bundle_data, bundle_success, tool_order_guidance = await self._fetch_stage2_bundle(session, symbol, cot_code)

        # Compute Zero-Arithmetic Invariants (SOTA Grounding)
        curr_px: Optional[float] = None
        atr_f: Optional[float] = None
        adr_f: Optional[float] = None
        try:
            from analysis.calculators.invariant_calculator import compute_trade_invariants, format_invariants_for_prompt
            if isinstance(raw_bundle_data, dict):
                hist = (
                    raw_bundle_data.get("get_price_history_H4")
                    or raw_bundle_data.get("get_price_history_H1")
                    or raw_bundle_data.get("get_price_history")
                )
                if hist and isinstance(hist, dict) and hist.get("bars"):
                    curr_px = hist["bars"][-1].get("close")
                if curr_px is None:
                    ind = (
                        raw_bundle_data.get("get_technical_indicators_H4")
                        or raw_bundle_data.get("get_technical_indicators_D1")
                        or raw_bundle_data.get("get_technical_indicators")
                    )
                    if ind and isinstance(ind, dict):
                        curr_px = ind.get("current_close") or ind.get("close")
                atr_raw = (
                    raw_bundle_data.get("get_atr_H4")
                    or raw_bundle_data.get("get_atr_D1")
                    or raw_bundle_data.get("get_atr")
                )
                atr_f = atr_raw.get("atr") if isinstance(atr_raw, dict) else atr_raw
                adr_raw = raw_bundle_data.get("get_daily_range_context")
                adr_f = adr_raw.get("adr_5d") if isinstance(adr_raw, dict) else None
                smc_raw = (
                    raw_bundle_data.get("get_smc_zones_H4")
                    or raw_bundle_data.get("get_smc_zones")
                )
                smc_f = smc_raw if isinstance(smc_raw, list) else (smc_raw.get("zones") if isinstance(smc_raw, dict) else [])
                sr_raw = (
                    raw_bundle_data.get("get_fibonacci_levels_H4")
                    or raw_bundle_data.get("get_fibonacci_levels")
                    or raw_bundle_data.get("get_optimal_intraday_levels")
                )
                sr_f = sr_raw if isinstance(sr_raw, list) else []

                if curr_px and atr_f:
                    invariants_dict = compute_trade_invariants(
                        symbol=symbol,
                        current_price=float(curr_px),
                        atr=float(atr_f),
                        adr_5d=float(adr_f) if adr_f else float(atr_f) * 2.5,
                        smc_zones=smc_f,
                        sr_zones=sr_f,
                        min_rr=float(self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3))
                    )
                    inv_block = format_invariants_for_prompt(invariants_dict)
                    initial_context_blocks.append(("PRE-COMPUTED TRADE INVARIANTS", inv_block))
        except Exception as inv_err:
            logger.debug(f"[{symbol}] Invariants computation non-fatal: {inv_err}")

        # TimesFM 3.0 Quantile Skewness Alpha Injection
        try:
            from indicators.timesfm_engine import TimesFMEngine
            from analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator
            tfm_engine = TimesFMEngine(self.settings)
            tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe="H1", max_age_hours=8.0)
            if tfm_fc and tfm_fc.get("quantiles"):
                alpha_res = TimesFMAlphaCalculator.calculate_skew_from_quantiles(
                    tfm_fc["quantiles"],
                    current_price=float(curr_px) if curr_px is not None else None
                )
                if alpha_res.get("valid"):
                    tfm_prompt_block = TimesFMAlphaCalculator.format_for_prompt(alpha_res)
                    initial_context_blocks.append(("TIMESFM 3.0 PROBABILISTIC SKEW ALPHA", tfm_prompt_block))
        except Exception as tfm_alpha_err:
            logger.debug(f"[{symbol}] TimesFM alpha prompt injection non-fatal: {tfm_alpha_err}")

        # Initialize Pi-Notebooks WorkingScratchpad for symbol
        try:
            from analysis.memory.working_scratchpad import WorkingScratchpad
            WorkingScratchpad.clear(symbol)
            seed_data = {}
            if atr_f is not None:
                seed_data["h4_atr"] = float(atr_f)
            if adr_f is not None:
                seed_data["daily_adr"] = float(adr_f)
            WorkingScratchpad.update_scratchpad(symbol, seed_data)
        except Exception as ws_err:
            logger.debug(f"[{symbol}] WorkingScratchpad init non-fatal: {ws_err}")

        # Extract detected regime from bundle data or classify
        detected_regime = ""
        if isinstance(raw_bundle_data, dict):
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
                from analysis.calculators.regime_classifier import classify_market_regime
                rc = await classify_market_regime(session, symbol, self.settings)
                detected_regime = rc.get("final_regime") or rc.get("label") or ""
            except Exception as e:
                logger.debug(f"[{symbol}] Regime classification fallback non-fatal: {e}")

        # Compose system prompt
        system_prompt, abort_prompt_res = self._compose_stage2_system_prompt(
            symbol, cot_code, effective_threshold, tool_order_guidance, detected_regime=detected_regime
        )
        if abort_prompt_res:
            return abort_prompt_res

        core_instructions = self._build_user_message(symbol)
        
        # Build context blocks
        context_blocks = initial_context_blocks + await self._build_stage2_context_blocks(
            session, symbol, brief_check, start_time, extra_context, stage1_confidence, coherence_injection
        )

        data_ok, data_reason = await self._check_minimum_data_quality(session, symbol)
        if not data_ok:
            logger.warning(f'[{symbol}] Data quality gate failed: {data_reason}')
            return {
                'success': True, 'symbol': symbol, 'decision': 'wait',
                'confidence': 0.0,
                'rationale': f'Insufficient data quality: {data_reason}',
                'analysis_id': None, 'elapsed_seconds': 0,
                'skipped_by_data_quality': True
            }

        # Task 4.1: Data coherence check
        cost_mode = self.settings.get('trading', {}).get('cost_mode', 'standard')
        if cost_mode != 'lite':
            is_coherent, coh_msg = await self._check_data_coherence_for_analysis(session, symbol)
            if not is_coherent:
                logger.warning(f'[{symbol}] Data coherence gate failed: {coh_msg}')
                return {
                    'success': True, 'symbol': symbol, 'decision': 'wait',
                    'confidence': 0.0,
                    'rationale': f'Data coherence failed: {coh_msg}',
                    'analysis_id': None, 'elapsed_seconds': 0,
                    'skipped_by_data_quality': True
                }
        else:
            logger.info(f'[{symbol}] Data coherence gate BYPASSED (lite mode)')

        # Pre-screen dengan Haiku sebelum menggunakan Sonnet 5 yang lebih mahal
        if bypass_prescreen:
            should_analyze, screen_reason = True, "bypassed via trigger"
        else:
            should_analyze, screen_reason = await self._run_prescreen(session, symbol)
        
        try:
            from database.models import PrescreenLog, PriceOHLCV
            from sqlalchemy import select as _psel
            last_price = (await session.execute(
                _psel(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol).order_by(PriceOHLCV.timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            session.add(PrescreenLog(symbol=symbol, decision=('analyze' if should_analyze else 'skip'),
                                      reason=screen_reason[:500], price_at_check=last_price))
            await session.commit()
        except Exception as e:
            logger.debug(f'Failed to log prescreen outcome: {e}')
            
        # Melacak keputusan prescreen untuk evaluasi akurasi
        try:
            session.add(ActivityLog(
                category="analysis",
                description=(
                    f"Haiku prescreen {symbol}: {'ANALYZE' if should_analyze else 'SKIP'} — {screen_reason[:100]}"
                ),
                actor="haiku_prescreen",
            ))
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
            message_parts.append('\n\n--- ADDITIONAL CONTEXT (Read before executing tools) ---')
            for label, content in context_blocks:
                message_parts.append(f'\n[{label}]\n{content}')
        
        user_message = '\n'.join(message_parts)

        # Bundling data teknikal untuk mengurangi panggilan tool
        if bundle_success:
            trimmed_msg = self._build_trimmed_user_message(symbol)
            user_message = f"{trimmed_msg}\n\n[PRE-FETCHED DATA]\n{data_bundle or ''}"
            if context_blocks:
                user_message += "\n\n" + '\n'.join(
                    f'[{label}]\n{content}' for label, content in context_blocks
                )
            logger.info(f"[{symbol}] Data bundle injected ({len(data_bundle or '')} chars), verbose instructions removed")
        else:
            logger.warning(f"[{symbol}] Data bundle empty — AI will call all tools manually")

        # Task 2.2: Verify data freshness right before sending to AI
        is_fresh, fresh_msg = await self._verify_data_currency(session, symbol)
        if not is_fresh:
            logger.info(f"[{symbol}] Data staleness check failed: {fresh_msg}")
            return {
                'success': True, 'symbol': symbol, 'decision': 'wait',
                'confidence': 0.0, 'analysis_id': None,
                'skipped_by_data_quality': True, 'rationale': fresh_msg,
                'elapsed_seconds': (_get_clock().now() - start_time).total_seconds()
            }

        precomputed_context = await self._fetch_precomputed_data(session, symbol)
        if precomputed_context:
            user_message += f"\n\n--- PRE-COMPUTED MACRO SIGNALS (for context) ---\n{precomputed_context}"

        analysis_cfg = self.settings.get("analysis", {}) or self.settings.get("claude", {})
        if bundle_success:
            effective_tool_turns = analysis_cfg.get("stage2_max_tool_turns", 12)
        else:
            effective_tool_turns = analysis_cfg.get("stage2_max_tool_turns_fallback", 20)
            logger.info(f"[{symbol}] Bundle unavailable — using fallback tool turns: {effective_tool_turns}")

        try:
            from analysis.calculators.regime_classifier import classify_market_regime
            regime_res = await classify_market_regime(session, symbol, self.settings)
            if regime_res and regime_res.get("regime"):
                user_message += f"\n\n[MARKET REGIME DETECTED]: {regime_res['regime'].upper()} (Quality: {regime_res.get('composite_quality', 'NORMAL')}). Adjust strategy accordingly."
        except Exception as e:
            logger.debug(f"Failed to fetch market regime for prompt injection: {e}")

        # SOTA Frozen Tool Selection: Deterministic 9 pinned tools permanently preserving 100% KV-Cache prefix hit rate across all symbols and turns
        dynamic_tools = STAGE2_FROZEN_TOOLS

        ineffective_factors_note = ""
        try:
            from utils.analytics.analysis_tracker import compute_factor_effectiveness
            eff = await compute_factor_effectiveness(session, days_back=30)
            dropped_factors = eff.get("dropped_factors", [])
            if dropped_factors:
                ineffective_factors_note = f"\n[NOTE: Statistically ineffective factors to avoid: {', '.join(dropped_factors)}]\n"
        except Exception as e:
            logger.debug(f"Failed to filter ineffective factors: {e}")

        # Injeksi AI Decision Memory
        extra_context_str = ineffective_factors_note
        try:
            from analysis.memory.decision_log import DecisionLogger
            lessons = await DecisionLogger.get_recent_lessons(session, symbol, limit=3)
            global_lessons = await DecisionLogger.get_global_lessons(session, exclude_symbol=symbol, limit=2)
            if lessons["real_trades"] or lessons["paper_whatifs"]:
                extra_context_str = "--- AI Decision Memory (Recent Lessons) ---\n"
                if lessons["real_trades"]:
                    extra_context_str += "Real Trades Outcome:\n"
                    for r in lessons["real_trades"]:
                        adj_str = f" | Next Adjustment: {r['next_adjustment']}" if r.get('next_adjustment') else ""
                        extra_context_str += f"- Decision: {r['decision']} | Profitable: {r['profitable']} | Tags: {r['tags']}{adj_str}\n  Specific Lesson: {r.get('specific_lesson', r['reflection'])}\n"
                if lessons["paper_whatifs"]:
                    extra_context_str += "Paper What-Ifs (Dodged/Missed):\n"
                    for r in lessons["paper_whatifs"]:
                        adj_str = f" | Next Adjustment: {r['next_adjustment']}" if r.get('next_adjustment') else ""
                        extra_context_str += f"- Blocked Decision: {r['decision']} (Reason: {r['reason_rejected']}) | Direction Correct: {r['direction_correct']} | Tags: {r['tags']}{adj_str}\n  Specific Lesson: {r.get('specific_lesson', r['reflection'])}\n"
            if global_lessons:
                if not extra_context_str:
                    extra_context_str = "--- AI Decision Memory (Recent Lessons) ---\n"
                extra_context_str += "\nCross-Symbol Structural Lessons (may generalize):\n"
                for gl in global_lessons:
                    extra_context_str += f"- [{gl['symbol']}] {gl['lesson']}\n"
            
            if isinstance(raw_bundle_data, dict):
                raw_bundle_data['recent_lessons'] = {
                    'symbol_lessons': lessons,
                    'global_lessons': global_lessons
                }
                    
            try:
                from analysis.memory.chronicle_writer import ChronicleWriter
                c_writer = ChronicleWriter(self.settings)
                chronicle_ctx = await c_writer.get_chronicle_for_symbol(session, symbol, days_back=30, limit=5)
                if not chronicle_ctx or "No specific macro chronicle" in chronicle_ctx:
                    chronicle_ctx = await c_writer.get_chronicle_context(session, days_back=30, limit=5)
                if chronicle_ctx:
                    if not extra_context_str:
                        extra_context_str = ""
                    extra_context_str += f"\n{chronicle_ctx}\n"
                    if isinstance(raw_bundle_data, dict):
                        raw_bundle_data['market_chronicle'] = chronicle_ctx
            except Exception as e:
                logger.debug(f"Failed to load chronicle context: {e}")

            compressed_query = select(ActivityLog).where(
                ActivityLog.category == 'compressed_memory'
            ).order_by(ActivityLog.timestamp.desc()).limit(2)
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
        use_specialists = self.settings.get('agent_architecture', {}).get('specialist_decomposition', True)
        if use_specialists and not bundle_success:
            logger.warning(f"[{symbol}] Specialist decomposition dilewati — pre-fetch data bundle gagal, laporan specialist akan berjalan tanpa konteks dan berpotensi menyesatkan adjudicator dengan sinyal 'NEUTRAL' palsu.")
            use_specialists = False
        if use_specialists:
            spec_extra_ctx, specialist_biases, specialist_confidence, specialist_trust = await self._execute_specialist_debate_pipeline(
                session, symbol, raw_bundle_data
            )
            extra_context_str += spec_extra_ctx

        # Compute prefetch_satisfied_tools from raw_bundle_data
        prefetch_satisfied_tools = set()
        if isinstance(raw_bundle_data, dict):
            for k, v in raw_bundle_data.items():
                if k.startswith('get_'):
                    is_valid = False
                    if isinstance(v, dict):
                        is_valid = bool(v) and not v.get('error')
                    elif isinstance(v, list):
                        is_valid = bool(v)
                    elif v is not None:
                        is_valid = True
                        
                    if is_valid:
                        prefetch_satisfied_tools.add(k)

        # Permanent Tool Schema Freeze: preserving 100% KV-cache hit rate across all symbols.
        # ToolExecutor already handles prefetch-satisfied tools via effective_called_tools.

        # Rate limiting
        try:
            from utils.api.claude_rate_limiter import ClaudeRateLimiter
            await ClaudeRateLimiter.acquire_session_slot(model_name=active_client.model)
        except Exception as e:
            logger.debug(f'Rate limiter error (non-fatal): {e}')

        # Wire in Per-Symbol Adaptive Thinking Budget (DeepSeek + SOTA Harness Pattern)
        try:
            from utils.llm.adaptive_thinking import PerSymbolAdaptiveThinkingAllocator
            vix_val = None
            regime_val = None
            if isinstance(raw_bundle_data, dict):
                v_data = raw_bundle_data.get('get_vix')
                if isinstance(v_data, dict):
                    vix_val = v_data.get('vix') or v_data.get('close')
                f_data = raw_bundle_data.get('get_fundamental_brief')
                if isinstance(f_data, dict):
                    regime_val = f_data.get('macro_narrative') or f_data.get('risk_sentiment')

            adaptive_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
                symbol=symbol,
                context={
                    'vix': vix_val,
                    'confluence_score': (stage1_confidence * 14.0) if stage1_confidence else None,
                    'regime': regime_val
                }
            )
            if hasattr(active_client, 'set_thinking_budget'):
                active_client.set_thinking_budget(adaptive_budget)
            elif hasattr(active_client, 'thinking_budget'):
                active_client.thinking_budget = adaptive_budget
            logger.info(f"[{symbol}] Adaptive reasoning budget dynamically set to {adaptive_budget} tokens")
        except Exception as e:
            logger.debug(f"[{symbol}] Adaptive thinking budget allocation error (non-fatal): {e}")

        stage_timeout = float((self.settings or {}).get("trading", {}).get("per_asset_timeout_seconds", 600.0))
        try:
            result = await asyncio.wait_for(
                active_client.run_agent(
                    session=session,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    tools=dynamic_tools,
                    stage_name=f"per_asset_{symbol}",
                    extra_context=extra_context_str if extra_context_str else None,
                    prefetch_satisfied_tools=prefetch_satisfied_tools
                ),
                timeout=stage_timeout
            )
        except asyncio.TimeoutError:
            msg = f"Per-asset analysis TIMEOUT for {symbol} (>{stage_timeout:.0f}s). Aborting."
            logger.error(msg)
            await self._log(session, msg, category="error")
            elapsed = (_get_clock().now() - start_time).total_seconds()
            return {
                "success": False,
                "symbol": symbol,
                "decision": "error",
                "error": f"Timeout exceeded ({stage_timeout:.0f}s)",
                "elapsed_seconds": elapsed,
            }


        elapsed = (_get_clock().now() - start_time).total_seconds()

        if not result["success"]:
            if result.get("is_billing_error") and (self.consent_callback is not None or (self.is_fallback_always_approved is not None and self.is_fallback_always_approved())):
                role_fallbacks = self.settings.get('llm', {}).get('task_roles', {}).get('stage2_per_asset_primary', {})
                fallback_model = role_fallbacks.get('billing_fallback') or role_fallbacks.get('fallback_2') or role_fallbacks.get('fallback_3') or 'gemini-3.6-flash'
                approved = False
                if self.is_fallback_always_approved is not None and self.is_fallback_always_approved():
                    approved = True
                elif self.consent_callback is not None:
                    logger.warning(f"[{symbol}] Billing error detected. Requesting fallback consent...")
                    approved = await self.consent_callback(f"Saldo LLM utama habis (Stage 2: {symbol}). Pindah ke model fallback ({fallback_model})?")
                
                if approved:
                    logger.info(f"[{symbol}] Fallback approved. Switching to fallback client ({fallback_model})...")
                    fallback_client = create_client(fallback_model, self.settings)
                    
                    messages = result.get("context_messages", [])
                    instruction = f"\n\nCRITICAL MANDATORY INSTRUCTION: You MUST call the `submit_asset_analysis` tool with 'symbol': '{symbol}' to record your final decision (buy/sell/wait/avoid) before finishing your turn. Ensure 'invalidation' is a plain string, NOT an array or list. Do not respond with just text."
                    if not messages:
                        messages = [
                            {"role": "user", "content": user_message + instruction}
                        ]
                    else:
                        messages.append({"role": "user", "content": instruction})
                    
                    fallback_result = await fallback_client.run_agent_from_messages(
                        session=session,
                        system_prompt=_flatten_system_prompt(system_prompt),
                        messages=messages,
                        tools=dynamic_tools,
                        max_tool_turns=active_client.max_tool_turns,
                        stage_name=f"per_asset_{symbol}"
                    )
                    
                    if fallback_result["success"]:
                        result = fallback_result

            if not result["success"]:
                msg = f"Per-asset analysis FAILED for {symbol}: {result.get('error')}"
                logger.error(msg)
                await self._log(session, msg, category="error")
                return {**result, "symbol": symbol, "elapsed_seconds": elapsed}

        # Pastikan analisis benar-benar tersimpan pada siklus/sesi saat ini
        from database.models import AssetAnalysis
        from datetime import timedelta
        analysis = (await session.execute(
            select(AssetAnalysis)
            .where(AssetAnalysis.symbol == symbol)
            .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
            .order_by(AssetAnalysis.generated_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if analysis:
            import re
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

        # Track AI compliance: log when required fields are missing
        if analysis and analysis.decision in ("buy", "sell"):
            # Post-Decision Closed-Loop Verification & Self-Correction (Harness Upgrade)
            try:
                from analysis.validators.output_verifier import OutputVerifier
                verifier = OutputVerifier(self.settings)
                raw_payload = {
                    "decision": analysis.decision,
                    "entry_condition": json.loads(analysis.entry_zone) if analysis.entry_zone else {},
                    "stop_loss": analysis.stop_loss,
                    "take_profit": analysis.take_profit,
                    "confluence_score": analysis.confluence_score,
                    "priced_in_score": analysis.priced_in_score,
                    "reevaluation_trigger": json.loads(analysis.reevaluation_trigger) if analysis.reevaluation_trigger else {},
                    "rationale": analysis.rationale,
                }
                verified, corrections = await verifier.verify_and_correct(
                    session=session,
                    settings=self.settings,
                    symbol=symbol,
                    raw_output=raw_payload,
                    context_data=raw_bundle_data if isinstance(raw_bundle_data, dict) else {},
                    client=active_client,
                    max_retries=1
                )
                if corrections:
                    logger.info(f"[{symbol}] Post-decision self-correction applied: {corrections}")
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
                    await session.commit()
            except Exception as e:
                logger.debug(f"[{symbol}] Output verifier non-fatal execution: {e}")

            # In-Harness Grounding Validator (Extended PR-07: lot_size, spread, margin, equity)
            try:
                from analysis.validators.in_harness_grounding import InHarnessGroundingValidator
                ez_parsed = json.loads(analysis.entry_zone) if analysis.entry_zone and isinstance(analysis.entry_zone, str) else (analysis.entry_zone if isinstance(analysis.entry_zone, dict) else {})
                
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

                # Fix 6.10: Extract lot_size from verification ledger, tool evidence, or ez_parsed
                # (AssetAnalysis model has no lot_size column in DB)
                lot_size_val = (
                    getattr(analysis, "lot_size", None)
                    or (verified.get("lot_size") if isinstance(verified, dict) else None)
                )
                if lot_size_val is None:
                    v_ledger = getattr(self, "verification_ledger", None)
                    if not v_ledger and hasattr(self, "tool_executor"):
                        v_ledger = getattr(self.tool_executor, "verification_ledger", None)
                    if v_ledger and hasattr(v_ledger, "get_passed_records"):
                        passed_records = v_ledger.get_passed_records(symbol)
                        for prec in reversed(passed_records):
                            if prec.tool_name in ("calculate_position_size", "validate_risk_limits") and isinstance(prec.details, dict):
                                lot_size_val = prec.details.get("lot_size") or prec.details.get("lots") or prec.details.get("recommended_lot_size")
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
                    if any("too far" in err or "too tight" in err or "Ungrounded" in err or "margin" in err.lower() or "spread" in err.lower() or "lot" in err.lower() for err in ground_errors):
                        logger.warning(f"[{symbol}] Demoting {analysis.decision.upper()} to WAIT due to grounding failure: {ground_errors}")
                        analysis.decision = "wait"
                        analysis.rationale = (analysis.rationale or "") + f" [GROUNDING REJECT: {'; '.join(ground_errors)}]"
                        await session.commit()
                        decision = "wait"
            except Exception as ground_err:
                logger.debug(f"[{symbol}] InHarnessGroundingValidator non-fatal: {ground_err}")

            # PR-11: Cross-Timeframe Confirmation Gate (HTF Alignment Sentinel)
            try:
                if str(analysis.decision or "").lower() in ("buy", "sell"):
                    from analysis.validators.cross_timeframe_gate import CrossTimeframeConfirmationGate
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
                logger.debug(f"[{symbol}] CrossTimeframeConfirmationGate non-fatal: {htf_err}")

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
                # Track for monitoring
                try:
                    from database.db import get_session
                    async with get_session() as track_session:
                        from database.models import SystemConfig
                        import json as _j
                        key = f"ai_compliance_missing_fields_{symbol}"
                        existing = (await track_session.execute(
                            select(SystemConfig).where(SystemConfig.key == key)
                        )).scalar_one_or_none()
                        count = 1
                        if existing and existing.value:
                            try:
                                count = _j.loads(existing.value).get("count", 0) + 1
                            except Exception:
                                pass
                        data = _j.dumps({"count": count, "last_seen": _get_clock().now().isoformat(), "fields": missing_fields})
                        if existing:
                            existing.value = data
                        else:
                            track_session.add(SystemConfig(key=key, value=data))
                        await track_session.commit()
                except Exception as e:
                    logger.debug(f"Failed to track AI compliance: {e}")

        if analysis and analysis.decision in ('buy', 'sell', 'wait'):
            try:
                from analysis.validators.adjudication_verifier import verify_adjudication
                # Fetch pending specialist biases: Priority 1: in-memory from this run, Priority 2: from saved analysis, Priority 3: SystemConfig
                target_biases = specialist_biases if specialist_biases else {}
                target_confidence = specialist_confidence if specialist_confidence else {}
                target_trust_weights = {k: round(specialist_trust.get(k, 1.0), 3) for k in target_biases} if specialist_trust else {}

                if not target_biases and analysis.specialist_biases_json:
                    try:
                        _b_data = json.loads(analysis.specialist_biases_json)
                        target_biases = _b_data.get('biases', {})
                        target_confidence = _b_data.get('confidence', {})
                        target_trust_weights = _b_data.get('trust_weights_used', {})
                    except Exception:
                        pass

                if not target_biases:
                    try:
                        from database.models import SystemConfig
                        _biases_key = f'pending_specialist_biases_{symbol}'
                        _cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == _biases_key))).scalar_one_or_none()
                        if _cfg and _cfg.value:
                            _b_data = json.loads(_cfg.value)
                            computed_at_str = _b_data.get('computed_at')
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
                                target_biases = _b_data.get('biases', {})
                                target_confidence = _b_data.get('confidence', {})
                                target_trust_weights = _b_data.get('trust_weights_used', {})
                    except Exception:
                        pass

                # Only verify adjudication if specialist biases exist (do not run if specialist decomposition was not used or failed)
                if target_biases:
                    parsed_trigger = None
                    if analysis.reevaluation_trigger:
                        try:
                            parsed_trigger = json.loads(analysis.reevaluation_trigger) if isinstance(analysis.reevaluation_trigger, str) else analysis.reevaluation_trigger
                        except Exception:
                            parsed_trigger = {"raw": str(analysis.reevaluation_trigger)}
                    
                    adj_check = await verify_adjudication(
                        self.settings, symbol, target_biases, target_confidence,
                        analysis.decision, analysis.rationale or '',
                        specialist_trust_weights=target_trust_weights,
                        confluence_score=int(analysis.confluence_score) if analysis.confluence_score is not None else None,
                        effective_threshold=int(effective_threshold) if effective_threshold is not None else None,
                        reeval_trigger=parsed_trigger if isinstance(parsed_trigger, dict) else None
                    )
                    if adj_check.get('verdict') == 'CONTRADICTS_OWN_FRAMEWORK':
                        logger.warning(f"[{symbol}] Adjudication framework violation: {adj_check.get('mismatch_explanation')}")
                        analysis.rationale = (analysis.rationale or '') + (
                            f"\n\n[SYSTEM: Adjudication verifier flagged inconsistency between framework rules "
                            f"and actual decision. {adj_check.get('mismatch_explanation','')}]"
                        )
                        if analysis.decision in ('buy', 'sell'):
                            # FIX: Reduced penalty (0.80 instead of 0.60)
                            analysis.confidence = (analysis.confidence or 0.7) * 0.80
                        await session.commit()
                    elif adj_check.get('verdict') == 'CONFIRM':
                        if adj_check.get('is_conditional_wait'):
                            logger.info(f"[{symbol}] Adjudication confirmed: conditional WAIT aligned with specialist directional bias and execution timing.")
                        else:
                            logger.debug(f"[{symbol}] Adjudication confirmed: decision strictly aligned with framework.")
                    elif adj_check.get('verdict') == 'FLAG_FOR_REVIEW':
                        logger.info(f"[{symbol}] Adjudication flagged for review: {adj_check.get('mismatch_explanation')}")
                    elif adj_check.get('verdict') == 'UNVERIFIED':
                        logger.warning(f"[{symbol}] Adjudication verification could not run (fail-closed): {adj_check.get('mismatch_explanation')}")
                        analysis.rationale = (analysis.rationale or '') + (
                            f"\n\n[SYSTEM: Adjudication verifier UNREACHABLE this cycle — decision NOT independently re-verified against the framework. Confidence discounted as a precaution.]"
                        )
                        if analysis.decision in ('buy', 'sell'):
                            # FIX: Mild penalty (0.92 instead of 0.85)
                            analysis.confidence = (analysis.confidence or 0.7) * 0.92
                        await session.commit()
            except Exception as e:
                logger.debug(f'[{symbol}] Adjudication verification failed (non-fatal): {e}')


        if analysis and analysis.decision in ("buy", "sell"):
            try:
                from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
                effective_threshold, _ = await compute_unified_confluence_threshold(
                    session=session,
                    symbol=symbol,
                    settings=self.settings,
                    market_regime=getattr(analysis, "market_regime", None)
                )
            except Exception as thr_err:
                logger.debug(f"[{symbol}] Failed computing unified threshold, using fallback: {thr_err}")
                effective_threshold = self.settings.get('trading', {}).get('auto_execute_min_confluence', 7)

            near_threshold = analysis.confluence_score and analysis.confluence_score <= effective_threshold + 1
            elevated_priced_in = analysis.priced_in_score and analysis.priced_in_score >= 6
            
            significant_disagreement_flag = False
            try:
                from database.models import SystemConfig
                from sqlalchemy import select as _sel
                key = f'specialist_disagreement_{symbol}'
                cfg = (await session.execute(_sel(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                if cfg and cfg.value:
                    try:
                        flag_data = json.loads(cfg.value) if isinstance(cfg.value, str) and cfg.value.startswith('{') else {}
                        flagged_at_str = flag_data.get('timestamp') or cfg.value
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
                if not sec_opinion.get('agree', True):
                    # FIX: Less punitive secondary model penalty (0.92 instead of 0.85)
                    analysis.confidence = (analysis.confidence or 0.8) * 0.92
                    analysis.rationale = (analysis.rationale or "") + (
                        f"\n\n[SYSTEM: Secondary Model disagreed "
                        f"(category={sec_opinion.get('disagreement_category')}, "
                        f"reason={sec_opinion.get('reason')}). Confidence slightly adjusted.]")
                    confidence = analysis.confidence
                    await session.commit()
                elif recent_sl_streak >= 2:
                    analysis.rationale = (analysis.rationale or "") + f"\n\n[SYSTEM: {recent_sl_streak} SL beruntun terdeteksi, second-opinion tetap setuju — tapi tetap waspada.]"
                    await session.commit()

        msg = (
            f"Per-asset analysis complete: {symbol} → {decision} "
            f"(conf={confidence:.2f}, {result['tool_calls_made']} tools, "
            f"{result['turns']} turns, {elapsed:.1f}s)"
        )
        logger.info(msg)
        await self._log(session, msg)

        try:
            from database.event_store import TradingEventStore
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
            from database.models import SystemConfig
            _biases_key = f'pending_specialist_biases_{symbol}'
            _cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == _biases_key))).scalar_one_or_none()
            if _cfg:
                await session.delete(_cfg)
                await session.commit()
        except Exception:
            pass

        entry_price_val = None
        if analysis and analysis.entry_zone:
            try:
                ez = json.loads(analysis.entry_zone) if isinstance(analysis.entry_zone, str) else analysis.entry_zone
                if isinstance(ez, dict) and "price" in ez:
                    entry_price_val = float(ez["price"])
            except Exception:
                pass
        if entry_price_val is None and analysis:
            if analysis.entry_price is not None:
                try:
                    entry_price_val = float(analysis.entry_price)
                except (ValueError, TypeError):
                    pass
            elif getattr(analysis, "price_at_analysis", None) is not None:
                try:
                    entry_price_val = float(getattr(analysis, "price_at_analysis"))
                except (ValueError, TypeError):
                    pass
            elif getattr(analysis, "current_price", None) is not None:
                try:
                    entry_price_val = float(getattr(analysis, "current_price"))
                except (ValueError, TypeError):
                    pass

        result.update({
            "symbol": symbol,
            "analysis_id": analysis_id,
            "decision": decision,
            "confidence": confidence,
            "entry_price": entry_price_val,
            "stop_loss": float(analysis.stop_loss) if (analysis and analysis.stop_loss is not None) else None,
            "take_profit": float(analysis.take_profit) if (analysis and analysis.take_profit is not None) else None,
            "confluence_score": int(analysis.confluence_score) if (analysis and analysis.confluence_score is not None) else None,
            "elapsed_seconds": elapsed,
        })
        return result

    async def _run_prescreen(self, session: AsyncSession, symbol: str) -> tuple[bool, str]:
        """
        Penyaringan (prescreen) kilat via Haiku. Menghemat token jika setup sangat tidak layak.
        Returns: (should_analyze: bool, alasan: str)
        """
        vix_row = None      # NEW: always initialized regardless of branch taken
        adx_val = None       # NEW
        skip_qual: dict = {}
        risk_state: dict = {}
        # === NEW: FORCE-ANALYZE ON PRICE MOVEMENT ===
        try:
            from database.models import PriceOHLCV, TechnicalIndicator
            from sqlalchemy import select
            last_analysis_time = self._last_analysis_time.get(symbol)
            if last_analysis_time:
                price_now = (await session.execute(
                    select(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol)
                    .order_by(PriceOHLCV.timestamp.desc()).limit(1))).scalar_one_or_none()
                price_then = (await session.execute(
                    select(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timestamp <= last_analysis_time)
                    .order_by(PriceOHLCV.timestamp.desc()).limit(1))).scalar_one_or_none()
                atr_row = (await session.execute(
                    select(TechnicalIndicator).where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == 'H4')
                    .where(TechnicalIndicator.indicator_name == 'ATR_14')
                    .order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
                if price_now and price_then and atr_row:
                    import json as _j
                    atr_raw = _j.loads(atr_row.value_json)
                    atr_val = atr_raw.get('atr', atr_raw.get('value', 0)) if isinstance(atr_raw, dict) else float(atr_raw)
                    if atr_val and abs(price_now - price_then) / atr_val >= 0.75:
                        return (True, f'Pergerakan harga signifikan sejak analisis terakhir '
                                       f'({abs(price_now - price_then)/atr_val:.2f}x ATR) — force ANALYZE')
        except Exception as e:
            logger.debug(f"Price-move prescreen check failed: {e}")

        # === QUICK LOCAL PRE-CHECK (no API call) ===
        try:
            from utils.calibration.prescreen_calibrator import compute_prescreen_skip_quality
            skip_qual = await compute_prescreen_skip_quality(session)
            
            local_quality = skip_qual.get('local_heuristic', {})
            local_false_skip_rate = local_quality.get('false_skip_rate_pct', 0) if isinstance(local_quality, dict) else 0
            
            # If false skip rate is >35%, we disable local deterministic gates so we don't miss trades
            if local_false_skip_rate <= 35:
                from database.models import TechnicalIndicator, VIXData
                from sqlalchemy import select
                import json as _j
                
                # Quick VIX check (system-level pause threshold)
                vix_row = (await session.execute(
                    select(VIXData).order_by(VIXData.date.desc()).limit(1)
                )).scalar_one_or_none()
                
                SAFE_HAVEN_SYMBOLS = {"XAUUSD", "USDJPY"}
                clean_sym = str(symbol).strip().upper().replace("/", "")
                if vix_row and vix_row.close >= 35 and clean_sym not in SAFE_HAVEN_SYMBOLS:
                    return (False, f'Quick local check: VIX={vix_row.close:.1f} >= 35 (non-safe-haven pause)')
                
                # Quick ADX check — extreme ranging
                adx_row = (await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == 'D1')
                    .where(TechnicalIndicator.indicator_name == 'ADX_14')
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()
                
                if adx_row:
                    adx_data = _j.loads(adx_row.value_json)
                    adx_val = adx_data.get('adx', 25) if isinstance(adx_data, dict) else float(adx_data)
                    if adx_val < 10:  # Extremely flat
                        return (False, f'Quick local check: ADX={adx_val:.1f} < 10 (dead market, no signal value)')
            else:
                logger.info(f"[{symbol}] Local prescreen gates bypassed due to high false-skip rate ({local_false_skip_rate}%)")
        except Exception as e:
            logger.debug(f'Quick local pre-check failed (non-fatal): {e}')

        # === NEW P1 (Phase 2.7): Quick Calendar Prescreen ===
        try:
            from database.models import EconomicCalendar
            from sqlalchemy import select as _sel_cal
            from datetime import timedelta as _td
            from utils.market.currency_utils import get_symbol_currencies
            sym_currencies = get_symbol_currencies(symbol)
            upcoming_cal = (await session.execute(
                _sel_cal(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(['high', 'High', 'HIGH']))
                .where(EconomicCalendar.currency.in_(list(sym_currencies)))
                .where(EconomicCalendar.event_time >= _get_clock().now())
                .where(EconomicCalendar.event_time <= _get_clock().now() + _td(minutes=15))
                .limit(1)
            )).scalar_one_or_none()
            if upcoming_cal:
                # Force skip if major news < 15m (harmonized with PreFlightTurnGate)
                return (False, f"Quick local check: High-impact event '{upcoming_cal.event_name}' in < 15m. Avoiding entry.")
        except Exception as e:
            logger.debug(f'Prescreen calendar check failed: {e}')

        if not self._haiku_client:
            return True, "prescreen disabled - no client"

        # Risk state check - lightweight
        try:
            from analysis.tools.tool_executor import ToolExecutor
            executor = ToolExecutor(session, settings=self.settings, symbol=symbol)
            risk_state = await executor.execute('get_risk_state', {})
            if risk_state.get('trading_paused'):
                return False, f'Risk state: trading paused ({risk_state.get("pause_reason", "unknown")})'
        except Exception:
            pass

        # Get minimal context for AI decision
        now_utc = _get_clock().now()
        weekday = now_utc.weekday()
        hour = now_utc.hour
        
        if weekday >= 5 and symbol not in self.always_open_assets:
            return False, 'Market closed (weekend, non-crypto)'
        
        bias_note = ""
        try:
            llm_quality = skip_qual.get('llm_prescreen', {}) if skip_qual else {}
            llm_false_skip_rate = llm_quality.get('false_skip_rate_pct', 0) if isinstance(llm_quality, dict) else 0
            if llm_false_skip_rate > 35:
                bias_note = ("\nNOTE: Recent calibration shows this prescreen has been too conservative (missing real "
                             "moves). When uncertain, lean YES.")
        except Exception as e:
            logger.debug(f'Prescreen calibration extraction failed: {e}')
            
        bias_note_default = ('\nDEFAULT BIAS: Biaya melewatkan setup bagus (false NO) jauh lebih '
                              'mahal daripada biaya analisis penuh yang ternyata tak perlu (false YES). '
                              'Saat benar-benar ragu antara YES/NO, pilih YES.')
        bias_note = bias_note if bias_note else bias_note_default

        # --- NEW: Extract nearest_zone_note ---
        nearest_zone_note = 'active market structure'
        try:
            from database.models import SRZone, PriceOHLCV, SwingPoint
            from sqlalchemy import select
            last_close = (await session.execute(
                select(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol).order_by(PriceOHLCV.timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            if last_close:
                zones = (await session.execute(
                    select(SRZone).where(SRZone.symbol == symbol).where(SRZone.timeframe == 'H4')
                )).scalars().all()
                if zones:
                    nearest = min(zones, key=lambda z: min(abs(z.price_high - last_close), abs(z.price_low - last_close)))
                    dist_pct = min(abs(nearest.price_high - last_close), abs(nearest.price_low - last_close)) / last_close * 100
                    nearest_zone_note = f'{dist_pct:.2f}% from nearest S/R zone (strength={nearest.strength})'
                else:
                    swings = (await session.execute(
                        select(SwingPoint).where(SwingPoint.symbol == symbol).where(SwingPoint.timeframe == 'H4').order_by(SwingPoint.timestamp.desc()).limit(4)
                    )).scalars().all()
                    if swings:
                        nearest_sw = min(swings, key=lambda s: abs(s.price - last_close))
                        dist_pct = abs(nearest_sw.price - last_close) / last_close * 100
                        nearest_zone_note = f'{dist_pct:.2f}% from nearest H4 swing {nearest_sw.type}'
                    else:
                        nearest_zone_note = 'S/R in calculation; volatility active (H4 ATR ready)'
        except Exception as e:
            logger.debug(f"Prescreen nearest zone check failed: {e}")
        # --- END NEW ---

        PRESCREEN_SCHEMA = {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["YES", "NO"]},
                "reason": {"type": "string"}
            },
            "required": ["decision", "reason"]
        }

        prompt = f"""Quick trading opportunity check for {symbol}. Evaluate whether we should proceed with full Stage 2 analysis.

Context:
- UTC time: {hour}:00, Day: {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][weekday]}
- Asset type: {'24/7 crypto' if symbol in self.always_open_assets else 'forex/commodity'}
- VIX: {'normal' if not vix_row else (str(round(vix_row.close, 1)) + (' HIGH' if vix_row.close > 22 else ' NORMAL'))}
- ADX: {'ranging' if adx_val is not None and adx_val < 15 else ('trending' if adx_val is not None and adx_val > 25 else 'weak')}
- Risk state: {'PAUSED' if risk_state and risk_state.get('trading_paused') else 'ACTIVE'}
- Proximity: {nearest_zone_note}

Rule:
- Return YES if price is within 1.0% of a strong S/R zone (strength>=3) OR within 1.0x ATR H4 OR standard risk/vix conditions hold.
- Return NO if: Risk paused OR market closed OR ADX dead (<12) OR VIX extreme (>35).{bias_note}
"""

        try:
            if hasattr(self._haiku_client, 'thinking_budget'):
                self._haiku_client.thinking_budget = 0
            if hasattr(self._haiku_client, 'thinking_level'):
                self._haiku_client.thinking_level = 'none'
            from utils.typesafe.jev_primitives import build_prescreen_questions
            prescreen_jev_q = build_prescreen_questions(symbol)
            resp = await self._haiku_client.classify_json(
                prompt=prompt,
                schema=PRESCREEN_SCHEMA,
                jev_questions=prescreen_jev_q,
                temperature=0.0
            )
            if resp and "reason" not in resp and "opportunity_score" in resp:
                resp["reason"] = f"opportunity_score={resp['opportunity_score']}"
            if resp and resp.get('decision') == 'YES':
                return True, resp.get('reason', '')[:80]
            elif resp and resp.get('decision') == 'NO':
                # --- NEW: BYPASS PRESCREEN IF HIGH CONFIDENCE OR BREAKING CATALYST ---
                try:
                    from database.models import FundamentalBrief, NewsItem
                    from sqlalchemy import select
                    from utils.protocol.context_coherence import SYMBOL_CURRENCY_MAP
                    from datetime import timedelta
                    
                    brief = (await session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    if brief and brief.confidence and brief.confidence >= 0.50:
                        logger.info(f"[{symbol}] Prescreen returned NO, but bypassing due to solid FundamentalBrief confidence ({brief.confidence})")
                        return True, 'forced_by_macro_override_high_conf'
                    
                    pair_info = SYMBOL_CURRENCY_MAP.get(symbol, {})
                    base_c, quote_c = pair_info.get('base'), pair_info.get('quote')
                    if base_c and quote_c:
                        recent_breaking = (await session.execute(
                            select(NewsItem)
                            .where(NewsItem.fetched_at >= _get_clock().now() - timedelta(hours=2))
                            .where(NewsItem.impact == 'BREAKING')
                            .where(NewsItem.currency_tags.like(f'%{base_c}%') | NewsItem.currency_tags.like(f'%{quote_c}%'))
                            .limit(1)
                        )).scalar_one_or_none()
                        if recent_breaking:
                            logger.info(f"[{symbol}] Prescreen returned NO, but bypassing due to BREAKING news catalyst")
                            return True, 'forced_by_macro_override_breaking_news'
                except Exception as e:
                    logger.debug(f'[{symbol}] Override check failed: {e}')
                # --- END NEW ---
                return False, resp.get('reason', '')[:80]
            else:
                return True, 'prescreen ambiguous - defaulting to allow'
        except Exception as e:
            return True, f'prescreen error - defaulting to allow: {str(e)[:40]}'

    async def _log(self, session: AsyncSession, description: str, category: str = "analysis") -> None:
        """Log a stage event to activity_log."""
        try:
            session.add(ActivityLog(
                category=category,
                description=description,
                actor="system",
            ))
            await session.commit()
        except Exception as e:
            logger.debug(f"Activity log write failed (non-fatal): {e}")
