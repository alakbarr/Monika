# ==============================================================================
# File: infrastructure/providers/codex_provider.py
# ==============================================================================

"""
OpenAI Codex Provider Client for Monika Trading Agent.
Connects to OpenAI Codex / ChatGPT subscription backend (https://chatgpt.com/backend-api/codex).
Utilizes OAuth tokens obtained via the official Codex Device Code Flow.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from monika.infrastructure.auth.codex_device_flow import (
    DEFAULT_CODEX_BASE_URL,
    resolve_codex_access_token,
)
from monika.infrastructure.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("TradingAgent.Providers.Codex")


class CodexProvider(OpenAIProvider):
    """
    Provider for OpenAI Codex / ChatGPT Plus & Pro subscription.
    Uses dynamic OAuth token resolution with auto-refresh capability.
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
        provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("codex", {})

        # 1. Resolve dynamic OAuth token (or explicit override)
        resolved_token = api_key or resolve_codex_access_token() or os.getenv("CODEX_ACCESS_TOKEN")

        # 2. Resolve base URL (defaults to official Codex endpoint)
        resolved_base_url = (
            base_url or os.getenv("CODEX_BASE_URL") or provider_cfg.get("base_url") or DEFAULT_CODEX_BASE_URL
        ).rstrip("/")

        super().__init__(
            model=model,
            max_tokens=max_tokens,
            api_key=resolved_token,
            settings=settings,
            temperature=temperature,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            provider_name="codex",
            **kwargs,
        )

        self.provider_name = "codex"
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
                logger.warning("OpenAI client library required for CodexProvider.")
                self.client = None
        else:
            self.client = None
            logger.warning("No active OpenAI Codex OAuth credentials found. Run 'monika auth login codex'.")

    def _ensure_active_token(self) -> bool:
        """Check and refresh the dynamic OAuth token before sending an inference request."""
        fresh_token = resolve_codex_access_token()
        if fresh_token and fresh_token != self.api_key:
            self.api_key = fresh_token
            if self.client:
                self.client.api_key = fresh_token
            return True
        return bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        system: Optional[Any] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        self._ensure_active_token()
        return await super().generate(prompt, system=system, temperature=temperature, max_tokens=max_tokens, **kwargs)

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[dict]:
        self._ensure_active_token()
        return await super().classify_json(
            prompt,
            system_prompt=system_prompt,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> Any:
        self._ensure_active_token()
        return await super().run_tool_agent(messages, tools, system_prompt)
