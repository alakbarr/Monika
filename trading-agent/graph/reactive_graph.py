# ==============================================================================
# File: graph/reactive_graph.py
# ==============================================================================

"""
Reactive Graph Workflow for AI Trading Agent (CRITICAL-01).

Menyatukan seluruh entry point eksekusi reaktif (news watcher, price trigger,
session trigger, quant edge runner) ke dalam LangGraph StateGraph terpadu.
Memastikan semua jalur reaktif melewati:
1. Event Ingestion & Normalization
2. Confluence & Spread Filtering
3. Multi-Agent Dialectic Debate & Risk Evaluation
4. Institutional RiskGate (fail-closed, exposure, drawdown)
5. Execution via ExecutionService (live/dry-run/paper)
6. State Checkpointing & Activity Logging
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.db import get_session
from database.models import AssetAnalysis, ActivityLog, TradeTrigger, SystemConfig
from execution.execution_service import ExecutionService
from graph.state import TradingState, merge_dicts, merge_lists
from langchain_core.runnables.config import RunnableConfig

logger = logging.getLogger("TradingAgent.Graph.ReactiveGraph")

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    StateGraph = None
    END = "END"
    MemorySaver = None


class ReactiveState(TradingState, total=False):
    """State khusus untuk eksekusi reaktif LangGraph."""
    event_type: str                     # 'news_event', 'price_trigger', 'session_trigger', 'edge_signal'
    event_data: Dict[str, Any]          # Raw event payload (trigger info, news items, signal metadata)
    extra_context: Optional[str]        # Context prompt string
    execution_results: Dict[str, Any]   # Results from ExecutionService per symbol
    confluence_filtered_trades: List[Tuple[str, dict]]
    debate_approved_trades: List[Tuple[str, dict]]


# -----------------------------------------------------------------------------
# Reactive Nodes
# -----------------------------------------------------------------------------

async def event_ingestion_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Ingest reactive event, load market regime/VIX, and resolve actionable trades."""
    event_type = state.get("event_type", "unknown")
    event_data = state.get("event_data") or {}
    symbols = list(state.get("symbols") or [])
    actionable = list(state.get("actionable_trades") or [])
    summary = dict(state.get("summary") or {})

    logger.info(f"[ReactiveGraph:Ingest] Ingesting event '{event_type}' with {len(actionable)} trade(s), {len(symbols)} symbol(s)")

    # 1. Ingest preplanned order or single trigger if actionable is empty
    if not actionable and event_type == "price_trigger":
        trigger_id = event_data.get("trigger_id")
        preplanned = event_data.get("preplanned_order")
        analysis_id = event_data.get("analysis_id")
        symbol = event_data.get("symbol")

        if symbol and analysis_id:
            actionable.append((symbol, {
                "analysis_id": analysis_id,
                "decision": (preplanned.get("type", "buy") if preplanned else "buy").lower(),
                "confidence": preplanned.get("confidence", 0.70) if preplanned else 0.70,
                "entry_price": event_data.get("current_price"),
                "stop_loss": preplanned.get("sl") if preplanned else None,
                "take_profit": preplanned.get("tp") if preplanned else None,
                "trigger_id": trigger_id,
                "is_preplanned": bool(preplanned),
            }))
            if symbol not in symbols:
                symbols.append(symbol)

    # 2. Ingest edge strategy signals if provided
    if not actionable and event_type == "edge_signal":
        analyses = event_data.get("analyses") or []
        for ana in analyses:
            ana_id = getattr(ana, "id", None)
            sym = getattr(ana, "symbol", None)
            dec = getattr(ana, "decision", "buy")
            conf = getattr(ana, "confidence", 0.65)
            if sym and ana_id:
                actionable.append((sym, {
                    "analysis_id": ana_id,
                    "decision": str(dec).lower(),
                    "confidence": float(conf),
                    "source_strategy_id": getattr(ana, "source_strategy_id", None),
                    "pair_group_id": event_data.get("pair_group_id"),
                }))
                if sym not in symbols:
                    symbols.append(sym)

    # 3. Load market regime if not present
    market_regime = state.get("market_regime")
    if not market_regime:
        try:
            async with get_session() as session:
                from database.models import FundamentalBrief
                row = (await session.execute(
                    select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                )).scalar_one_or_none()
                market_regime = (row.macro_regime if (row and row.macro_regime) else (row.risk_sentiment if row and row.risk_sentiment else "normal")) if row else "normal"
        except Exception:
            market_regime = "normal"

    summary["reactive_event"] = {
        "event_type": event_type,
        "symbols": symbols,
        "initial_actionable_count": len(actionable),
        "timestamp": clock.now().isoformat()
    }

    return {
        "symbols": symbols,
        "actionable_trades": actionable,
        "market_regime": market_regime,
        "summary": summary
    }


