import logging
import os
from typing import Optional, Any
from analysis.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("TradingAgent.OllamaProvider")


class OllamaProvider(OpenAIProvider):
    """
    Provider untuk model Ollama (local inference via native OpenAI-compatible API).
    Endpoints: http://localhost:11434/v1
    Mendukung full tool calling, streaming, dan structured output.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        settings: Optional[dict] = None,
        max_tokens: int = 8192,
        max_tool_turns: int = 15,
        thinking_level: str = "none",
        model: Optional[str] = None,
        **kwargs: Any,
    ):
        effective_model = model_name or model or "llama3"
        effective_settings = settings or {}
        super().__init__(
            effective_model,
            max_tokens=max_tokens,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            settings=effective_settings,
            **kwargs,
        )
        self.provider_name = "ollama"
        ollama_cfg = effective_settings.get("llm", {}).get("providers", {}).get("ollama", {})
        raw_base = ollama_cfg.get("base_url", "http://localhost:11434").rstrip("/")
        if not raw_base.endswith("/v1"):
            raw_base = f"{raw_base}/v1"
        self.base_url = raw_base
        self.api_key = "ollama"
        self.kwargs = kwargs

        try:
            from openai import AsyncOpenAI

            timeout = float(ollama_cfg.get("timeout_seconds", 180.0))
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=timeout,
                max_retries=1,
            )
        except ImportError:
            logger.warning("OpenAI package not installed for Ollama client. Run `pip install openai`.")
            self.client = None
