# ==============================================================================
# File: application/analysis/debate/debate_orchestrator.py
# ==============================================================================

"""
Dialectical Multi-Agent Debate Orchestrator.

Orchestrates dialectical deliberation between Bull Specialist, Bear Specialist,
and Chief Investment Judge for ad-hoc symbol analysis and trade proposals.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.debate.bear_analyst import generate_bear_dissent
from monika.application.analysis.debate.bull_analyst import generate_bull_advocacy
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.DebateOrchestrator")


class DebateOrchestrator:
    """
    Coordinates multi-agent dialectical deliberation (Bull vs Bear vs Judge).
    """

    def __init__(self, settings: Optional[dict[str, Any]] = None) -> None:
        self.settings: dict[str, Any] = settings or {}

    async def run_symbol_debate(
        self,
        symbol: str,
        market_data: Optional[dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Execute an ad-hoc dialectical debate session for a given symbol.
        """
        clean_symbol = symbol.upper().strip().replace("/", "")
        data = market_data or {}
        raw_data = data.get("raw_data") or {}
        context_str = data.get("context_str") or ""

        fact_sheet: Any = context_str if context_str else f"Market data context for {clean_symbol}."

        regime_info = raw_data.get("get_volatility_regime_H4") or {}
        vix_info = raw_data.get("get_vix") or {}

        original_context: dict[str, Any] = {
            "symbol": clean_symbol,
            "decision": "BUY",
            "market_regime": regime_info.get("regime", "ranging"),
            "vix": vix_info.get("current", 16.0),
        }

        bull_client = get_client_for_task("debate_bull", self.settings)
        bear_client = get_client_for_task("debate_bear", self.settings)
        judge_client = get_client_for_task("debate_judge", self.settings)

        if not bull_client or not bear_client or not judge_client:
            logger.warning("[DebateOrchestrator] Missing LLM client for debate participants; returning neutral WAIT.")
            return {
                "decision": "WAIT",
                "confidence": 0.0,
                "rationale": "LLM client configuration unavailable for debate orchestration.",
                "bull_summary": "LLM unavailable.",
                "bear_summary": "LLM unavailable.",
                "confluence_score": 0.0,
                "entry_zone": None,
                "stop_loss": None,
                "take_profit": None,
                "transcript": [],
            }

        bull_claim = await generate_bull_advocacy(
            client=bull_client,
            symbol=clean_symbol,
            original_context=original_context,
            fact_sheet=fact_sheet,
        )

        bear_dissent = await generate_bear_dissent(
            client=bear_client,
            symbol=clean_symbol,
            original_context=original_context,
            fact_sheet=fact_sheet,
            bull_claim=bull_claim,
        )

        judge_verdict = await evaluate_debate(
            client=judge_client,
            symbol=clean_symbol,
            original_context=original_context,
            bull_claim=bull_claim,
            bear_dissent=bear_dissent,
        )

        decision = str(judge_verdict.get("final_decision") or judge_verdict.get("verdict") or "WAIT").upper()
        confidence = float(judge_verdict.get("confidence") or 0.0)
        rationale = str(judge_verdict.get("synthesis_rationale") or judge_verdict.get("rationale") or "")
        bull_summary = str(bull_claim.get("thesis_summary") or bull_claim.get("argument") or "")
        bear_summary = str(bear_dissent.get("dissent_summary") or bear_dissent.get("argument") or "")
        confluence_score = float(judge_verdict.get("confluence_score") or 0.0)

        return {
            "decision": decision,
            "confidence": confidence,
            "rationale": rationale,
            "bull_summary": bull_summary,
            "bull_thesis": bull_summary,
            "bear_summary": bear_summary,
            "bear_dissent": bear_summary,
            "confluence_score": confluence_score,
            "entry_zone": judge_verdict.get("recommended_entry_zone"),
            "stop_loss": judge_verdict.get("recommended_sl"),
            "take_profit": judge_verdict.get("recommended_tp"),
            "transcript": [
                {"role": "bull_specialist", "content": bull_summary},
                {"role": "bear_specialist", "content": bear_summary},
                {"role": "investment_judge", "content": rationale},
            ],
        }
