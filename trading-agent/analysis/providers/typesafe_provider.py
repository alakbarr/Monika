"""
TypeSafe (Jev) Provider: System One Decision-Making Engine.

Integrates TypeSafe's Jev model family (jev-latest, jev-1.13) into Monika's
multi-provider LLM fabric. Unlike generative models, Jev evaluates unstructured state
against typed questions (Choice, Score, Noul) returning deterministic decisions and
calibrated probabilities in sub-100ms without prose hallucinations.
"""

import os
import time
import logging
from typing import Optional, Any, Dict, List, Union

from analysis.providers.base_provider import BaseLLMClient
from utils.typesafe.jev_primitives import (
    schema_to_jev_questions,
    parse_jev_response_to_dict,
)

logger = logging.getLogger("TradingAgent.TypeSafeProvider")


class TypeSafeProvider(BaseLLMClient):
    """
    BaseLLMClient adapter for TypeSafe Jev System One model.
    Specialized for fast, typed classification, scoring, and boolean decision-making.
    """

    provider_name: str = "typesafe"

    def __init__(
        self,
        model: str = "jev-latest",
        max_tokens: int = 2048,
        max_tool_turns: int = 1,
        thinking_level: str = "none",
        settings: Optional[dict] = None,
        temperature: float = 0.0,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        confidence_threshold: float = 0.70,
        **kwargs: Any
    ):
        super().__init__(
            model=model,
            max_tokens=max_tokens,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            settings=settings,
            temperature=temperature,
            **kwargs
        )
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        self.base_url = base_url or os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
        self.confidence_threshold = confidence_threshold
        self._client = None

    def _get_client(self):
        """Lazy initialization of AsyncTypeSafeClient."""
        if self._client is None:
            from typesafe_sdk import AsyncTypeSafeClient
            resolved_key = self.api_key or os.getenv("TYPESAFE_API_KEY")
            if not resolved_key:
                raise ValueError("TYPESAFE_API_KEY not configured in environment or settings")
            self._client = AsyncTypeSafeClient(
                api_key=resolved_key,
                base_url=self.base_url
            )
        return self._client

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> Optional[dict]:
        """
        Executes System One evaluation using Jev primitives.
        Accepts explicit `jev_questions` in kwargs or automatically translates JSON Schema.
        """
        t0 = time.perf_counter()
        client = self._get_client()

        # 1. Resolve Questions: explicit Jev primitives or schema-converted
        jev_questions = kwargs.get("jev_questions")
        if not jev_questions:
            if not schema:
                logger.warning(f"[{self.model}] Neither jev_questions nor schema provided to classify_json")
                return None
            jev_questions = schema_to_jev_questions(schema, base_prompt=prompt)

        if not jev_questions:
            logger.warning(f"[{self.model}] No questions could be resolved for schema: {schema}")
            return None

        # 2. Resolve State: explicit structured state or prompt/system text
        state = kwargs.get("state")
        if state is None:
            if system_prompt:
                state = f"System Context:\n{system_prompt}\n\nTask:\n{prompt}"
            else:
                state = prompt

        task_name = kwargs.get("task_name", self.role or "classify_json")
        session = kwargs.get("session")

        try:
            # 3. Invoke Jev System One API
            response = await client.system_one(
                state=state,
                questions=jev_questions,
                model=self.model,
                timeout=kwargs.get("timeout", 15.0)
            )

            latency_ms = int((time.perf_counter() - t0) * 1000)

            # 4. Token & Cost Logging
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)

            await self._save_token_usage(
                model_name=self.model,
                task_name=task_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                session=session,
                task_role=self.role,
                subsystem=self.subsystem,
                symbol=self.symbol,
                cycle_id=self.cycle_id,
                execution_time_ms=latency_ms,
                status="success"
            )

            # 5. Transform SystemOneResponse to standard dict
            result = parse_jev_response_to_dict(
                response,
                schema=schema,
                default_confidence_threshold=self.confidence_threshold
            )

            # Check confidence gating if requested
            min_conf = kwargs.get("min_confidence", self.confidence_threshold)
            if min_conf and result.get("_confidence", 1.0) < min_conf:
                if kwargs.get("reject_low_confidence", False):
                    logger.info(
                        f"[{self.model}] Jev decision confidence {result.get('_confidence', 0):.2f} "
                        f"below required {min_conf:.2f} — escalating to fallback chain"
                    )
                    return None

            return result

        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(f"[{self.model}] Jev evaluation failed ({latency_ms}ms): {e}")
            await self._save_token_usage(
                model_name=self.model,
                task_name=task_name,
                input_tokens=0,
                output_tokens=0,
                session=session,
                task_role=self.role,
                subsystem=self.subsystem,
                symbol=self.symbol,
                cycle_id=self.cycle_id,
                execution_time_ms=latency_ms,
                status=f"error: {str(e)[:100]}"
            )
            # Returning None signals FallbackClientWrapper to failover to next model
            return None

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> Optional[str]:
        """Jev is a System One decision model and does not generate free text."""
        raise NotImplementedError(
            f"Model '{self.model}' (TypeSafe Jev) is a pure decision engine and does not support free-text generation. "
            "Use classify_json() for structured evaluation."
        )

    async def run_chat_loop(
        self,
        system_prompt: str,
        conversation_history: list,
        new_user_message: str,
        tools: list,
        tool_executor: Any = None
    ) -> dict:
        """Jev does not support interactive chat loops."""
        raise NotImplementedError(
            f"Model '{self.model}' (TypeSafe Jev) does not support interactive chat loops."
        )

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> Any:
        """Jev does not support tool-calling agent loops."""
        raise NotImplementedError(
            f"Model '{self.model}' (TypeSafe Jev) does not support tool-calling loops."
        )

    async def ping(self) -> bool:
        """Pings TypeSafe Jev API with a minimal test evaluation."""
        try:
            from typesafe_sdk import Noul
            client = self._get_client()
            res = await client.system_one(
                state="Health check",
                questions={"status": Noul(instructions="Is system alive?")},
                model=self.model,
                timeout=5.0
            )
            return bool(res and res.answers)
        except Exception as e:
            logger.warning(f"[{self.model}] TypeSafe ping failed: {e}")
            return False
