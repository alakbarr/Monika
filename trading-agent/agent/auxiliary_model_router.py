# ==============================================================================
# File: agent/auxiliary_model_router.py
# ==============================================================================

"""
Auxiliary Model Router, Parameter Rejection Ladder & Reasoning Floor Stepper.
Dedicated routing engine for low-latency, low-cost micro-tasks with automatic parameter adaptation.

1. Task-Specific Routing:
   Dispatches non-trading background tasks (compression, session titles, option clarification,
   skill curation, intent extraction) to optimized, cost-efficient fast models without polluting
   the primary trading analytical pipeline.

2. Parameter Rejection Ladder:
   When an auxiliary endpoint rejects optional parameters with HTTP 400 (e.g. unsupported
   temperature, presence_penalty, frequency_penalty, or max_tokens), the ladder systematically
   prunes parameters rung-by-rung until the request succeeds.

3. Reasoning Floor Stepping & Memoization:
   For models that disallow disabled reasoning (throwing HTTP 400 when effort is 'none'),
   automatically steps effort up to 'low', memoizes the route in _FLOORED_ROUTES, and
   proactively applies the floor on future invocations without repeating the failed turn.
"""

from __future__ import annotations

import enum
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Agent.AuxiliaryModelRouter")


class AuxiliaryTaskType(str, enum.Enum):
    """Supported specialized auxiliary tasks."""
    COMPRESSION = "compression"
    TITLE_GENERATION = "title_generation"
    CLARIFY_OPTIONS = "clarify_options"
    SKILL_CURATOR = "skill_curator"
    VISION_ANALYSIS = "vision_analysis"
    INTENT_DETECTION = "intent_detection"
    QUICK_SUMMARY = "quick_summary"


# Global set of (provider, model) routes known to mandate non-zero reasoning
_FLOORED_ROUTES: Set[Tuple[str, str]] = set()


