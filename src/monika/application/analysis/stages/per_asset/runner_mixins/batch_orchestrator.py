# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/batch_orchestrator.py
# Description: Batch orchestration and parallel execution mixin for PerAssetRunner
# ==============================================================================

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.stages.per_asset.runner_mixins.base import (
    _RunnerMixinBase,
    _get_asyncio,
)
from monika.infrastructure.database.models import ActivityLog

logger = logging.getLogger("TradingAgent.PerAssetStage")


class BatchOrchestratorMixin(_RunnerMixinBase):
    """Mixin handling multi-asset batch coordination, parallel worker execution, and activity logging."""

    async def _fetch_stage1_confidence(self, session: AsyncSession) -> float:
        """P2-2: Fetch stage1 confidence fresh per-call instead of caching on shared instance.
        Fixes race condition where NewsWatcher/TriggerChecker/PositionExitReviewer call
        run_one() concurrently on the same instance and read stale cross-cycle values.
        """
        from monika.core.calibration.confidence_calibrator import get_calibrated_confidence
        from monika.infrastructure.database.models import FundamentalBrief

        try:
            brief = (
                await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
            ).scalar_one_or_none()
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

        def _format_intel_for_symbol(sym: str, intel_list: Optional[list]) -> str:
            if not intel_list:
                return ""
            relevant = []
            sym_clean = sym.upper().replace("/", "")
            for item in intel_list:
                raw_aff = item.get("affected_symbols") or []
                if isinstance(raw_aff, str):
                    aff_list = [s.strip() for s in raw_aff.split(",") if s.strip()]
                else:
                    aff_list = list(raw_aff)
                aff = [s.upper().replace("/", "") for s in aff_list]
                if not aff or "ALL" in aff or sym_clean in aff:
                    relevant.append(item)
            if not relevant:
                return ""
            lines = ["[OPERATOR MARKET INTELLIGENCE & DIRECTIVES FOR THIS ASSET]"]
            for it in relevant:
                lines.append(f"• ID #{it.get('id')} [{it.get('intel_type', '').upper()}]: {it.get('title')}")
                lines.append(
                    f"  Directive: {it.get('directive', 'neutral')} | Target Cycle: {it.get('target_cycle', 'continuous')}"
                )
                lines.append(f"  Summary: {it.get('summary')}")
                if it.get("full_content"):
                    lines.append(f"  Details: {it.get('full_content')[:400]}")
            return "\n".join(lines)

        targets = symbols or self.asset_universe
        logger.info(f"Running per-asset analysis for {len(targets)} symbols: {targets}")
        try:
            from monika.application.analysis.event_broadcaster import emit_analysis_event

            emit_analysis_event("analysis_step_start", {"step": "prefetch_data", "symbols": targets})
        except Exception:
            pass

        # Ambil nilai confidence dari brief Tahap 1 untuk menyesuaikan agresivitas Tahap 2
        stage1_confidence = 0.50
        try:
            from monika.infrastructure.database.models import FundamentalBrief

            async with session_factory() as session:
                brief = (
                    await session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()
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
                        symbol_context = (per_symbol_contexts or {}).get(symbol, "")
                        intel_context = _format_intel_for_symbol(symbol, user_market_intel)
                        combined_context = "\n\n".join(filter(None, [extra_context, symbol_context, intel_context]))
                        return symbol, await self.run_one(
                            session,
                            symbol,
                            combined_context or None,
                            skip_cooldown=skip_cooldown,
                            is_secondary=is_secondary,
                            use_session_trigger_client=use_session_trigger_client,
                            stage1_confidence=stage1_confidence,
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
                    symbol_context = (per_symbol_contexts or {}).get(symbol, "")
                    intel_context = _format_intel_for_symbol(symbol, user_market_intel)
                    combined_context = "\n\n".join(filter(None, [extra_context, symbol_context, intel_context]))
                    try:
                        result = await self.run_one(
                            session,
                            symbol,
                            combined_context or None,
                            skip_cooldown=skip_cooldown,
                            is_secondary=is_secondary,
                            use_session_trigger_client=use_session_trigger_client,
                            stage1_confidence=stage1_confidence,
                        )
                    except Exception as e:
                        logger.error(f"[{symbol}] run_one raised unhandled exception — isolating: {e}", exc_info=True)
                        result = {
                            "success": False,
                            "symbol": symbol,
                            "decision": "error",
                            "error": str(e),
                            "elapsed_seconds": 0,
                        }
                    results[symbol] = result
                    await _get_asyncio().sleep(1)

            try:
                from monika.application.analysis.event_broadcaster import emit_analysis_event

                total_in = sum(r.get("input_tokens", 0) for r in results.values() if isinstance(r, dict))
                total_out = sum(r.get("output_tokens", 0) for r in results.values() if isinstance(r, dict))
                emit_analysis_event(
                    "analysis_step_complete",
                    {
                        "step": "prefetch_data",
                        "symbols": targets,
                        "input_tokens": total_in,
                        "output_tokens": total_out,
                    },
                )
            except Exception:
                pass

            return results

    async def _log(self, session: AsyncSession, description: str, category: str = "analysis") -> None:
        """Log a stage event to activity_log."""
        try:
            session.add(
                ActivityLog(
                    category=category,
                    description=description,
                    actor="system",
                )
            )
            await session.commit()
        except Exception as e:
            logger.debug(f"Activity log write failed (non-fatal): {e}")
