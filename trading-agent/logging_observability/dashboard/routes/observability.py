# ==============================================================================
# File: logging_observability/dashboard/routes/observability.py
# Description: Traces, Graph State, and Deep Observability Endpoints
# ==============================================================================

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("TradingAgent.DashboardAPI.Observability")

observability_router = APIRouter()


# ---------------------------------------------------------------------------
# Distributed Tracing Endpoints
# ---------------------------------------------------------------------------

@observability_router.get("/api/traces", tags=["Observability"])
async def get_traces(
    cycle_id: Optional[str] = Query(None, description="Filter spans by cycle_id"),
    trace_id: Optional[str] = Query(None, description="Filter spans by trace_id"),
    kind: Optional[str] = Query(None, description="Filter by kind: cycle, node, llm, tool"),
    limit: int = Query(100, ge=1, le=1000, description="Max spans to return"),
):
    """Retrieve distributed trace spans from the in-memory trace store."""
    from logging_observability.tracing.exporters import global_trace_store
    spans = global_trace_store.get_spans(limit=limit, trace_id=trace_id, cycle_id=cycle_id, kind=kind)
    return {"spans": spans, "total": len(spans)}


@observability_router.get("/api/traces/{trace_id}", tags=["Observability"])
async def get_trace_tree(trace_id: str):
    """Retrieve hierarchical trace tree for a specific trace_id."""
    from logging_observability.tracing.exporters import global_trace_store
    tree = global_trace_store.get_trace_tree(trace_id)
    if not tree:
        return JSONResponse(status_code=404, content={"detail": f"Trace {trace_id} not found."})
    return {"trace_id": trace_id, "roots": tree}


