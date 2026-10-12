# ==============================================================================
# File: agent/moa_trace.py
# ==============================================================================

"""
Full MoA Turn Trace Persistence and Observability.

Appends structured JSON Lines records to a dedicated trace directory for every MoA run.
Stores full proposer outputs, aggregator synthesis, model names, latency, and token metrics.
Enables transparent inspection, retrospective auditing, and trajectory export.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default directory for MoA trace logs
DEFAULT_MOA_TRACE_DIR = Path("moa-traces")


def _sanitize_session_id(session_id: Optional[str]) -> str:
    """Sanitize session ID for safe file name generation."""
    if not session_id:
        return "default_session"
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(session_id))


def get_moa_trace_dir(custom_dir: Optional[str | Path] = None) -> Path:
    """Resolve active MoA trace directory."""
    if custom_dir:
        p = Path(os.path.expandvars(os.path.expanduser(str(custom_dir))))
    else:
        p = DEFAULT_MOA_TRACE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def slot_metrics(
    slot_info: Dict[str, Any],
    label: str,
    output: Optional[str] = None,
    usage: Optional[Dict[str, int]] = None,
    latency_ms: float = 0.0,
    cost_usd: Optional[float] = None,
    is_failed: bool = False,
) -> Dict[str, Any]:
    """Format single proposer or aggregator metrics dictionary."""
    return {
        "label": label,
        "model": slot_info.get("model", "unknown"),
        "provider": slot_info.get("provider", "unknown"),
        "temperature": slot_info.get("temperature"),
        "output": output,
        "usage": usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "latency_ms": round(latency_ms, 2),
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        "is_failed": is_failed,
    }


def save_moa_turn(
    *,
    session_id: Optional[str],
    preset_name: str,
    proposer_traces: List[Dict[str, Any]],
    aggregator_trace: Dict[str, Any],
    user_prompt: str,
    total_latency_ms: float,
    trace_dir: Optional[str | Path] = None,
) -> Optional[Path]:
    """
    Append one complete MoA turn record to <trace_dir>/<session_id>.jsonl.
    Swallows I/O exceptions defensively to guarantee zero-crash execution in production.
    """
    try:
        base_dir = get_moa_trace_dir(trace_dir)
        clean_sid = _sanitize_session_id(session_id)
        file_path = base_dir / f"{clean_sid}.jsonl"

        total_cost = 0.0
        for pt in proposer_traces:
            if pt.get("cost_usd"):
                total_cost += pt["cost_usd"]
        if aggregator_trace.get("cost_usd"):
            total_cost += aggregator_trace["cost_usd"]

        record = {
            "timestamp": time.time(),
            "datetime_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_id": clean_sid,
            "preset_name": preset_name,
            "user_prompt": user_prompt,
            "proposers": proposer_traces,
            "aggregator": aggregator_trace,
            "total_latency_ms": round(total_latency_ms, 2),
            "total_cost_usd": round(total_cost, 6),
        }

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return file_path
    except Exception as exc:
        logger.warning("Failed to save MoA trace: %s", exc)
        return None


def get_trace_history(
    session_id: str,
    limit: int = 50,
    trace_dir: Optional[str | Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve historical MoA trace turns for a session in reverse chronological order."""
    base_dir = get_moa_trace_dir(trace_dir)
    clean_sid = _sanitize_session_id(session_id)
    file_path = base_dir / f"{clean_sid}.jsonl"
    if not file_path.exists():
        return []

    records = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return list(reversed(records[-limit:]))
    except Exception as exc:
        logger.warning("Failed to read MoA traces for %s: %s", session_id, exc)
        return []
