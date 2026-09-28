# ==============================================================================
# File: agent/moa_loop.py
# ==============================================================================

"""
Mixture-of-Agents (MoA) Runtime & Modern Reasoning Orchestrator.

Implements multi-model collaborative deliberation combining next-generation reasoning engines:
- Claude Sonnet 5 (Chief Synthesizer / Master Arbitrator)
- DeepSeek V4 Pro & V4.1 Flash (Algorithmic Rigor, Scenario Stress-Testing)
- GPT-6 Astra & Sol (Liquidity & Depth Inference, Cross-Asset Game Theory)
- Gemini 3.8 Flash (Global Macro Correlation & Multimodal Pattern Ingestion)

Provides parallel proposer fan-out, advisory system framing, resilient degraded-mode failover,
and automatic JSONL trace logging.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.moa_alternation import destination_key, merge_same_role_messages
from agent.moa_trace import save_moa_turn, slot_metrics

logger = logging.getLogger(__name__)

# Advisory prompt framing to prevent proposers from hallucinating tool execution
MOA_ADVISORY_SYSTEM_PROMPT = (
    "You are an expert reference advisor in a Mixture of Agents (MoA) council. "
    "You are NOT the acting agent and do NOT execute tools or make API/broker calls directly. "
    "A separate lead orchestrator model holds tool privileges and will execute concrete actions.\n\n"
    "CRITICAL DIRECTIVES:\n"
    "1. Never claim to have executed orders, accessed live terminals, or modified state.\n"
    "2. Provide razor-sharp, objective, and mathematically grounded analysis.\n"
    "3. Surface high-probability opportunities, hidden tail risks, counter-theses, and edge cases.\n"
    "4. Formulate actionable recommendations with explicit risk/reward and invalidation levels.\n"
    "5. Be concise, direct, and structured. No conversational fluff."
)

MOA_AGGREGATOR_SYSTEM_PROMPT = (
    "You are the Lead Arbitrator and Chief Synthesizer in a Mixture of Agents (MoA) process. "
    "You have received specialized advisory assessments from multiple cutting-edge reasoning models.\n\n"
    "YOUR RESPONSIBILITIES:\n"
    "1. Cross-examine the advisors: identify consensus, resolve contradictory claims, and discard hallucinated assumptions.\n"
    "2. Synthesize an authoritative, coherent, and actionable master directive.\n"
    "3. If in trading mode, explicitly specify thesis conviction, risk barriers, and optimal execution tactics.\n"
    "4. Provide clear guidance for immediate downstream tool execution."
)

# Standard presets combining modern frontier models
MOA_PRESETS: Dict[str, Dict[str, Any]] = {
    "trading_quant_moa": {
        "description": "High-conviction quantitative and macroeconomic multi-agent council",
        "proposers": [
            {
                "label": "DeepSeek-V4-Pro",
                "model": "deepseek-v4-pro",
                "provider": "deepseek",
                "temperature": 0.2,
                "role_focus": "Algorithmic logic, quantitative risk, volatility distribution",
            },
            {
                "label": "DeepSeek-V4.1-Flash",
                "model": "deepseek-v4.1-flash",
                "provider": "deepseek",
                "temperature": 0.3,
                "role_focus": "Rapid scenario stress-testing, tail-risk permutations",
            },
            {
                "label": "Gemini-3.8-Flash",
                "model": "gemini-3.8-flash",
                "provider": "google",
                "temperature": 0.2,
                "role_focus": "Global macro cross-asset trends, sentiment dynamics",
            },
            {
                "label": "GPT-6-Astra",
                "model": "gpt-6-astra",
                "provider": "openai",
                "temperature": 0.2,
                "role_focus": "Structural liquidity, order book imbalance, execution routing",
            },
        ],
        "aggregator": {
            "label": "Claude-Sonnet-5",
            "model": "claude-sonnet-5",
            "provider": "anthropic",
            "temperature": 0.2,
        },
    },
    "general_reasoning_moa": {
        "description": "Multi-perspective general problem solving and architecture debate",
        "proposers": [
            {
                "label": "DeepSeek-V4-Pro",
                "model": "deepseek-v4-pro",
                "provider": "deepseek",
                "temperature": 0.2,
                "role_focus": "Logic and edge case detection",
            },
            {
                "label": "Gemini-3.8-Flash",
                "model": "gemini-3.8-flash",
                "provider": "google",
                "temperature": 0.3,
                "role_focus": "Comprehensive factual synthesis",
            },
            {
                "label": "GPT-6-Astra",
                "model": "gpt-6-astra",
                "provider": "openai",
                "temperature": 0.2,
                "role_focus": "Strategy and architectural soundness",
            },
        ],
        "aggregator": {
            "label": "Claude-Sonnet-5",
            "model": "claude-sonnet-5",
            "provider": "anthropic",
            "temperature": 0.2,
        },
    },
    "fast_scalp_moa": {
        "description": "Ultra-low latency dual-proposer sprint for scalping & immediate triggers",
        "proposers": [
            {
                "label": "DeepSeek-V4.1-Flash",
                "model": "deepseek-v4.1-flash",
                "provider": "deepseek",
                "temperature": 0.1,
                "role_focus": "Microstructure & order flow momentum",
            },
            {
                "label": "Gemini-3.8-Flash",
                "model": "gemini-3.8-flash",
                "provider": "google",
                "temperature": 0.1,
                "role_focus": "Immediate news shock & calendar impact",
            },
        ],
        "aggregator": {
            "label": "GPT-6-Astra",
            "model": "gpt-6-astra",
            "provider": "openai",
            "temperature": 0.1,
        },
    },
}


@dataclass
class MoAResult:
    """Final outcome of an MoA deliberation cycle."""
    synthesis: str
    preset_name: str
    aggregator_label: str
    proposer_metrics: List[Dict[str, Any]]
    aggregator_metrics: Dict[str, Any]
    total_latency_ms: float
    is_degraded: bool = False
    trace_path: Optional[str] = None


def trim_head_tail_context(
    messages: List[Dict[str, Any]],
    max_tool_chars: int = 500,
    max_total_messages: int = 24,
) -> List[Dict[str, Any]]:
    """
    Applies zero-cost head-tail preview to historical tool responses and trims excessive
    turn depth so MoA deliberation layers never encounter token bloat.
    """
    if not messages:
        return []

    pruned = []
    for msg in messages:
        m = dict(msg)
        content = m.get("content")
        role = m.get("role")
        if role == "tool" and isinstance(content, str) and len(content) > max_tool_chars:
            half = max_tool_chars // 2
            head = content[:half]
            tail = content[-half:]
            omitted = len(content) - max_tool_chars
            m["content"] = f"{head}\n... [truncated {omitted} characters in historical context] ...\n{tail}"
        pruned.append(m)

    if len(pruned) > max_total_messages:
        head_zone = pruned[:2]
        tail_zone = pruned[-(max_total_messages - 2):]
        pruned = head_zone + tail_zone

    return pruned


class MoARuntime:
    """
    Orchestrates Mixture-of-Agents parallel generation, aggregation, and failovers.
    """

    def __init__(
        self,
        llm_caller: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], str]] = None,
        default_preset: str = "trading_quant_moa",
        default_timeout: float = 30.0,
        trace_dir: Optional[str] = None,
    ):
        """
        Args:
            llm_caller: Function with signature (slot_config, messages) -> response_text.
                        If None, uses simulated or auxiliary provider client.
            default_preset: Default preset key in MOA_PRESETS.
            default_timeout: Timeout per LLM call in seconds.
            trace_dir: Optional directory for JSONL trace logging.
        """
        self.llm_caller = llm_caller or self._default_llm_caller
        self.default_preset = default_preset
        self.default_timeout = default_timeout
        self.trace_dir = trace_dir

    def _default_llm_caller(self, slot: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
        """Default fallback LLM invocation. Can be monkeypatched or overridden."""
        model = slot.get("model", "unknown")
        label = slot.get("label", model)
        return f"[{label} ({model}) deliberated advice for context]"

    def _execute_single_proposer(
        self,
        proposer: Dict[str, Any],
        user_prompt: str,
        history: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """
        Executes a single reference proposer synchronously in a thread pool worker.
        Returns: (proposer_slot, output_text, metrics_dict)
        """
        label = proposer.get("label", proposer.get("model", "unknown"))
        start_time = time.monotonic()

        cleaned_history = trim_head_tail_context(history)
        messages = [
            {"role": "system", "content": MOA_ADVISORY_SYSTEM_PROMPT},
            *cleaned_history,
            {
                "role": "user",
                "content": f"[Role Focus: {proposer.get('role_focus', 'Advisory Analysis')}]\n{user_prompt}",
            },
        ]
        # Clean up role alternation
        messages = merge_same_role_messages(messages)

        try:
            output = self.llm_caller(proposer, messages)
            latency_ms = (time.monotonic() - start_time) * 1000
            metrics = slot_metrics(
                proposer,
                label=label,
                output=output,
                latency_ms=latency_ms,
                usage={"input_tokens": len(user_prompt) // 4 + 100, "output_tokens": len(output) // 4, "total_tokens": (len(user_prompt) + len(output)) // 4 + 100},
                is_failed=False,
            )
            return proposer, output, metrics
        except Exception as exc:
            latency_ms = (time.monotonic() - start_time) * 1000
            error_msg = f"[failed: {exc}]"
            logger.warning("MoA proposer %s failed: %s", label, exc)
            metrics = slot_metrics(
                proposer,
                label=label,
                output=error_msg,
                latency_ms=latency_ms,
                is_failed=True,
            )
            return proposer, error_msg, metrics

    def run_moa(
        self,
        user_prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        preset_name: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> MoAResult:
        """
        Synchronous MoA turn execution. Fans out proposers in parallel, then synthesizes via aggregator.
        """
        start_total = time.monotonic()
        preset_key = preset_name or self.default_preset
        preset = MOA_PRESETS.get(preset_key, MOA_PRESETS["trading_quant_moa"])
        proposers = preset.get("proposers", [])
        aggregator = preset.get("aggregator", {})
        timeout_sec = timeout or self.default_timeout
        history_msgs = list(history or [])

        # 1. Parallel Proposers Fan-out
        proposer_outputs: List[Tuple[str, str, Dict[str, Any]]] = []
        with ThreadPoolExecutor(max_workers=min(len(proposers), 8)) as executor:
            future_to_slot = {
                executor.submit(self._execute_single_proposer, p, user_prompt, history_msgs): p
                for p in proposers
            }
            try:
                for future in as_completed(future_to_slot, timeout=timeout_sec):
                    try:
                        slot, output, metrics = future.result()
                        label = slot.get("label", slot.get("model", "unknown"))
                        proposer_outputs.append((label, output, metrics))
                    except Exception as exc:
                        slot = future_to_slot[future]
                        label = slot.get("label", slot.get("model", "unknown"))
                        error_msg = f"[failed: {exc}]"
                        m = slot_metrics(slot, label=label, output=error_msg, is_failed=True)
                        proposer_outputs.append((label, error_msg, m))
            except TimeoutError:
                logger.warning(f"[MOALoop] Proposers timed out after {timeout_sec}s. Processing completed proposals.")
                for future, slot in future_to_slot.items():
                    if not future.done():
                        future.cancel()
                        label = slot.get("label", slot.get("model", "unknown"))
                        error_msg = f"[timed out after {timeout_sec}s]"
                        m = slot_metrics(slot, label=label, output=error_msg, is_failed=True)
                        proposer_outputs.append((label, error_msg, m))

        # Check success rate
        successful_proposals = [
            (lbl, out, m) for lbl, out, m in proposer_outputs if not m.get("is_failed")
        ]
        is_all_failed = len(successful_proposals) == 0

        # 2. Aggregator Synthesis
        agg_label = aggregator.get("label", aggregator.get("model", "Aggregator"))
        agg_start = time.monotonic()

        if is_all_failed:
            logger.warning("MoA: All reference models failed. Aggregator running in standalone degraded mode.")
            synth_user_msg = (
                f"[All reference models failed]\n"
                f"Original User Request:\n{user_prompt}\n\n"
                f"Please provide your complete, standalone assessment and execution plan."
            )
            is_degraded = True
        else:
            proposals_text = "\n\n".join(
                f"--- Advisor {idx}: {lbl} ---\n{out}"
                for idx, (lbl, out, _) in enumerate(successful_proposals, start=1)
            )
            synth_user_msg = (
                f"Original User Request:\n{user_prompt}\n\n"
                f"Reference Advisor Perspectives:\n{proposals_text}\n\n"
                f"Synthesize the consensus, resolve contradictions, and deliver the final execution plan."
            )
            is_degraded = len(successful_proposals) < len(proposers)

        agg_history = trim_head_tail_context(history_msgs)
        agg_messages = [
            {"role": "system", "content": MOA_AGGREGATOR_SYSTEM_PROMPT},
            *agg_history,
            {"role": "user", "content": synth_user_msg},
        ]
        agg_messages = merge_same_role_messages(agg_messages)

        try:
            synthesis = self.llm_caller(aggregator, agg_messages)
            agg_latency = (time.monotonic() - agg_start) * 1000
            agg_metrics = slot_metrics(
                aggregator,
                label=agg_label,
                output=synthesis,
                latency_ms=agg_latency,
                usage={"input_tokens": len(synth_user_msg) // 4 + 150, "output_tokens": len(synthesis) // 4, "total_tokens": (len(synth_user_msg) + len(synthesis)) // 4 + 150},
                is_failed=False,
            )
        except Exception as exc:
            agg_latency = (time.monotonic() - agg_start) * 1000
            synthesis = f"[Aggregator {agg_label} Failed: {exc}]"
            logger.error("MoA aggregator %s failed: %s", agg_label, exc)
            agg_metrics = slot_metrics(
                aggregator,
                label=agg_label,
                output=synthesis,
                latency_ms=agg_latency,
                is_failed=True,
            )

        total_latency_ms = (time.monotonic() - start_total) * 1000
        proposer_metrics = [m for _, _, m in proposer_outputs]

        # 3. Save JSONL Trace
        trace_path = save_moa_turn(
            session_id=session_id,
            preset_name=preset_key,
            proposer_traces=proposer_metrics,
            aggregator_trace=agg_metrics,
            user_prompt=user_prompt,
            total_latency_ms=total_latency_ms,
            trace_dir=self.trace_dir,
        )

        return MoAResult(
            synthesis=synthesis,
            preset_name=preset_key,
            aggregator_label=agg_label,
            proposer_metrics=proposer_metrics,
            aggregator_metrics=agg_metrics,
            total_latency_ms=total_latency_ms,
            is_degraded=is_degraded,
            trace_path=str(trace_path) if trace_path else None,
        )

    async def run_moa_async(
        self,
        user_prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        preset_name: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> MoAResult:
        """
        Asynchronous wrapper executing the ThreadPool fan-out on the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_moa(
                user_prompt=user_prompt,
                history=history,
                preset_name=preset_name,
                session_id=session_id,
                timeout=timeout,
            ),
        )


