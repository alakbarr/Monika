# ==============================================================================
# File: infrastructure/providers/fallback_wrapper.py
# ==============================================================================

"""
Fallback Client Wrapper.
Tries primary model and cascades to fallback providers/models on failure.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import os
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from monika.infrastructure.llm.rate_limiting.streaming import StreamSafetyTimeoutError, StreamTimeoutError
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockBlock, MockResponse
from monika.infrastructure.providers.circuit_breaker import (
    HOT_PATH_ROLES,
    _UNSUPPORTED_SCHEMA_ROUTES,
    EndpointBlackhole,
    ProviderCircuitBreaker,
)

if TYPE_CHECKING:
    from monika.infrastructure.providers.llm_factory import LLMFactory


class _FallbackLoggerProxy(logging.Logger):
    def __init__(self) -> None:
        super().__init__("TradingAgent.LLMFactory")

    def __getattribute__(self, name: str) -> Any:
        if name in ("__init__", "__class__"):
            return super().__getattribute__(name)
        mod = sys.modules.get("monika.infrastructure.providers.llm_factory")
        if mod is not None and hasattr(mod, "logger"):
            return getattr(mod.logger, name)
        return super().__getattribute__(name)


logger: logging.Logger = _FallbackLoggerProxy()


def _safe_clone(val: Any) -> Any:
    """Deepcopy serializable data (like messages/tools) while skipping unpicklable objects (like AsyncSession)."""
    if val is None or isinstance(val, (int, float, str, bool, bytes)):
        return val
    type_name = type(val).__name__
    if any(
        unpicklable in type_name
        for unpicklable in ("Session", "Connection", "Engine", "Client", "Socket", "Loop", "Task")
    ):
        return val
    if isinstance(val, list):
        return [_safe_clone(x) for x in val]
    if isinstance(val, dict):
        return {k: _safe_clone(v) for k, v in val.items()}
    if isinstance(val, set):
        return set(val)
    if isinstance(val, tuple):
        return tuple(_safe_clone(x) for x in val)
    try:
        return copy.deepcopy(val)
    except Exception:
        return val


class FallbackClientWrapper(BaseLLMClient):
    """
    Wrapper that tries primary model, and if it fails, tries fallback models.
    """

    _shared_role_slot_cooldowns: dict[str, dict[str, float]] = {}
    _shared_role_backoff: dict[str, dict[str, int]] = {}

    def __init__(
        self, factory: LLMFactory, primary: str, fallbacks: list[str], role_config: dict, task_role: str = "default"
    ):
        self.factory = factory
        self.primary = primary
        self.fallbacks = fallbacks
        self.role_config = role_config
        self.task_role = task_role
        self.max_cost_per_call = (
            float(role_config["max_cost_per_call"]) if role_config.get("max_cost_per_call") is not None else None
        )
        if self.task_role not in self._shared_role_slot_cooldowns:
            self._shared_role_slot_cooldowns[self.task_role] = {}
        self._slot_cooldowns: dict[str, float] = self._shared_role_slot_cooldowns[self.task_role]

        if self.task_role not in self._shared_role_backoff:
            self._shared_role_backoff[self.task_role] = {}
        self._slot_backoff_count: dict[str, int] = self._shared_role_backoff[self.task_role]
        self._primary_cooldown_until = self._slot_cooldowns.get("primary")
        self._active_slot: str = "primary"

        try:
            primary_provider = factory._resolve_provider(primary, role_config=role_config, slot_name="primary")
        except TypeError:
            primary_provider = factory._resolve_provider(primary)
        primary_thinking = factory._resolve_thinking_level(primary, role_config, primary_provider, slot_name="primary")

        from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

        primary_raw_max = role_config.get("max_tokens", 8192)
        primary_eff_max = resolve_effective_max_tokens(
            model_name=primary,
            provider_name=primary_provider,
            requested_max_tokens=primary_raw_max,
            thinking_level=primary_thinking,
            settings=factory._settings,
        )

        # Set attributes required by BaseLLMClient
        super().__init__(
            model=primary,
            max_tokens=primary_eff_max,
            max_tool_turns=role_config.get("max_tool_turns", 15),
            thinking_level=primary_thinking,
            settings=factory._settings,
            temperature=float(role_config.get("temperature", 0.0)),
            role=task_role,
        )

        self._dynamic_thinking_budget = None
        is_primary_thinking_disabled = (
            str(primary_thinking or "none").lower() in ("none", "off") or role_config.get("thinking_budget") == 0
        )
        if is_primary_thinking_disabled:
            self.thinking_budget = 0
        else:
            try:
                from monika.infrastructure.llm.adaptive_thinking import (
                    PerSymbolAdaptiveThinkingAllocator,
                    QuantizedThinkingAllocator,
                    clamp_thinking_budget_to_answer_room,
                )

                level_to_budget = {
                    "minimal": 1024,
                    "low": 1024,
                    "medium": 4096,
                    "high": 10000,
                    "max": 16000,
                    "xhigh": 16000,
                    "extended": 16000,
                }
                base_b = level_to_budget.get(str(primary_thinking).lower(), 4096)
                raw_b = PerSymbolAdaptiveThinkingAllocator.get_thinking_budget_for_task(task_role, base_budget=base_b)
                if raw_b > 0:
                    final_fc_max = resolve_effective_max_tokens(
                        model_name=primary,
                        provider_name=primary_provider,
                        requested_max_tokens=primary_raw_max,
                        thinking_budget=raw_b,
                        thinking_level=primary_thinking,
                        settings=factory._settings,
                    )
                    self.max_tokens = final_fc_max
                    if isinstance(self.max_tokens, int) and self.max_tokens > 1024:
                        raw_b = clamp_thinking_budget_to_answer_room(
                            raw_b, max_tokens=self.max_tokens, min_answer_tokens=1024
                        )
                self.thinking_budget = QuantizedThinkingAllocator.quantize(raw_b) if raw_b > 0 else 0
            except Exception:
                self.thinking_budget = 4096

    @property
    def provider_name(self) -> str:
        """Returns the provider name of the currently active model slot."""
        try:
            active_model = self.model or self.primary
            active_slot: Optional[str] = getattr(self, "_active_slot", None)
            if active_slot == "primary" and active_model != self.primary:
                active_slot = None
            elif active_slot and active_slot.startswith("fallback_") and hasattr(self, "fallbacks"):
                try:
                    fb_idx = int(active_slot.split("_", 1)[1]) - 1
                    if not (0 <= fb_idx < len(self.fallbacks) and self.fallbacks[fb_idx] == active_model):
                        active_slot = None
                except ValueError, IndexError:
                    active_slot = None
            if active_slot is None:
                if active_model == self.primary:
                    active_slot = "primary"
                elif hasattr(self, "fallbacks"):
                    for idx, fb_mod in enumerate(self.fallbacks):
                        if fb_mod == active_model:
                            active_slot = f"fallback_{idx + 1}"
                            break
            try:
                return self.factory._resolve_provider(
                    active_model, role_config=getattr(self, "role_config", None), slot_name=active_slot
                )
            except TypeError:
                return self.factory._resolve_provider(active_model)
        except Exception:
            return getattr(self, "_provider_name", "") or ""

    @provider_name.setter
    def provider_name(self, value: str) -> None:
        self._provider_name = value

    def _maybe_restore_primary(self) -> bool:
        """Check if primary provider cooldown has expired and restore it."""
        import time

        now = time.time()
        expired = [s for s, t in self._slot_cooldowns.items() if now >= t]
        for s in expired:
            self._slot_cooldowns.pop(s, None)

        primary_cd = self._slot_cooldowns.get("primary")
        if primary_cd is None and self._primary_cooldown_until is not None:
            if now >= self._primary_cooldown_until:
                self._primary_cooldown_until = None
                self.model = self.primary
                self._active_slot = "primary"
                return True
        elif primary_cd is not None and now >= primary_cd:
            logger.info(
                f"[{self.task_role}][FallbackClientWrapper] Primary model '{self.primary}' "
                f"cooldown expired â€” restoring to primary."
            )
            self._slot_cooldowns.pop("primary", None)
            self._primary_cooldown_until = None
            self.model = self.primary
            self._active_slot = "primary"
            return True
        elif primary_cd is not None:
            self._primary_cooldown_until = primary_cd
            return False
        return False

    def set_thinking_budget(self, budget: int) -> None:
        """Sets thinking budget dynamically for wrapper and upcoming provider invocations."""
        if str(getattr(self, "thinking_level", "")).lower() in ("none", "off"):
            self.thinking_budget = 0
            self._dynamic_thinking_budget = None
            return

        from monika.infrastructure.llm.adaptive_thinking import QuantizedThinkingAllocator

        quantized = QuantizedThinkingAllocator.quantize(budget)
        self.thinking_budget = quantized
        self._dynamic_thinking_budget = quantized

    async def _execute_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        # Check dynamic runtime model hot-swap overrides
        try:
            from monika.infrastructure.providers.runtime_model_registry import RuntimeModelRegistry

            registry = RuntimeModelRegistry.get_instance()
            hot_primary = registry.get_role_model(self.task_role, "primary")
            if hot_primary:
                self.primary = hot_primary
            for i in range(len(self.fallbacks)):
                hot_fb = registry.get_role_model(self.task_role, f"fallback_{i + 1}")
                if hot_fb:
                    self.fallbacks[i] = hot_fb
        except Exception:
            pass

        self._maybe_restore_primary()

        if self._primary_cooldown_until or "primary" in self._slot_cooldowns:
            models_to_try = [(f"fallback_{i + 1}", model) for i, model in enumerate(self.fallbacks)]
            if not models_to_try:
                models_to_try = [("primary", self.primary)]
        else:
            models_to_try = [("primary", self.primary)] + [
                (f"fallback_{i + 1}", model) for i, model in enumerate(self.fallbacks)
            ]
        last_error = None
        last_failed_dict = None

        # Check global budget circuit breaker
        bypass_budget = kwargs.pop("_bypass_budget_check", False)
        is_budget_paused = False
        if not bypass_budget:
            try:
                from monika.core.analytics.cost_tracker import CostTracker

                is_budget_paused = bool(CostTracker.is_budget_paused_cached())
            except Exception as e:
                logger.debug(f"[CircuitBreaker] Cached budget check error: {e}")

        # Stage-aware fast timeouts for hot-path trading vs agent harness loops
        explicit_timeout = kwargs.pop("_per_model_timeout", None)
        if explicit_timeout is not None:
            per_model_timeout = float(explicit_timeout)
        elif method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
            max_turns = float((self.role_config or {}).get("max_tool_turns") or 15)
            cfg_pm_timeout = (self.role_config or {}).get("per_model_timeout_seconds")
            if cfg_pm_timeout is not None:
                per_model_timeout = float(cfg_pm_timeout)
            else:
                per_model_timeout = max(300.0, max_turns * 45.0)
        elif self.task_role in HOT_PATH_ROLES:
            max_turns = float((self.role_config or {}).get("max_tool_turns") or 3)
            cfg_pm_timeout = (self.role_config or {}).get("per_model_timeout_seconds")
            if cfg_pm_timeout is not None:
                per_model_timeout = float(cfg_pm_timeout)
            else:
                per_model_timeout = max(180.0, max_turns * 45.0)
        else:
            cfg_pm_timeout = (self.role_config or {}).get("per_model_timeout_seconds")
            per_model_timeout = float(cfg_pm_timeout) if cfg_pm_timeout is not None else 360.0

        # Check if all candidate models are in active cooldown
        now_ts = time.time()
        active_candidates = [
            (s, m) for s, m in models_to_try if not (s in self._slot_cooldowns and self._slot_cooldowns[s] > now_ts)
        ]
        if not active_candidates and models_to_try:
            earliest_slot, earliest_model = min(
                models_to_try,
                key=lambda sm: self._slot_cooldowns.get(sm[0], float("inf")),
            )
            min_diff = self._slot_cooldowns.get(earliest_slot, float("inf")) - now_ts
            if min_diff <= 60.0:
                logger.info(
                    f"[{self.task_role}] All models in cooldown — reviving near-expiry slot {earliest_slot} '{earliest_model}'"
                )
                self._slot_cooldowns.pop(earliest_slot, None)

        for slot_name, model in models_to_try:
            # If budget is paused, bypass paid models and execute only free tier models
            if is_budget_paused and self.factory.is_model_paid(
                model, role_config=self.role_config, slot_name=slot_name
            ):
                logger.warning(
                    f"[{self.task_role}] Budget paused: Skipping paid slot {slot_name} '{model}'. Falling back to free candidate."
                )
                continue

            # Skip slot if currently in active cooldown
            now = time.time()
            if slot_name in self._slot_cooldowns and self._slot_cooldowns[slot_name] > now:
                remaining = self._slot_cooldowns[slot_name] - now
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' (in cooldown for {remaining:.1f}s)")
                continue

            try:
                provider = self.factory._resolve_provider(model, role_config=self.role_config, slot_name=slot_name)
            except TypeError:
                provider = self.factory._resolve_provider(model)

            # TypeSafe / Jev models are System One decision engines and do not support top-level array schemas in classify_json
            if provider == "typesafe" and method_name == "classify_json" and not kwargs.get("jev_questions"):
                sch = kwargs.get("schema") or (args[2] if len(args) > 2 and isinstance(args[2], dict) else None)
                if isinstance(sch, dict) and sch.get("type") == "array":
                    last_error = f"TypeSafe model '{model}' ({slot_name}) does not support top-level array schema in classify_json"
                    logger.debug(
                        f"[{self.task_role}] Skipping {slot_name} '{model}' â€” "
                        f"TypeSafe Jev does not support array schemas in classify_json"
                    )
                    continue

            if not ProviderCircuitBreaker.is_provider_available(provider, model=model):
                logger.info(
                    f"[{self.task_role}] Skipping {slot_name} '{model}' â€” provider '{provider}' circuit is OPEN"
                )
                continue
            if ProviderCircuitBreaker.is_model_blacklisted(provider, model):
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' â€” model is blacklisted")
                continue
            if EndpointBlackhole.is_blackholed(model) or EndpointBlackhole.is_blackholed(provider):
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' â€” endpoint/model is blackholed")
                continue

            try:
                from monika.infrastructure.credentials.credential_pool import get_credential_pool

                cred_pool = get_credential_pool()
                if cred_pool:
                    try:
                        avail = cred_pool.is_model_available(model, provider=provider)
                    except TypeError:
                        avail = cred_pool.is_model_available(model)
                    if not avail:
                        logger.info(
                            f"[{self.task_role}] Skipping {slot_name} '{model}' â€” in CredentialPool model cooldown"
                        )
                        continue
            except Exception:
                pass

            # Cost-aware guidance: check baseline pricing if max_cost_per_call is configured
            if self.max_cost_per_call is not None:
                try:
                    from monika.infrastructure.providers.pricing_catalog import get_model_pricing

                    p = get_model_pricing(model)
                    est_in = min(4096, self.max_tokens // 2)
                    est_out = min(2048, self.max_tokens // 4)
                    est_cost = (est_in / 1_000_000.0) * p.input + (est_out / 1_000_000.0) * p.output
                    if est_cost > (self.max_cost_per_call * 1.5):
                        logger.warning(
                            f"[{self.task_role}] Slot '{slot_name}' model '{model}' baseline cost "
                            f"(${est_cost:.4f}) exceeds max_cost_per_call (${self.max_cost_per_call:.4f})."
                        )
                except Exception:
                    pass

            try:
                client = self.factory._create_client_instance(
                    model, self.role_config, slot_name=slot_name, task_role=self.task_role
                )
            except TypeError:
                client = self.factory._create_client_instance(model, self.role_config, slot_name=slot_name)
            if not client:
                continue
            client.role = self.task_role
            client.task_role = self.task_role
            is_none_thinking = str(getattr(self, "thinking_level", "")).lower() in ("none", "off") or str(
                getattr(client, "thinking_level", "")
            ).lower() in ("none", "off")
            if not is_none_thinking and self._dynamic_thinking_budget is not None:
                set_tb: Any = getattr(client, "set_thinking_budget", None)
                if callable(set_tb):
                    res_tb: Any = set_tb(self._dynamic_thinking_budget)
                    if inspect.isawaitable(res_tb):
                        await res_tb
                elif hasattr(client, "thinking_budget"):
                    client.thinking_budget = self._dynamic_thinking_budget
            elif is_none_thinking:
                set_tb = getattr(client, "set_thinking_budget", None)
                if callable(set_tb):
                    res_tb = set_tb(0)
                    if inspect.isawaitable(res_tb):
                        await res_tb
                elif hasattr(client, "thinking_budget"):
                    client.thinking_budget = 0

            slot_retries = 0
            slot_timeout = per_model_timeout
            method = getattr(client, method_name, None)
            while True:
                try:
                    method = getattr(client, method_name, None)
                    if not callable(method):
                        logger.debug(f"Client {client} does not implement callable method '{method_name}'")
                        break
                    # Safely clone mutable message lists / dicts while preserving unpicklable session objects
                    safe_args = [_safe_clone(a) for a in args]
                    safe_kwargs = {k: _safe_clone(v) for k, v in kwargs.items()}

                    # Dynamic capability clamping (prevent context/output token limit errors across fallback slots)
                    from monika.infrastructure.providers.capabilities import (
                        get_model_capabilities,
                        resolve_effective_max_tokens,
                    )

                    caps = get_model_capabilities(model)
                    wrapper_settings = getattr(self, "settings", None) or getattr(
                        getattr(self, "factory", None), "_settings", None
                    )
                    eff_slot_ceiling = resolve_effective_max_tokens(
                        model_name=model,
                        provider_name=provider,
                        requested_max_tokens=safe_kwargs.get("max_tokens") or getattr(client, "max_tokens", None),
                        thinking_level=getattr(client, "thinking_level", "none"),
                        thinking_budget=getattr(client, "thinking_budget", 0),
                        settings=wrapper_settings,
                    )
                    if "max_tokens" in safe_kwargs and isinstance(safe_kwargs["max_tokens"], int):
                        safe_kwargs["max_tokens"] = min(safe_kwargs["max_tokens"], eff_slot_ceiling)
                    elif isinstance(getattr(client, "max_tokens", None), int) and not isinstance(
                        client.max_tokens, bool
                    ):
                        safe_kwargs["max_tokens"] = eff_slot_ceiling

                    # Memoized schema rejection check: strip native response_format if previously rejected
                    if (provider, model) in _UNSUPPORTED_SCHEMA_ROUTES and "response_format" in safe_kwargs:
                        safe_kwargs.pop("response_format", None)

                    # Cleanse opaque reasoning signatures if cross-provider model switch occurs
                    target_prov = getattr(client, "provider_name", "") or provider
                    preserve_fn = getattr(client, "_preserve_reasoning_signatures", None)
                    if callable(preserve_fn):
                        if "messages" in safe_kwargs and isinstance(safe_kwargs["messages"], list):
                            safe_kwargs["messages"] = preserve_fn(safe_kwargs["messages"], target_prov)
                        elif safe_args and isinstance(safe_args[0], list):
                            safe_args[0] = preserve_fn(safe_args[0], target_prov)

                    # Adapt Jev-specific arguments if falling back to generative LLM provider
                    if provider != "typesafe":
                        jev_q = safe_kwargs.get("jev_questions")
                        if isinstance(jev_q, (dict, list)):
                            from monika.core.primitives.jev_primitives import (
                                jev_questions_to_schema,
                                list_to_jev_questions,
                            )

                            if isinstance(jev_q, list):
                                jev_q = list_to_jev_questions(jev_q)

                            if method_name == "classify_json" and not safe_kwargs.get("schema"):
                                safe_kwargs["schema"] = jev_questions_to_schema(jev_q)
                            elif method_name == "generate_content" and not safe_kwargs.get("response_schema"):
                                safe_kwargs["response_schema"] = jev_questions_to_schema(jev_q)

                        # If user prompt is empty but structured state is provided, synthesize state prompt
                        if "state" in safe_kwargs:
                            st_val = safe_kwargs.get("state")
                            st_str = (
                                json.dumps(st_val, indent=2, sort_keys=True)
                                if isinstance(st_val, (dict, list))
                                else str(st_val)
                            )
                            if method_name == "classify_json":
                                if safe_args and (safe_args[0] == "" or safe_args[0] is None):
                                    safe_args[0] = f"Evaluate the following state context:\n{st_str}"
                                elif not safe_args and safe_kwargs.get("prompt") in ("", None):
                                    safe_kwargs["prompt"] = f"Evaluate the following state context:\n{st_str}"
                            elif method_name == "generate_content":
                                if safe_kwargs.get("user_message") in ("", None):
                                    safe_kwargs["user_message"] = f"Evaluate the following state context:\n{st_str}"

                    # â”€â”€ Hook Interception: pre_llm_call & prompt section injection â”€â”€
                    try:
                        import importlib

                        engine = importlib.import_module("monika.application.plugins.engine.engine").get_plugin_engine()
                        if engine:
                            await engine.emit_hook(
                                "pre_llm_call",
                                task_role=self.task_role,
                                model=model,
                                method=method_name,
                                kwargs=safe_kwargs,
                            )
                    except Exception as h_err:
                        logger.debug(f"[LLMDispatch] pre_llm_call notice: {h_err}")

                    try:
                        import importlib

                        psr = importlib.import_module(
                            "monika.application.analysis.prompt_sections"
                        ).get_prompt_section_registry()
                        ctx_info = {"task_role": self.task_role, "model": model}

                        def _format_system_prompt(sys_val):
                            if isinstance(sys_val, str):
                                return psr.format_full_prompt(sys_val, ctx_info)
                            elif isinstance(sys_val, (list, tuple)):
                                return type(sys_val)(
                                    psr.format_full_prompt(s, ctx_info) if isinstance(s, str) else s for s in sys_val
                                )
                            return sys_val

                        if "system" in safe_kwargs:
                            safe_kwargs["system"] = _format_system_prompt(safe_kwargs["system"])
                        elif "system_prompt" in safe_kwargs:
                            safe_kwargs["system_prompt"] = _format_system_prompt(safe_kwargs["system_prompt"])
                    except Exception as ps_err:
                        logger.debug(f"[LLMDispatch] prompt sections notice: {ps_err}")

                    try:
                        sig = inspect.signature(method)
                        has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                        if not has_var_kwargs:
                            safe_kwargs = {k: v for k, v in safe_kwargs.items() if k in sig.parameters}
                    except Exception as sig_err:
                        logger.debug(f"[LLMDispatch] signature filter notice: {sig_err}")

                    # Model-agnostic dynamic timeout floor:
                    # SOTA reasoning engines and multi-turn loops need sufficient time budget.
                    # Evaluates thinking level, thinking budget, and role turns dynamically without hardcoding model names.
                    from monika.infrastructure.providers.capabilities import resolve_stale_timeout_floor

                    raw_lvl = getattr(client, "thinking_level", None)
                    model_thinking_level = (
                        raw_lvl
                        if isinstance(raw_lvl, str)
                        else (self.thinking_level if isinstance(self.thinking_level, str) else None)
                    )

                    raw_budget = getattr(client, "thinking_budget", None)
                    model_thinking_budget = (
                        int(raw_budget)
                        if isinstance(raw_budget, (int, float))
                        else (
                            int(self._dynamic_thinking_budget)
                            if isinstance(self._dynamic_thinking_budget, (int, float))
                            else None
                        )
                    )

                    caps = getattr(client, "capabilities", None)
                    supports_native_thinking = getattr(caps, "supports_native_thinking", False) is True

                    if explicit_timeout is not None:
                        slot_timeout = per_model_timeout
                    elif method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
                        role_turns = float((self.role_config or {}).get("max_tool_turns") or 15)
                        model_floor = resolve_stale_timeout_floor(
                            model_name=model,
                            default_timeout=0.0,
                            thinking_level=model_thinking_level,
                            thinking_budget=model_thinking_budget,
                            supports_native_thinking=supports_native_thinking,
                        )
                        is_thinking_active = (
                            (model_thinking_level and str(model_thinking_level).lower() not in ("none", "off", ""))
                            or bool(model_thinking_budget and model_thinking_budget > 0)
                            or model_floor >= 180.0
                        )
                        if is_thinking_active:
                            slot_timeout = max(per_model_timeout, model_floor, role_turns * 90.0, 600.0)
                        else:
                            slot_timeout = max(per_model_timeout, role_turns * 45.0, 300.0)
                    else:
                        model_floor = resolve_stale_timeout_floor(
                            model_name=model,
                            default_timeout=per_model_timeout,
                            thinking_level=model_thinking_level,
                            thinking_budget=model_thinking_budget,
                            supports_native_thinking=supports_native_thinking,
                        )
                        is_thinking_active = (
                            (model_thinking_level and str(model_thinking_level).lower() not in ("none", "off", ""))
                            or bool(model_thinking_budget and model_thinking_budget > 0)
                            or model_floor >= 180.0
                        )
                        slot_timeout = max(per_model_timeout, model_floor, 360.0 if is_thinking_active else 180.0)

                    call_coro: Any = method(*safe_args, **safe_kwargs)
                    result = await asyncio.wait_for(call_coro, timeout=slot_timeout)

                    if method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages", "run_tool_agent"]:
                        if isinstance(result, dict) and result.get("success") is False:
                            # Treat as failure if the agent loop failed completely
                            last_failed_dict = result
                            last_error = result.get("error", "Unknown error in agent loop")
                            logger.warning(f"Model {model} ({slot_name}) failed in {method_name}: {last_error}")
                            cnt = self._slot_backoff_count.get(slot_name, 0)
                            cd_duration = min(60.0 * (2**cnt), 1800.0)
                            self._slot_cooldowns[slot_name] = time.time() + cd_duration
                            self._slot_backoff_count[slot_name] = cnt + 1
                            if slot_name == "primary":
                                self._primary_cooldown_until = self._slot_cooldowns[slot_name]
                            break

                    is_empty_res = (result is None) or (
                        method_name in ["generate", "generate_content"] and not str(result).strip()
                    )
                    if is_empty_res and method_name in ["generate", "classify_json", "generate_content"]:
                        logger.warning(f"Model {model} ({slot_name}) returned empty/None in {method_name}")
                        last_error = f"Model {model} ({slot_name}) returned empty/None response"
                        cnt = self._slot_backoff_count.get(slot_name, 0)
                        cd_duration = min(60.0 * (2**cnt), 1800.0)
                        self._slot_cooldowns[slot_name] = time.time() + cd_duration
                        self._slot_backoff_count[slot_name] = cnt + 1
                        if slot_name == "primary":
                            self._primary_cooldown_until = self._slot_cooldowns[slot_name]
                        break

                    # Normalize metadata when fallback generative LLM answers a Jev-intended task
                    if provider != "typesafe" and isinstance(result, dict):
                        result.setdefault("_confidence", 0.85)
                        result.setdefault("_is_fallback", True)
                        if "_is_high_confidence" not in result:
                            result["_is_high_confidence"] = True

                    self.model = model
                    self._active_slot = slot_name
                    if isinstance(result, dict):
                        result["model_used"] = model
                    self.thinking_level = getattr(client, "thinking_level", self.thinking_level)
                    ProviderCircuitBreaker.record_provider_success(provider, model=model)
                    # Reset backoff count and clear cooldown for this slot on success
                    self._slot_backoff_count[slot_name] = 0
                    self._slot_cooldowns.pop(slot_name, None)
                    if slot_name == "primary":
                        self._primary_cooldown_until = None

                    if slot_name != "primary":
                        msg = (
                            f"[LLMFallbackAudit] Task role '{self.task_role}' downgraded from primary '{self.primary}' "
                            f"to {slot_name} '{model}' (method={method_name}, prior_error={last_error})"
                        )
                        logger.warning(msg)
                        try:

                            async def _record_fallback_log(text_msg: str):
                                try:
                                    from monika.infrastructure.database.db import get_session
                                    from monika.infrastructure.database.models import ActivityLog

                                    async with get_session() as s:
                                        s.add(
                                            ActivityLog(
                                                category="system",
                                                description=text_msg[:500],
                                                actor="llm_factory",
                                            )
                                        )
                                        await s.commit()
                                except Exception as db_err:
                                    logger.debug(f"Failed to record fallback log to DB: {db_err}")

                            asyncio.create_task(_record_fallback_log(msg))
                        except Exception:
                            pass

                    # â”€â”€ Hook Interception: post_llm_call â”€â”€
                    try:
                        import importlib

                        engine = importlib.import_module("monika.application.plugins.engine.engine").get_plugin_engine()
                        if engine:
                            await engine.emit_hook(
                                "post_llm_call",
                                task_role=self.task_role,
                                model=model,
                                method=method_name,
                                response=result,
                            )
                    except Exception as h_err:
                        logger.debug(f"[LLMDispatch] post_llm_call notice: {h_err}")

                    return result
                except (asyncio.TimeoutError, StreamTimeoutError, StreamSafetyTimeoutError) as timeout_err:
                    # Attempt 1x dual-protocol non-streaming fallback if stream failed
                    if (
                        kwargs.get("stream", True)
                        and method_name in ["generate", "generate_content"]
                        and callable(method)
                    ):
                        try:
                            logger.info(
                                f"[{self.task_role}] Stream timeout on {slot_name}/{model}, attempting 1x non-streaming fallback..."
                            )
                            ns_kwargs = dict(kwargs)
                            ns_kwargs["stream"] = False
                            ns_coro: Any = method(*args, **ns_kwargs)
                            ns_res = await asyncio.wait_for(ns_coro, timeout=25.0)
                            if ns_res is not None:
                                self.model = model
                                self._active_slot = slot_name
                                self._slot_backoff_count[slot_name] = 0
                                self._slot_cooldowns.pop(slot_name, None)
                                return ns_res
                        except Exception as ns_err:
                            logger.debug(f"Non-streaming fallback failed: {ns_err}")

                    from monika.infrastructure.providers.provider_failover_classifier import FailoverReason

                    reason = FailoverReason.NETWORK_TIMEOUT
                    detail = (
                        f" ({timeout_err})"
                        if isinstance(timeout_err, (StreamTimeoutError, StreamSafetyTimeoutError))
                        else f" after {slot_timeout:.0f}s"
                    )
                    last_error = f"Model {model} ({slot_name}) timed out in {method_name}{detail}"
                    logger.warning(f"{last_error}. Trying next fallback...")

                    ProviderCircuitBreaker.record_provider_failure(
                        provider, is_server_or_timeout=True, reason="timeout", model=model
                    )

                    cnt = self._slot_backoff_count.get(slot_name, 0)
                    cd_duration = min(60.0 * (2**cnt), 1800.0)
                    self._slot_cooldowns[slot_name] = time.time() + cd_duration
                    self._slot_backoff_count[slot_name] = cnt + 1
                    if slot_name == "primary":
                        self._primary_cooldown_until = self._slot_cooldowns[slot_name]

                    last_failed_dict = {
                        "slot": slot_name,
                        "model": model,
                        "reason": reason.value,
                        "detail": detail,
                    }
                    break
                except Exception as e:
                    # Memoize unsupported response_format if model returned schema rejection error
                    err_msg = str(e).lower()
                    if "response_format" in err_msg or "schema validation" in err_msg or "json_schema" in err_msg:
                        _UNSUPPORTED_SCHEMA_ROUTES.add((provider, model))
                        logger.warning(
                            f"[{self.task_role}] Memoized unsupported response_format for {provider}/{model}"
                        )
                        if "response_format" in kwargs and slot_retries < 1:
                            slot_retries += 1
                            kwargs.pop("response_format", None)
                            logger.info(
                                f"[{self.task_role}] Retrying {slot_name}/{model} in-place without response_format"
                            )
                            continue

                    # â”€â”€ C4: STRUCTURED ERROR CLASSIFICATION â”€â”€
                    from monika.infrastructure.providers.provider_failover_classifier import (
                        FailoverReason,
                        classify_error,
                    )

                    reason, detail = classify_error(e)

                    logger.warning(
                        f"[{self.task_role}] {slot_name}/{model} error: "
                        f"reason={reason.value}, detail={detail}, type={type(e).__name__}"
                    )

                    # Strategy 1: Compress â€” don't failover for agent loops, but failover for single-turn calls
                    if reason.should_compress:
                        if method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages", "run_tool_agent"]:
                            logger.info(
                                f"[{self.task_role}] {reason.value} â€” "
                                f"propagating for upstream compaction (not failing over)"
                            )
                            raise  # Let agent_harness.py C2 handle compression
                        else:
                            logger.info(
                                f"[{self.task_role}] {reason.value} in single-turn {method_name} â€” "
                                f"failing over to next fallback candidate."
                            )

                    # Strategy 1b: Completion ceiling exceeded â€” clamp max_tokens and retry same slot in-place
                    if reason.is_completion_ceiling:
                        from monika.infrastructure.providers.provider_failover_classifier import (
                            extract_completion_ceiling,
                        )

                        ceiling = extract_completion_ceiling(e)
                        if ceiling and ceiling > 0 and slot_retries < 1:
                            slot_retries += 1
                            logger.info(
                                f"[{self.task_role}] Completion ceiling exceeded ({ceiling} tokens). "
                                f"Clamping max_tokens and retrying {slot_name} in-place."
                            )
                            if hasattr(client, "max_tokens"):
                                client.max_tokens = min(client.max_tokens, ceiling)
                            if "max_tokens" in kwargs:
                                kwargs["max_tokens"] = min(kwargs["max_tokens"], ceiling)
                            continue

                    # Strategy 1c: Hard Quota / Billing Depleted â€” immediate blacklist for 7200s and failover
                    if reason.is_hard_quota_exhausted:
                        logger.error(
                            f"[{self.task_role}] Hard quota / credits exhausted for {provider}/{model}. "
                            f"Blacklisting model for 7200s and failing over immediately."
                        )
                        ProviderCircuitBreaker.blacklist_model(provider, model, reason=reason.value, duration=7200.0)
                        self._slot_cooldowns[slot_name] = time.time() + 7200.0
                        last_error = e
                        last_failed_dict = {
                            "slot": slot_name,
                            "model": model,
                            "reason": reason.value,
                            "detail": detail,
                        }
                        break

                    is_hot_path = getattr(self, "task_role", "") in HOT_PATH_ROLES
                    is_rate_or_auth = reason in (
                        FailoverReason.RATE_LIMIT_API,
                        FailoverReason.RATE_LIMIT_MODEL,
                        FailoverReason.TRANSIENT_RATE_LIMIT,
                        FailoverReason.UPSTREAM_RATE_LIMIT,
                        FailoverReason.AUTH_TRANSIENT,
                    )

                    # Strategy 2: In-Flight Key Rotation from APICredentialPool
                    if is_rate_or_auth:
                        try:
                            from monika.infrastructure.credentials.credential_pool import CredentialPool

                            cred_pool = CredentialPool.get_instance()
                            curr_key = getattr(client, "api_key", None) or getattr(client, "_api_key", None)
                            if curr_key:
                                cred_pool.report_rate_limit(provider, curr_key, model=model)
                            next_key = cred_pool.get_key(provider, model=model, is_hot_path=is_hot_path)
                            if next_key and next_key != curr_key:
                                logger.info(
                                    f"[{self.task_role}] In-flight key rotation for {provider} on {slot_name}. Retrying immediately."
                                )
                                if hasattr(client, "set_api_key") and callable(client.set_api_key):
                                    client.set_api_key(next_key)
                                else:
                                    if hasattr(client, "api_key"):
                                        setattr(client, "api_key", next_key)
                                    if hasattr(client, "_api_key"):
                                        setattr(client, "_api_key", next_key)
                                    underlying = getattr(client, "client", None)
                                    if underlying is not None and hasattr(underlying, "api_key"):
                                        setattr(underlying, "api_key", next_key)
                                continue
                        except Exception as pool_err:
                            logger.debug(f"Credential pool rotation pass-through: {pool_err}")

                    # Strategy 3: Retry same model with backoff OR Eager Failover for hot paths
                    can_failover = (
                        reason.can_failover(is_hot_path=is_hot_path)
                        if hasattr(reason, "can_failover")
                        else reason.should_failover
                    )
                    if not can_failover and reason.max_retries > 0:
                        if slot_retries < reason.max_retries:
                            backoff = reason.backoff_seconds * (1.5**slot_retries)
                            slot_retries += 1
                            logger.info(
                                f"[{self.task_role}] {reason.value} â€” retrying {slot_name} "
                                f"after {backoff:.1f}s (attempt {slot_retries}/{reason.max_retries})"
                            )
                            if backoff > 0:
                                await asyncio.sleep(backoff)
                            continue

                    # Strategy 4: Failover to next model with exponential cooldown
                    is_server_or_timeout = reason in (
                        FailoverReason.SERVER_ERROR,
                        FailoverReason.NETWORK_TIMEOUT,
                        FailoverReason.NETWORK_CONNECTION,
                    )
                    ProviderCircuitBreaker.record_provider_failure(
                        provider, is_server_or_timeout=is_server_or_timeout, reason=reason.value, model=model
                    )
                    if reason in (
                        FailoverReason.AUTH_PERMANENT,
                        FailoverReason.BILLING_EXHAUSTED,
                        FailoverReason.HARD_QUOTA_EXHAUSTED,
                        FailoverReason.MODEL_NOT_FOUND,
                    ):
                        cd_time = 7200.0 if reason.is_hard_quota_exhausted else 1800.0
                        ProviderCircuitBreaker.blacklist_model(provider, model, reason=reason.value, duration=cd_time)

                    if reason == FailoverReason.NETWORK_CONNECTION or "connection refused" in str(e).lower():
                        EndpointBlackhole.blackhole_endpoint(model, ttl_seconds=30.0)
                        EndpointBlackhole.blackhole_endpoint(provider, ttl_seconds=30.0)

                    # Check for upstream Retry-After delay header (honoring provider guidance)
                    from monika.infrastructure.providers.base_provider import extract_retry_after

                    retry_delay = extract_retry_after(e)
                    if retry_delay and retry_delay > 0:
                        cd_duration = min(retry_delay, 1800.0)
                        logger.info(
                            f"[{self.task_role}] Honoring upstream Retry-After delay of {cd_duration:.1f}s for {slot_name}/{model}"
                        )
                    else:
                        cnt = self._slot_backoff_count.get(slot_name, 0)
                        cd_duration = min(60.0 * (2**cnt), 1800.0)
                    self._slot_cooldowns[slot_name] = time.time() + cd_duration
                    self._slot_backoff_count[slot_name] = self._slot_backoff_count.get(slot_name, 0) + 1
                    if slot_name == "primary":
                        self._primary_cooldown_until = self._slot_cooldowns[slot_name]

                    last_error = e
                    last_failed_dict = {
                        "slot": slot_name,
                        "model": model,
                        "reason": reason.value,
                        "detail": detail,
                    }

                    if is_hot_path:
                        logger.warning(
                            f"[AutoFailover] HOT PATH role '{self.task_role}' automatically failing over "
                            f"from {slot_name}/{model} due to {reason.value}. Zero-consent failover engaged."
                        )

                        async def _notify_failover_post_facto(role: str, failed_model: str, err_reason: str):
                            try:
                                from monika.infrastructure.notifications.telegram_notifier import get_notifier

                                await get_notifier().send_alert(
                                    f"[PERINGATAN] *HOT PATH Auto-Failover*\n"
                                    f"Role: `{role}`\n"
                                    f"Failed: `{failed_model}`\n"
                                    f"Reason: `{err_reason}`\n"
                                    f"Switching to next candidate in fallback chain."
                                )
                            except Exception:
                                pass

                        try:
                            asyncio.create_task(_notify_failover_post_facto(self.task_role, model, reason.value))
                        except Exception:
                            pass

                    break

        if last_error is None:
            if is_budget_paused:
                last_error = (
                    f"AI Budget is paused and all paid candidate models were skipped "
                    f"(no eligible free fallback available or all failed) for task_role='{self.task_role}'"
                )
            else:
                last_error = "All candidate models skipped (active cooldown or provider circuits open)"

        logger.error(f"All fallback models failed for {method_name}. Last error: {last_error}")

        # Return sensible defaults on complete failure
        if method_name in ["generate", "generate_content", "classify_json", "system_one"]:
            return None
        elif method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
            res = {
                "success": False,
                "error": str(last_error),
                "tool_calls_made": 0,
                "turns": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            if isinstance(last_failed_dict, dict):
                res.update(last_failed_dict)
                res["success"] = False
                res["error"] = str(last_error)
            return res
        elif method_name == "run_tool_agent":
            return MockResponse(
                content=[MockBlock("text", text="All fallback models failed")],
                stop_reason="error",
                input_tokens=0,
                output_tokens=0,
            )

        raise Exception(f"All fallback models failed. Last error: {last_error}")

    def _get_client(self, slot_name: str = "primary") -> Optional[BaseLLMClient]:
        """Returns client instance for specified slot (defaults to active primary)."""
        if slot_name == "primary":
            model = self.primary
        elif slot_name.startswith("fallback_"):
            try:
                fb_idx = int(slot_name.split("_", 1)[1]) - 1
                model = (
                    self.fallbacks[fb_idx]
                    if 0 <= fb_idx < len(self.fallbacks)
                    else (self.fallbacks[0] if self.fallbacks else self.primary)
                )
            except ValueError, IndexError:
                model = self.fallbacks[0] if self.fallbacks else self.primary
        else:
            model = self.fallbacks[0] if self.fallbacks else self.primary
        try:
            return self.factory._create_client_instance(
                model, self.role_config, slot_name=slot_name, task_role=self.task_role
            )
        except TypeError:
            return self.factory._create_client_instance(model, self.role_config, slot_name=slot_name)

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[str]:
        call_kwargs = dict(system=system, temperature=temperature, **kwargs)
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("generate", prompt, **call_kwargs)

    async def generate_content(
        self,
        system_prompt: str = "",
        user_message: str = "",
        response_schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[str]:
        call_kwargs = dict(
            system_prompt=system_prompt,
            user_message=user_message,
            response_schema=response_schema,
            temperature=temperature,
            **kwargs,
        )
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("generate_content", **call_kwargs)

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[dict]:
        call_kwargs = dict(system_prompt=system_prompt, schema=schema, temperature=temperature, **kwargs)
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("classify_json", prompt, **call_kwargs)

    async def system_one(self, state: Any, questions: dict, timeout: float = 15.0, **kwargs: Any) -> Any:
        return await self._execute_with_fallback(
            "system_one", state=state, questions=questions, timeout=timeout, **kwargs
        )

    async def run_tool_agent(
        self, messages: list, tools: list, system_prompt: Any, tool_choice: Optional[Any] = None, **kwargs
    ) -> MockResponse:
        return await self._execute_with_fallback(
            "run_tool_agent", messages, tools, system_prompt, tool_choice=tool_choice, **kwargs
        )

    async def run_agent(
        self,
        session,
        system_prompt: str | tuple[str, str] | Any,
        user_message: str,
        tools: list,
        stage_name: str = "unknown",
        extra_context: Optional[str] = None,
        prefetch_satisfied_tools: Optional[set] = None,
        **kwargs,
    ) -> dict:
        return await self._execute_with_fallback(
            "run_agent",
            session,
            system_prompt,
            user_message,
            tools,
            stage_name=stage_name,
            extra_context=extra_context,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            **kwargs,
        )

    async def run_chat_loop(
        self,
        system_prompt: str,
        conversation_history: list,
        new_user_message: str,
        tools: list,
        tool_executor=None,
        **kwargs,
    ) -> dict:
        return await self._execute_with_fallback(
            "run_chat_loop",
            system_prompt,
            conversation_history,
            new_user_message,
            tools,
            tool_executor=tool_executor,
            **kwargs,
        )

    async def run_agent_from_messages(
        self,
        session,
        system_prompt: str | tuple[str, str] | Any,
        messages: list,
        tools: list,
        max_tool_turns: int = 15,
        stage_name: str = "unknown",
        prefetch_satisfied_tools: Optional[set] = None,
        **kwargs,
    ) -> dict:
        return await self._execute_with_fallback(
            "run_agent_from_messages",
            session,
            system_prompt,
            messages,
            tools,
            max_tool_turns=max_tool_turns,
            stage_name=stage_name,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            **kwargs,
        )