async def confluence_filter_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Filter candidate trades using confluence score and confidence thresholds."""
    actionable = list(state.get("actionable_trades") or [])
    if not actionable:
        return {"actionable_trades": []}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    settings = scheduler.settings if scheduler and hasattr(scheduler, "settings") else {}
    trading_cfg = settings.get("trading", {})

    min_confluence = trading_cfg.get("auto_execute_min_confluence", 7)
    min_confidence = trading_cfg.get("auto_execute_min_confidence", 0.60)

    # Check database dynamic override
    try:
        async with get_session() as session:
            cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == "auto_execute_min_confidence_override")
            )).scalar_one_or_none()
            if cfg and cfg.value:
                min_confidence = float(cfg.value)
    except Exception:
        pass

    surviving: List[Tuple[str, dict]] = []
    filtered: List[Tuple[str, dict]] = []

    async with get_session() as session:
        for sym, r in actionable:
            analysis_id = r.get("analysis_id")
            if not analysis_id:
                surviving.append((sym, r))
                continue

            ana = await session.get(AssetAnalysis, analysis_id)
            if not ana:
                surviving.append((sym, r))
                continue

            conf = float(ana.confidence or r.get("confidence", 0.0))
            confluence = int(ana.confluence_score or 0)

            # Edge strategies or preplanned orders may have custom thresholds
            if r.get("source_strategy_id") or r.get("is_preplanned"):
                effective_min_conf = min_confidence - 0.05
                effective_min_confluence = max(4, min_confluence - 3)
            else:
                effective_min_conf = min_confidence
                effective_min_confluence = min_confluence

            if conf >= effective_min_conf and confluence >= effective_min_confluence:
                surviving.append((sym, r))
            else:
                logger.info(
                    f"[ReactiveGraph:ConfluenceFilter] {sym} filtered out: conf={conf:.2f} (min {effective_min_conf:.2f}), "
                    f"confluence={confluence} (min {effective_min_confluence})"
                )
                filtered.append((sym, r))

    summary = dict(state.get("summary") or {})
    summary["confluence_filter"] = {
        "surviving_count": len(surviving),
        "filtered_count": len(filtered),
        "min_confluence": min_confluence,
        "min_confidence": min_confidence
    }

    return {
        "actionable_trades": surviving,
        "confluence_filtered_trades": filtered,
        "summary": summary
    }


async def fast_debate_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run dialectic debate and risk persona verification on candidate trades."""
    actionable = list(state.get("actionable_trades") or [])
    if not actionable:
        return {"actionable_trades": []}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    settings = scheduler.settings if scheduler and hasattr(scheduler, "settings") else {}
    enable_debate = settings.get("agent_architecture", {}).get("enable_debate", True)

    if not enable_debate:
        logger.info("[ReactiveGraph:Debate] Debate disabled in settings. Skipping to RiskGate.")
        return {"actionable_trades": actionable}

    try:
        from graph.nodes.debate.subgraph import build_debate_subgraph
        debate_sub = build_debate_subgraph()
        debate_res = await debate_sub.ainvoke(state, config=config)
        approved = debate_res.get("actionable_trades", [])
        logger.info(f"[ReactiveGraph:Debate] Fast debate completed. {len(approved)}/{len(actionable)} trade(s) approved.")
        return {
            "actionable_trades": approved,
            "debate_states": debate_res.get("debate_states", {}),
            "investment_verdicts": debate_res.get("investment_verdicts", {}),
            "portfolio_decisions": debate_res.get("portfolio_decisions", {}),
            "risk_debate_states": debate_res.get("risk_debate_states", {}),
        }
    except Exception as e:
        logger.warning(f"[ReactiveGraph:Debate] Debate subgraph failed ({e}). Proceeding to RiskGate with caution.", exc_info=True)
        return {"actionable_trades": actionable}