class MoAChatCompletions:
    """
    Standard OpenAI-compatible Chat Completions adapter for the MoA engine.
    Allows drop-in use anywhere a chat completion client is expected.
    """

    def __init__(self, runtime: Optional[MoARuntime] = None, preset: str = "trading_quant_moa"):
        self.runtime = runtime or MoARuntime()
        self.preset = preset

    def create(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Synchronous chat completion."""
        if not messages:
            return {"choices": [{"message": {"role": "assistant", "content": ""}}]}

        last_msg = messages[-1]
        user_prompt = last_msg.get("content", "")
        history = messages[:-1]

        res = self.runtime.run_moa(
            user_prompt=user_prompt,
            history=history,
            preset_name=model or self.preset,
            session_id=session_id,
            timeout=timeout,
        )

        total_tokens = sum(
            p.get("usage", {}).get("total_tokens", 0) for p in res.proposer_metrics
        ) + res.aggregator_metrics.get("usage", {}).get("total_tokens", 0)

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": res.synthesis,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "total_tokens": total_tokens,
            },
            "moa_result": res,
        }

    async def create_async(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Asynchronous chat completion."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.create(
                messages=messages,
                model=model,
                temperature=temperature,
                timeout=timeout,
                session_id=session_id,
                **kwargs,
            ),
        )

