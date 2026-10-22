# ==============================================================================
# File: infrastructure/providers/opencode_provider.py
# ==============================================================================

"""
OpenCode Go / Zen Provider Client for Monika Trading Agent.
Connects directly to OpenCode's OpenAI-compatible inference endpoint (https://opencode.ai/zen/go/v1).
Enables multi-model execution of DeepSeek, GLM, Qwen, Kimi, and Claude Haiku models
via the OpenCode Go ($10/mo) subscription or OpenCode Zen with full tool-calling support.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from monika.core.security.credential_vault import vault
from monika.infrastructure.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("TradingAgent.Providers.OpenCode")

DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/inference/go/openai/v1"


class OpenCodeProvider(OpenAIProvider):
    """
    Provider for models accessed through OpenCode Go / Zen subscription.
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
        provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("opencode", {})
        resolved_key = (
            api_key
            or vault.get_secret("OPENCODE_API_KEY")
            or os.getenv("OPENCODE_API_KEY")
            or provider_cfg.get("api_key")
        )

        resolved_base_url = (
            base_url or os.getenv("OPENCODE_BASE_URL") or provider_cfg.get("base_url") or DEFAULT_OPENCODE_BASE_URL
        ).rstrip("/")

        super().__init__(
            model=model,
            max_tokens=max_tokens,
            api_key=resolved_key,
            settings=settings,
            temperature=temperature,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            provider_name="opencode",
            **kwargs,
        )

        self.provider_name = "opencode"
        self.base_url = resolved_base_url

        if self.api_key:
            try:
                from openai import AsyncOpenAI

                max_retries = provider_cfg.get("max_retries", 3)
                timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
                default_headers = {
                    "User-Agent": "Monika-TradingAgent/1.0",
                    "x-opencode-session": "monika_session",
                }
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    max_retries=max_retries,
                    timeout=timeout_sec,
                    default_headers=default_headers,
                )
            except ImportError:
                logger.warning("OpenAI client library required for OpenCodeProvider.")
                self.client = None
        else:
            self.client = None
            logger.warning("No OPENCODE_API_KEY set. OpenCode models will not function.")

    def _apply_reasoning_params(self, kwargs: dict) -> None:
        """
        Apply reasoning parameters if a reasoning/thinking model is targeted
        (e.g., DeepSeek R1, Kimi, GLM, Muse Spark).
        Pops temperature to prevent HTTP 400 rejection on reasoning endpoints.
        """
        if self.thinking_level and self.thinking_level != "none":
            kwargs.pop("temperature", None)
            lvl = str(self.thinking_level).lower()
            effort_map = {
                "low": "low",
                "medium": "medium",
                "high": "high",
                "xhigh": "high",
                "extended": "high",
                "max": "high",
            }
            kwargs["reasoning_effort"] = effort_map.get(lvl, "medium")
            extra_body = kwargs.setdefault("extra_body", {})
            extra_body["thinking"] = True
