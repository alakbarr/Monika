import logging
import json
import asyncio
from typing import Optional, Any
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock, _flatten_system_prompt

logger = logging.getLogger("TradingAgent.OllamaProvider")

class OllamaProvider(BaseLLMClient):
    """
    Provider untuk model Ollama (local inference).
    Requires: `pip install langchain-ollama` and Ollama server running at base_url.
    """
    def __init__(self, model_name: Optional[str] = None, settings: Optional[dict] = None, max_tokens: int = 8192,
                 max_tool_turns: int = 15, thinking_level: str = "none", model: Optional[str] = None, **kwargs):
        effective_model = model_name or model or "llama3"
        effective_settings = settings or {}
        super().__init__(effective_model, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                         thinking_level=thinking_level, settings=effective_settings, **kwargs)
        ollama_cfg = effective_settings.get("llm", {}).get("providers", {}).get("ollama", {})

        self.base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        self._client = None

    def _get_client(self):
        if self._client is None:
            num_predict = max(self.max_tokens, 32768)
            timeout_sec = float((self.settings or {}).get("llm", {}).get("providers", {}).get("ollama", {}).get("timeout_seconds", 180.0))
            try:
                from langchain_ollama import ChatOllama  # type: ignore
                self._client = ChatOllama(model=self.model, base_url=self.base_url, temperature=0.0, num_predict=num_predict, client_kwargs={"timeout": timeout_sec})
            except (ImportError, TypeError):
                try:
                    from langchain_community.chat_models import ChatOllama  # type: ignore
                    self._client = ChatOllama(model=self.model, base_url=self.base_url, temperature=0.0, num_predict=num_predict, request_timeout=timeout_sec)
                except (ImportError, TypeError):
                    try:
                        from langchain_ollama import ChatOllama  # type: ignore
                        self._client = ChatOllama(model=self.model, base_url=self.base_url, temperature=0.0, num_predict=num_predict)
                    except ImportError:
                        raise ImportError("Install langchain-ollama: pip install langchain-ollama")
        return self._client

    async def generate(self, prompt: str, system: Any = "", temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
        client = self._get_client()
        messages = []
        flat_sys = _flatten_system_prompt(system)
        if flat_sys:
            messages.append(SystemMessage(content=flat_sys))
        if prompt:
            messages.append(HumanMessage(content=prompt))
        call_options = {}
        if temperature is not None:
            call_options["temperature"] = temperature
        if max_tokens is not None:
            call_options["num_predict"] = max_tokens

        invoker = client
        if call_options and hasattr(client, "bind"):
            bind_res = client.bind(**call_options)
            if not asyncio.iscoroutine(bind_res):
                invoker = bind_res
        response = await invoker.ainvoke(messages)
        if hasattr(response, 'response_metadata') and response.response_metadata:
            prompt_tokens = response.response_metadata.get('prompt_eval_count', 0)
            completion_tokens = response.response_metadata.get('eval_count', 0)
            if prompt_tokens or completion_tokens:
                asyncio.create_task(self._save_token_usage(self.model, "generate", prompt_tokens, completion_tokens))
        elif hasattr(response, 'usage_metadata') and response.usage_metadata:
            prompt_tokens = response.usage_metadata.get('input_tokens', 0)
            completion_tokens = response.usage_metadata.get('output_tokens', 0)
            if prompt_tokens or completion_tokens:
                asyncio.create_task(self._save_token_usage(self.model, "generate", prompt_tokens, completion_tokens))
        if response is None:
            return None
        content = getattr(response, "content", None)
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        if schema:
            prompt = f"{prompt}\n\nRespond with ONLY valid JSON conforming exactly to this schema:\n{json.dumps(schema)}\nNo markdown, no explanations."
        else:
            prompt = f"{prompt}\n\nRespond with ONLY valid JSON, no markdown, no explanation."
            
        text = await self.generate(prompt, system=system_prompt or "", temperature=temperature, max_tokens=max_tokens, **kwargs)
        if not text:
            return None
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except Exception:
            pass
        return None

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> MockResponse:
        if tools:
            raise NotImplementedError("Ollama provider does not support tool calling")
        flat_sys = _flatten_system_prompt(system_prompt)
        prompt = flat_sys + "\n\n" + str(messages[-1].get("content", "") if messages else "")
        text = await self.generate(prompt) or ""
        return MockResponse([MockBlock("text", text=text)], "end_turn", 0, len(text) // 4)

    async def run_chat_loop(self, system_prompt: Any, conversation_history: list,
                             new_user_message: str, tools: list, tool_executor=None) -> dict:
        flat_sys = _flatten_system_prompt(system_prompt)
        prompt = flat_sys + "\n\n" + new_user_message
        result = await self.generate(prompt) or ""
        return {"success": True, "reply": result, "tool_calls_made": 0, "turns": 1}
