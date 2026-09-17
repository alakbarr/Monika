# ==============================================================================
# File: graph/nodes/debate/bull_advocate_node.py
# ==============================================================================

import json
import logging
import asyncio
from typing import Dict, Any, Optional

from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from database.models import AssetAnalysis
from analysis.providers.llm_factory import get_client_for_task
from analysis.debate.bull_analyst import generate_bull_advocacy
from analysis.debate.fact_sheet import build_fact_sheet
from graph.nodes.debate.helpers import inject_coherence_and_intel, _is_grounded, sync_facade_patches

logger = logging.getLogger("TradingAgent.Graph.Debate.BullAdvocateNode")


async def bull_advocate_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sub-agent node: Bull Advocate.
    Memeriksa tesis awal, membangun fact sheet, menginjeksi coherence/intel,
    dan menghasilkan verified_bull_claim untuk setiap actionable trade.
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
        logger.info("Debate is disabled in settings. Bypassing bull advocate node.")
        return {}

    logger.info(f"[Debate:BullAdvocate] Generating bull advocacy for {len(actionable)} trades...")
    debate_states = dict(state.get("debate_states", {}))
    user_market_intel = state.get("user_market_intel") or []

    bull_client = get_client_for_task("debate_bull", settings)
    if not bull_client:
        bull_client = get_client_for_task("debate_bear", settings)

    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        analysis_id = r["analysis_id"]
        async with semaphore:
            try:
                async with get_session() as session:
                    ana = await session.get(AssetAnalysis, analysis_id)
                    if not ana:
                        return sym, None

                    bull_thesis = ana.rationale or ""
                    decision = ana.decision.upper()

                    bull_thesis, rel_intel = await inject_coherence_and_intel(
                        session, sym, bull_thesis, user_market_intel
                    )

                    fact_sheet = await build_fact_sheet(session, analysis_id)
                    entry_zone_data = json.loads(ana.entry_zone) if ana.entry_zone else {}
                    original_context = {
                        'decision': decision,
                        'rationale': bull_thesis,
                        'confluence_score': ana.confluence_score,
                        'confluence_factors': json.loads(ana.confluence_factors_json) if ana.confluence_factors_json else [],
                        'entry_price': entry_zone_data.get('price'),
                        'stop_loss': ana.stop_loss,
                        'take_profit': ana.take_profit,
                        'invalidation': ana.invalidation,
                        'user_market_intel': rel_intel,
                    }

                    verified_bull_claim = await generate_bull_advocacy(bull_client, sym, original_context, fact_sheet)

                    curr_p = float(ana.price_at_analysis or 0.0)
                    if not _is_grounded(verified_bull_claim, curr_p):
                        verified_bull_claim['strength_score'] = max(1, verified_bull_claim.get('strength_score', 5) - 2)
                        verified_bull_claim['ungrounded_penalty'] = True

                    return sym, {
                        'analysis_id': analysis_id,
                        'decision': decision,
                        'bull_thesis': bull_thesis,
                        'entry_zone_data': entry_zone_data,
                        'original_context': original_context,
                        'fact_sheet': fact_sheet,
                        'verified_bull_claim': verified_bull_claim,
                        'rel_intel': rel_intel,
                        'curr_p': curr_p,
                    }
            except Exception as e:
                logger.error(f"[{sym}] Bull advocacy failed: {e}", exc_info=True)
                return sym, None

    tasks = [_process_single(sym, r) for sym, r in actionable]
    results = await asyncio.gather(*tasks)

    for sym, res in results:
        if res:
            existing = debate_states.get(sym, {})
            existing.update(res)
            debate_states[sym] = existing

    return {"debate_states": debate_states}
