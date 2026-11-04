"""
LLM Factory: Satu pintu masuk untuk membuat klien LLM.

Semua komponen WAJIB menggunakan factory ini.
claude_client.py dan gemini_client.py SUDAH DIHAPUS.
"""

import asyncio
import copy
import inspect
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from monika.infrastructure.llm.rate_limiting.streaming import StreamSafetyTimeoutError, StreamTimeoutError
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockBlock, MockResponse
from monika.infrastructure.providers.circuit_breaker import (
    HOT_PATH_ROLES,
    _UNSUPPORTED_SCHEMA_ROUTES,
    EndpointBlackhole,
    ProviderCircuitBreaker,
)
from monika.infrastructure.providers.fallback_wrapper import FallbackClientWrapper, _safe_clone

logger = logging.getLogger("TradingAgent.LLMFactory")


ROLE_ALIASES: dict[str, str] = {
    "conservative_risk": "risk_gate_conservative",
    "aggressive_risk": "risk_gate_aggressive",
    "neutral_risk": "risk_gate_neutral",
    "risk_gate_conservative": "conservative_risk",
    "risk_gate_aggressive": "aggressive_risk",
    "risk_gate_neutral": "neutral_risk",
    "trade_reflection": "reflection",
    "reflection": "trade_reflection",
}

