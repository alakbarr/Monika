# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/recovery.py
# Description: Multi-tier fallback recovery mixin for PerAssetRunner
# ==============================================================================

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.stages.per_asset.runner_mixins.base import (
    _RunnerMixinBase,
    _get_clock,
)
from monika.infrastructure.database.models import AssetAnalysis

logger = logging.getLogger("TradingAgent.PerAssetStage")


class RecoveryMixin(_RunnerMixinBase):
    """Mixin providing multi-tier recovery when LLM fails to invoke submit_asset_analysis."""

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
                {"role": "user", "content": recovery_nudge},
            ]
            if hasattr(active_client, "run_agent_from_messages"):
                rec_result = await active_client.run_agent_from_messages(
                    session=session,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=dynamic_tools,
                    max_tool_turns=3,
                    stage_name=f"per_asset_{symbol}",
                )
                if rec_result.get("success"):
                    analysis = (
                        await session.execute(
                            select(AssetAnalysis)
                            .where(AssetAnalysis.symbol == symbol)
                            .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
                            .order_by(AssetAnalysis.generated_at.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
        except Exception as rec_err:
            logger.warning(f"[{symbol}] Tier 1 recovery nudge failed: {rec_err}")

        # --- TIER 2: Heuristic Text Extraction Fallback ---
        if not analysis and final_text:
            try:
                text_lower = final_text.lower()
                extracted_decision = None

                # Use strict pattern matching to avoid false positives on words like "wait for pullback"
                m_dec = re.search(
                    r'\b(?:decision|action)\s*[:=]\s*["\']?\*?\*?(buy|sell|avoid|wait)\*?\*?["\']?', text_lower
                )
                if m_dec:
                    extracted_decision = m_dec.group(1)
                elif (
                    '"decision": "buy"' in text_lower
                    or "'decision': 'buy'" in text_lower
                    or "**decision**: buy" in text_lower
                ):
                    extracted_decision = "buy"
                elif (
                    '"decision": "sell"' in text_lower
                    or "'decision': 'sell'" in text_lower
                    or "**decision**: sell" in text_lower
                ):
                    extracted_decision = "sell"
                elif (
                    '"decision": "avoid"' in text_lower
                    or "'decision': 'avoid'" in text_lower
                    or "**decision**: avoid" in text_lower
                ):
                    extracted_decision = "avoid"
                elif (
                    '"decision": "wait"' in text_lower
                    or "'decision': 'wait'" in text_lower
                    or "**decision**: wait" in text_lower
                ):
                    extracted_decision = "wait"

                if extracted_decision:
                    logger.info(
                        f"[{symbol}] Tier 2 heuristic extracted decision '{extracted_decision}' from final text."
                    )
                    fallback_payload = {
                        "symbol": symbol,
                        "decision": extracted_decision,
                        "confidence": 0.5,
                        "rationale": final_text[:1000]
                        if final_text
                        else f"Extracted from model final text ({extracted_decision})",
                        "invalidation": "Extracted via heuristic text recovery",
                    }
                    if extracted_decision in ("buy", "sell"):
                        fallback_payload["entry_condition"] = {"type": "market", "detail": "Extracted market entry"}
                        # Try extracting numerical SL and TP from text if available
                        m_sl = re.search(r"(?:stop[-_\s]*loss|sl)\s*[:=]\s*([0-9.]+)", text_lower)
                        m_tp = re.search(r"(?:take[-_\s]*profit|tp)\s*[:=]\s*([0-9.]+)", text_lower)
                        if m_sl and m_tp:
                            try:
                                fallback_payload["stop_loss"] = float(m_sl.group(1))
                                fallback_payload["take_profit"] = float(m_tp.group(1))
                            except ValueError:
                                fallback_payload["stop_loss"] = None
                                fallback_payload["take_profit"] = None

                    from monika.application.analysis.tools.tool_executor import ToolExecutor

                    executor = ToolExecutor(
                        session, settings=self.settings, model_name=active_client.model, symbol=symbol
                    )
                    submit_res = await executor._tool_submit_asset_analysis(fallback_payload)
                    if submit_res.get("status") in ("recorded", "success") or "id" in submit_res:
                        analysis = (
                            await session.execute(
                                select(AssetAnalysis)
                                .where(AssetAnalysis.symbol == symbol)
                                .where(AssetAnalysis.generated_at >= start_time - timedelta(seconds=15))
                                .order_by(AssetAnalysis.generated_at.desc())
                                .limit(1)
                            )
                        ).scalar_one_or_none()
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
                    generated_at=_get_clock().now(),
                )
                session.add(fallback_record)
                await session.commit()
                analysis = fallback_record
            except Exception as tier3_err:
                logger.error(f"[{symbol}] Tier 3 record insertion failed: {tier3_err}")

        return analysis
