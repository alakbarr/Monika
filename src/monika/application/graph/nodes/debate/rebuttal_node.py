# ==============================================================================
# File: graph/nodes/debate/rebuttal_node.py
# ==============================================================================

import asyncio
import logging
from typing import Any, Dict, Optional

from langchain_core.runnables.config import RunnableConfig

from monika.application.analysis.debate.bear_analyst import generate_bear_rebuttal
from monika.application.analysis.debate.bull_analyst import generate_bull_rebuttal
from monika.application.graph.nodes.debate.helpers import (
    _is_grounded,
    resolve_debate_timeout,
    sync_facade_patches,
)
from monika.application.graph.state import TradingState
from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.Graph.Debate.RebuttalNode")


async def rebuttal_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sub-agent node: Dialectic Rebuttal.
    Dijalankan saat disagreement tinggi (>= 4) dan konfigurasi debate_rounds >= 2.
    """
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (
        config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)
    ) or {}
    scheduler = (
        configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    )
    settings = scheduler.settings if scheduler else {}
    debate_cfg = settings.get("agent_architecture", {})

    if not debate_cfg.get("enable_debate", True):
        return {}

    debate_states = dict(state.get("debate_states", {}))
    bull_client = get_client_for_task("debate_bull", settings)
    bear_client = get_client_for_task("debate_bear", settings)
    if not bull_client:
        bull_client = bear_client
    if not bear_client:
        bear_client = bull_client

    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        deb = debate_states.get(sym, {})
        if not deb.get("needs_rebuttal"):
            return sym, None

        verified_bull_claim = deb.get("verified_bull_claim")
        bear_dissent = deb.get("bear_dissent")
        original_context = deb.get("original_context")
        fact_sheet = deb.get("fact_sheet") or ""
        curr_p = deb.get("curr_p", 0.0)

        if not verified_bull_claim or not bear_dissent or not original_context:
            return sym, None

        decision = str(original_context.get("decision", "buy")).lower()
        is_sell = decision in ("sell", "short")
        run_bull_rebuttal = decision in ("buy", "long", "wait", "conflict_adjudication", "neutral")
        run_bear_rebuttal = decision in ("sell", "short", "wait", "conflict_adjudication", "neutral")

        turn_client = bear_client if is_sell else bull_client
        turn_timeout = resolve_debate_timeout(settings, turn_client)
        async with semaphore:
            try:
                logger.info(f"[{sym}] Executing round 2 dialectic rebuttal (direction={decision.upper()})...")
                bull_reb: Optional[Dict[str, Any]] = None
                bear_reb: Optional[Dict[str, Any]] = None
                async with asyncio.timeout(turn_timeout):
                    if run_bull_rebuttal and run_bear_rebuttal:
                        bull_reb = await generate_bull_rebuttal(
                            bull_client, sym, original_context, fact_sheet, verified_bull_claim, bear_dissent
                        )
                        bear_reb = await generate_bear_rebuttal(
                            bear_client, sym, original_context, fact_sheet, bear_dissent, verified_bull_claim
                        )
                    elif run_bear_rebuttal:
                        bear_reb = await generate_bear_rebuttal(
                            bear_client, sym, original_context, fact_sheet, bear_dissent, verified_bull_claim
                        )
                    else:
                        bull_reb = await generate_bull_rebuttal(
                            bull_client, sym, original_context, fact_sheet, verified_bull_claim, bear_dissent
                        )

                ref_sheet = fact_sheet if isinstance(fact_sheet, dict) else None
                if isinstance(bull_reb, dict) and not _is_grounded(bull_reb, curr_p, reference=ref_sheet):
                    bull_reb["rebuttal_strength"] = max(1, bull_reb.get("rebuttal_strength", 5) - 2)
                    bull_reb["ungrounded_penalty"] = True
                if isinstance(bear_reb, dict) and not _is_grounded(bear_reb, curr_p, reference=ref_sheet):
                    bear_reb["rebuttal_strength"] = max(1, bear_reb.get("rebuttal_strength", 5) - 2)
                    bear_reb["ungrounded_penalty"] = True

                new_turn = deb.get("turn", 1) + 1
                if bull_reb is not None and bear_reb is not None:
                    combined_rebuttal = {
                        "bull_rebuttal": bull_reb,
                        "bear_rebuttal": bear_reb,
                        "rebuttal_strength": max(
                            int(bull_reb.get("rebuttal_strength", 5) or 5),
                            int(bear_reb.get("rebuttal_strength", 5) or 5),
                        ),
                    }
                    return sym, {
                        "bull_rebuttal": bull_reb,
                        "bear_rebuttal": bear_reb,
                        "rebuttal": combined_rebuttal,
                        "pro_rebuttal": combined_rebuttal,
                        "turn": new_turn,
                        "needs_rebuttal": False,
                        "divergence": 0.0,
                        "disagreement": 0,
                    }

                rebuttal_res = bear_reb if is_sell else bull_reb
                return sym, {
                    "bull_rebuttal": rebuttal_res,
                    "bear_rebuttal": rebuttal_res,
                    "rebuttal": rebuttal_res,
                    "pro_rebuttal": rebuttal_res,
                    "turn": new_turn,
                    "needs_rebuttal": False,
                    "divergence": 0.0,
                    "disagreement": 0,
                }
            except Exception as e:
                logger.error(f"[{sym}] Rebuttal failed: {e}", exc_info=True)
                new_turn = deb.get("turn", 1) + 1
                return sym, {
                    "turn": new_turn,
                    "needs_rebuttal": False,
                    "divergence": 0.0,
                    "disagreement": 0,
                    "rebuttal_error": str(e),
                }

    tasks = [_process_single(sym, r) for sym, r in actionable]
    results = await asyncio.gather(*tasks)

    for sym, res in results:
        if res:
            existing = debate_states.get(sym, {})
            existing.update(res)
            debate_states[sym] = existing

    return {"debate_states": debate_states}
