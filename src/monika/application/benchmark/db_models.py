from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

import monika.core.primitives.clock as clock
from monika.infrastructure.database.models import Base


def _now():
    return clock.now()


class BenchmarkRun(Base):
    __tablename__ = "llm_benchmark_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    judge_model: Mapped[str] = mapped_column(String(160))
    reference_model: Mapped[str] = mapped_column(String(160))
    tasks_json: Mapped[str] = mapped_column(Text, nullable=True)
    models_json: Mapped[str] = mapped_column(Text, nullable=True)


class BenchmarkResult(Base):
    __tablename__ = "llm_benchmark_result"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("llm_benchmark_run.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    context_key: Mapped[str] = mapped_column(String(160))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)
    latency_s: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)
    schema_valid: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    deterministic_score: Mapped[float] = mapped_column(Float, nullable=True)
    judge_scores_json: Mapped[str] = mapped_column(Text, nullable=True)
    judge_overall: Mapped[float] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    raw_output: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_no_cache: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd_with_cache: Mapped[float] = mapped_column(Float, default=0.0)
    thinking_tokens: Mapped[int] = mapped_column(Integer, default=0)
    provider_route: Mapped[str] = mapped_column(String(80), default="direct")
