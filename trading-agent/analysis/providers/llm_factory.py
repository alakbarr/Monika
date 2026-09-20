"""
LLM Factory: Satu pintu masuk untuk membuat klien LLM.

Semua komponen WAJIB menggunakan factory ini.
claude_client.py dan gemini_client.py SUDAH DIHAPUS.
"""

import logging
import copy
import asyncio
import inspect
from typing import Optional, Any
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock
from utils.api.streaming import StreamTimeoutError, StreamSafetyTimeoutError
import time

logger = logging.getLogger("TradingAgent.LLMFactory")

# Memoized routes that reject native response_format / json_schema
_UNSUPPORTED_SCHEMA_ROUTES: set[tuple[str, str]] = set()

# Trading hot-path roles requiring zero-downtime eager failover
HOT_PATH_ROLES: set[str] = {
    "stage1_fundamental", "stage2_per_asset_primary", "stage2_per_asset_secondary",
    "stage2", "stage2_essential", "debate", "debate_judge", "bull_debater", "bear_debater",
    "bull_analyst", "bear_analyst", "judge", "investment_judge", "risk_gate",
    "pre_commit_gate", "execution_verifier", "position_guardian", "trailing_stop",
    "trigger_evaluator", "reactive_graph", "alpha_synthesis", "signal_arbitrator"
}

class ProviderCircuitBreaker:
    """
    Tracks consecutive 5xx/timeouts and permanent entitlement errors across providers.
    States: CLOSED (normal), OPEN (cooldown after 3 failures), HALF_OPEN (1 canary probe).
    """
    _states: dict[str, str] = {}
    _consecutive_failures: dict[str, int] = {}
    _open_until: dict[str, float] = {}
    _blacklisted_models: dict[tuple[str, str], float] = {}
    _blacklist_reasons: dict[tuple[str, str], str] = {}
    
    FAILURE_THRESHOLD: int = 3
    COOLDOWN_SECONDS: float = 60.0

    @classmethod
    def is_provider_available(cls, provider: str) -> bool:
        state = cls._states.get(provider, "CLOSED")
        if state == "OPEN":
            now = time.time()
            if now >= cls._open_until.get(provider, 0.0):
                cls._states[provider] = "HALF_OPEN"
                logger.info(f"[CircuitBreaker] Provider '{provider}' transitioning OPEN -> HALF_OPEN (canary probe allowed)")
                return True
            return False
        return True

    @classmethod
    def record_provider_success(cls, provider: str) -> None:
        if cls._consecutive_failures.get(provider, 0) > 0 or cls._states.get(provider) != "CLOSED":
            logger.info(f"[CircuitBreaker] Provider '{provider}' healthy. Circuit CLOSED.")
        cls._consecutive_failures[provider] = 0
        cls._states[provider] = "CLOSED"
        cls._open_until.pop(provider, None)

    @classmethod
    def record_provider_failure(cls, provider: str, is_server_or_timeout: bool = True, reason: str = "") -> None:
        if is_server_or_timeout:
            cnt = cls._consecutive_failures.get(provider, 0) + 1
            cls._consecutive_failures[provider] = cnt
            if cnt >= cls.FAILURE_THRESHOLD:
                cls._states[provider] = "OPEN"
                cls._open_until[provider] = time.time() + cls.COOLDOWN_SECONDS
                logger.warning(
                    f"[CircuitBreaker] Provider '{provider}' circuit OPEN ({cnt} consecutive server/timeout errors). "
                    f"Cooldown for {cls.COOLDOWN_SECONDS:.0f}s. Reason: {reason}"
                )

    @classmethod
    def blacklist_model(cls, provider: str, model: str, reason: str, duration: float = 1800.0) -> None:
        key = (provider, model)
        cls._blacklisted_models[key] = time.time() + duration
        cls._blacklist_reasons[key] = reason
        logger.warning(f"[CapabilityBlacklist] Blacklisting model '{model}' ({provider}) for {duration:.0f}s. Reason: {reason}")

    @classmethod
    def is_model_blacklisted(cls, provider: str, model: str) -> bool:
        key = (provider, model)
        if key in cls._blacklisted_models:
            if time.time() < cls._blacklisted_models[key]:
                return True
            cls._blacklisted_models.pop(key, None)
            cls._blacklist_reasons.pop(key, None)
        return False

    @classmethod
    def reset(cls) -> None:
        cls._states.clear()
        cls._consecutive_failures.clear()
        cls._open_until.clear()
        cls._blacklisted_models.clear()
        cls._blacklist_reasons.clear()


