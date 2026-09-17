import time
from dataclasses import dataclass, field
from typing import Optional, Any
from analysis.providers.llm_factory import create_client
from analysis.providers.base_provider import BaseLLMClient
from .model_registry import make_role_config


@dataclass
class InvokeResult:
    model_name: str
    provider: str
    raw_output: Any
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


def _attach_usage_capture(client: BaseLLMClient) -> dict:
    """generate()/classify_json()/run_agent() semuanya memanggil
    self._save_token_usage(...) secara internal -- kita intercept di sini
    supaya dapat token count TANPA menulis ke TokenUsageLog produksi."""
    usage = {"input_tokens": 0, "output_tokens": 0}

    async def _capture(model_name, task_name, input_tokens, output_tokens, session=None):
        usage["input_tokens"] += input_tokens or 0
        usage["output_tokens"] += output_tokens or 0

    client._save_token_usage = _capture  # type: ignore[method-assign]
    return usage


def make_client(model_name: str, settings: dict, **role_kwargs) -> BaseLLMClient:
    return create_client(model_name, settings, make_role_config(**role_kwargs))


async def invoke_text(model_name, settings, system_prompt, prompt, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        out = await client.generate(prompt, system=system_prompt)
        return InvokeResult(model_name, client.__class__.__name__, out,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0)
    except Exception as e:
        return InvokeResult(model_name, client.__class__.__name__, None,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0, error=str(e))


async def invoke_json(model_name, settings, system_prompt, prompt, schema, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        out = await client.classify_json(prompt, system_prompt=system_prompt, schema=schema)
        return InvokeResult(model_name, client.__class__.__name__, out,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0)
    except Exception as e:
        return InvokeResult(model_name, client.__class__.__name__, None,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0, error=str(e))


async def invoke_agent(model_name, settings, session, system_prompt, user_message, tools, stage_name, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        result = await client.run_agent(session=session, system_prompt=system_prompt,
                                         user_message=user_message, tools=tools, stage_name=stage_name)
        elapsed = time.monotonic() - t0
        in_tok = result.get("input_tokens", usage["input_tokens"])
        out_tok = result.get("output_tokens", usage["output_tokens"])
        if not result.get("success"):
            return InvokeResult(model_name, client.__class__.__name__, result, in_tok, out_tok, elapsed,
                                 error=result.get("error", "agent run failed"))
        return InvokeResult(model_name, client.__class__.__name__, result, in_tok, out_tok, elapsed,
                             extra={"tool_calls_made": result.get("tool_calls_made"), "turns": result.get("turns")})
    except Exception as e:
        return InvokeResult(model_name, client.__class__.__name__, None,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0, error=str(e))


async def invoke_chat(model_name, settings, system_prompt, history, message, tools, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        result = await client.run_chat_loop(system_prompt=system_prompt, conversation_history=history,
                                             new_user_message=message, tools=tools)
        elapsed = time.monotonic() - t0
        in_tok = result.get("input_tokens", usage["input_tokens"])
        out_tok = result.get("output_tokens", usage["output_tokens"])
        if not result.get("success", True):
            return InvokeResult(model_name, client.__class__.__name__, result, in_tok, out_tok, elapsed,
                                 error=result.get("error", "chat run failed"))
        return InvokeResult(model_name, client.__class__.__name__, result, in_tok, out_tok, elapsed)
    except Exception as e:
        return InvokeResult(model_name, client.__class__.__name__, None,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0, error=str(e))


async def invoke_custom(model_name, settings, fn, *args, **role_kwargs) -> InvokeResult:
    """Untuk task yang fungsi produksinya SUDAH menerima `client` sebagai
    parameter (bull/bear/judge analyst, risk_gate_llm, portfolio_manager)."""
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        out = await fn(client, *args)
        return InvokeResult(model_name, client.__class__.__name__, out,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0)
    except Exception as e:
        return InvokeResult(model_name, client.__class__.__name__, None,
                             usage["input_tokens"], usage["output_tokens"], time.monotonic() - t0, error=str(e))