KNOWN_PROVIDER_PREFIXES: tuple[str, ...] = (
    "gemini",
    "anthropic",
    "openai",
    "openrouter",
    "deepseek",
    "groq",
    "typesafe",
    "9router",
    "ninerouter",
    "nine_router",
    "ollama",
    "openai_compatible",
    "vertex",
    "opencode",
    "opencode_go",
    "opencode-go",
    "antigravity",
    "agy",
    "zai",
    "glm",
    "z-ai",
    "z.ai",
    "codex",
)


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
        self.settings = settings
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
            alias_role = ROLE_ALIASES.get(task_role)
            if alias_role and alias_role in self._task_roles:
                role_config = self._task_roles.get(alias_role)
        if not role_config:
            default_mod = (
                self._llm_config.get("default_model")
                or self._task_roles.get("chat_telegram", {}).get("primary")
                or (next(iter(self._catalog.keys())) if self._catalog else "gpt-6.1-sol-medium")
            )
            default_prov = (
                self._llm_config.get("default_provider")
                or self._task_roles.get("chat_telegram", {}).get("provider")
                or "openrouter"
            )
            logger.warning(
                f"Unknown task role: {task_role}, falling back to configured default '{default_mod}' ({default_prov})"
            )
            role_config = {
                "primary": default_mod,
                "provider": default_prov,
                "max_tokens": 8192,
                "max_tool_turns": 15,
                "temperature": 0.0,
                "thinking": {
                    "openrouter": "max",
                    "gemini": "max",
                    "anthropic": "max",
                    "openai": "max",
                    "deepseek": "max",
                    "groq": "max",
                },
            }

        primary_model = (
            role_config.get("primary")
            or self._llm_config.get("default_model")
            or (next(iter(self._catalog.keys())) if self._catalog else "gpt-6.1-sol-medium")
        )
        primary_prov = self._resolve_provider(primary_model, role_config=role_config, slot_name="primary")
        _, primary_clean = self._split_provider_prefix(primary_model)
        seen_routes: set[tuple[str, str]] = {(primary_prov, primary_clean)}
        fallback_chain: list[str] = []

        # 1. Support list format: fallback: [...] or fallbacks: [...]
        list_fb = role_config.get("fallback") or role_config.get("fallbacks")
        if isinstance(list_fb, list):
            for idx, m in enumerate(list_fb):
                m_str = str(m).strip()
                if m_str:
                    fb_prov = self._resolve_provider(m_str, role_config=role_config, slot_name=f"fallback_{idx + 1}")
                    _, fb_clean = self._split_provider_prefix(m_str)
                    if (fb_prov, fb_clean) not in seen_routes:
                        seen_routes.add((fb_prov, fb_clean))
                        fallback_chain.append(m_str)
        elif isinstance(list_fb, str) and list_fb.strip():
            m_str = list_fb.strip()
            fb_prov = self._resolve_provider(m_str, role_config=role_config, slot_name="fallback_1")
            _, fb_clean = self._split_provider_prefix(m_str)
            if (fb_prov, fb_clean) not in seen_routes:
                seen_routes.add((fb_prov, fb_clean))
                fallback_chain.append(m_str)

        # 2. Support numbered slots: fallback_1, fallback_2, ..., fallback_10
        for i in range(1, 11):
            slot_key = f"fallback_{i}"
            fb_val = role_config.get(slot_key)
            if fb_val:
                m_str = str(fb_val).strip()
                if m_str:
                    fb_prov = self._resolve_provider(m_str, role_config=role_config, slot_name=slot_key)
                    _, fb_clean = self._split_provider_prefix(m_str)
                    if (fb_prov, fb_clean) not in seen_routes:
                        seen_routes.add((fb_prov, fb_clean))
                        fallback_chain.append(m_str)

        # Arena-Informed Dynamic Routing (if enabled)
        arena_cfg = self._llm_config.get("arena_routing", {})
        if arena_cfg.get("enabled", False):
            try:
                arena_winner = self._resolve_arena_preferred_model(
                    task_role=task_role,
                    current_primary=primary_model,
                    min_matches=int(arena_cfg.get("min_matches", 10)),
                    min_elo_delta=float(arena_cfg.get("min_elo_delta", 50.0)),
                )
                if arena_winner and arena_winner != primary_model:
                    logger.info(
                        f"[ArenaRouting] Dynamic model promotion for task '{task_role}': "
                        f"Promoting '{arena_winner}' over '{primary_model}' based on Alpha Arena Elo rating."
                    )
                    if primary_model not in fallback_chain:
                        fallback_chain.insert(0, primary_model)
                    primary_model = arena_winner
            except Exception as e_ar:
                logger.debug(f"[ArenaRouting] Notice: {e_ar}")

        return self._create_client_with_fallback(primary_model, fallback_chain, role_config, task_role=task_role)

    def _resolve_arena_preferred_model(
        self,
        task_role: str,
        current_primary: str,
        min_matches: int = 10,
        min_elo_delta: float = 50.0,
    ) -> Optional[str]:
        """Checks cached Elo leaderboard to find if another model outperforms current primary."""
        standings = getattr(self, "_cached_arena_standings", None)
        if standings is None:
            try:
                import json
                from monika.core.paths import get_data_dir

                lb_file = get_data_dir() / "arena_leaderboard.json"
                if lb_file.exists():
                    data = json.loads(lb_file.read_text(encoding="utf-8"))
                    standings = data.get("standings", [])
                    self._cached_arena_standings = standings
            except Exception:
                self._cached_arena_standings = []
                standings = []

        if not standings:
            return None

        current_elo = 1200.0
        for s in standings:
            if s.get("name") == current_primary:
                current_elo = float(s.get("elo", 1200.0))
                break

        for s in standings:
            candidate = s.get("name")
            cand_elo = float(s.get("elo", 1200.0))
            cand_matches = int(s.get("matches", 0))
            if candidate and candidate != current_primary and cand_matches >= min_matches:
                if (cand_elo - current_elo) >= min_elo_delta and (candidate in self._catalog or ":" in candidate):
                    return candidate
        return None

    @staticmethod
    def _split_provider_prefix(model_name: str) -> tuple[Optional[str], str]:
        """Splits an explicit 'provider:model_name' prefix if the prefix is a known provider."""
        if ":" in model_name:
            prefix, remainder = model_name.split(":", 1)
            prefix_lower = prefix.strip().lower()
            if prefix_lower in KNOWN_PROVIDER_PREFIXES and remainder.strip():
                return prefix_lower, remainder.strip()
        return None, model_name

    def _is_model_compatible_with_provider(
        self, model_name: str, provider_name: str, model_info: Optional[dict] = None
    ) -> bool:
        """Checks whether a model is compatible with a role-configured provider override."""
        prov = provider_name.strip().lower()
        _, clean_name = self._split_provider_prefix(model_name)
        name = clean_name.strip().lower()
        cat = (
            model_info
            if isinstance(model_info, dict)
            else (self._catalog.get(model_name) or self._catalog.get(clean_name) or {})
        )
        mapped_name = str(cat.get("model_name") or cat.get("model") or cat.get("remote_model") or "").strip().lower()
        combined_names = (name, mapped_name) if mapped_name else (name,)

        # Explicit 9Router route prefixes are only compatible with 9Router
        if (
            name.startswith(("9router/", "9r/", "kr/", "if/", "oc/", "ocz/", "mmf/", "gc/", "af/", "combo/"))
            or "9router" in name
            or "ninerouter" in name
        ):
            return prov in ("9router", "ninerouter", "nine_router")

        # Explicit OpenRouter route prefixes/suffixes
        if name.startswith("openrouter/") or name.endswith("-openrouter"):
            return prov == "openrouter"

        # System One / TypeSafe decision models must always use TypeSafeProvider
        if cat.get("provider") == "typesafe" or any(
            k in name
            for k in (
                "jev",
                "typesafe",
                "kev",
                "nanojev",
                "liquid-d1",
                "lfm-7b-d1",
                "luna-decision",
                "mercury-decide",
            )
        ):
            return prov == "typesafe"

        if prov in ("gemini", "antigravity", "agy", "vertex"):
            return any("gemini" in n or "gemma" in n or n.startswith("google/") for n in combined_names)
        if prov == "anthropic":
            return any(
                any(k in n for k in ("claude", "opus", "sonnet", "haiku", "fable")) or n.startswith("anthropic/")
                for n in combined_names
            )
        if prov in ("openai", "codex"):
            return any(
                not n.startswith("groq")
                and "gpt-oss" not in n
                and (any(k in n for k in ("gpt", "o1", "o3", "o4", "codex", "chatgpt")) or n.startswith("openai/"))
                for n in combined_names
            )
        if prov == "deepseek":
            return any("deepseek" in n or "r1" in n or n.startswith("deepseek/") for n in combined_names)
        if prov in ("zai", "glm", "z-ai", "z.ai"):
            return any("glm" in n or n.startswith(("z-ai/", "zhipu/")) for n in combined_names)
        if prov == "groq":
            return cat.get("provider") == "groq" or any(
                any(
                    k in n
                    for k in ("groq", "qwen", "llama", "mixtral", "gemma", "whisper", "compound", "gpt-oss", "kimi")
                )
                for n in combined_names
            )
        if prov in ("opencode", "opencode_go", "opencode-go"):
            return any(
                any(
                    k in n
                    for k in (
                        "contributor",
                        "opencode",
                        "glm",
                        "kimi",
                        "minimax",
                        "mimo",
                        "muse",
                        "gemini",
                        "claude",
                        "gpt",
                        "deepseek",
                        "qwen",
                    )
                )
                for n in combined_names
            )
        if prov in ("9router", "ninerouter", "nine_router", "openrouter", "openai_compatible"):
            return cat.get("provider") != "ollama"
        if prov == "ollama":
            return cat.get("provider") == "ollama" or "ollama" in name or "local" in name
        return False

    def _resolve_provider(
        self, model_name: str, role_config: Optional[dict] = None, slot_name: Optional[str] = None
    ) -> str:
        # 1. Explicit provider:model prefix always takes highest precedence
        explicit_prefix, clean_name = self._split_provider_prefix(model_name)
        if explicit_prefix:
            return explicit_prefix

        model_info = self._catalog.get(model_name) or self._catalog.get(clean_name) or {}
        catalog_provider = model_info.get("provider") if isinstance(model_info, dict) else None

        # System One / TypeSafe decision models always require TypeSafeProvider
        if catalog_provider == "typesafe":
            return "typesafe"

        providers_dict = getattr(self, "_providers", {}) or (getattr(self, "settings", {}) or {}).get("llm", {}).get(
            "providers", {}
        )

        # 2. Honor task_role provider override when compatible with the model
        if isinstance(role_config, dict):
            slot_prov = role_config.get(f"{slot_name}_provider") if slot_name else None
            if not slot_prov and slot_name and isinstance(role_config.get("providers"), dict):
                slot_prov = role_config["providers"].get(slot_name)
            if not slot_prov and slot_name and isinstance(role_config.get("provider"), dict):
                slot_prov = role_config["provider"].get(slot_name)
            raw_prov = role_config.get("provider")
            default_prov = raw_prov.get("primary") if isinstance(raw_prov, dict) else raw_prov
            role_prov = slot_prov or default_prov
            if isinstance(role_prov, str) and role_prov.strip():
                role_prov_norm = role_prov.strip().lower()
                prov_cfg = providers_dict.get(role_prov_norm)
                is_role_prov_disabled = isinstance(prov_cfg, dict) and prov_cfg.get("enabled") is False
                if not is_role_prov_disabled:
                    if slot_prov:
                        if self._is_model_compatible_with_provider(clean_name, role_prov_norm, model_info):
                            return role_prov_norm
                    elif role_prov_norm == "openrouter":
                        if catalog_provider in (None, "openrouter") or (
                            slot_name in (None, "primary")
                            and self._is_model_compatible_with_provider(clean_name, "openrouter", model_info)
                        ):
                            return "openrouter"
                    elif self._is_model_compatible_with_provider(clean_name, role_prov_norm, model_info):
                        return role_prov_norm

        # 3. Model catalog provider
        if catalog_provider:
            return str(catalog_provider)

        name = clean_name.lower()

        # 9Router prefix & provider resolution
        if (
            name.startswith(("9router/", "9r/", "kr/", "if/", "oc/", "ocz/", "mmf/", "gc/", "af/", "combo/"))
            or "9router" in name
            or "ninerouter" in name
        ):
            return "9router"

        # System One Decision Models (TypeSafe Jev, Kev, NanoJev, Liquid, Luna, Mercury) â€” direct or routed via OpenRouter
        if any(k in name for k in ("jev", "typesafe", "kev", "nanojev", "liquid", "luna", "mercury")):
            return "typesafe"

        # Guess provider
        if "openrouter" in name or "ox-alpha" in name or name.startswith(("stealth/", "meta/")):
            return "openrouter"
        if ("contributor" in name or "opencode" in name) and not name.startswith(("oc/", "ocz/")):
            return "opencode"
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
        if "claude" in name or "haiku" in name or "opus" in name or "sonnet" in name or "fable" in name:
            prov_entry = providers_dict.get("anthropic")
            if prov_entry is not None and prov_entry.get("enabled") is False:
                if providers_dict.get("openrouter", {}).get("enabled", True):
                    return "openrouter"
            return "anthropic"
        if "gpt" in name:
            prov_entry = providers_dict.get("openai")
            if prov_entry is not None and prov_entry.get("enabled") is False:
                if providers_dict.get("openrouter", {}).get("enabled", True):
                    return "openrouter"
            return "openai"
        if "deepseek" in name:
            prov_entry = providers_dict.get("deepseek")
            if prov_entry is not None and prov_entry.get("enabled") is False:
                if providers_dict.get("openrouter", {}).get("enabled", True):
                    return "openrouter"
            return "deepseek"
        if "ollama" in name:
            return "ollama"
        if "grok" in name:
            return "openai_compatible"
        if "groq" in name:
            return "groq"
        return "openai_compatible"

    def is_model_paid(
        self,
        model_name: str,
        role_config: Optional[dict] = None,
        slot_name: Optional[str] = "primary",
        provider: Optional[str] = None,
    ) -> bool:
        """
        Determines whether a candidate model/slot is paid or free.
        Used by FallbackClientWrapper to bypass paid models when budget is paused.
        """
        if not model_name:
            return False

        from monika.core.analytics.pricing import is_paid_model

        resolved_prov = provider
        if not resolved_prov:
            try:
                resolved_prov = self._resolve_provider(model_name, role_config=role_config, slot_name=slot_name)
            except Exception:
                resolved_prov = None

        is_direct_free_tier: Optional[bool] = None
        if isinstance(role_config, dict):
            slot_tier = (
                role_config.get(f"{slot_name}_gemini_tier")
                or role_config.get(f"{slot_name}_tier")
                or (role_config.get("gemini_tier") if slot_name in (None, "primary") else None)
            )
            if slot_tier == "paid":
                is_direct_free_tier = False
            elif slot_tier == "free":
                is_direct_free_tier = True

        return is_paid_model(
            model_name,
            provider=resolved_prov,
            is_direct_free_tier=is_direct_free_tier,
        )

    def _resolve_thinking_level(
        self, model_name: str, role_config: dict, provider_name: str, slot_name: Optional[str] = None
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
        _, clean_lookup_name = self._split_provider_prefix(model_name)
        thinking_cfg = role_config.get("thinking")

        if thinking_cfg is False or role_config.get("thinking_budget") == 0:
            return "none"

        if isinstance(thinking_cfg, dict):
            # 1. Exact model name (or provider-stripped model name)
            if model_name in thinking_cfg:
                return str(thinking_cfg[model_name]).lower()
            if clean_lookup_name in thinking_cfg:
                return str(thinking_cfg[clean_lookup_name]).lower()

            # 2. Short name / stripped prefix (e.g., 'glm-5.2:free' for 'z-ai/glm-5.2:free')
            short_name = clean_lookup_name.split("/")[-1] if "/" in clean_lookup_name else clean_lookup_name
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
            if clean_lookup_name in thinking_by_model:
                return str(thinking_by_model[clean_lookup_name]).lower()
            short_name = clean_lookup_name.split("/")[-1] if "/" in clean_lookup_name else clean_lookup_name
            if short_name in thinking_by_model:
                return str(thinking_by_model[short_name]).lower()

        # Check model catalog default
        cat_entry = self._catalog.get(model_name) or self._catalog.get(clean_lookup_name) or {}
        if isinstance(cat_entry, dict) and "default_thinking" in cat_entry:
            return str(cat_entry["default_thinking"]).lower()

        return "none"

    def _create_client_instance(
        self, model_name: str, role_config: dict, slot_name: Optional[str] = None, task_role: Optional[str] = None
    ) -> Optional[BaseLLMClient]:
        provider_name = self._resolve_provider(model_name, role_config=role_config, slot_name=slot_name)
        provider_config = self._providers.get(provider_name)
        if provider_config is None and provider_name in ("9router", "ninerouter", "nine_router"):
            for alt in ("ninerouter", "9router", "nine_router"):
                if alt in self._providers:
                    provider_config = self._providers[alt]
                    break
        provider_config = provider_config or {}

        # In a real scenario, we might want to fail gracefully, but for now we assume enabled
        if provider_config and not provider_config.get("enabled", True):
            if not role_config.get("_benchmark_mode") and not (":" in model_name):
                logger.warning(f"Provider {provider_name} is disabled.")
                return None

        from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

        raw_max_tokens = role_config.get("max_tokens", 8192)
        max_tool_turns = role_config.get("max_tool_turns", 15)
        temperature = float(role_config.get("temperature", 0.0))

        thinking_level = self._resolve_thinking_level(model_name, role_config, provider_name, slot_name=slot_name)
        effective_max_tokens = resolve_effective_max_tokens(
            model_name=model_name,
            provider_name=provider_name,
            requested_max_tokens=raw_max_tokens,
            thinking_level=thinking_level,
            settings=getattr(self, "settings", None) or getattr(getattr(self, "factory", None), "_settings", None),
        )
        role_cfg_effective = dict(role_config)
        role_cfg_effective["max_tokens"] = effective_max_tokens

        _, lookup_model_name = self._split_provider_prefix(model_name)
        cat_entry = self._catalog.get(model_name) or self._catalog.get(lookup_model_name) or {}
        clean_model_name = lookup_model_name
        if isinstance(cat_entry, dict):
            mapped_model = cat_entry.get("model_name") or cat_entry.get("model") or cat_entry.get("remote_model")
            if mapped_model:
                mapped_str = str(mapped_model)
                if "/" in mapped_str and provider_name in (
                    "gemini",
                    "antigravity",
                    "agy",
                    "vertex",
                    "anthropic",
                    "openai",
                    "codex",
                    "deepseek",
                    "zai",
                    "glm",
                    "z-ai",
                    "z.ai",
                ):
                    clean_model_name = mapped_str.split("/", 1)[1]
                else:
                    clean_model_name = mapped_str

        _, clean_model_name = self._split_provider_prefix(clean_model_name)

        # Retrieve healthy API key from CredentialPool (M2)
        # Note: OpenRouter manages its own dual-tier key pool (OPENROUTER_PAID_API_KEY vs OPENROUTER_API_KEYS)
        # with model-aware paid/free routing & per-model cooldowns. Do not override with a generic pooled key.
        try:
            from monika.infrastructure.credentials.credential_pool import get_credential_pool

            cred_pool = get_credential_pool()
            if provider_name == "openrouter":
                pooled_key = None
            else:
                pooled_key = cred_pool.get_key(provider_name, model=clean_model_name)
        except Exception:
            cred_pool = None
            pooled_key = None

        # Routing adjustments for System One models via OpenRouter (e.g. jaredpalmer/kev-4b, liquid/lfm-7b-d1, or openrouter/typesafe/jev-latest)
        if provider_name == "typesafe":
            m_lower = model_name.lower()
            is_openrouter_route = (
                model_name.startswith("openrouter/")
                or any(k in m_lower for k in ("kev", "liquid", "luna", "mercury"))
                or (model_name.startswith("typesafe/") and "openrouter" in m_lower)
                or provider_config.get("use_openrouter", False)
            )
            if is_openrouter_route:
                if cred_pool:
                    pooled_key = cred_pool.get_key("openrouter") or pooled_key
                if not pooled_key:
                    pooled_key = os.getenv("OPENROUTER_PAID_API_KEY") or os.getenv("OPENROUTER_API_KEY")
                provider_config = dict(provider_config)
                provider_config["base_url"] = provider_config.get("base_url") or "https://openrouter.ai/api"
                provider_config["use_openrouter"] = True
                if clean_model_name.startswith("openrouter/"):
                    clean_model_name = clean_model_name[len("openrouter/") :]
                if clean_model_name.lower() in ("kev", "kev-4b"):
                    clean_model_name = "jaredpalmer/kev-4b"
                elif clean_model_name.lower() in ("liquid-d1", "lfm-7b-d1", "liquid/lfm-7b-d1"):
                    clean_model_name = "liquid/lfm-7b-d1"
                elif clean_model_name.lower() in (
                    "luna-decision",
                    "luna/decision",
                    "gpt-6-luna-decisions",
                    "openai/gpt-6-luna-decisions",
                ):
                    clean_model_name = "openai/gpt-6-luna-decisions"
                elif clean_model_name.lower() in ("mercury-decide", "mercury/decide"):
                    clean_model_name = "mercury/decide"

        from monika.infrastructure.providers.provider_registry import ProviderRegistry

        slot_gemini_tier = None
        if isinstance(role_config, dict):
            slot_gemini_tier = (
                role_config.get(f"{slot_name}_gemini_tier")
                or role_config.get(f"{slot_name}_tier")
                or (role_config.get("gemini_tier") if slot_name in (None, "primary") else None)
            )

        client = ProviderRegistry.create_client(
            provider_name=provider_name,
            model_name=clean_model_name,
            settings=self._settings,
            role_config=role_config,
            task_role=task_role or "default",
            thinking_level=thinking_level,
            api_key=pooled_key,
            provider_config=provider_config,
            gemini_tier=slot_gemini_tier,
        )
        if client is None:
            return None

        # SOTA Dynamic Thinking Budget Wiring
        if client is not None:
            try:
                from monika.infrastructure.llm.adaptive_thinking import (
                    PerSymbolAdaptiveThinkingAllocator,
                    clamp_thinking_budget_to_answer_room,
                )

                is_disabled = str(thinking_level or "none").lower() in ("none", "off")
                if not is_disabled:
                    level_to_budget = {
                        "minimal": 1024,
                        "low": 1024,
                        "medium": 4096,
                        "high": 10000,
                        "max": 16000,
                        "xhigh": 16000,
                        "extended": 16000,
                    }
                    base_b = level_to_budget.get(thinking_level.lower(), 4000)
                    adaptive_budget = PerSymbolAdaptiveThinkingAllocator.get_thinking_budget_for_task(
                        task_role or "", base_budget=base_b
                    )

                    final_eff_max = resolve_effective_max_tokens(
                        model_name=clean_model_name,
                        provider_name=provider_name,
                        requested_max_tokens=raw_max_tokens,
                        thinking_budget=adaptive_budget,
                        thinking_level=thinking_level,
                        settings=self._settings,
                    )
                    if isinstance(final_eff_max, int) and final_eff_max > 1024:
                        adaptive_budget = clamp_thinking_budget_to_answer_room(
                            adaptive_budget, max_tokens=final_eff_max, min_answer_tokens=1024
                        )

                    if hasattr(client, "set_thinking_budget"):
                        client.set_thinking_budget(adaptive_budget)
                    elif hasattr(client, "thinking_budget"):
                        client.thinking_budget = adaptive_budget
                else:
                    if hasattr(client, "set_thinking_budget"):
                        client.set_thinking_budget(0)
                    elif hasattr(client, "thinking_budget"):
                        client.thinking_budget = 0
            except Exception:
                pass

        return client

    def _create_client_with_fallback(
        self, primary: str, fallbacks: list[str], role_config: dict, task_role: str = "default"
    ) -> "BaseLLMClient":
        """
        Creates a wrapper client that implements fallback logic across providers.
        """
        return FallbackClientWrapper(self, primary, fallbacks, role_config, task_role=task_role)


# Helper function for easy access
def get_client_for_task(task_role: str, settings: Optional[dict] = None) -> BaseLLMClient:
    resolved_settings: dict
    if not settings:
        try:
            from monika.core.config.settings import load_settings

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


__all__ = [
    "EndpointBlackhole",
    "FallbackClientWrapper",
    "HOT_PATH_ROLES",
    "LLMFactory",
    "ProviderCircuitBreaker",
    "_UNSUPPORTED_SCHEMA_ROUTES",
    "_safe_clone",
    "create_client",
    "get_client_for_task",
]
