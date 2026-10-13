# ==============================================================================
# File: application/benchmark/task_specs/base.py
# ==============================================================================

"""
Base data classes and common helpers for benchmark task specifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from ..db_access import BenchmarkToolExecutor

logger = logging.getLogger("Benchmark.TaskSpecs")


@dataclass
class BenchmarkCase:
    context_key: str
    category: str
    system_prompt: str = ""
    user_prompt: str = ""
    schema: Optional[dict[str, Any]] = None
    tools: Optional[list[Any]] = None
    stage_name: str = ""
    history: Optional[list[Any]] = None
    role_kwargs: dict[str, Any] = field(default_factory=dict)
    custom_fn: Optional[Callable[..., Any]] = None
    custom_args: tuple[Any, ...] = ()
    context_summary: str = ""  # yang dilihat judge sebagai "context yang diberikan"
    state: Optional[dict[str, Any]] = None
    questions: Optional[list[Any]] = None
    expected_answers: Optional[dict[str, Any]] = None
    latency_target_ms: float = 100.0
    fixture_data: Optional[dict[str, Any]] = None

    def __init__(
        self,
        context_key: str,
        category: str,
        system_prompt: str = "",
        user_prompt: str = "",
        schema: Optional[dict[str, Any]] = None,
        tools: Optional[list[Any]] = None,
        stage_name: str = "",
        history: Optional[list[Any]] = None,
        role_kwargs: Optional[dict[str, Any]] = None,
        custom_fn: Optional[Callable[..., Any]] = None,
        custom_args: tuple[Any, ...] = (),
        context_summary: str = "",
        state: Optional[dict[str, Any]] = None,
        questions: Optional[list[Any]] = None,
        expected_answers: Optional[dict[str, Any]] = None,
        latency_target_ms: float = 100.0,
        fixture_data: Optional[dict[str, Any]] = None,
    ) -> None:
        self.context_key = context_key
        self.category = category
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.schema = schema
        self.tools = tools
        self.stage_name = stage_name
        self.history = history
        self.role_kwargs = role_kwargs if role_kwargs is not None else {}
        self.custom_fn = custom_fn
        self.custom_args = custom_args
        self.context_summary = context_summary
        self.state = state
        self.questions = questions
        self.expected_answers = expected_answers
        self.latency_target_ms = latency_target_ms
        self.fixture_data = fixture_data


@dataclass
class TaskSpec:
    task_id: str
    category: str
    mode: str  # "agent" | "json" | "text" | "chat" | "custom" | "system_one"
    build_case: Callable[[Any, dict[str, Any], Any], Awaitable[BenchmarkCase]]


def _sym(settings: dict[str, Any]) -> str:
    return settings.get("_benchmark_symbol") or settings.get("trading", {}).get("asset_universe", ["EURUSD"])[0]
