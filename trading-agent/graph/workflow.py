# pyright: reportMissingImports=false
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import StateGraph, END  # type: ignore
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except ImportError:
    StateGraph = None  # type: ignore
    END = "END"
    MemorySaver = None  # type: ignore

from graph.state import TradingState
from graph.nodes.data_node import fetch_data_node
from graph.nodes.fundamental_node import fundamental_analysis_node
from graph.nodes.per_asset_node import per_asset_analysis_node
from graph.nodes.debate_node import debate_node
from graph.nodes.debate.subgraph import build_debate_subgraph
from graph.nodes.risk_gate_node import risk_gate_node
from graph.nodes.execution_node import execution_node
from graph.nodes.reflection_node import reflection_node
from graph.nodes.plan_refinement_node import plan_refinement_node
import asyncio
import functools
import inspect
from graph.nodes.state_pruner import prune_after_fundamental, prune_after_debate, prune_before_execution
from logging_observability.tracing.spans import node_span
import time
from analysis.event_broadcaster import emit_analysis_event


def _extract_tokens_from_result(node_name: str, res: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from node result dict if available."""
    inp = 0
    out = 0
    if isinstance(res, dict):
        if "input_tokens" in res or "output_tokens" in res:
            inp += int(res.get("input_tokens", 0) or 0)
            out += int(res.get("output_tokens", 0) or 0)
        sum_dict = res.get("summary")
        if isinstance(sum_dict, dict):
            for k in (node_name, "fundamental", "per_asset", "debate", "risk_gate", "execution"):
                sub = sum_dict.get(k)
                if isinstance(sub, dict):
                    if "input_tokens" in sub or "output_tokens" in sub:
                        inp += int(sub.get("input_tokens", 0) or 0)
                        out += int(sub.get("output_tokens", 0) or 0)
                    else:
                        # Nested dict per symbol (e.g., summary["per_asset"]["EURUSD"] = {...})
                        for sym_val in sub.values():
                            if isinstance(sym_val, dict):
                                inp += int(sym_val.get("input_tokens", 0) or 0)
                                out += int(sym_val.get("output_tokens", 0) or 0)
    return inp, out


def _build_node_payload_summary(node_name: str, res: Any, state: Any) -> Optional[dict]:
    """Extract structured output summary payload for the dashboard node inspector."""
    if not isinstance(res, dict):
        return None
    try:
        if node_name in ("data_gathering", "prefetch_data"):
            return {
                "events_count": len(res.get("upcoming_events", [])),
                "market_regime": res.get("market_regime", "normal"),
                "status": "data_gathered"
            }
        elif node_name == "fundamental_analysis":
            sum_fund = res.get("summary", {}).get("fundamental", {})
            return {
                "brief_id": sum_fund.get("brief_id"),
                "success": sum_fund.get("success", True),
                "tool_calls": sum_fund.get("tool_calls", 0),
                "elapsed_s": sum_fund.get("elapsed_s", 0.0),
                "input_tokens": sum_fund.get("input_tokens", 0),
                "output_tokens": sum_fund.get("output_tokens", 0),
            }
        elif node_name == "per_asset_analysis":
            pa = res.get("asset_analyses", {})
            actionable = res.get("actionable_trades", [])
            decisions = {sym: (r.get("decision") if isinstance(r, dict) else str(r)) for sym, r in pa.items()}
            return {
                "total_analyzed": len(pa),
                "decisions": decisions,
                "actionable_symbols": [sym for sym, _ in actionable] if actionable else [],
            }
        elif node_name in ("bull_advocate", "bear_dissent", "debate_judge", "rebuttal", "debate"):
            deb_states = res.get("debate_states") or (state.get("debate_states") if isinstance(state, dict) else {}) or {}
            actionable = res.get("actionable_trades") or (state.get("actionable_trades") if isinstance(state, dict) else []) or []
            return {
                "actionable_count": len(actionable),
                "symbols": [s for s, _ in actionable] if actionable else [],
                "debate_states": {
                    s: {
                        "decision": d.get("decision"),
                        "strength": (d.get("verified_bull_claim") or {}).get("strength_score"),
                        "judge_verdict": d.get("investment_verdict") or d.get("final_decision"),
                    }
                    for s, d in deb_states.items()
                } if deb_states else {},
            }
        elif node_name == "reflection":
            sum_refl = res.get("summary", {}).get("reflection", {}) if isinstance(res.get("summary"), dict) else {}
            return {
                "reflection_summary": sum_refl,
                "vix": res.get("vix"),
            }
        elif node_name == "risk_gate":
            actionable = res.get("actionable_trades", [])
            approved = res.get("approved_trades", [])
            return {
                "actionable_count": len(actionable),
                "approved_count": len(approved),
                "approved_symbols": [s for s, _ in approved] if approved else [],
            }
        elif node_name == "execution":
            sum_exec = res.get("summary", {}).get("execution", {}) if isinstance(res.get("summary"), dict) else {}
            return {
                "status": sum_exec.get("status", "completed"),
                "count": sum_exec.get("count", 0),
            }
    except Exception:
        pass
    return None


def _is_node_skipped(node_name: str, res: Any, state: Any) -> bool:
    """Determine if a node was skipped/bypassed due to empty candidate set."""
    actionable = state.get("actionable_trades", []) if isinstance(state, dict) else []
    if node_name in ("bull_advocate", "bear_dissent", "debate_judge", "rebuttal") and not actionable:
        return True
    if node_name == "execution":
        approved = state.get("approved_trades", []) if isinstance(state, dict) else []
        if not approved and not actionable:
            return True
    return False


def _wrap_traced_node(node_name: str, node_fn: Any):
    """Wraps a LangGraph node function with distributed tracing, token tracking, and live event broadcasting."""
    if not callable(node_fn) or hasattr(node_fn, "astream") or hasattr(node_fn, "ainvoke"):
        return node_fn

    if inspect.iscoroutinefunction(node_fn):
        @functools.wraps(node_fn)
        async def _traced_async_node_fn(state: Any, *args, **kwargs):
            cycle_id = state.get("cycle_id") if isinstance(state, dict) else None
            sym = state.get("symbol", "") if isinstance(state, dict) else ""
            emit_analysis_event("analysis_step_start", {"cycle_id": cycle_id, "step": node_name, "symbol": sym})
            t0 = time.time()
            res = None
            with node_span(node_name, cycle_id=cycle_id) as span_inst:
                res = await node_fn(state, *args, **kwargs)
                dur_s = time.time() - t0
                inp, out = _extract_tokens_from_result(node_name, res)
                if span_inst:
                    span_inst.set_attribute("input_tokens", inp)
                    span_inst.set_attribute("output_tokens", out)
                    is_skipped = _is_node_skipped(node_name, res, state)
                    span_inst.set_attribute("is_skipped", is_skipped)
                    payload = _build_node_payload_summary(node_name, res, state)
                    if payload:
                        span_inst.set_attribute("output_payload", payload)
            dur_s = time.time() - t0
            inp, out = _extract_tokens_from_result(node_name, res)
            try:
                from utils.llm.context_tracker import get_context_tracker
                if inp or out:
                    get_context_tracker().record_usage(input_tokens=inp, output_tokens=out, step=node_name)
            except Exception:
                pass
            emit_analysis_event(
                "analysis_step_complete",
                {
                    "cycle_id": cycle_id,
                    "step": node_name,
                    "duration_s": dur_s,
                    "duration_ms": dur_s * 1000,
                    "input_tokens": inp,
                    "output_tokens": out,
                },
            )
            return res

        return _traced_async_node_fn
    else:
        @functools.wraps(node_fn)
        def _traced_sync_node_fn(state: Any, *args, **kwargs):
            cycle_id = state.get("cycle_id") if isinstance(state, dict) else None
            sym = state.get("symbol", "") if isinstance(state, dict) else ""
            emit_analysis_event("analysis_step_start", {"cycle_id": cycle_id, "step": node_name, "symbol": sym})
            t0 = time.time()
            res = None
            with node_span(node_name, cycle_id=cycle_id) as span_inst:
                res = node_fn(state, *args, **kwargs)
                dur_s = time.time() - t0
                inp, out = _extract_tokens_from_result(node_name, res)
                if span_inst:
                    span_inst.set_attribute("input_tokens", inp)
                    span_inst.set_attribute("output_tokens", out)
                    is_skipped = _is_node_skipped(node_name, res, state)
                    span_inst.set_attribute("is_skipped", is_skipped)
                    payload = _build_node_payload_summary(node_name, res, state)
                    if payload:
                        span_inst.set_attribute("output_payload", payload)
            dur_s = time.time() - t0
            inp, out = _extract_tokens_from_result(node_name, res)
            try:
                from utils.llm.context_tracker import get_context_tracker
                if inp or out:
                    get_context_tracker().record_usage(input_tokens=inp, output_tokens=out, step=node_name)
            except Exception:
                pass
            emit_analysis_event(
                "analysis_step_complete",
                {
                    "cycle_id": cycle_id,
                    "step": node_name,
                    "duration_s": dur_s,
                    "duration_ms": dur_s * 1000,
                    "input_tokens": inp,
                    "output_tokens": out,
                },
            )
            return res

        return _traced_sync_node_fn


def build_trading_graph(db_url: Optional[str] = None) -> Any:
    """
    Menyusun graf yang merepresentasikan siklus penuh AI Trading Agent.
    """
    if StateGraph is None:
        raise RuntimeError("LangGraph is not installed. Please install langgraph to use the trading graph workflow.")

    workflow = StateGraph(TradingState)
    
    # 1. Define nodes
    workflow.add_node("data_gathering", _wrap_traced_node("data_gathering", fetch_data_node))
    workflow.add_node("fundamental_analysis", _wrap_traced_node("fundamental_analysis", fundamental_analysis_node))
    workflow.add_node("prune_fundamental", _wrap_traced_node("prune_fundamental", prune_after_fundamental))
    workflow.add_node("per_asset_analysis", _wrap_traced_node("per_asset_analysis", per_asset_analysis_node))
    
    # LangGraph multi-agent debate decomposition: wire decomposed debate subgraph with checkpointing and node tracing
    try:
        sub_checkpointer = MemorySaver() if MemorySaver is not None else None
        debate_subgraph = build_debate_subgraph(checkpointer=sub_checkpointer, node_wrapper=_wrap_traced_node)
        workflow.add_node("debate", debate_subgraph)
    except Exception as e:
        logger.warning(f"Could not compile debate subgraph ({e}), falling back to debate_node facade")
        workflow.add_node("debate", _wrap_traced_node("debate", debate_node))

    workflow.add_node("reflection", _wrap_traced_node("reflection", reflection_node))
    workflow.add_node("risk_gate", _wrap_traced_node("risk_gate", risk_gate_node))
    workflow.add_node("plan_refinement", _wrap_traced_node("plan_refinement", plan_refinement_node))
    workflow.add_node("execution", _wrap_traced_node("execution", execution_node))
    
    # 2. Define edges & entry point
    workflow.set_entry_point("data_gathering")
    
    # Setelah data gathering, cek apakah budget pause
    def data_routing(state: TradingState) -> str:
        if state.get("should_pause"):
            return "END"
        return "fundamental_analysis"
        
    workflow.add_conditional_edges(
        "data_gathering",
        data_routing,
        {
            "fundamental_analysis": "fundamental_analysis",
            "END": END
        }
    )
    
    # Setelah fundamental, lanjut ke per_asset
    def fundamental_routing(state: TradingState) -> str:
        if state.get("should_pause"):
            errors = state.get('node_errors', {})
            fund_error = errors.get('fundamental') or ''
            
            # Permanent errors -> langsung END
            if any(perm in fund_error for perm in ['AuthenticationError', 'invalid_api_key', 'permanent_error']):
                return 'END'
                
            retry_count = state.get('fundamental_retry_count', 0)
            if retry_count <= 1:
                return 'fundamental_analysis' # re-run same node
            return "END"
            
        # NEW: SSVP pre-check sebelum per_asset
        ssvp_blocked = state.get('ssvp_blocked', False)
        if ssvp_blocked:
            ssvp_cds = state.get('ssvp_cds_score', 0.0)
            import logging
            logger = logging.getLogger(__name__)
            
            retry = state.get('ssvp_retry_count', 0)
            if retry >= 2:
                logger.warning(f"[SSVP] Routing blocked max retries reached: CDS={ssvp_cds:.2f} — ENDING")
                return 'END'
                
            logger.warning(f"[SSVP] Routing blocked: CDS={ssvp_cds:.2f} — triggering Stage 1 re-run (retry {retry})")
            return 'fundamental_analysis'  # Re-run Stage 1
            
        return "prune_fundamental"
        
    workflow.add_conditional_edges(
        "fundamental_analysis",
        fundamental_routing,
        {
            "fundamental_analysis": "fundamental_analysis",
            "prune_fundamental": "prune_fundamental",
            "END": END
        }
    )
    workflow.add_edge("prune_fundamental", "per_asset_analysis")
    
    workflow.add_node("prune_debate", _wrap_traced_node("prune_debate", prune_after_debate))
    workflow.add_edge("per_asset_analysis", "debate")
    workflow.add_edge("debate", "prune_debate")
    workflow.add_edge("prune_debate", "reflection")
    
    def reflection_routing(state: TradingState) -> str:
        if state.get("should_pause"):
            return "END"
        return "risk_gate"  # Always evaluate — quant alpha may promote WAIT assets
        
    workflow.add_conditional_edges(
        "reflection",
        reflection_routing,
        {
            "risk_gate": "risk_gate",
            "END": END
        }
    )
    
    workflow.add_node("prune_execution", _wrap_traced_node("prune_execution", prune_before_execution))

    # Setelah risk gate, cek apakah ada trade yang disetujui atau penolakan yang bisa disempurnakan
    def risk_routing(state: TradingState) -> str:
        actionable = state.get('actionable_trades', [])
        if actionable and len(actionable) > 0:
            return "prune_execution"
        if state.get("is_negotiable_rejection") and state.get("refinement_count", 0) < 2:
            return "plan_refinement"
        return "END"
        
    workflow.add_conditional_edges(
        "risk_gate",
        risk_routing,
        {
            "prune_execution": "prune_execution",
            "plan_refinement": "plan_refinement",
            "END": END
        }
    )
    workflow.add_edge("plan_refinement", "risk_gate")
    workflow.add_edge("prune_execution", "execution")
    workflow.add_edge("execution", END)
    
    # PR-04: Authoritative PostgreSQL checkpointer (no SQLite dual-write overhead)
    checkpointer = None
    if db_url:
        pg_url = db_url.replace('+asyncpg', '').replace('postgresql+psycopg2', 'postgresql')
        if pg_url.startswith(('postgresql://', 'postgres://')):
            try:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
                from psycopg_pool import AsyncConnectionPool  # type: ignore
                pool: Any = AsyncConnectionPool(
                    conninfo=pg_url,
                    max_size=20,
                    kwargs={"autocommit": True, "prepare_threshold": 0},
                    open=False
                )
                pg_checkpointer = AsyncPostgresSaver(pool)
                setattr(pg_checkpointer, "_needs_setup", True)
                checkpointer = pg_checkpointer
                logger.info('LangGraph: Authoritative PostgreSQL checkpointer created (setup pending)')
            except ImportError:
                logger.warning('langgraph-checkpoint-postgres not installed, using MemorySaver fallback')
                checkpointer = MemorySaver() if MemorySaver is not None else None
            except Exception as e:
                logger.error(f'PostgreSQL checkpointer init failed: {e}. Using MemorySaver fallback.')
                checkpointer = MemorySaver() if MemorySaver is not None else None
        else:
            checkpointer = MemorySaver() if MemorySaver is not None else None
    else:
        checkpointer = MemorySaver() if MemorySaver is not None else None
        
    return workflow.compile(checkpointer=checkpointer)
