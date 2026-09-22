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
            inp = int(res.get("input_tokens", 0) or 0)
            out = int(res.get("output_tokens", 0) or 0)
            return inp, out
        sum_dict = res.get("summary")
        if isinstance(sum_dict, dict):
            node_sum = sum_dict.get(node_name)
            if isinstance(node_sum, dict):
                inp = int(node_sum.get("input_tokens", 0) or 0)
                out = int(node_sum.get("output_tokens", 0) or 0)
                return inp, out
            for k in ("fundamental", "per_asset", "debate", "risk_gate", "execution"):
                sub = sum_dict.get(k)
                if isinstance(sub, dict) and ("input_tokens" in sub or "output_tokens" in sub):
                    inp += int(sub.get("input_tokens", 0) or 0)
                    out += int(sub.get("output_tokens", 0) or 0)
    return inp, out


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
            with node_span(node_name, cycle_id=cycle_id):
                res = await node_fn(state, *args, **kwargs)
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
            with node_span(node_name, cycle_id=cycle_id):
                res = node_fn(state, *args, **kwargs)
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
        actionable = state.get("actionable_trades", [])
        if actionable:
            return "risk_gate"
        return "END"
        
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
    
    # Monika v2 (PR-04): Authoritative PostgreSQL checkpointer (no SQLite dual-write overhead)
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
