import logging
import json
from typing import Dict, Any, Optional
import os
from analysis.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

class DeepSeekProvider(OpenAIProvider):
    """
    Provider untuk model DeepSeek.
    Menggunakan OpenAI library karena API DeepSeek kompatibel dengan OpenAI.
    """
    def __init__(self, model: str, max_tokens: int = 2048, api_key: Optional[str] = None, settings: Optional[dict] = None,
                 temperature: float = 0.0, max_tool_turns: int = 15, thinking_level: str = "none", **kwargs):
        super().__init__(model, max_tokens=max_tokens, api_key=api_key, settings=settings,
                         temperature=temperature, max_tool_turns=max_tool_turns,
                         thinking_level=thinking_level, **kwargs)
        self.provider_name = "deepseek"
        self._is_deepseek = True
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.kwargs = kwargs
        try:
            from openai import AsyncOpenAI
            timeout = float((self.settings or {}).get('llm', {}).get('providers', {}).get('deepseek', {}).get('timeout_seconds', 120.0))
            self.client = AsyncOpenAI(
                api_key=self.api_key, 
                base_url="https://api.deepseek.com/v1",
                timeout=timeout,
                max_retries=2
            )
        except ImportError:
            logger.warning("OpenAI package not installed. Run `pip install openai`.")
            self.client = None
