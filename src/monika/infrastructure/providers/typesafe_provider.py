"""
TypeSafe (Jev) Provider: System One Decision-Making Engine.

Integrates TypeSafe's Jev model family (jev-latest, jev-1.13) into Monika's
multi-provider LLM fabric. Unlike generative models, Jev evaluates unstructured state
against typed questions (Choice, Score, Noul) returning deterministic decisions and
calibrated probabilities in sub-100ms without prose hallucinations.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from typesafe_sdk import AsyncTypeSafeClient
    from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

from monika.core.primitives.jev_primitives import (
    list_to_jev_questions,
    parse_jev_response_to_dict,
    schema_to_jev_questions,
)
from monika.infrastructure.providers.base_provider import BaseLLMClient

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
        **kwargs: Any,
    ):
        # Normalize model aliases
        clean_model = model
        if clean_model.startswith("openrouter/"):
            clean_model = clean_model[len("openrouter/") :]
        if clean_model.lower() in ("kev", "kev-4b"):
            clean_model = "jaredpalmer/kev-4b"
        elif clean_model.lower() in ("liquid-d1", "lfm-7b-d1", "liquid/lfm-7b-d1"):
            clean_model = "liquid/lfm-7b-d1"
        elif clean_model.lower() in (
            "luna-decision",
            "luna/decision",
            "gpt-6-luna-decisions",
            "openai/gpt-6-luna-decisions",
        ):
            clean_model = "openai/gpt-6-luna-decisions"
        elif clean_model.lower() in ("mercury-decide", "mercury/decide"):
            clean_model = "mercury/decide"

        super().__init__(
            model=clean_model,
            max_tokens=max_tokens,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            settings=settings,
            temperature=temperature,
            **kwargs,
        )

        # Base URL resolution
        if base_url:
            self.base_url = base_url
        elif "openrouter" in (model or "").lower() or any(
            k in (model or "").lower() for k in ("kev", "liquid", "luna", "mercury")
        ):
            self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
        else:
            self.base_url = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")

        self.is_openrouter = (
            "openrouter.ai" in (self.base_url or "")
            or "openrouter" in (model or "").lower()
            or bool(kwargs.get("use_openrouter", False))
        )

        # API Key resolution
        if api_key:
            self.api_key = api_key
        elif self.is_openrouter:
            self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_PAID_API_KEY")
        else:
            self.api_key = os.getenv("TYPESAFE_API_KEY")

        self.temperature: float = float(temperature)
        self.confidence_threshold = confidence_threshold
        self._client: Optional[Any] = None
        self._or_client: Optional[Any] = None
        self._ts_client: Optional[Any] = None

    def _get_openrouter_client(self) -> "OpenRouterProvider":
        """Lazy initialization of OpenRouterProvider for OpenRouter-routed models."""
        if self._or_client is None:
            if self._client is not None:
                return self._client
            from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

            or_model = self.model
            if or_model in ("jev-latest", "jev-router", "typesafe/jev-latest", "typesafe/jev-router"):
                or_model = "typesafe/jev-router"
            elif or_model in ("liquid-d1", "lfm-7b-d1", "liquid/lfm-7b-d1"):
                or_model = "liquid/lfm-2.5-2.6b:free"
            elif or_model in ("luna-decision", "luna/decision", "gpt-6-luna-decisions", "openai/gpt-6-luna-decisions"):
                or_model = "openai/gpt-6-luna-decisions"
            elif or_model in ("mercury-decide", "mercury/decide"):
                or_model = "inception/mercury-2.5"

            self._or_client = OpenRouterProvider(
                model=or_model,
                max_tokens=self.max_tokens,
                max_tool_turns=self.max_tool_turns,
                thinking_level="none",
                settings=self.settings,
                temperature=self.temperature,
                api_key=self.api_key,
            )
        return self._or_client

    async def _call_openrouter_decisions(self, state: Any, questions: dict, timeout: float = 15.0) -> Any:
        """Invokes OpenRouter's native alpha decisions endpoint for openai/gpt-6-luna-decisions."""
        import aiohttp
        from typesafe_sdk import Choice, Noul, Score, SystemOneResponse, ChoiceAnswer, NoulAnswer, ScoreAnswer
        from typesafe_sdk._core.response_types import Usage

        normalized_q: dict[str, Any] = {}
        for q_name, q_val in questions.items():
            if isinstance(q_val, dict):
                d = dict(q_val)
                if d.get("type") == "choice" and "criteria" not in d:
                    choices = d.get("choices") or d.get("options") or []
                    d["criteria"] = {str(c): str(c) for c in choices}
                normalized_q[q_name] = d
            elif isinstance(q_val, Choice):
                normalized_q[q_name] = {
                    "type": "choice",
                    "instructions": q_val.instructions,
                    "criteria": q_val.criteria,
                }
            elif isinstance(q_val, Score):
                normalized_q[q_name] = {"type": "score", "instructions": q_val.instructions, "criteria": q_val.criteria}
            elif isinstance(q_val, Noul):
                normalized_q[q_name] = {"type": "noul", "instructions": q_val.instructions}
            elif hasattr(q_val, "instructions"):
                q_type = getattr(q_val, "type", "choice" if hasattr(q_val, "criteria") else "noul")
                normalized_q[q_name] = {
                    "type": q_type,
                    "instructions": getattr(q_val, "instructions", ""),
                    "criteria": getattr(q_val, "criteria", {}),
                }
            else:
                normalized_q[q_name] = {"type": "noul", "instructions": str(q_val)}

        payload = {
            "model": "openai/gpt-6-luna-decisions",
            "state": str(state) if not isinstance(state, (str, dict, list)) else state,
            "questions": normalized_q,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = "https://openrouter.ai/api/alpha/decisions"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"OpenRouter decisions API failed ({resp.status}): {text}")
                data = await resp.json()
                answers = {}
                for k, v in data.get("answers", {}).items():
                    v_type = v.get("type")
                    if v_type == "choice":
                        answers[k] = ChoiceAnswer(
                            choice=v.get("choice", ""),
                            confidence=float(v.get("confidence", 1.0)),
                            probabilities=v.get("probabilities", {}),
                        )
                    elif v_type == "score":
                        answers[k] = ScoreAnswer(
                            score=float(v.get("score", 0)),
                            confidence=float(v.get("confidence", 1.0)),
                            legend=v.get("legend", {}),
                            probabilities=v.get("probabilities", {}),
                        )
                    else:
                        prob = float(v.get("noul", 0.5))
                        answers[k] = NoulAnswer(
                            noul=prob,
                        )
                usage_data = data.get("usage", {})
                usage = Usage(
                    input_tokens=int(usage_data.get("input_tokens", 0)),
                    output_tokens=int(usage_data.get("output_tokens", 0)),
                )
                return SystemOneResponse(
                    model=data.get("model", self.model),
                    answers=answers,
                    usage=usage,
                )

    def _get_typesafe_client(self) -> "AsyncTypeSafeClient":
        """Lazy initialization of AsyncTypeSafeClient for direct TypeSafe models."""
        if self._ts_client is None:
            if self._client is not None:
                return self._client
            from typesafe_sdk import AsyncTypeSafeClient

            resolved_key = self.api_key or os.getenv("TYPESAFE_API_KEY")
            if not resolved_key:
                raise ValueError("TYPESAFE_API_KEY not configured in environment or settings")
            self._ts_client = AsyncTypeSafeClient(api_key=resolved_key, base_url=self.base_url)
        return self._ts_client

    def _get_client(self) -> Union["OpenRouterProvider", "AsyncTypeSafeClient"]:
        """Lazy initialization of client (OpenRouterProvider for OpenRouter, or AsyncTypeSafeClient for TypeSafe direct)."""
        if self.is_openrouter:
            return self._get_openrouter_client()
        return self._get_typesafe_client()

    async def system_one(self, state: Any, questions: dict, timeout: float = 15.0, **kwargs: Any) -> Any:
        """Direct pass-through to underlying client or OpenRouter decisions / JSON translation."""
        if self.model == "openai/gpt-6-luna-decisions":
            return await self._call_openrouter_decisions(state=state, questions=questions, timeout=timeout)
        if self.is_openrouter:
            from monika.core.primitives.jev_primitives import jev_questions_to_schema

            schema = jev_questions_to_schema(questions)
            state_str = str(state) if not isinstance(state, str) else state
            return await self.classify_json(prompt=state_str, schema=schema, timeout=timeout, **kwargs)
        client = self._get_typesafe_client()
        return await client.system_one(
            state=state, questions=questions, model=kwargs.get("model", self.model), timeout=timeout
        )

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[dict]:
        """
        Executes System One evaluation using Jev primitives or OpenRouter completion.
        Accepts explicit `jev_questions` in kwargs or automatically translates JSON Schema.
        """
        if self.model == "openai/gpt-6-luna-decisions":
            t0 = time.perf_counter()
            jev_questions = kwargs.get("jev_questions")
            if isinstance(jev_questions, list):
                jev_questions = list_to_jev_questions(jev_questions)
            elif not jev_questions:
                if not schema:
                    logger.warning(f"[{self.model}] Neither jev_questions nor schema provided to classify_json")
                    return None
                if schema.get("type") == "array":
                    return None
                jev_questions = schema_to_jev_questions(schema, base_prompt=prompt)

            if not jev_questions:
                return None

            state = kwargs.get("state")
            if state is None:
                if system_prompt:
                    state = f"System Context:\n{system_prompt}\n\nTask:\n{prompt}"
                else:
                    state = prompt

            task_name = kwargs.get("task_name", self.role or "classify_json")
            try:
                response = await self._call_openrouter_decisions(
                    state=state, questions=jev_questions, timeout=kwargs.get("timeout", 15.0)
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                input_tokens = getattr(response.usage, "input_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
                cached_tokens = getattr(response.usage, "cached_tokens", 0) or 0
                pt_details = getattr(response.usage, "prompt_tokens_details", None)
                if not cached_tokens and pt_details is not None:
                    cached_tokens = getattr(pt_details, "cached_tokens", 0) or 0
                await self._save_token_usage(
                    model_name=self.model,
                    task_name=task_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    latency_ms=latency_ms,
                    session=kwargs.get("session"),
                )
                return parse_jev_response_to_dict(response, schema=schema)
            except Exception as e:
                logger.error(f"[{self.model}] OpenRouter decisions failed: {e}")
                return None

        if self.is_openrouter:
            or_client = self._get_openrouter_client()
            jev_questions = kwargs.get("jev_questions")
            if jev_questions and not schema:
                from monika.core.primitives.jev_primitives import jev_questions_to_schema

                if isinstance(jev_questions, list):
                    jev_questions = list_to_jev_questions(jev_questions)
                schema = jev_questions_to_schema(jev_questions)
            state = kwargs.get("state")
            final_prompt = prompt
            if state and not prompt:
                final_prompt = str(state)
            elif state and prompt and str(state) not in prompt:
                final_prompt = f"{prompt}\n\nContext:\n{state}"
            return await or_client.classify_json(
                prompt=final_prompt,
                system_prompt=system_prompt,
                schema=schema,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                **kwargs,
            )

        t0 = time.perf_counter()
        client = self._get_typesafe_client()

        # 1. Resolve Questions: explicit Jev primitives or schema-converted
        jev_questions = kwargs.get("jev_questions")
        if isinstance(jev_questions, list):
            jev_questions = list_to_jev_questions(jev_questions)
        elif not jev_questions:
            if not schema:
                logger.warning(f"[{self.model}] Neither jev_questions nor schema provided to classify_json")
                return None
            if schema.get("type") == "array":
                logger.debug(
                    f"[{self.model}] TypeSafe Jev does not support array schemas directly in classify_json. "
                    f"Returning None to trigger failover to next LLM fallback."
                )
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
                state=state, questions=jev_questions, model=self.model, timeout=kwargs.get("timeout", 15.0)
            )

            latency_ms = int((time.perf_counter() - t0) * 1000)

            # 4. Token & Cost Logging
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            cached_tokens = getattr(response.usage, "cached_tokens", 0) or 0
            pt_details = getattr(response.usage, "prompt_tokens_details", None)
            if not cached_tokens and pt_details is not None:
                cached_tokens = getattr(pt_details, "cached_tokens", 0) or 0

            await self._save_token_usage(
                model_name=self.model,
                task_name=task_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                session=session,
                task_role=self.role,
                subsystem=self.subsystem,
                symbol=self.symbol,
                cycle_id=self.cycle_id,
                execution_time_ms=latency_ms,
                status="success",
            )

            # 5. Transform SystemOneResponse to standard dict
            result = parse_jev_response_to_dict(
                response, schema=schema, default_confidence_threshold=self.confidence_threshold
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
                status=f"error: {str(e)[:100]}",
            )
            # Returning None signals FallbackClientWrapper to failover to next model
            return None

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
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
        tool_executor: Any = None,
    ) -> dict:
        """Jev does not support interactive chat loops."""
        raise NotImplementedError(f"Model '{self.model}' (TypeSafe Jev) does not support interactive chat loops.")

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> Any:
        """Jev does not support tool-calling agent loops."""
        raise NotImplementedError(f"Model '{self.model}' (TypeSafe Jev) does not support tool-calling loops.")

    async def ping(self) -> bool:
        """Pings TypeSafe Jev API with a minimal test evaluation."""
        try:
            from typesafe_sdk import Noul

            client = self._get_typesafe_client()
            res = await client.system_one(
                state="Health check",
                questions={"status": Noul(instructions="Is system alive?")},
                model=self.model,
                timeout=5.0,
            )
            return bool(res and res.answers)
        except Exception as e:
            logger.warning(f"[{self.model}] TypeSafe ping failed: {e}")
            return False