class LLMFactory:
    """
    Factory terpusat. Resolves:
    - provider detection dari model_catalog
    - thinking config per provider
    - rate limit checks
    - fallback chain orchestration
    """

    def __init__(self, settings: dict):
        self._settings = settings
        self._llm_config = settings.get("llm", {})
        self._providers = self._llm_config.get("providers", {})
        self._catalog = self._llm_config.get("model_catalog", {})
        self._task_roles = self._llm_config.get("task_roles", {})

    def get_client_for_task(self, task_role: str) -> "BaseLLMClient":
        """
        Buat client untuk task role tertentu.
        """
        role_config = self._task_roles.get(task_role)
        if not role_config:
            logger.warning(f"Unknown task role: {task_role}, falling back to default gemini")
            role_config = {
                "primary": "gemini-3.5-flash-lite",
                "max_tokens": 8192,
                "max_tool_turns": 15,
                "temperature": 0.0,
                "thinking": {"gemini": "none"}
            }

        primary_model = role_config.get("primary", "gemini-3.5-flash-lite")
        fallback_chain: list[str] = [
            str(role_config[f"fallback_{i}"])
            for i in range(1, 11)
            if role_config.get(f"fallback_{i}")
        ]

        return self._create_client_with_fallback(primary_model, fallback_chain, role_config, task_role=task_role)


    def _resolve_provider(self, model_name: str) -> str:
        model_info = self._catalog.get(model_name, {})
        if "provider" in model_info:
            return model_info["provider"]
            
        # Guess provider
        name = model_name.lower()
        if "openrouter" in name or "ox-alpha" in name or name.startswith("stealth/"):
            return "openrouter"
        if "jev" in name or "typesafe" in name:
            return "typesafe"
        if "glm" in name or "kimi" in name or "minimax" in name or "mimo" in name or "muse" in name:
            return "openrouter"
        if name.startswith("groq"):
            return "groq"
        if "/" in name:
            return "openrouter"
        if "flash" in name and "gemini" in name:
            return "gemini"
        if "gemini" in name:
            return "gemini"
        if "claude" in name or "haiku" in name:
            return "anthropic"
        if "gpt" in name:
            return "openai"
        if "deepseek" in name:
            return "deepseek"
        if "ollama" in name:
            # ponytail: name-guess only; qwen/llama removed — bare names like
            # "qwen3.8-27b" silently routed to local ollama (no tool calling).
            # Catalog entries carry explicit provider; unknown names now fail
            # visibly via openai_compatible + _check_model_roles startup guard.
            return "ollama"
        if "grok" in name:
            return "openai_compatible"
        if "groq" in name:
            return "groq"
        return "openai_compatible"

    def _resolve_thinking_level(
        self,
        model_name: str,
        role_config: dict,
        provider_name: str,
        slot_name: Optional[str] = None
    ) -> str:
        """
        Resolves thinking level with multi-tier granular priority:
        1. role_config['thinking'][exact_model_name]
        2. role_config['thinking'][alias_or_short_name] (e.g. stripped org prefix or alias match)
        3. role_config['thinking'][slot_name] (e.g. 'primary', 'fallback_1', 'fallback_2')
        4. role_config['thinking_by_model'][exact_model_name / short_name] (if separate section is used)
        5. model_catalog[model_name].get('default_thinking') (catalog-level default)
        6. role_config['thinking'][provider_name] (provider-level default in role)
        7. role_config['thinking'] (if string, e.g. 'high')
        8. 'none' (safe fallback)
        """
        thinking_cfg = role_config.get("thinking")
        
        if isinstance(thinking_cfg, dict):
            # 1. Exact model name
            if model_name in thinking_cfg:
                return str(thinking_cfg[model_name]).lower()
                
            # 2. Short name / stripped prefix (e.g., 'glm-5.2:free' for 'z-ai/glm-5.2:free')
            short_name = model_name.split("/")[-1] if "/" in model_name else model_name
            if short_name in thinking_cfg:
                return str(thinking_cfg[short_name]).lower()
                
            # Also check if without :free suffix
            base_name = short_name.split(":")[0] if ":" in short_name else short_name
            if base_name in thinking_cfg:
                return str(thinking_cfg[base_name]).lower()

            # 3. Slot name (e.g. 'primary', 'fallback_1', ...)
            if slot_name and slot_name in thinking_cfg:
                return str(thinking_cfg[slot_name]).lower()
                
            # 4. Provider level
            if provider_name in thinking_cfg:
                return str(thinking_cfg[provider_name]).lower()

        elif isinstance(thinking_cfg, str) and thinking_cfg.strip():
            return thinking_cfg.strip().lower()

        # Check thinking_by_model if present in role_config
        thinking_by_model = role_config.get("thinking_by_model")
        if isinstance(thinking_by_model, dict):
            if model_name in thinking_by_model:
                return str(thinking_by_model[model_name]).lower()
            short_name = model_name.split("/")[-1] if "/" in model_name else model_name
            if short_name in thinking_by_model:
                return str(thinking_by_model[short_name]).lower()

        # Check model catalog default
        cat_entry = self._catalog.get(model_name, {})
        if isinstance(cat_entry, dict) and "default_thinking" in cat_entry:
            return str(cat_entry["default_thinking"]).lower()

        return "none"

    def _create_client_instance(self, model_name: str, role_config: dict, slot_name: Optional[str] = None, task_role: Optional[str] = None) -> Optional[BaseLLMClient]:
        provider_name = self._resolve_provider(model_name)
        provider_config = self._providers.get(provider_name, {})
        
        # In a real scenario, we might want to fail gracefully, but for now we assume enabled
        if provider_config and not provider_config.get("enabled", True):
            logger.warning(f"Provider {provider_name} is disabled.")
            return None

        max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))
        
        thinking_level = self._resolve_thinking_level(model_name, role_config, provider_name, slot_name=slot_name)

        # Retrieve healthy API key from CredentialPool (M2)
        try:
            from utils.api.credential_pool import get_credential_pool
            cred_pool = get_credential_pool()
            pooled_key = cred_pool.get_key(provider_name)
        except Exception:
            cred_pool = None
            pooled_key = None

        client = None
        key_kwargs = {"api_key": pooled_key} if pooled_key else {}
        if provider_name == "anthropic":
            from analysis.providers.anthropic_provider import AnthropicProvider
            client = AnthropicProvider(model_name, max_tokens, max_tool_turns, thinking_level, self._settings, temperature, role=task_role, **key_kwargs)
        elif provider_name == "gemini":
            from analysis.providers.gemini_provider import GeminiProvider
            client = GeminiProvider(model_name, max_tokens, max_tool_turns, thinking_level, self._settings, temperature, role=task_role, **key_kwargs)
            if pooled_key and hasattr(client, "api_key"):
                setattr(client, "api_key", pooled_key)
        elif provider_name == "openai":
            from analysis.providers.openai_provider import OpenAIProvider
            client = OpenAIProvider(
                model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                thinking_level=thinking_level, settings=self._settings, temperature=temperature, role=task_role,
                **key_kwargs
            )
        elif provider_name == "deepseek":
            from analysis.providers.deepseek_provider import DeepSeekProvider
            client = DeepSeekProvider(
                model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                thinking_level=thinking_level, settings=self._settings, temperature=temperature, role=task_role,
                **key_kwargs
            )
        elif provider_name == "ollama":
            from analysis.providers.ollama_provider import OllamaProvider
            client = OllamaProvider(
                model_name, self._settings, max_tokens=max_tokens,
                max_tool_turns=max_tool_turns, thinking_level=thinking_level, role=task_role
            )
        elif provider_name == "groq":
            from analysis.providers.groq_provider import GroqProvider
            client = GroqProvider(
                model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                thinking_level=thinking_level, settings=self._settings, temperature=temperature, role=task_role,
                **key_kwargs
            )
        elif provider_name == "openrouter":
            from analysis.providers.openrouter_provider import OpenRouterProvider
            client = OpenRouterProvider(
                model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                thinking_level=thinking_level, settings=self._settings,
                temperature=temperature, role=task_role,
                **key_kwargs
            )
        elif provider_name == "typesafe":
            from analysis.providers.typesafe_provider import TypeSafeProvider
            base_url = provider_config.get("base_url", "https://api.typesafe.ai")
            confidence_thresh = float(role_config.get("confidence_threshold", 0.70))
            client = TypeSafeProvider(
                model=model_name,
                max_tokens=max_tokens,
                max_tool_turns=max_tool_turns,
                thinking_level="none",
                settings=self._settings,
                temperature=temperature,
                base_url=base_url,
                confidence_threshold=confidence_thresh,
                role=task_role,
                **key_kwargs
            )
        elif provider_name in ("openai_compatible",):
            from analysis.providers.openai_provider import OpenAIProvider
            base_url = provider_config.get("base_url", "http://localhost:8000/v1")
            client = OpenAIProvider(
                model_name, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                thinking_level=thinking_level, settings=self._settings,
                temperature=temperature, base_url=base_url, role=task_role,
                **key_kwargs
            )
        else:
            logger.error(f"Provider {provider_name} not implemented yet.")
            return None

        # SOTA Dynamic Thinking Budget Wiring
        if client is not None:
            try:
                from utils.llm.adaptive_thinking import PerSymbolAdaptiveThinkingAllocator
                if thinking_level and thinking_level != "none":
                    level_to_budget = {"low": 1024, "medium": 4096, "high": 10000, "max": 16000, "xhigh": 16000}
                    base_b = level_to_budget.get(thinking_level.lower(), 4000)
                    adaptive_budget = PerSymbolAdaptiveThinkingAllocator.get_thinking_budget_for_task(task_role or "", base_budget=base_b)
                else:
                    adaptive_budget = PerSymbolAdaptiveThinkingAllocator.get_thinking_budget_for_task(task_role or "")

                if hasattr(client, "set_thinking_budget"):
                    client.set_thinking_budget(adaptive_budget)
                elif hasattr(client, "thinking_budget"):
                    client.thinking_budget = adaptive_budget
            except Exception:
                pass

        return client

    def _create_client_with_fallback(self, primary: str, fallbacks: list[str], role_config: dict, task_role: str = "default") -> "BaseLLMClient":
        """
        Creates a wrapper client that implements fallback logic across providers.
        """
        return FallbackClientWrapper(self, primary, fallbacks, role_config, task_role=task_role)


