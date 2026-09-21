"""
Token Auditor Service — Layanan audit analitik konsumsi token AI multi-dimensi.
Menyediakan agregasi per task role, subsystem, symbol, model/provider, dan cycle trace.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, desc, case

from database.db import get_session
from database.models import TokenUsageLog

logger = logging.getLogger("TradingAgent.TokenAuditor")


class TokenAuditor:
    """Layanan audit komprehensif untuk melacak dan menganalisis konsumsi token AI."""

    @staticmethod
    async def get_summary(hours: int = 24) -> Dict[str, Any]:
        """Mengembalikan ringkasan global konsumsi token dan estimasi biaya."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            stmt = (
                select(
                    func.count(TokenUsageLog.id).label("total_calls"),
                    func.coalesce(func.sum(TokenUsageLog.input_tokens), 0).label("sum_input"),
                    func.coalesce(func.sum(TokenUsageLog.output_tokens), 0).label("sum_output"),
                    func.coalesce(func.sum(TokenUsageLog.thinking_tokens), 0).label("sum_thinking"),
                    func.coalesce(func.sum(TokenUsageLog.total_tokens), 0).label("sum_total"),
                    func.coalesce(func.sum(TokenUsageLog.cached_tokens), 0).label("sum_cached"),
                    func.coalesce(func.sum(TokenUsageLog.cache_creation_tokens), 0).label("sum_cache_creation"),
                    func.coalesce(func.sum(TokenUsageLog.cost_estimate), 0.0).label("sum_cost"),
                    func.coalesce(func.avg(TokenUsageLog.execution_time_ms), 0).label("avg_latency_ms"),
                    func.sum(case((TokenUsageLog.status == "success", 1), else_=0)).label("success_count"),
                    func.sum(case((TokenUsageLog.slot_name != "primary", 1), else_=0)).label("fallback_count"),
                    func.sum(case((TokenUsageLog.status == "rate_limited", 1), else_=0)).label("rate_limit_count"),
                    func.sum(case((TokenUsageLog.status == "error", 1), else_=0)).label("error_count"),
                )
                .where(TokenUsageLog.timestamp >= since)
            )
            row = (await session.execute(stmt)).first()
            if not row or not row.total_calls:
                return {
                    "time_window_hours": hours,
                    "total_calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "thinking_tokens": 0,
                    "pure_content_tokens": 0,
                    "thinking_pct_of_output": 0.0,
                    "total_tokens": 0,
                    "cached_tokens": 0,
                    "cache_creation_tokens": 0,
                    "cache_hit_rate_pct": 0.0,
                    "total_cost_usd": 0.0,
                    "avg_latency_ms": 0.0,
                    "success_count": 0,
                    "fallback_count": 0,
                    "rate_limit_count": 0,
                    "error_count": 0,
                }

            sum_in = int(row.sum_input)
            sum_out = int(row.sum_output)
            sum_thinking = int(row.sum_thinking)
            sum_cached = int(row.sum_cached)
            cache_hit_rate = round((sum_cached / sum_in * 100.0), 2) if sum_in > 0 else 0.0
            pure_content = max(0, sum_out - sum_thinking)
            thinking_pct = round((sum_thinking / sum_out * 100.0), 2) if sum_out > 0 else 0.0

            return {
                "time_window_hours": hours,
                "total_calls": int(row.total_calls),
                "input_tokens": sum_in,
                "output_tokens": sum_out,
                "thinking_tokens": sum_thinking,
                "pure_content_tokens": pure_content,
                "thinking_pct_of_output": thinking_pct,
                "total_tokens": int(row.sum_total),
                "cached_tokens": sum_cached,
                "cache_creation_tokens": int(row.sum_cache_creation),
                "cache_hit_rate_pct": cache_hit_rate,
                "total_cost_usd": round(float(row.sum_cost), 6),
                "avg_latency_ms": round(float(row.avg_latency_ms), 1),
                "success_count": int(row.success_count or 0),
                "fallback_count": int(row.fallback_count or 0),
                "rate_limit_count": int(row.rate_limit_count or 0),
                "error_count": int(row.error_count or 0),
            }

    @staticmethod
    async def get_role_breakdown(hours: int = 24) -> List[Dict[str, Any]]:
        """Mengembalikan rincian konsumsi token yang dikelompokkan per task role."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            effective_role = func.coalesce(TokenUsageLog.task_role, TokenUsageLog.task_name)
            stmt = (
                select(
                    effective_role.label("task_role"),
                    TokenUsageLog.subsystem,
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.avg(TokenUsageLog.input_tokens).label("avg_in"),
                    func.avg(TokenUsageLog.output_tokens).label("avg_out"),
                    func.avg(TokenUsageLog.thinking_tokens).label("avg_thinking"),
                    func.avg(TokenUsageLog.total_tokens).label("avg_total"),
                    func.sum(TokenUsageLog.output_tokens).label("sum_out"),
                    func.sum(TokenUsageLog.thinking_tokens).label("sum_thinking"),
                    func.sum(TokenUsageLog.total_tokens).label("sum_total"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                    func.sum(TokenUsageLog.cost_estimate).label("sum_cost"),
                    func.avg(TokenUsageLog.execution_time_ms).label("avg_latency_ms"),
                    func.sum(case((TokenUsageLog.slot_name != "primary", 1), else_=0)).label("fallback_count")
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(effective_role, TokenUsageLog.subsystem)
                .order_by(func.sum(TokenUsageLog.total_tokens).desc())
            )
            rows = (await session.execute(stmt)).all()
            results = []
            for r in rows:
                m = dict(r._mapping)
                sum_out = int(m["sum_out"] or 0)
                sum_thinking = int(m["sum_thinking"] or 0)
                thinking_pct = round((sum_thinking / sum_out * 100.0), 2) if sum_out > 0 else 0.0
                results.append({
                    "task_role": m["task_role"],
                    "subsystem": m["subsystem"] or "system",
                    "calls": m["call_count"],
                    "avg_input": round(float(m["avg_in"]), 1) if m["avg_in"] else 0.0,
                    "avg_output": round(float(m["avg_out"]), 1) if m["avg_out"] else 0.0,
                    "avg_thinking": round(float(m["avg_thinking"]), 1) if m["avg_thinking"] else 0.0,
                    "sum_thinking": sum_thinking,
                    "thinking_pct": thinking_pct,
                    "avg_total": round(float(m["avg_total"]), 1) if m["avg_total"] else 0.0,
                    "sum_total": int(m["sum_total"] or 0),
                    "sum_cached": int(m["sum_cached"] or 0),
                    "sum_cost_usd": round(float(m["sum_cost"]), 6) if m["sum_cost"] else 0.0,
                    "avg_latency_ms": round(float(m["avg_latency_ms"]), 1) if m["avg_latency_ms"] else 0.0,
                    "fallback_calls": int(m["fallback_count"] or 0),
                })
            return results

    @staticmethod
    async def get_subsystem_breakdown(hours: int = 24) -> List[Dict[str, Any]]:
        """Mengembalikan rincian konsumsi token per kategori subsistem."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            effective_subsystem = func.coalesce(TokenUsageLog.subsystem, "system")
            stmt = (
                select(
                    effective_subsystem.label("subsystem"),
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.sum(TokenUsageLog.input_tokens).label("sum_input"),
                    func.sum(TokenUsageLog.output_tokens).label("sum_output"),
                    func.sum(TokenUsageLog.thinking_tokens).label("sum_thinking"),
                    func.sum(TokenUsageLog.total_tokens).label("sum_total"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                    func.sum(TokenUsageLog.cost_estimate).label("sum_cost"),
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(effective_subsystem)
                .order_by(func.sum(TokenUsageLog.total_tokens).desc())
            )
            rows = (await session.execute(stmt)).all()
            
            total_tokens_all = sum(int(r._mapping["sum_total"] or 0) for r in rows)
            total_cost_all = sum(float(r._mapping["sum_cost"] or 0.0) for r in rows)

            results = []
            for r in rows:
                m = dict(r._mapping)
                sum_total = int(m["sum_total"] or 0)
                sum_cost = float(m["sum_cost"] or 0.0)
                pct_tokens = round((sum_total / total_tokens_all * 100.0), 2) if total_tokens_all > 0 else 0.0
                pct_cost = round((sum_cost / total_cost_all * 100.0), 2) if total_cost_all > 0 else 0.0
                results.append({
                    "subsystem": m["subsystem"],
                    "calls": m["call_count"],
                    "sum_input": int(m["sum_input"] or 0),
                    "sum_output": int(m["sum_output"] or 0),
                    "sum_thinking": int(m["sum_thinking"] or 0),
                    "sum_total": sum_total,
                    "sum_cached": int(m["sum_cached"] or 0),
                    "sum_cost_usd": round(sum_cost, 6),
                    "pct_tokens": pct_tokens,
                    "pct_cost": pct_cost,
                })
            return results

    @staticmethod
    async def get_symbol_breakdown(hours: int = 24) -> List[Dict[str, Any]]:
        """Mengembalikan rincian konsumsi token per instrumen aset / simbol."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            effective_symbol = func.coalesce(TokenUsageLog.symbol, "GLOBAL_MACRO")
            stmt = (
                select(
                    effective_symbol.label("symbol"),
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.sum(TokenUsageLog.total_tokens).label("sum_total"),
                    func.sum(TokenUsageLog.thinking_tokens).label("sum_thinking"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                    func.sum(TokenUsageLog.cost_estimate).label("sum_cost"),
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(effective_symbol)
                .order_by(func.sum(TokenUsageLog.total_tokens).desc())
            )
            rows = (await session.execute(stmt)).all()
            results = []
            for r in rows:
                m = dict(r._mapping)
                results.append({
                    "symbol": m["symbol"],
                    "calls": m["call_count"],
                    "sum_total": int(m["sum_total"] or 0),
                    "sum_thinking": int(m["sum_thinking"] or 0),
                    "sum_cached": int(m["sum_cached"] or 0),
                    "sum_cost_usd": round(float(m["sum_cost"]), 6) if m["sum_cost"] else 0.0,
                })
            return results

    @staticmethod
    async def get_provider_breakdown(hours: int = 24) -> List[Dict[str, Any]]:
        """Mengembalikan rincian utilisasi per provider & model AI."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            stmt = (
                select(
                    TokenUsageLog.provider,
                    TokenUsageLog.model_name,
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.sum(TokenUsageLog.input_tokens).label("sum_input"),
                    func.sum(TokenUsageLog.output_tokens).label("sum_output"),
                    func.sum(TokenUsageLog.thinking_tokens).label("sum_thinking"),
                    func.sum(TokenUsageLog.total_tokens).label("sum_total"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                    func.sum(TokenUsageLog.cost_estimate).label("sum_cost"),
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(TokenUsageLog.provider, TokenUsageLog.model_name)
                .order_by(func.sum(TokenUsageLog.total_tokens).desc())
            )
            rows = (await session.execute(stmt)).all()
            results = []
            for r in rows:
                m = dict(r._mapping)
                results.append({
                    "provider": m["provider"],
                    "model_name": m["model_name"],
                    "calls": m["call_count"],
                    "sum_input": int(m["sum_input"] or 0),
                    "sum_output": int(m["sum_output"] or 0),
                    "sum_thinking": int(m["sum_thinking"] or 0),
                    "sum_total": int(m["sum_total"] or 0),
                    "sum_cached": int(m["sum_cached"] or 0),
                    "sum_cost_usd": round(float(m["sum_cost"]), 6) if m["sum_cost"] else 0.0,
                })
            return results

    @staticmethod
    async def get_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
        """Mengambil record log token terbaru dengan metadata lengkap."""
        async with get_session() as session:
            stmt = (
                select(TokenUsageLog)
                .order_by(desc(TokenUsageLog.timestamp))
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "provider": log.provider,
                    "model_name": log.model_name,
                    "task_name": log.task_name,
                    "task_role": log.task_role,
                    "subsystem": log.subsystem,
                    "symbol": log.symbol,
                    "cycle_id": log.cycle_id,
                    "input_tokens": log.input_tokens,
                    "output_tokens": log.output_tokens,
                    "thinking_tokens": log.thinking_tokens,
                    "total_tokens": log.total_tokens,
                    "cached_tokens": log.cached_tokens,
                    "cost_estimate": log.cost_estimate,
                    "execution_time_ms": log.execution_time_ms,
                    "status": log.status,
                    "slot_name": log.slot_name,
                }
                for log in rows
            ]

    @staticmethod
    async def get_stage_and_slot_breakdown(hours: int = 24) -> List[Dict[str, Any]]:
        """Mengembalikan rincian konsumsi token yang dikelompokkan per stage subsistem dan slot model (primary vs fallback)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            effective_subsystem = func.coalesce(TokenUsageLog.subsystem, "system")
            effective_slot = func.coalesce(TokenUsageLog.slot_name, "primary")
            stmt = (
                select(
                    effective_subsystem.label("subsystem"),
                    effective_slot.label("slot_name"),
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.sum(TokenUsageLog.input_tokens).label("sum_input"),
                    func.sum(TokenUsageLog.output_tokens).label("sum_output"),
                    func.sum(TokenUsageLog.total_tokens).label("sum_total"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                    func.sum(TokenUsageLog.cost_estimate).label("sum_cost"),
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(effective_subsystem, effective_slot)
                .order_by(effective_subsystem, effective_slot)
            )
            rows = (await session.execute(stmt)).all()
            results = []
            for r in rows:
                m = dict(r._mapping)
                sum_in = int(m["sum_input"] or 0)
                sum_cached = int(m["sum_cached"] or 0)
                cache_hit_rate = round((sum_cached / sum_in * 100.0), 2) if sum_in > 0 else 0.0
                results.append({
                    "subsystem": m["subsystem"],
                    "slot_name": m["slot_name"],
                    "calls": m["call_count"],
                    "sum_input": sum_in,
                    "sum_output": int(m["sum_output"] or 0),
                    "sum_total": int(m["sum_total"] or 0),
                    "sum_cached": sum_cached,
                    "cache_hit_rate_pct": cache_hit_rate,
                    "sum_cost_usd": round(float(m["sum_cost"]), 6) if m["sum_cost"] else 0.0,
                })
            return results

    @staticmethod
    async def get_cache_performance_audit(hours: int = 24) -> Dict[str, Any]:
        """Audit komprehensif performa cache prompt (rasio hit cache per model dan global)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_session() as session:
            stmt_global = (
                select(
                    func.count(TokenUsageLog.id).label("total_calls"),
                    func.coalesce(func.sum(TokenUsageLog.input_tokens), 0).label("sum_input"),
                    func.coalesce(func.sum(TokenUsageLog.cached_tokens), 0).label("sum_cached"),
                    func.coalesce(func.sum(TokenUsageLog.cache_creation_tokens), 0).label("sum_cache_creation"),
                )
                .where(TokenUsageLog.timestamp >= since)
            )
            row_g = (await session.execute(stmt_global)).first()
            sum_input = int(row_g.sum_input) if row_g else 0
            sum_cached = int(row_g.sum_cached) if row_g else 0
            sum_creation = int(row_g.sum_cache_creation) if row_g else 0
            global_hit_rate = round((sum_cached / sum_input * 100.0), 2) if sum_input > 0 else 0.0

            stmt_models = (
                select(
                    TokenUsageLog.model_name,
                    func.count(TokenUsageLog.id).label("calls"),
                    func.sum(TokenUsageLog.input_tokens).label("sum_input"),
                    func.sum(TokenUsageLog.cached_tokens).label("sum_cached"),
                )
                .where(TokenUsageLog.timestamp >= since)
                .group_by(TokenUsageLog.model_name)
                .order_by(func.sum(TokenUsageLog.input_tokens).desc())
            )
            rows_m = (await session.execute(stmt_models)).all()
            model_breakdown = []
            for r in rows_m:
                m = dict(r._mapping)
                m_in = int(m["sum_input"] or 0)
                m_cached = int(m["sum_cached"] or 0)
                m_hit_rate = round((m_cached / m_in * 100.0), 2) if m_in > 0 else 0.0
                model_breakdown.append({
                    "model_name": m["model_name"],
                    "calls": m["calls"],
                    "input_tokens": m_in,
                    "cached_tokens": m_cached,
                    "cache_hit_rate_pct": m_hit_rate,
                })

            return {
                "time_window_hours": hours,
                "total_calls": int(row_g.total_calls) if row_g else 0,
                "total_input_tokens": sum_input,
                "cache_read_tokens": sum_cached,
                "cache_creation_tokens": sum_creation,
                "uncached_input_tokens": max(0, sum_input - sum_cached),
                "global_cache_hit_rate_pct": global_hit_rate,
                "model_cache_breakdown": model_breakdown,
            }

