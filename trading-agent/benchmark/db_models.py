from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from database.models import Base


def _now():
    return datetime.now(timezone.utc)


class BenchmarkRun(Base):
    __tablename__ = "llm_benchmark_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    judge_model: Mapped[str] = mapped_column(String(80))
    reference_model: Mapped[str] = mapped_column(String(80))
    tasks_json: Mapped[str] = mapped_column(Text, nullable=True)
    models_json: Mapped[str] = mapped_column(Text, nullable=True)


class BenchmarkResult(Base):
    __tablename__ = "llm_benchmark_result"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("llm_benchmark_run.id"), index=True)
    task_id: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    context_key: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    deterministic_score: Mapped[float] = mapped_column(Float, nullable=True)
    judge_scores_json: Mapped[str] = mapped_column(Text, nullable=True)
    judge_overall: Mapped[float] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    raw_output: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