def _build_graph_state_for_cycle(
    cycle_id: Optional[str] = None,
    symbol: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs the LangGraph DAG topology state with node statuses, execution durations,
    token consumption, inputs, and payloads for the frontend visualizer.
    Supports filtering by specific symbol across Stage 2 and downstream nodes.
    """
    from logging_observability.tracing.exporters import global_trace_store

    discovered_cycles = []
    seen = set()
    for s in reversed(global_trace_store._spans):
        cid = s.attributes.get("cycle_id") or (s.name.split("cycle:")[-1] if s.kind == "cycle" and ":" in s.name else None)
        if cid and cid not in seen:
            seen.add(cid)
            discovered_cycles.append(cid)

    target_cycle = cycle_id if cycle_id else (discovered_cycles[0] if discovered_cycles else None)

    if not target_cycle:
        return {
            "cycle_id": None,
            "status": "idle",
            "started_at": None,
            "completed_at": None,
            "total_duration_ms": 0.0,
            "total_tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
            "available_cycles": [],
            "available_symbols": [],
            "selected_symbol": None,
            "nodes": [],
            "edges": [],
        }

    cycle_spans = [
        s for s in global_trace_store._spans
        if s.attributes.get("cycle_id") == target_cycle or s.trace_id == target_cycle or (s.kind == "cycle" and target_cycle in s.name)
    ]

    available_cycles = [
        {"cycle_id": cid, "label": f"Cycle #{cid.split('-')[-1] if '-' in cid else cid[:12]}", "status": "completed"}
        for cid in discovered_cycles
    ]

    def find_span(aliases: List[str]):
        for s in cycle_spans:
            if s.kind == "node":
                node_name = s.attributes.get("node_name") or s.name.replace("node:", "")
                if node_name in aliases or s.name in aliases or any(s.name == f"node:{a}" for a in aliases):
                    return s
        for s in cycle_spans:
            node_name = s.attributes.get("node_name") or s.name.replace("node:", "")
            if node_name in aliases or s.name in aliases or any(s.name == f"node:{a}" for a in aliases):
                return s
        return None

    # Identify node spans
    s_prefetch = find_span(["node:data_gathering", "data_gathering", "node:prefetch_data", "prefetch_data"])
    s_fund = find_span(["node:fundamental_analysis", "fundamental_analysis", "node:fundamental_brief", "fundamental_brief"])
    s_asset = find_span(["node:per_asset_analysis", "per_asset_analysis"])
    s_bull = find_span(["node:bull_advocate", "bull_advocate", "bull_thesis"])
    s_bear = find_span(["node:bear_dissent", "bear_dissent", "bear_thesis"])
    s_judge = find_span(["node:debate_judge", "debate_judge", "adjudicator", "node:debate", "debate"])
    s_reflect = find_span(["node:reflection", "reflection", "reflection_node"])
    s_risk = find_span(["node:risk_gate", "risk_gate"])
    s_exec = find_span(["node:execution", "execution"])

    span_map = {
        "prefetch_data": s_prefetch,
        "fundamental_brief": s_fund,
        "per_asset_analysis": s_asset,
        "bull_advocate": s_bull,
        "bear_dissent": s_bear,
        "debate_judge": s_judge,
        "reflection": s_reflect,
        "risk_gate": s_risk,
        "execution": s_exec,
    }

    # Discover available symbols
    symbol_set = set()
    if s_asset and s_asset.attributes.get("output_payload"):
        payload = s_asset.attributes.get("output_payload")
        if isinstance(payload, dict):
            if "per_asset" in payload and isinstance(payload["per_asset"], dict):
                symbol_set.update(payload["per_asset"].keys())
            if "symbols" in payload and isinstance(payload["symbols"], list):
                symbol_set.update(payload["symbols"])
    for s in cycle_spans:
        sym = s.attributes.get("symbol")
        if sym and isinstance(sym, str):
            symbol_set.add(sym.strip().upper())
        syms = s.attributes.get("symbols")
        if syms and isinstance(syms, list):
            for item in syms:
                if isinstance(item, str):
                    symbol_set.add(item.strip().upper())

    if not symbol_set:
        symbol_set.update(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])

    available_symbols = sorted(list(symbol_set))
    filter_sym = symbol.strip().upper() if symbol and symbol.strip().upper() in available_symbols else None

    # Check which nodes ran downstream
    node_sequence = [
        "prefetch_data",
        "fundamental_brief",
        "per_asset_analysis",
        "bull_advocate",
        "bear_dissent",
        "debate_judge",
        "reflection",
        "risk_gate",
        "execution",
    ]

    has_downstream_ran = {}
    downstream_active = False
    for nid in reversed(node_sequence):
        has_downstream_ran[nid] = downstream_active
        sp = span_map.get(nid)
        if sp is not None and sp.end_time:
            downstream_active = True

    has_running_node = any(s.kind in ("node", "cycle") and not s.end_time for s in cycle_spans)
    cycle_finished = (not has_running_node) and (
        any(s.kind == "cycle" and s.end_time for s in cycle_spans)
        or (s_exec is not None and bool(s_exec.end_time))
        or (s_risk is not None and s_risk.status == "ERROR" and bool(s_risk.end_time))
    )

    def get_node_tokens(node_id: str, node_span_obj, filter_sym_val: Optional[str] = None):
        if not node_span_obj:
            return {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0}

        in_tok = node_span_obj.attributes.get("input_tokens", 0)
        out_tok = node_span_obj.attributes.get("output_tokens", 0)
        cost = node_span_obj.attributes.get("cost_usd", 0.0)

        child_llm_spans = [
            s for s in cycle_spans
            if s.parent_span_id == node_span_obj.span_id and s.kind == "llm"
        ]

        if filter_sym_val and node_id in ("per_asset_analysis", "bull_advocate", "bear_dissent", "debate_judge"):
            payload = node_span_obj.attributes.get("output_payload")
            if isinstance(payload, dict):
                per_asset_info = payload.get("per_asset", {}).get(filter_sym_val)
                if isinstance(per_asset_info, dict) and "token_usage" in per_asset_info:
                    tu = per_asset_info["token_usage"]
                    if isinstance(tu, dict):
                        in_tok = int(tu.get("input_tokens", 0) or 0)
                        out_tok = int(tu.get("output_tokens", 0) or 0)
                        cost = float(tu.get("cost_usd", 0.0) or 0.0)

            sym_child = [s for s in child_llm_spans if s.attributes.get("symbol") == filter_sym_val]
            if sym_child:
                child_llm_spans = sym_child

        if child_llm_spans:
            child_in = sum(s.attributes.get("input_tokens", 0) for s in child_llm_spans)
            child_out = sum(s.attributes.get("output_tokens", 0) for s in child_llm_spans)
            child_cost = sum(s.attributes.get("cost_usd", 0.0) for s in child_llm_spans)
            if in_tok == 0 and out_tok == 0:
                in_tok, out_tok, cost = child_in, child_out, child_cost
            else:
                in_tok = max(in_tok, child_in)
                out_tok = max(out_tok, child_out)
                cost = max(cost, child_cost)

        total = in_tok + out_tok
        return {
            "input": in_tok,
            "output": out_tok,
            "total": total,
            "cost_usd": round(cost, 6)
        }

    def resolve_node(
        node_id: str,
        name: str,
        stage: str,
        span_obj,
    ):
        if not span_obj:
            if cycle_finished and (has_downstream_ran.get(node_id, False) or node_id in ("execution", "risk_gate")):
                skip_reason = f"Skipped in this cycle ({name})"
                if node_id in ("bull_advocate", "bear_dissent", "debate_judge"):
                    skip_reason = "Skipped: No actionable trades qualified for dialectic debate"
                elif node_id == "execution":
                    skip_reason = "Skipped: No trade proposals approved by Risk Gate"

                return {
                    "id": node_id,
                    "name": name,
                    "stage": stage,
                    "status": "skipped",
                    "duration_ms": 0.0,
                    "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                    "input_summary": skip_reason,
                    "output_payload": {"status": "skipped", "reason": skip_reason},
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                }

            return {
                "id": node_id,
                "name": name,
                "stage": stage,
                "status": "pending",
                "duration_ms": 0.0,
                "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                "input_summary": f"Pending {name} execution",
                "output_payload": None,
                "started_at": None,
                "completed_at": None,
                "error": None,
            }

        if span_obj.attributes.get("is_skipped") is True:
            status = "skipped"
        elif span_obj.status == "ERROR" or span_obj.error:
            status = "failed"
        elif not span_obj.end_time:
            status = "running"
        else:
            status = "done"

        duration = round(span_obj.duration_ms, 1) if span_obj.duration_ms else 0.0
        tokens = get_node_tokens(node_id, span_obj, filter_sym_val=filter_sym)
        input_sum = span_obj.attributes.get("input_summary") or f"{name} execution ({status})"
        output_data = span_obj.attributes.get("output_payload")

        if filter_sym and status == "done":
            if node_id == "per_asset_analysis" and isinstance(output_data, dict):
                per_asset_map = output_data.get("per_asset", {})
                if filter_sym in per_asset_map:
                    output_data = {
                        "symbol": filter_sym,
                        "data": per_asset_map[filter_sym],
                        "total_evaluated_assets": len(per_asset_map)
                    }
            elif node_id in ("bull_advocate", "bear_dissent", "debate_judge") and isinstance(output_data, dict):
                trades = output_data.get("actionable_trades", [])
                theses = output_data.get("asset_theses", {})
                sym_debated = (
                    any(t.get("symbol") == filter_sym or (isinstance(t, (list, tuple)) and t[0] == filter_sym) for t in trades)
                    or (filter_sym in theses)
                )
                if not sym_debated:
                    status = "skipped"
                    input_sum = f"Skipped: {filter_sym} did not meet confidence threshold for debate"
                    output_data = {"status": "skipped", "symbol": filter_sym, "reason": input_sum}
            elif node_id == "risk_gate" and isinstance(output_data, dict):
                evals = output_data.get("evaluated_trades", [])
                sym_evals = [t for t in evals if t.get("symbol") == filter_sym]
                if sym_evals:
                    output_data = {"symbol": filter_sym, "evaluated_trades": sym_evals}
                elif evals:
                    status = "skipped"
                    input_sum = f"Skipped: No trades evaluated for {filter_sym}"
                    output_data = {"status": "skipped", "symbol": filter_sym, "reason": input_sum}
            elif node_id == "execution" and isinstance(output_data, dict):
                execs = output_data.get("executed_orders", [])
                sym_execs = [o for o in execs if o.get("symbol") == filter_sym]
                if sym_execs:
                    output_data = {"symbol": filter_sym, "executed_orders": sym_execs}
                else:
                    status = "skipped"
                    input_sum = f"Skipped: No orders executed for {filter_sym}"
                    output_data = {"status": "skipped", "symbol": filter_sym, "reason": input_sum}

        if not output_data and status == "done":
            output_data = {"status": "completed", "node": node_id}

        return {
            "id": node_id,
            "name": name,
            "stage": stage,
            "status": status,
            "duration_ms": duration,
            "tokens": tokens,
            "input_summary": input_sum,
            "output_payload": output_data,
            "started_at": span_obj.start_time,
            "completed_at": span_obj.end_time,
            "error": span_obj.error,
        }

    nodes = [
        resolve_node("prefetch_data", "Prefetch Data", "prefetch", s_prefetch),
        resolve_node("fundamental_brief", "Fundamental Brief", "stage1", s_fund),
        resolve_node("per_asset_analysis", "Per-Asset Analysis", "stage2", s_asset),
        resolve_node("bull_advocate", "Bull Advocate", "debate", s_bull),
        resolve_node("bear_dissent", "Bear Dissent", "debate", s_bear),
        resolve_node("debate_judge", "Debate Judge", "debate", s_judge),
        resolve_node("reflection", "Reflection & Learning", "reflection", s_reflect),
        resolve_node("risk_gate", "Risk Gate", "risk", s_risk),
        resolve_node("execution", "Execution Service", "execution", s_exec),
    ]

    edges = [
        {"from": "prefetch_data", "to": "fundamental_brief"},
        {"from": "fundamental_brief", "to": "per_asset_analysis"},
        {"from": "per_asset_analysis", "to": "bull_advocate"},
        {"from": "per_asset_analysis", "to": "bear_dissent"},
        {"from": "bull_advocate", "to": "debate_judge"},
        {"from": "bear_dissent", "to": "debate_judge"},
        {"from": "debate_judge", "to": "reflection"},
        {"from": "reflection", "to": "risk_gate"},
        {"from": "risk_gate", "to": "execution"},
    ]

    total_duration = sum(n["duration_ms"] for n in nodes)
    total_tokens_in = sum(n["tokens"]["input"] for n in nodes)
    total_tokens_out = sum(n["tokens"]["output"] for n in nodes)
    total_cost = sum(n["tokens"]["cost_usd"] for n in nodes)

    statuses = [n["status"] for n in nodes]
    if "failed" in statuses:
        overall_status = "failed"
    elif "running" in statuses:
        overall_status = "running"
    elif all(st in ("done", "skipped") for st in statuses):
        overall_status = "completed"
    elif all(st == "pending" for st in statuses):
        overall_status = "pending"
    else:
        overall_status = "completed" if cycle_finished else "running"

    started_nodes = [n["started_at"] for n in nodes if n.get("started_at")]
    completed_nodes = [n["completed_at"] for n in nodes if n.get("completed_at")]

    started_at = started_nodes[0] if started_nodes else None
    completed_at = completed_nodes[-1] if (overall_status in ("completed", "failed") and completed_nodes) else None

    if target_cycle and not any(c["cycle_id"] == target_cycle for c in available_cycles):
        available_cycles.insert(0, {
            "cycle_id": target_cycle,
            "label": f"Cycle #{target_cycle.split('-')[-1] if '-' in target_cycle else target_cycle[:12]}",
            "status": overall_status
        })

    return {
        "cycle_id": target_cycle,
        "status": overall_status,
        "started_at": started_at,
        "completed_at": completed_at,
        "total_duration_ms": round(total_duration, 1),
        "total_tokens": {
            "input": total_tokens_in,
            "output": total_tokens_out,
            "total": total_tokens_in + total_tokens_out,
            "cost_usd": round(total_cost, 6),
        },
        "available_cycles": available_cycles,
        "available_symbols": available_symbols,
        "selected_symbol": filter_sym,
        "nodes": nodes,
        "edges": edges,
    }


@observability_router.get("/api/traces/cycle/{cycle_id}", tags=["Observability"])
async def get_cycle_trace_summary(cycle_id: str, symbol: Optional[str] = Query(None)):
    """Retrieve aggregate telemetry and trace spans for a cycle."""
    from logging_observability.tracing.exporters import global_trace_store
    summary = global_trace_store.get_cycle_summary(cycle_id)
    spans = global_trace_store.get_spans(limit=500, cycle_id=cycle_id)
    graph_state = _build_graph_state_for_cycle(cycle_id, symbol=symbol)
    return {"cycle_id": cycle_id, "summary": summary, "spans": spans, "graph_state": graph_state}


@observability_router.get("/api/observability/graph-state", tags=["Observability"])
async def get_graph_state(
    cycle_id: Optional[str] = Query(None, description="Filter graph state by cycle_id. Defaults to latest cycle."),
    symbol: Optional[str] = Query(None, description="Filter graph state and token/trade breakdown by asset symbol.")
):
    """
    Retrieve topology, execution status, latencies, tokens, and payloads
    for the LangGraph multi-agent pipeline visualizer.
    """
    return _build_graph_state_for_cycle(cycle_id, symbol=symbol)


# ---------------------------------------------------------------------------
# Advanced Observability Endpoints (Phase 5.2 - IMPROVEMENT-2)
# ---------------------------------------------------------------------------

@observability_router.get("/api/observability/playbook-tree", tags=["Observability"])
async def get_playbook_tree():
    """
    Visualisasi grafik pohon turunan playbook dari MicroPlaybookCompiler.
    Menggabungkan playbook di database (PlaybookRuleAttribution) dan file sistem (skills/trading/playbooks/).
    """
    from database.db import get_session
    from database.models import PlaybookRuleAttribution
    from sqlalchemy import select

    root = {
        "name": "Trading Playbooks",
        "type": "root",
        "children": []
    }
    symbols_map: Dict[str, Dict[str, Any]] = {}

    try:
        async with get_session() as session:
            rows = (await session.execute(
                select(PlaybookRuleAttribution).order_by(PlaybookRuleAttribution.symbol, PlaybookRuleAttribution.promoted_at.desc())
            )).scalars().all()
            for r in rows:
                sym = r.symbol or "GLOBAL"
                if sym not in symbols_map:
                    symbols_map[sym] = {"name": sym, "type": "symbol", "children": []}
                symbols_map[sym]["children"].append({
                    "id": r.id,
                    "name": f"Rule-{r.rule_hash[:8]}",
                    "status": r.status,
                    "rule_text": r.rule_text,
                    "times_triggered": r.times_triggered,
                    "wins_count": r.wins_count,
                    "losses_count": r.losses_count,
                    "win_rate": r.win_rate,
                    "total_pnl": r.total_pnl,
                    "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
                })
    except Exception as e:
        logger.debug(f"Failed to load DB playbooks for tree: {e}")

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    playbooks_dir = base_dir / "skills" / "trading" / "playbooks"
    if playbooks_dir.exists():
        for f in list(playbooks_dir.glob("*.md")) + list(playbooks_dir.glob("*/SKILL.md")):
            name = f.parent.name if f.name == "SKILL.md" else f.name
            sym = "GENERIC"
            for part in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD"]:
                if part.lower() in name.lower():
                    sym = part
                    break
            if sym not in symbols_map:
                symbols_map[sym] = {"name": sym, "type": "symbol", "children": []}
            is_stale = False
            try:
                content = f.read_text(encoding="utf-8")
                is_stale = "[STATUS: STALE]" in content
            except Exception:
                pass
            symbols_map[sym]["children"].append({
                "name": name,
                "status": "stale" if is_stale else "active",
                "source": "file",
                "path": str(f.relative_to(base_dir)),
            })
        archive_dir = playbooks_dir / "archive"
        if archive_dir.exists():
            for f in archive_dir.glob("*.md"):
                sym = "ARCHIVE"
                if sym not in symbols_map:
                    symbols_map[sym] = {"name": sym, "type": "symbol", "children": []}
                symbols_map[sym]["children"].append({
                    "name": f.name,
                    "status": "archived",
                    "source": "file_archive",
                })

    root["children"] = list(symbols_map.values())
    return root


@observability_router.get("/api/observability/prompt-cache-metrics", tags=["Observability"])
async def get_prompt_cache_metrics(limit: int = Query(20, ge=1, le=100)):
    """
    Grafik metrik prompt cache hit rate vs miss rate per siklus.
    Mengambil data dari TokenUsageLog.
    """
    from database.db import get_session
    from database.models import TokenUsageLog
    from sqlalchemy import select, desc

    cycles: List[Dict[str, Any]] = []
    total_cached = 0
    total_input = 0
    total_creation = 0

    try:
        async with get_session() as session:
            rows = (await session.execute(
                select(TokenUsageLog)
                .order_by(desc(TokenUsageLog.timestamp))
                .limit(limit * 10)
            )).scalars().all()

            cycle_groups: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                cid = r.cycle_id or (r.timestamp.strftime("%Y-%m-%d %H:%M") if r.timestamp else "default")
                if cid not in cycle_groups:
                    cycle_groups[cid] = {
                        "cycle_id": cid,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                        "cached_tokens": 0,
                        "input_tokens": 0,
                        "cache_creation_tokens": 0,
                        "output_tokens": 0,
                        "requests": 0,
                    }
                grp = cycle_groups[cid]
                c_tok = r.cached_tokens or 0
                i_tok = r.input_tokens or 0
                cr_tok = r.cache_creation_tokens or 0
                grp["cached_tokens"] += c_tok
                grp["input_tokens"] += i_tok
                grp["cache_creation_tokens"] += cr_tok
                grp["output_tokens"] += (r.output_tokens or 0)
                grp["requests"] += 1
                total_cached += c_tok
                total_input += i_tok
                total_creation += cr_tok

            for cid, grp in list(cycle_groups.items())[:limit]:
                inp = grp["input_tokens"]
                cached = grp["cached_tokens"]
                hit_rate = round((cached / inp * 100), 2) if inp > 0 else 0.0
                grp["hit_rate_pct"] = hit_rate
                cycles.append(grp)
    except Exception as e:
        logger.debug(f"Failed to fetch prompt cache metrics: {e}")

    overall_hit_rate = round((total_cached / total_input * 100), 2) if total_input > 0 else 0.0
    return {
        "overall_hit_rate_pct": overall_hit_rate,
        "total_cached_tokens": total_cached,
        "total_input_tokens": total_input,
        "total_cache_creation_tokens": total_creation,
        "cycles": cycles,
    }


@observability_router.get("/api/observability/tool-latencies", tags=["Observability"])
async def get_tool_latencies():
    """
    Histogram dan distribusi latensi eksekusi tool handler.
    Mengambil data dari global_trace_store spans dengan kind='tool'.
    """
    from logging_observability.tracing.exporters import global_trace_store

    tool_spans = global_trace_store.get_spans(limit=1000, kind="tool")
    stats_by_tool: Dict[str, Dict[str, Any]] = {}

    for s in tool_spans:
        tname = s.get("name") or s.get("attributes", {}).get("tool.name") or "unknown_tool"
        duration = s.get("duration_ms", 0.0)
        if tname not in stats_by_tool:
            stats_by_tool[tname] = {
                "tool_name": tname,
                "count": 0,
                "durations": [],
                "buckets": {
                    "<50ms": 0,
                    "50-200ms": 0,
                    "200-500ms": 0,
                    "500-1000ms": 0,
                    ">1000ms": 0,
                }
            }
        rec = stats_by_tool[tname]
        rec["count"] += 1
        rec["durations"].append(duration)
        if duration < 50:
            rec["buckets"]["<50ms"] += 1
        elif duration < 200:
            rec["buckets"]["50-200ms"] += 1
        elif duration < 500:
            rec["buckets"]["200-500ms"] += 1
        elif duration < 1000:
            rec["buckets"]["500-1000ms"] += 1
        else:
            rec["buckets"][">1000ms"] += 1

    summary: List[Dict[str, Any]] = []
    for tname, data in stats_by_tool.items():
        durations = sorted(data["durations"])
        cnt = data["count"]
        p50 = durations[int(cnt * 0.5)] if cnt else 0.0
        p90 = durations[int(cnt * 0.9)] if cnt else 0.0
        p99 = durations[int(cnt * 0.99)] if cnt else 0.0
        avg = round(sum(durations) / cnt, 2) if cnt else 0.0
        summary.append({
            "tool_name": tname,
            "call_count": cnt,
            "avg_ms": avg,
            "p50_ms": round(p50, 2),
            "p90_ms": round(p90, 2),
            "p99_ms": round(p99, 2),
            "buckets": data["buckets"],
        })

    summary.sort(key=lambda x: x["call_count"], reverse=True)
    return {
        "total_tool_calls": len(tool_spans),
        "tools": summary,
    }


@observability_router.get("/api/observability/trajectories", tags=["Observability"])
async def get_trade_trajectories(limit: int = Query(50, ge=1, le=500)):
    """
    Retrieve logged trade decision trajectories from TradeTrajectoryLogger JSONL logs.
    """
    from benchmark.trade_trajectory_logger import TradeTrajectoryLogger
    logger_inst = TradeTrajectoryLogger()
    records = logger_inst.load_recent_trajectories(limit=limit)
    return {
        "total": len(records),
        "trajectories": records,
    }


@observability_router.get("/api/observability/cycles/{cycle_id}/lineage", tags=["Observability"])
async def get_cycle_decision_lineage(cycle_id: str, target_seq: Optional[int] = Query(None)):
    """
    Retrieve decision lineage and SHA-256 chain integrity for a trading cycle from TradingCycleEventLog.
    """
    from logging_observability.trading_cycle_event_log import get_cycle_event_log
    event_log = get_cycle_event_log()
    reconstruction = event_log.reconstruct_cycle(cycle_id)
    is_valid, reason = event_log.verify_cycle_integrity(cycle_id)
    lineage = []
    if target_seq is not None:
        raw_lineage = event_log.trace_decision_lineage(cycle_id, target_seq)
        lineage = [e.to_dict() for e in raw_lineage]

    return {
        "cycle_id": cycle_id,
        "integrity_valid": is_valid,
        "integrity_error": reason,
        "total_events": reconstruction.get("total_events", 0),
        "events": reconstruction.get("events", []),
        "lineage": lineage,
        "start_time": reconstruction.get("start_time"),
        "end_time": reconstruction.get("end_time"),
    }

