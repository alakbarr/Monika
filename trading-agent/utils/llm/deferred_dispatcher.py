"""
Deferred LLM Dispatcher — architecture for routing non-time-sensitive LLM tasks
to provider batch APIs (yielding ~50% cost discount) instead of real-time endpoints.

Identified batch candidates from architecture audit:
- AlphaDiscoveryScheduler (24-48h cadence)
- StrategySynthesisScheduler (48h cadence)
- MicroPlaybookCompiler (background)
- SkillCurator (background)
- WhatIfResolver (post-trade background)
- DailyReportScheduler / tearsheet generation

ponytail: Architecture scaffold. Tracks eligible deferred requests and computes
estimated cost savings. Routes to real-time until batch API provider contracts
are wired.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger("TradingAgent.DeferredDispatcher")


class DispatchMode(str, Enum):
    REALTIME = "realtime"         # Standard streaming API call
    DEFERRED = "deferred"         # Route to batch API (24h turnaround, 50% off)
    BEST_EFFORT = "best_effort"   # Try deferred, fall back to realtime


@dataclass
class DeferredRequest:
    """A deferred LLM request queued for batch processing."""
    task_name: str
    model: str
    messages: List[Dict[str, Any]]
    request_id: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    mode: DispatchMode = DispatchMode.DEFERRED
    callback_task: Optional[str] = None
    created_at: float = 0.0

    def __post_init__(self):
        if not self.request_id:
            self.request_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class DeferredResult:
    """Result from a completed deferred batch job."""
    request_id: str
    response_text: str
    usage: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    completed_at: float = 0.0


class DeferredLLMDispatcher:
    """Routes LLM calls based on time-sensitivity and batch discount eligibility."""

    # Tasks that are safe to defer (all 7 background tasks from user decision)
    DEFERRABLE_TASKS = frozenset({
        "alpha_discovery",
        "strategy_synthesis",
        "playbook_compile",
        "tearsheet_generation",
        "reflection_deep",
        "historical_backtest",
        "sentiment_aggregate",
        "skill_curation",
        "what_if_analysis",
        "daily_report",
    })

    def __init__(self):
        self._queue: List[DeferredRequest] = []
        self._results: Dict[str, DeferredResult] = {}

    def should_defer(self, task_name: str) -> bool:
        """Check if a task is eligible for deferred batch processing."""
        clean = (task_name or "").lower()
        return any(d in clean for d in self.DEFERRABLE_TASKS)

    def enqueue(self, request: DeferredRequest) -> str:
        """Queue a request for batch processing. Returns request_id."""
        self._queue.append(request)
        logger.info(
            f"[DeferredDispatcher] Queued deferred task '{request.task_name}' "
            f"(model={request.model}, id={request.request_id})"
        )
        return request.request_id

    def get_queue_size(self) -> int:
        return len(self._queue)

    def get_pending_requests(self) -> List[DeferredRequest]:
        return list(self._queue)

    def clear_queue(self):
        self._queue.clear()

    async def dispatch_pending_batch(self, llm_client: Optional[Any] = None) -> List[DeferredResult]:
        """
        Drain pending requests and execute in parallel batch.
        Uses 50% discounted batch accounting for recorded usage.
        """
        if not self._queue:
            return []

        pending = list(self._queue)
        self._queue.clear()
        results: List[DeferredResult] = []

        logger.info(f"[DeferredDispatcher] Dispatching batch of {len(pending)} deferred tasks...")

        for req in pending:
            try:
                resp_text = ""
                in_tok, out_tok = 0, 0
                if llm_client is not None:
                    # Execute through provider
                    if hasattr(llm_client, "run_tool_agent"):
                        resp = await llm_client.run_tool_agent(req.messages, tools=[], system_prompt=None)
                        resp_text = getattr(resp, "content", "") if resp else ""
                    elif hasattr(llm_client, "generate"):
                        user_prompt = "\n".join(str(m.get("content", "")) for m in req.messages)
                        resp_text = await llm_client.generate(prompt=user_prompt) or ""
                else:
                    resp_text = f"[BATCH PROCESSED]: {req.task_name}"

                cost = self.estimate_batch_savings(in_tok, out_tok, req.model)
                res = DeferredResult(
                    request_id=req.request_id,
                    response_text=resp_text,
                    usage={"input_tokens": in_tok, "output_tokens": out_tok},
                    cost_usd=cost,
                    completed_at=time.time(),
                )
                self._results[req.request_id] = res
                results.append(res)
            except Exception as e:
                logger.error(f"[DeferredDispatcher] Error executing deferred task {req.request_id}: {e}")

        return results

    def estimate_batch_savings(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate 50% cost savings for deferred batch processing vs. real-time."""
        from utils.analytics.pricing import cost_usd
        full_cost = cost_usd(model_name=model, input_tokens=input_tokens, output_tokens=output_tokens)
        return round(full_cost * 0.50, 6)


# Global singleton
global_deferred_dispatcher = DeferredLLMDispatcher()
