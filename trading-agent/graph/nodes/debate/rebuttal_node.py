# ==============================================================================
# File: graph/nodes/debate/rebuttal_node.py
# ==============================================================================

import logging
import asyncio
from typing import Dict, Any, Optional

from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from analysis.providers.llm_factory import get_client_for_task
from analysis.debate.bull_analyst import generate_bull_rebuttal
from analysis.debate.bear_analyst import generate_bear_rebuttal
from graph.nodes.debate.helpers import _is_grounded, sync_facade_patches

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

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
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

        async with semaphore:
            try:
                logger.info(f"[{sym}] Executing round 2 dialectic rebuttal (direction={decision.upper()})...")
                if is_sell:
                    rebuttal_res = await generate_bear_rebuttal(
                        bear_client, sym, original_context, fact_sheet, verified_bull_claim, bear_dissent
                    )
                else:
                    rebuttal_res = await generate_bull_rebuttal(
                        bull_client, sym, original_context, fact_sheet, verified_bull_claim, bear_dissent
                    )

                if not _is_grounded(rebuttal_res, curr_p):
                    rebuttal_res['rebuttal_strength'] = max(1, rebuttal_res.get('rebuttal_strength', 5) - 2)
                    rebuttal_res['ungrounded_penalty'] = True

                new_turn = deb.get("turn", 1) + 1
                return sym, {
                    'bull_rebuttal': rebuttal_res,
                    'bear_rebuttal': rebuttal_res,
                    'turn': new_turn,
                    'needs_rebuttal': False
                }
            except Exception as e:
                logger.error(f"[{sym}] Rebuttal failed: {e}", exc_info=True)
                return sym, None

    tasks = [_process_single(sym, r) for sym, r in actionable]
    results = await asyncio.gather(*tasks)

    for sym, res in results:
        if res:
            existing = debate_states.get(sym, {})
            existing.update(res)
            debate_states[sym] = existing

    return {"debate_states": debate_states}
