# ==============================================================================
# File: infrastructure/providers/zai_provider.py
# ==============================================================================

"""
Z.AI / GLM Provider Client for Monika Trading Agent.
Connects directly to Zhipu AI's PaaS / Coding Plan endpoint (https://api.z.ai/api/paas/v4).
Enables subscription-tier execution of GLM-5.3, GLM-5.2, and GLM-4.x models
with thinking/reasoning parameters and full tool-calling support.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from monika.core.security.credential_vault import vault
from monika.infrastructure.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("TradingAgent.Providers.ZAI")

DEFAULT_ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"


class ZAIProvider(OpenAIProvider):
    """
    Provider for Zhipu AI (GLM) models via Z.AI Coding Plan or PaaS API.
    Uses OpenAI-compatible Chat Completions endpoint.
    """

    def __init__(
        self,
        model: str,
        max_tokens: int = 4096,
        api_key: Optional[str] = None,
        settings: Optional[dict] = None,
        temperature: float = 0.0,
        max_tool_turns: int = 15,
        thinking_level: str = "none",
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("zai", {})
        resolved_key = (
            api_key
            or vault.get_secret("ZAI_API_KEY")
            or os.getenv("ZAI_API_KEY")
            or vault.get_secret("GLM_API_KEY")
            or os.getenv("GLM_API_KEY")
            or provider_cfg.get("api_key")
        )

        resolved_base_url = (
            base_url or os.getenv("ZAI_BASE_URL") or provider_cfg.get("base_url") or DEFAULT_ZAI_BASE_URL
        ).rstrip("/")

        super().__init__(
            model=model,
            max_tokens=max_tokens,
            api_key=resolved_key,
            settings=settings,
            temperature=temperature,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            provider_name="zai",
            **kwargs,
        )

        self.provider_name = "zai"
        self.base_url = resolved_base_url

        if self.api_key:
            try:
                from openai import AsyncOpenAI

                max_retries = provider_cfg.get("max_retries", 3)
                timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    max_retries=max_retries,
                    timeout=timeout_sec,
                )
            except ImportError:
                logger.warning("OpenAI client library required for ZAIProvider.")
                self.client = None
        else:
            self.client = None
            logger.warning("No ZAI_API_KEY or GLM_API_KEY set. Z.AI models will not function.")

    def _apply_reasoning_params(self, kwargs: dict) -> None:
        """
        Apply thinking / reasoning parameters specific to GLM-5.x models:
        GLM accepts `extra_body: {"thinking": True}` or `reasoning_effort`.
        """
        if self.thinking_level and self.thinking_level != "none":
            extra_body = kwargs.setdefault("extra_body", {})
            extra_body["thinking"] = True

            # Map thinking level to GLM reasoning_effort if supported
            effort_map = {"low": "low", "medium": "medium", "high": "high"}
            effort = effort_map.get(str(self.thinking_level).lower())
            if effort:
                kwargs["reasoning_effort"] = effort
        elif self.thinking_level == "none":
            extra_body = kwargs.setdefault("extra_body", {})
            extra_body["thinking"] = False