async def reactive_risk_gate_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run institutional RiskGate verification (fail-closed, exposure, drawdown)."""
    actionable = list(state.get("actionable_trades") or [])
    if not actionable:
        return {"actionable_trades": []}

    from graph.nodes.risk_gate_node import risk_gate_node
    res = await risk_gate_node(state, config=config)
    return res


async def reactive_execution_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Execute risk-approved trades via ExecutionService with proper DB status updates."""
    actionable = list(state.get("actionable_trades") or [])
    summary = dict(state.get("summary") or {})
    execution_results = {}

    if not actionable:
        summary["execution"] = {"status": "no_actionable_trades", "executed_count": 0}
        return {"summary": summary, "execution_results": {}}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    settings = scheduler.settings if scheduler and hasattr(scheduler, "settings") else {}
    trading_cfg = settings.get("trading", {})
    auto_execute = trading_cfg.get("auto_execute", False)

    mt5_client = getattr(scheduler, "_mt5", None) if scheduler else None
    dry_run = getattr(scheduler, "dry_run", False) if scheduler else False

    exec_svc = getattr(scheduler, "_execution_service", None) or getattr(scheduler, "execution_service", None)
    if not exec_svc:
        exec_svc = ExecutionService(settings, mt5_client=mt5_client, dry_run=dry_run)

    equity = None
    if mt5_client:
        try:
            acc = await mt5_client.get_account_info()
            equity = acc.get("equity") if acc else None
        except Exception:
            pass

    event_data = state.get("event_data") or {}
    pair_group_id = str(event_data.get("pair_group_id") or "")
    analyses_to_execute = event_data.get("analyses") or []
    session_override = event_data.get("session")

    async def _do_execution(session: AsyncSession):
        # 1. Handle paired hedge order from edge strategy runner
        if len(analyses_to_execute) == 2 and hasattr(exec_svc, "execute_paired_analyses"):
            try:
                p_res = await exec_svc.execute_paired_analyses(
                    session, analyses_to_execute[0], analyses_to_execute[1], pair_group_id
                )
                execution_results["paired"] = p_res.get("summary", str(p_res)) if isinstance(p_res, dict) else str(p_res)
            except Exception as e:
                logger.error(f"[ReactiveGraph:Execution] Paired execution failed: {e}")
                execution_results["paired"] = f"error: {e}"
        elif len(analyses_to_execute) == 1 and hasattr(exec_svc, "execute_analysis"):
            try:
                ana_target = analyses_to_execute[0]
                res = await exec_svc.execute_analysis(session, ana_target, equity)
                exec_summary = res.summary() if hasattr(res, "summary") else str(res)
                execution_results[ana_target.symbol] = exec_summary
                if getattr(res, "executed", False):
                    ana_target.execution_status = "executed"
                elif not getattr(res, "risk_approved", True):
                    ana_target.execution_status = "blocked"
                else:
                    ana_target.execution_status = "failed"
                ana_target.execution_notes = exec_summary
                await session.commit()
            except Exception as e:
                logger.error(f"[ReactiveGraph:Execution] Analysis execution failed: {e}")
                execution_results[analyses_to_execute[0].symbol] = f"error: {e}"
        else:
            # 2. Standard per-symbol execution from actionable_trades
            for sym, r in actionable:
                analysis_id = r.get("analysis_id")
                if not analysis_id:
                    continue
                ana = await session.get(AssetAnalysis, analysis_id)
                if not ana:
                    continue

                if auto_execute:
                    try:
                        res = await exec_svc.execute_analysis(session, ana, equity)
                        exec_summary = res.summary() if hasattr(res, "summary") else str(res)
                        execution_results[sym] = exec_summary

                        if getattr(res, "executed", False):
                            ana.execution_status = "executed"
                        elif not getattr(res, "risk_approved", True):
                            ana.execution_status = "blocked"
                        else:
                            ana.execution_status = "failed"
                        ana.execution_notes = exec_summary
                        await session.commit()
                        logger.info(f"[ReactiveGraph:Execution] {sym} -> {ana.execution_status}: {exec_summary}")
                    except Exception as e:
                        logger.error(f"[ReactiveGraph:Execution] Failed executing {sym}: {e}", exc_info=True)
                        ana.execution_status = "failed"
                        ana.execution_notes = str(e)
                        await session.commit()
                        execution_results[sym] = f"error: {e}"
                else:
                    logger.info(f"[ReactiveGraph:Execution] auto_execute=false. Proposal logged for {sym}.")
                    ana.execution_status = "proposed"
                    ana.execution_notes = "Auto-execute disabled in settings; proposal recorded."
                    await session.commit()
                    execution_results[sym] = "proposed"

    if session_override:
        await _do_execution(session_override)
    else:
        async with get_session() as session:
            await _do_execution(session)

    summary["execution"] = {
        "status": "completed",
        "results": execution_results,
        "executed_count": sum(1 for v in execution_results.values() if "executed" in str(v).lower())
    }

    return {
        "execution_results": execution_results,
        "summary": summary
    }


