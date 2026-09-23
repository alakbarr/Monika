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


def _build_graph_state_for_cycle(cycle_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Constructs the LangGraph DAG topology state with node statuses, execution durations,
    token consumption, inputs, and payloads for the frontend visualizer.
    """
    from logging_observability.tracing.exporters import global_trace_store

    discovered_cycles = []
    seen = set()
    for s in reversed(global_trace_store._spans):
        cid = s.attributes.get("cycle_id") or (s.name.split("cycle:")[-1] if s.kind == "cycle" and ":" in s.name else None)
        if cid and cid not in seen:
            seen.add(cid)
            discovered_cycles.append(cid)

    target_cycle = cycle_id if cycle_id else (discovered_cycles[0] if discovered_cycles else "cycle-live-847")

    cycle_spans = [
        s for s in global_trace_store._spans
        if s.attributes.get("cycle_id") == target_cycle or s.trace_id == target_cycle or (s.kind == "cycle" and target_cycle in s.name)
    ]

    is_synthetic = (target_cycle in ("cycle-live-847", "cycle-hist-846")) and not cycle_spans

    available_cycles = [
        {"cycle_id": cid, "label": f"Cycle #{cid.split('-')[-1] if '-' in cid else cid[:12]}", "status": "completed"}
        for cid in discovered_cycles
    ]
    if not available_cycles:
        available_cycles = [
            {"cycle_id": "cycle-live-847", "label": "Cycle #847 (Live)", "status": "completed"},
            {"cycle_id": "cycle-hist-846", "label": "Cycle #846 (Archived)", "status": "completed"},
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

    def get_node_tokens(node_span_obj, default_in=0, default_out=0, default_cost=0.0):
        if not node_span_obj:
            if is_synthetic:
                return {"input": default_in, "output": default_out, "total": default_in + default_out, "cost_usd": default_cost}
            return {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0}
        in_tok = node_span_obj.attributes.get("input_tokens", 0)
        out_tok = node_span_obj.attributes.get("output_tokens", 0)
        cost = node_span_obj.attributes.get("cost_usd", 0.0)
        for s in cycle_spans:
            if s.parent_span_id == node_span_obj.span_id and s.kind == "llm":
                in_tok += s.attributes.get("input_tokens", 0)
                out_tok += s.attributes.get("output_tokens", 0)
                cost += s.attributes.get("cost_usd", 0.0)
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
        mock_duration: float,
        mock_in: int,
        mock_out: int,
        mock_cost: float,
        mock_summary: str,
        mock_payload: Any
    ):
        if is_synthetic:
            return {
                "id": node_id,
                "name": name,
                "stage": stage,
                "status": "done",
                "duration_ms": mock_duration,
                "tokens": {"input": mock_in, "output": mock_out, "total": mock_in + mock_out, "cost_usd": mock_cost},
                "input_summary": mock_summary,
                "output_payload": mock_payload,
                "started_at": "2026-09-14T02:00:00Z",
                "completed_at": "2026-09-14T02:00:05Z",
                "error": None,
            }

        if not span_obj:
            return {
                "id": node_id,
                "name": name,
                "stage": stage,
                "status": "pending",
                "duration_ms": 0.0,
                "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                "input_summary": "Pending execution in pipeline",
                "output_payload": None,
                "started_at": None,
                "completed_at": None,
                "error": None,
            }

        if span_obj.status == "ERROR" or span_obj.error:
            status = "failed"
        elif not span_obj.end_time:
            status = "running"
        else:
            status = "done"

        duration = round(span_obj.duration_ms, 1) if span_obj.duration_ms else 0.0
        tokens = get_node_tokens(span_obj)
        input_sum = span_obj.attributes.get("input_summary") or f"{name} execution ({status})"
        output_data = span_obj.attributes.get("output_payload")
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

    s_fund = find_span(["node:fundamental_analysis", "fundamental_analysis", "node:fundamental_brief", "fundamental_brief"])
    s_prefetch = find_span(["node:data_gathering", "data_gathering", "node:prefetch_data", "prefetch_data"])
    s_bull = find_span(["node:bull_advocate", "bull_advocate", "bull_thesis"])
    s_bear = find_span(["node:bear_dissent", "bear_dissent", "bear_thesis"])
    s_judge = find_span(["node:debate_judge", "debate_judge", "adjudicator", "node:debate", "debate"])
    s_risk = find_span(["node:risk_gate", "risk_gate"])
    s_exec = find_span(["node:execution", "execution"])

    nodes = [
        resolve_node(
            "fundamental_brief", "Fundamental Brief", "stage1", s_fund,
            3420.0, 12500, 2100, 0.0146,
            "Macro calendar, yield curves, DXY momentum, and COT positioning feeds",
            {
                "macro_bias": "BULLISH_EUR",
                "dxy_trend": "bearish",
                "vix": 14.2,
                "regime": "Risk-On Expansion",
                "confidence": 0.82
            }
        ),
        resolve_node(
            "prefetch_data", "Prefetch Data", "prefetch", s_prefetch,
            1180.0, 0, 0, 0.0,
            "Watchlist: EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD (OHLCV M15/H1)",
            {
                "symbols_fetched": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
                "candles_count": 2400,
                "freshness_ms": 250,
                "cache_hit": True
            }
        ),
        resolve_node(
            "bull_advocate", "Bull Advocate", "debate", s_bull,
            2850.0, 9800, 1850, 0.0116,
            "Technical EMA-50 breakout, liquidity sweep absorption, positive DXY beta",
            {
                "thesis": "Bullish momentum established above 1.0850 support with institutional orderbook absorption.",
                "conviction_score": 84.0,
                "target_price": 1.092,
                "upside_catalysts": ["Orderbook buy imbalance +18%", "DXY downward break"]
            }
        ),
        resolve_node(
            "bear_dissent", "Bear Dissent", "debate", s_bear,
            2720.0, 9600, 1720, 0.0113,
            "H4 RSI bearish divergence, overhead supply pool at 1.0890, Fed speaker risk",
            {
                "counter_thesis": "Potential bull trap near major sell-side liquidity pool with hidden RSI divergence.",
                "conviction_score": 48.0,
                "invalidation_level": 1.0815,
                "downside_risks": ["Hawkish Fed commentary", "Overbought M15 oscillator"]
            }
        ),
        resolve_node(
            "debate_judge", "Debate Judge", "debate", s_judge,
            3150.0, 13300, 2750, 0.016,
            "Synthesis of Bull Advocate vs Bear Dissent arguments with playbook matching",
            {
                "verdict": "BUY",
                "confidence": 78.5,
                "edge_score": 2.4,
                "reasoning": "Macro risk-on regime and DXY weakness dominate technical divergence. Asymmetric upside.",
                "stop_loss": 1.082,
                "take_profit": 1.091,
                "risk_reward_ratio": 2.35
            }
        ),
        resolve_node(
            "risk_gate", "Risk Gate", "risk", s_risk,
            420.0, 0, 0, 0.0,
            "Portfolio VAR check, daily drawdown limit, correlation matrix, max lot limits",
            {
                "passed": True,
                "daily_drawdown_current": 0.85,
                "max_allowed_daily_dd": 3.0,
                "adjusted_lot": 0.02,
                "correlation_check": "passed",
                "status_message": "Cleared risk gate: Trade size sized to 1.0% equity risk"
            }
        ),
        resolve_node(
            "execution", "Execution", "execution", s_exec,
            820.0, 0, 0, 0.0,
            "Order dispatch: BUY EURUSD 0.02 lots via MT5 execution service / Paper broker",
            {
                "ticket": 4829103,
                "symbol": "EURUSD",
                "action": "BUY",
                "lot": 0.02,
                "price": 1.08472,
                "status": "FILLED",
                "mode": "paper",
                "latency_ms": 138.5
            }
        ),
    ]

    edges = [
        {"from": "fundamental_brief", "to": "prefetch_data"},
        {"from": "prefetch_data", "to": "bull_advocate"},
        {"from": "prefetch_data", "to": "bear_dissent"},
        {"from": "bull_advocate", "to": "debate_judge"},
        {"from": "bear_dissent", "to": "debate_judge"},
        {"from": "debate_judge", "to": "risk_gate"},
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
    elif any(st == "done" for st in statuses) and any(st == "pending" for st in statuses):
        overall_status = "running"
    elif all(st == "pending" for st in statuses):
        overall_status = "pending"
    else:
        overall_status = "completed"

    started_nodes = [n["started_at"] for n in nodes if n.get("started_at")]
    completed_nodes = [n["completed_at"] for n in nodes if n.get("completed_at")]

    started_at = started_nodes[0] if started_nodes else None
    completed_at = completed_nodes[-1] if (overall_status in ("completed", "failed") and completed_nodes) else None

    if target_cycle and not is_synthetic and not any(c["cycle_id"] == target_cycle for c in available_cycles):
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
        "nodes": nodes,
        "edges": edges,
    }


@observability_router.get("/api/traces/cycle/{cycle_id}", tags=["Observability"])
async def get_cycle_trace_summary(cycle_id: str):
    """Retrieve aggregate telemetry and trace spans for a cycle."""
    from logging_observability.tracing.exporters import global_trace_store
    summary = global_trace_store.get_cycle_summary(cycle_id)
    spans = global_trace_store.get_spans(limit=500, cycle_id=cycle_id)
    graph_state = _build_graph_state_for_cycle(cycle_id)
    return {"cycle_id": cycle_id, "summary": summary, "spans": spans, "graph_state": graph_state}


@observability_router.get("/api/observability/graph-state", tags=["Observability"])
async def get_graph_state(
    cycle_id: Optional[str] = Query(None, description="Filter graph state by cycle_id. Defaults to latest cycle.")
):
    """
    Retrieve topology, execution status, latencies, tokens, and payloads
    for the LangGraph multi-agent pipeline visualizer.
    """
    return _build_graph_state_for_cycle(cycle_id)


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
        for f in playbooks_dir.glob("*.md"):
            name = f.name
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