class ParameterRejectionLadder:
    """
    Sequentially removes optional LLM parameters upon HTTP 400 errors.
    """
    RUNG_DROP_PENALTIES = 1     # Drop presence/frequency penalties
    RUNG_DROP_TEMPERATURE = 2   # Drop temperature and top_p
    RUNG_DROP_MAX_TOKENS = 3    # Drop max_tokens / max_completion_tokens
    RUNG_BARE_MINIMUM = 4       # Send only model and messages

    @classmethod
    def apply_rung(cls, rung: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """Returns a sanitized copy of params for the given ladder rung."""
        p = dict(params)
        if rung >= cls.RUNG_DROP_PENALTIES:
            p.pop("presence_penalty", None)
            p.pop("frequency_penalty", None)
        if rung >= cls.RUNG_DROP_TEMPERATURE:
            p.pop("temperature", None)
            p.pop("top_p", None)
        if rung >= cls.RUNG_DROP_MAX_TOKENS:
            p.pop("max_tokens", None)
            p.pop("max_completion_tokens", None)
        return p


class ReasoningFloorManager:
    """
    Manages models that require explicit reasoning effort settings.
    """

    @classmethod
    def is_floored(cls, provider: str, model: str) -> bool:
        """Returns True if this route is known to require non-zero reasoning effort."""
        return (provider.lower(), model.lower()) in _FLOORED_ROUTES

    @classmethod
    def record_floored_route(cls, provider: str, model: str) -> None:
        """Records a route as requiring a minimum reasoning floor ('low')."""
        key = (provider.lower(), model.lower())
        if key not in _FLOORED_ROUTES:
            _FLOORED_ROUTES.add(key)
            logger.info(f"[ReasoningFloorManager] Memoized floored route: {provider}/{model} -> reasoning_effort='low'")

    @classmethod
    def adapt_request(cls, provider: str, model: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Proactively applies reasoning floor if route is floored."""
        adapted = dict(params)
        if cls.is_floored(provider, model):
            adapted["reasoning_effort"] = "low"
            # Floored reasoning models often disallow custom temperature
            adapted.pop("temperature", None)
        return adapted


class AuxiliaryModelRouter:
    """
    Central coordinator for auxiliary LLM calls across the agent framework.
    """

    def __init__(
        self,
        default_caller: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
        task_role_mapping: Optional[Dict[AuxiliaryTaskType, Tuple[str, str]]] = None,
    ):
        self._default_caller = default_caller
        self._task_role_mapping = task_role_mapping or {
            AuxiliaryTaskType.COMPRESSION: ("openrouter", "google/gemini-2.5-flash"),
            AuxiliaryTaskType.TITLE_GENERATION: ("openrouter", "google/gemini-2.5-flash"),
            AuxiliaryTaskType.CLARIFY_OPTIONS: ("openrouter", "google/gemini-2.5-flash"),
            AuxiliaryTaskType.SKILL_CURATOR: ("openrouter", "deepseek/deepseek-chat"),
            AuxiliaryTaskType.INTENT_DETECTION: ("groq", "llama-3.3-70b-versatile"),
            AuxiliaryTaskType.QUICK_SUMMARY: ("openrouter", "google/gemini-2.5-flash"),
        }

    def register_task_route(self, task: AuxiliaryTaskType, provider: str, model: str) -> None:
        """Overrides the provider and model mapping for a specific auxiliary task."""
        self._task_role_mapping[task] = (provider, model)
        logger.debug(f"[AuxiliaryModelRouter] Route registered: {task.value} -> {provider}/{model}")

    def call_auxiliary(
        self,
        task: AuxiliaryTaskType,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
        caller: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
    ) -> str:
        """
        Executes an auxiliary task through the parameter ladder and reasoning floor stepper.
        """
        provider, model = self._task_role_mapping.get(
            task, ("openrouter", "google/gemini-2.5-flash")
        )
        dispatch_caller = caller or self._default_caller
        if dispatch_caller is None:
            raise RuntimeError("No LLM caller supplied to AuxiliaryModelRouter")

        # Prepare base params
        params: Dict[str, Any] = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        if system_prompt:
            params["messages"] = [{"role": "system", "content": system_prompt}] + messages
        if custom_params:
            params.update(custom_params)

        # Apply reasoning floor if already memoized
        params = ReasoningFloorManager.adapt_request(provider, model, params)

        # Ladder execution loop
        last_exception: Optional[Exception] = None
        for rung in range(0, ParameterRejectionLadder.RUNG_BARE_MINIMUM + 1):
            rung_params = ParameterRejectionLadder.apply_rung(rung, params)
            try:
                response = dispatch_caller(provider, model, rung_params)
                # Extract text
                if isinstance(response, str):
                    return response
                elif hasattr(response, "content"):
                    return str(response.content)
                elif isinstance(response, dict) and "choices" in response:
                    return str(response["choices"][0]["message"]["content"])
                return str(response)

            except Exception as exc:
                last_exception = exc
                err_msg = str(exc).lower()

                # Check for reasoning rejection (e.g. "reasoning_effort is required" or "does not support reasoning=none")
                if "reasoning" in err_msg and ("require" in err_msg or "unsupported" in err_msg or "400" in err_msg):
                    ReasoningFloorManager.record_floored_route(provider, model)
                    params["reasoning_effort"] = "low"
                    params.pop("temperature", None)
                    logger.info(f"[AuxiliaryModelRouter] Stepped up reasoning floor for {provider}/{model}, retrying...")
                    continue

                # Check if error is parameter-related (HTTP 400 / invalid_request_error)
                if "400" in err_msg or "parameter" in err_msg or "unrecognized" in err_msg:
                    logger.warning(
                        f"[AuxiliaryModelRouter] Parameter rejected by {provider}/{model} (rung {rung}): {exc}. "
                        f"Advancing ladder to rung {rung + 1}..."
                    )
                    continue

                # If non-parameter error (e.g. 500, network, auth), raise immediately
                raise

        raise RuntimeError(f"[AuxiliaryModelRouter] All ladder rungs exhausted for {provider}/{model}: {last_exception}")