async def reactive_checkpoint_node(state: ReactiveState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Persist final execution log and record reactive activity."""
    event_type = state.get("event_type", "reactive_cycle")
    summary = state.get("summary") or {}
    exec_res = state.get("execution_results") or {}

    try:
        async with get_session() as session:
            act = ActivityLog(
                timestamp=clock.now(),
                category="trading",
                actor="reactive_graph",
                description=f"Reactive execution completed for '{event_type}'. Results: {json.dumps(exec_res)}"
            )
            session.add(act)
            await session.commit()
    except Exception as e:
        logger.warning(f"[ReactiveGraph:Checkpoint] Could not persist activity log: {e}")

    return {"summary": summary}


# -----------------------------------------------------------------------------
# Graph Builder & Routing Logic
# -----------------------------------------------------------------------------

def route_after_ingest(state: ReactiveState) -> str:
    """Route after event ingestion: edge signals go to risk_gate; empty trades to checkpoint."""
    if not state.get("actionable_trades"):
        return "checkpoint"
    if state.get("event_type") == "edge_signal":
        return "risk_gate"
    return "confluence_filter"


def route_after_confluence(state: ReactiveState) -> str:
    """Route after confluence filter: surviving trades proceed to fast_debate."""
    if state.get("actionable_trades"):
        return "fast_debate"
    return "checkpoint"


def route_after_debate(state: ReactiveState) -> str:
    """Route after debate: approved trades proceed to risk_gate."""
    if state.get("actionable_trades"):
        return "risk_gate"
    return "checkpoint"


def route_after_risk(state: ReactiveState) -> str:
    """Route after risk gate: approved trades proceed to execution."""
    if state.get("actionable_trades"):
        return "execution"
    return "checkpoint"


def build_reactive_graph(checkpointer: Optional[Any] = None) -> Any:
    """Build and compile the LangGraph Reactive StateGraph."""
    if StateGraph is None:
        raise RuntimeError("LangGraph is not installed. Cannot build reactive graph.")

    workflow = StateGraph(ReactiveState)

    # 1. Add nodes
    workflow.add_node("event_ingestion", event_ingestion_node)
    workflow.add_node("confluence_filter", confluence_filter_node)
    workflow.add_node("fast_debate", fast_debate_node)
    workflow.add_node("risk_gate", reactive_risk_gate_node)
    workflow.add_node("execution", reactive_execution_node)
    workflow.add_node("checkpoint", reactive_checkpoint_node)

    # 2. Entry point
    workflow.set_entry_point("event_ingestion")

    # 3. Edges
    workflow.add_conditional_edges(
        "event_ingestion",
        route_after_ingest,
        {"confluence_filter": "confluence_filter", "risk_gate": "risk_gate", "checkpoint": "checkpoint"}
    )

    workflow.add_conditional_edges(
        "confluence_filter",
        route_after_confluence,
        {"fast_debate": "fast_debate", "checkpoint": "checkpoint"}
    )

    workflow.add_conditional_edges(
        "fast_debate",
        route_after_debate,
        {"risk_gate": "risk_gate", "checkpoint": "checkpoint"}
    )

    workflow.add_conditional_edges(
        "risk_gate",
        route_after_risk,
        {"execution": "execution", "checkpoint": "checkpoint"}
    )

    workflow.add_edge("execution", "checkpoint")
    workflow.add_edge("checkpoint", END)

    return workflow.compile(checkpointer=checkpointer)


_REACTIVE_GRAPH_INSTANCE = None

def get_reactive_graph(checkpointer: Optional[Any] = None) -> Any:
    """Retrieve or build the global singleton reactive graph instance."""
    global _REACTIVE_GRAPH_INSTANCE
    if _REACTIVE_GRAPH_INSTANCE is None:
        _REACTIVE_GRAPH_INSTANCE = build_reactive_graph(checkpointer=checkpointer)
    return _REACTIVE_GRAPH_INSTANCE