def _safe_clone(val):
    """Deepcopy serializable data (like messages/tools) while skipping unpicklable objects (like AsyncSession)."""
    if val is None or isinstance(val, (int, float, str, bool, bytes)):
        return val
    type_name = type(val).__name__
    if any(unpicklable in type_name for unpicklable in ("Session", "Connection", "Engine", "Client", "Socket", "Loop", "Task")):
        return val
    if isinstance(val, list):
        return [_safe_clone(x) for x in val]
    if isinstance(val, dict):
        return {k: _safe_clone(v) for k, v in val.items()}
    if isinstance(val, set):
        return {_safe_clone(x) for x in val}
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
    def __init__(self, factory: LLMFactory, primary: str, fallbacks: list[str], role_config: dict, task_role: str = "default"):
        self.factory = factory
        self.primary = primary
        self.fallbacks = fallbacks
        self.role_config = role_config
        self.task_role = task_role
        self._primary_cooldown_until = None
        self._slot_cooldowns: dict[str, float] = {}
        self._slot_backoff_count: dict[str, int] = {}
        
        primary_provider = factory._resolve_provider(primary)
        primary_thinking = factory._resolve_thinking_level(primary, role_config, primary_provider, slot_name="primary")
        
        # Set attributes required by BaseLLMClient
        super().__init__(
            model=primary,
            max_tokens=role_config.get("max_tokens", 8192),
            max_tool_turns=role_config.get("max_tool_turns", 15),
            thinking_level=primary_thinking,
            settings=factory._settings,
            temperature=float(role_config.get("temperature", 0.0)),
            role=task_role
        )

        self._dynamic_thinking_budget = None
        try:
            from utils.llm.adaptive_thinking import PerSymbolAdaptiveThinkingAllocator, QuantizedThinkingAllocator
            raw_b = PerSymbolAdaptiveThinkingAllocator.get_thinking_budget_for_task(task_role)
            self._dynamic_thinking_budget = QuantizedThinkingAllocator.quantize(raw_b)
            self.thinking_budget = self._dynamic_thinking_budget
        except Exception:
            self.thinking_budget = 4096
            self._dynamic_thinking_budget = 4096

    def _maybe_restore_primary(self) -> bool:
        """Check if primary provider cooldown has expired and restore it."""
        import time
        now = time.time()
        expired = [s for s, t in self._slot_cooldowns.items() if now >= t]
        for s in expired:
            self._slot_cooldowns.pop(s, None)

        if not self._primary_cooldown_until:
            return False
        if now >= self._primary_cooldown_until:
            logger.info(
                f"[{self.task_role}][FallbackClientWrapper] Primary model '{self.primary}' "
                f"cooldown expired — restoring to primary."
            )
            self._primary_cooldown_until = None
            self.model = self.primary
            return True
        return False

    def set_thinking_budget(self, budget: int) -> None:
        """Sets thinking budget dynamically for wrapper and upcoming provider invocations."""
        from utils.llm.adaptive_thinking import QuantizedThinkingAllocator
        quantized = QuantizedThinkingAllocator.quantize(budget)
        self.thinking_budget = quantized
        self._dynamic_thinking_budget = quantized

    async def _execute_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        # Check dynamic runtime model hot-swap overrides
        try:
            from analysis.providers.runtime_model_registry import RuntimeModelRegistry
            registry = RuntimeModelRegistry.get_instance()
            hot_primary = registry.get_role_model(self.task_role, "primary")
            if hot_primary:
                self.primary = hot_primary
            for i in range(len(self.fallbacks)):
                hot_fb = registry.get_role_model(self.task_role, f"fallback_{i+1}")
                if hot_fb:
                    self.fallbacks[i] = hot_fb
        except Exception:
            pass

        if self._primary_cooldown_until or "primary" in self._slot_cooldowns:
            models_to_try = [
                (f"fallback_{i+1}", model) for i, model in enumerate(self.fallbacks)
            ]
            if not models_to_try:
                models_to_try = [("primary", self.primary)]
        else:
            models_to_try = [("primary", self.primary)] + [
                (f"fallback_{i+1}", model) for i, model in enumerate(self.fallbacks)
            ]
        last_error = None
        last_failed_dict = None

        # Check global budget circuit breaker
        bypass_budget = kwargs.pop("_bypass_budget_check", False)
        if not bypass_budget:
            try:
                from utils.analytics.cost_tracker import CostTracker
                if CostTracker.is_budget_paused_cached():
                    logger.critical(f"[CircuitBreaker] Global AI Budget is paused. Blocking LLM call for task_role='{self.task_role}'")
                    if method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
                        return {"success": False, "error": "AI Budget Paused", "status": "blocked"}
                    return None
            except Exception as e:
                logger.debug(f"[CircuitBreaker] Cached budget check error: {e}")
        
        # Stage-aware fast timeouts for hot-path trading
        explicit_timeout = kwargs.pop("_per_model_timeout", None)
        if explicit_timeout is not None:
            per_model_timeout = float(explicit_timeout)
        elif self.task_role in HOT_PATH_ROLES:
            max_turns = float((self.role_config or {}).get("max_tool_turns", 3))
            per_model_timeout = max(45.0, min(120.0, max_turns * 30.0))
        elif method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
            max_turns = float((self.role_config or {}).get("max_tool_turns", 15))
            per_model_timeout = max(300.0, max_turns * 45.0)
        else:
            per_model_timeout = 180.0

        for slot_name, model in models_to_try:
            # Skip slot if currently in active cooldown
            now = time.time()
            if slot_name in self._slot_cooldowns and self._slot_cooldowns[slot_name] > now:
                remaining = self._slot_cooldowns[slot_name] - now
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' (in cooldown for {remaining:.1f}s)")
                continue

            provider = self.factory._resolve_provider(model)
            if not ProviderCircuitBreaker.is_provider_available(provider):
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' — provider '{provider}' circuit is OPEN")
                continue
            if ProviderCircuitBreaker.is_model_blacklisted(provider, model):
                logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' — model is blacklisted")
                continue

            try:
                from utils.api.credential_pool import get_credential_pool
                cred_pool = get_credential_pool()
                if cred_pool and not cred_pool.is_model_available(model):
                    logger.info(f"[{self.task_role}] Skipping {slot_name} '{model}' — in CredentialPool model cooldown")
                    continue
            except Exception:
                pass

            client = self.factory._create_client_instance(model, self.role_config, slot_name=slot_name)
            if not client:
                continue
            client.role = self.task_role
            client.task_role = self.task_role
            if self._dynamic_thinking_budget is not None:
                set_tb: Any = getattr(client, "set_thinking_budget", None)
                if callable(set_tb):
                    res_tb: Any = set_tb(self._dynamic_thinking_budget)
                    if inspect.isawaitable(res_tb):
                        await res_tb
                elif hasattr(client, "thinking_budget"):
                    client.thinking_budget = self._dynamic_thinking_budget
                
            slot_retries = 0
            while True:
                try:
                    method = getattr(client, method_name)
                    # Safely clone mutable message lists / dicts while preserving unpicklable session objects
                    safe_args = [_safe_clone(a) for a in args]
                    safe_kwargs = {k: _safe_clone(v) for k, v in kwargs.items()}

                    # Dynamic capability clamping (prevent context/output token limit errors)
                    from analysis.providers.capabilities import get_model_capabilities
                    caps = get_model_capabilities(model)
                    if caps and caps.max_output_tokens:
                        if "max_tokens" in safe_kwargs and isinstance(safe_kwargs["max_tokens"], int):
                            if safe_kwargs["max_tokens"] > caps.max_output_tokens:
                                safe_kwargs["max_tokens"] = caps.max_output_tokens

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

                    result = await asyncio.wait_for(
                        method(*safe_args, **safe_kwargs),
                        timeout=per_model_timeout
                    )
                    
                    if method_name in ["run_agent", "run_chat_loop", "run_agent_from_messages"]:
                        if isinstance(result, dict) and result.get("success") is False:
                            # Treat as failure if the agent loop failed completely
                            last_failed_dict = result
                            last_error = result.get("error", "Unknown error in agent loop")
                            logger.warning(f"Model {model} ({slot_name}) failed in {method_name}: {last_error}")
                            break
                        
                    if result is None and method_name in ["generate", "classify_json", "generate_content"]:
                        logger.warning(f"Model {model} ({slot_name}) returned None in {method_name}")
                        break
                        
                    self.model = model
                    self.thinking_level = getattr(client, "thinking_level", self.thinking_level)
                    ProviderCircuitBreaker.record_provider_success(provider)
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
                                    from database.db import get_session
                                    from database.models import ActivityLog
                                    async with get_session() as s:
                                        s.add(ActivityLog(
                                            category='system',
                                            description=text_msg[:500],
                                            actor='llm_factory',
                                        ))
                                        await s.commit()
                                except Exception as db_err:
                                    logger.debug(f"Failed to record fallback log to DB: {db_err}")
                            asyncio.create_task(_record_fallback_log(msg))
                        except Exception:
                            pass
                    return result
                except (asyncio.TimeoutError, StreamTimeoutError, StreamSafetyTimeoutError) as timeout_err:
                    # Attempt 1x dual-protocol non-streaming fallback if stream failed
                    if kwargs.get("stream", True) and method_name in ["generate", "generate_content"]:
                        try:
                            logger.info(f"[{self.task_role}] Stream timeout on {slot_name}/{model}, attempting 1x non-streaming fallback...")
                            ns_kwargs = dict(kwargs)
                            ns_kwargs["stream"] = False
                            ns_res = await asyncio.wait_for(method(*args, **ns_kwargs), timeout=25.0)
                            if ns_res is not None:
                                self.model = model
                                self._slot_backoff_count[slot_name] = 0
                                self._slot_cooldowns.pop(slot_name, None)
                                return ns_res
                        except Exception as ns_err:
                            logger.debug(f"Non-streaming fallback failed: {ns_err}")

                    from analysis.providers.provider_failover_classifier import FailoverReason
                    reason = FailoverReason.NETWORK_TIMEOUT
                    detail = f" ({timeout_err})" if isinstance(timeout_err, (StreamTimeoutError, StreamSafetyTimeoutError)) else f" after {per_model_timeout:.0f}s"
                    last_error = f"Model {model} ({slot_name}) timed out in {method_name}{detail}"
                    logger.warning(f"{last_error}. Trying next fallback...")

                    ProviderCircuitBreaker.record_provider_failure(provider, is_server_or_timeout=True, reason="timeout")

                    import time
                    cnt = self._slot_backoff_count.get(slot_name, 0)
                    cd_duration = min(60.0 * (2 ** cnt), 1800.0)
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
                        logger.warning(f"[{self.task_role}] Memoized unsupported response_format for {provider}/{model}")

                    # ── C4: STRUCTURED ERROR CLASSIFICATION ──
                    from analysis.providers.provider_failover_classifier import classify_error, FailoverReason
                    reason, detail = classify_error(e)

                    logger.warning(
                        f"[{self.task_role}] {slot_name}/{model} error: "
                        f"reason={reason.value}, detail={detail}, type={type(e).__name__}"
                    )

                    # Strategy 1: Compress — don't failover
                    if reason.should_compress:
                        logger.info(
                            f"[{self.task_role}] {reason.value} — "
                            f"propagating for upstream compaction (not failing over)"
                        )
                        raise  # Let agent_harness.py C2 handle compression

                    is_hot_path = getattr(self, "task_role", "") in HOT_PATH_ROLES
                    is_rate_or_auth = reason in (
                        FailoverReason.RATE_LIMIT_API,
                        FailoverReason.RATE_LIMIT_MODEL,
                        FailoverReason.AUTH_TRANSIENT,
                    )

                    # Strategy 2: In-Flight Key Rotation from APICredentialPool
                    if is_rate_or_auth:
                        try:
                            from utils.api.credential_pool import APICredentialPool
                            cred_pool = APICredentialPool()
                            curr_key = getattr(client, "api_key", None) or getattr(client, "_api_key", None)
                            if curr_key:
                                cred_pool.report_rate_limit(provider, curr_key, model=model)
                            next_key = cred_pool.get_key(provider, model=model, is_hot_path=is_hot_path)
                            if next_key and next_key != curr_key:
                                logger.info(f"[{self.task_role}] In-flight key rotation for {provider} on {slot_name}. Retrying immediately.")
                                if hasattr(client, "api_key"):
                                    client.api_key = next_key
                                if hasattr(client, "_api_key"):
                                    client._api_key = next_key
                                if hasattr(client, "client") and hasattr(client.client, "api_key"):
                                    client.client.api_key = next_key
                                continue
                        except Exception as pool_err:
                            logger.debug(f"Credential pool rotation pass-through: {pool_err}")

                    # Strategy 3: Retry same model with backoff OR Eager Failover for hot paths
                    can_failover = reason.can_failover(is_hot_path=is_hot_path) if hasattr(reason, "can_failover") else reason.should_failover
                    if not can_failover and reason.max_retries > 0:
                        if slot_retries < reason.max_retries:
                            backoff = reason.backoff_seconds * (1.5 ** slot_retries)
                            slot_retries += 1
                            logger.info(
                                f"[{self.task_role}] {reason.value} — retrying {slot_name} "
                                f"after {backoff:.1f}s (attempt {slot_retries}/{reason.max_retries})"
                            )
                            if backoff > 0:
                                await asyncio.sleep(backoff)
                            continue

                    # Strategy 4: Failover to next model with exponential cooldown
                    is_server_or_timeout = (reason in (FailoverReason.SERVER_ERROR, FailoverReason.NETWORK_TIMEOUT, FailoverReason.NETWORK_CONNECTION))
                    ProviderCircuitBreaker.record_provider_failure(provider, is_server_or_timeout=is_server_or_timeout, reason=reason.value)
                    if reason in (FailoverReason.AUTH_PERMANENT, FailoverReason.BILLING_EXHAUSTED, FailoverReason.MODEL_NOT_FOUND):
                        ProviderCircuitBreaker.blacklist_model(provider, model, reason=reason.value, duration=1800.0)

                    import time
                    cnt = self._slot_backoff_count.get(slot_name, 0)
                    cd_duration = min(60.0 * (2 ** cnt), 1800.0)
                    self._slot_cooldowns[slot_name] = time.time() + cd_duration
                    self._slot_backoff_count[slot_name] = cnt + 1
                    if slot_name == "primary":
                        self._primary_cooldown_until = self._slot_cooldowns[slot_name]

                    last_error = e
                    last_failed_dict = {
                        "slot": slot_name,
                        "model": model,
                        "reason": reason.value,
                        "detail": detail,
                    }
                    break
                
        logger.error(f"All fallback models failed for {method_name}. Last error: {last_error}")
        
        # Return sensible defaults on complete failure
        if method_name in ["generate", "generate_content", "classify_json"]:
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

    async def generate(self, prompt: str, system: str = "", temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs) -> Optional[str]:
        call_kwargs = dict(system=system, temperature=temperature, **kwargs)
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("generate", prompt, **call_kwargs)

    async def generate_content(self, system_prompt: str = "", user_message: str = "",
                                response_schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs) -> Optional[str]:
        call_kwargs = dict(system_prompt=system_prompt, user_message=user_message, response_schema=response_schema, temperature=temperature, **kwargs)
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("generate_content", **call_kwargs)
        
    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs) -> Optional[dict]:
        call_kwargs = dict(system_prompt=system_prompt, schema=schema, temperature=temperature, **kwargs)
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        return await self._execute_with_fallback("classify_json", prompt, **call_kwargs)
        
    async def run_tool_agent(self, messages: list, tools: list, system_prompt: str, **kwargs) -> MockResponse:
        return await self._execute_with_fallback("run_tool_agent", messages, tools, system_prompt, **kwargs)
        
    async def run_agent(self, session, system_prompt: str | tuple[str, str] | Any, user_message: str, tools: list, stage_name: str = "unknown", extra_context: Optional[str] = None, prefetch_satisfied_tools: Optional[set] = None, **kwargs) -> dict:
        return await self._execute_with_fallback("run_agent", session, system_prompt, user_message, tools, stage_name=stage_name, extra_context=extra_context, prefetch_satisfied_tools=prefetch_satisfied_tools, **kwargs)
        
    async def run_chat_loop(self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None, **kwargs) -> dict:
        return await self._execute_with_fallback("run_chat_loop", system_prompt, conversation_history, new_user_message, tools, tool_executor=tool_executor, **kwargs)
        
    async def run_agent_from_messages(self, session, system_prompt: str | tuple[str, str] | Any, messages: list, tools: list, max_tool_turns: int = 15, stage_name: str = "unknown", prefetch_satisfied_tools: Optional[set] = None, **kwargs) -> dict:
        return await self._execute_with_fallback("run_agent_from_messages", session, system_prompt, messages, tools, max_tool_turns=max_tool_turns, stage_name=stage_name, prefetch_satisfied_tools=prefetch_satisfied_tools, **kwargs)


# Helper function for easy access
def get_client_for_task(task_role: str, settings: Optional[dict] = None) -> BaseLLMClient:
    resolved_settings: dict
    if settings is None:
        try:
            from config.settings import load_settings
            loaded = load_settings()
            resolved_settings = dict(loaded) if isinstance(loaded, dict) else loaded.model_dump()
        except Exception:
            resolved_settings = {}
    else:
        resolved_settings = settings
    factory = LLMFactory(resolved_settings)
    return factory.get_client_for_task(task_role)

def create_client(model_name: str, settings: dict, role_config: Optional[dict] = None) -> BaseLLMClient:
    factory = LLMFactory(settings)
    if not role_config:
        role_config = {"primary": model_name}
    client = factory._create_client_instance(model_name, role_config)
    if not client:
        raise ValueError(f"Could not create client for {model_name}")
    return client
