# ==============================================================================
# File: graph/nodes/debate/bear_dissent_node.py
# ==============================================================================

import logging
import asyncio
from typing import Dict, Any, Optional

from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from analysis.providers.llm_factory import get_client_for_task
from analysis.debate.bear_analyst import generate_bear_dissent
from graph.nodes.debate.helpers import _is_grounded, sync_facade_patches

logger = logging.getLogger("TradingAgent.Graph.Debate.BearDissentNode")


async def bear_dissent_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sub-agent node: Bear Dissent.
    Menantang klaim bull, mendeteksi risiko tersembunyi, dan mengukur level ketidaksepakatan (disagreement).
    """
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    debate_cfg = settings.get("agent_architecture", {})

    if not debate_cfg.get("enable_debate", True):
        return {}

    debate_states = dict(state.get("debate_states", {}))
    bear_client = get_client_for_task("debate_bear", settings)

    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        deb = debate_states.get(sym, {})
        verified_bull_claim = deb.get("verified_bull_claim")
        original_context = deb.get("original_context")
        fact_sheet = deb.get("fact_sheet") or ""
        curr_p = deb.get("curr_p", 0.0)

        if not verified_bull_claim or not original_context:
            return sym, None

        turn = deb.get("turn", 1)
        rebuttal_claim = deb.get("bull_rebuttal") or deb.get("bear_rebuttal") or deb.get("rebuttal") or deb.get("pro_rebuttal")
        context_to_use = dict(original_context)
        claim_to_use = dict(verified_bull_claim)
        rebuttal_completed = bool(rebuttal_claim or deb.get("rebuttal_completed", False))
        if rebuttal_claim:
            context_to_use["bull_rebuttal"] = rebuttal_claim
            context_to_use["rebuttal"] = rebuttal_claim
            claim_to_use["rebuttal"] = rebuttal_claim

        async with semaphore:
            try:
                bear_dissent = await generate_bear_dissent(
                    bear_client, sym, context_to_use, claim_to_use, fact_sheet
                )

                if not _is_grounded(bear_dissent, curr_p, reference=fact_sheet if isinstance(fact_sheet, dict) else None):
                    bear_dissent['risk_severity'] = max(1, bear_dissent.get('risk_severity', 5) - 2)
                    bear_dissent['ungrounded_penalty'] = True

                if rebuttal_claim:
                    bull_strength = rebuttal_claim.get('rebuttal_strength', verified_bull_claim.get('strength_score', 5))
                else:
                    bull_strength = verified_bull_claim.get('strength_score', 5)
                bear_severity = bear_dissent.get('risk_severity', 5)
                disagreement = abs(bull_strength - (10 - bear_severity))
                divergence = round(disagreement / 10.0, 2)
                max_rounds = debate_cfg.get('debate_rounds', 2)
                needs_rebuttal = divergence > 0.40 and turn < 2 and max_rounds >= 2 and not rebuttal_completed

                if needs_rebuttal:
                    logger.info(f'[{sym}] High debate divergence ({divergence:.2f}) at turn {turn} — cyclic dialectic rebuttal required')

                return sym, {
                    'bear_dissent': bear_dissent,
                    'disagreement': disagreement,
                    'divergence': divergence,
                    'turn': turn,
                    'needs_rebuttal': needs_rebuttal,
                    'rebuttal_completed': rebuttal_completed
                }
            except Exception as e:
                logger.error(f"[{sym}] Bear dissent failed: {e}", exc_info=True)
                return sym, None

    tasks = [_process_single(sym, r) for sym, r in actionable]
    results = await asyncio.gather(*tasks)

    for sym, res in results:
        if res:
            existing = debate_states.get(sym, {})
            existing.update(res)
            debate_states[sym] = existing

    return {"debate_states": debate_states}
