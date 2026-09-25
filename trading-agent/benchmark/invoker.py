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
    cached_tokens: int = 0
    thinking_tokens: int = 0
    latency_s: float = 0.0
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


def _attach_usage_capture(client: BaseLLMClient) -> dict:
    """generate()/classify_json()/run_agent() semuanya memanggil
    self._save_token_usage(...) secara internal -- kita intercept di sini
    supaya dapat token count TANPA menulis ke TokenUsageLog produksi."""
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "thinking_tokens": 0,
    }

    async def _capture(model_name, task_name, input_tokens, output_tokens, session=None, **kwargs):
        usage["input_tokens"] += input_tokens or 0
        usage["output_tokens"] += output_tokens or 0
        if kwargs.get("cached_tokens"):
            usage["cached_tokens"] += kwargs["cached_tokens"] or 0
        if kwargs.get("thinking_tokens"):
            usage["thinking_tokens"] += kwargs["thinking_tokens"] or 0

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
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=out,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


async def invoke_json(model_name, settings, system_prompt, prompt, schema, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        out = await client.classify_json(prompt, system_prompt=system_prompt, schema=schema)
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=out,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


async def invoke_agent(model_name, settings, session, system_prompt, user_message, tools, stage_name, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        result = await client.run_agent(session=session, system_prompt=system_prompt,
                                         user_message=user_message, tools=tools, stage_name=stage_name)
        elapsed = time.monotonic() - t0
        in_tok = (result.get("input_tokens") if isinstance(result, dict) else None) or usage.get("input_tokens", 0)
        out_tok = (result.get("output_tokens") if isinstance(result, dict) else None) or usage.get("output_tokens", 0)
        cached_tok = (result.get("cached_tokens") if isinstance(result, dict) else None) or usage.get("cached_tokens", 0)
        thinking_tok = (result.get("thinking_tokens") if isinstance(result, dict) else None) or usage.get("thinking_tokens", 0)
        if not (isinstance(result, dict) and result.get("success")):
            err_msg = result.get("error", "agent run failed") if isinstance(result, dict) else "agent run failed"
            return InvokeResult(
                model_name=model_name,
                provider=client.__class__.__name__,
                raw_output=result,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached_tok,
                thinking_tokens=thinking_tok,
                latency_s=elapsed,
                error=err_msg,
            )
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=result,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            thinking_tokens=thinking_tok,
            latency_s=elapsed,
            extra={
                "tool_calls_made": result.get("tool_calls_made") if isinstance(result, dict) else None,
                "turns": result.get("turns") if isinstance(result, dict) else None,
            },
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


async def invoke_chat(model_name, settings, system_prompt, history, message, tools, **role_kwargs) -> InvokeResult:
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        result = await client.run_chat_loop(system_prompt=system_prompt, conversation_history=history,
                                             new_user_message=message, tools=tools)
        elapsed = time.monotonic() - t0
        in_tok = (result.get("input_tokens") if isinstance(result, dict) else None) or usage.get("input_tokens", 0)
        out_tok = (result.get("output_tokens") if isinstance(result, dict) else None) or usage.get("output_tokens", 0)
        cached_tok = (result.get("cached_tokens") if isinstance(result, dict) else None) or usage.get("cached_tokens", 0)
        thinking_tok = (result.get("thinking_tokens") if isinstance(result, dict) else None) or usage.get("thinking_tokens", 0)
        if isinstance(result, dict) and not result.get("success", True):
            return InvokeResult(
                model_name=model_name,
                provider=client.__class__.__name__,
                raw_output=result,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached_tok,
                thinking_tokens=thinking_tok,
                latency_s=elapsed,
                error=result.get("error", "chat run failed"),
            )
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=result,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            thinking_tokens=thinking_tok,
            latency_s=elapsed,
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


async def invoke_custom(model_name, settings, fn, *args, **role_kwargs) -> InvokeResult:
    """Untuk task yang fungsi produksinya SUDAH menerima `client` sebagai
    parameter (bull/bear/judge analyst, risk_gate_llm, portfolio_manager)."""
    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        out = await fn(client, *args)
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=out,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


async def invoke_system_one(
    model_name: str,
    settings: dict,
    state: Optional[dict],
    questions: Optional[list],
    prompt: str = "",
    schema: Optional[dict] = None,
    **role_kwargs,
) -> InvokeResult:
    """
    Invokes a fast decision-making model (<100ms target).
    Supports TypeSafe JEV natively, or fast generative LLMs in strict JSON classification mode.
    """
    import json
    role_kwargs.setdefault("max_tokens", 1024)
    role_kwargs.setdefault("temperature", 0.0)
    role_kwargs.setdefault("thinking", "none")

    client = make_client(model_name, settings, **role_kwargs)
    usage = _attach_usage_capture(client)
    t0 = time.monotonic()
    try:
        if hasattr(client, "classify_json") and ("typesafe" in client.__class__.__name__.lower() or "jev" in model_name.lower()):
            # Native TypeSafe JEV System One path
            out = await client.classify_json(
                prompt=prompt or "Evaluate state against questions",
                state=state or {},
                jev_questions=questions or [],
            )
        elif hasattr(client, "classify_json") and schema:
            # Standard classify_json with json schema
            formatted_prompt = f"STATE:\n{json.dumps(state or {}, indent=2)}\n\n{prompt}" if state else prompt
            out = await client.classify_json(
                formatted_prompt,
                schema=schema,
            )
        elif hasattr(client, "generate_content"):
            # Generative LLM fallback
            sys_p = "You are an ultra-fast deterministic System One decision evaluator. Output ONLY valid JSON."
            user_msg = (
                f"STATE:\n{json.dumps(state or {}, indent=2)}\n\n"
                f"QUESTIONS:\n{json.dumps(questions or [], indent=2)}\n\n"
                f"{prompt}"
            )
            raw = await client.generate_content(
                system_prompt=sys_p,
                user_message=user_msg,
                response_schema=schema,
                temperature=0.0,
            )
            if isinstance(raw, str):
                try:
                    out = json.loads(raw)
                except Exception:
                    out = {"raw_response": raw}
            else:
                out = raw
        else:
            # Base generate fallback
            formatted_prompt = f"STATE:\n{json.dumps(state or {}, indent=2)}\n\n{prompt}" if state else prompt
            raw_str = await client.generate(formatted_prompt, system="Output JSON only.")
            try:
                out = json.loads(raw_str)
            except Exception:
                out = {"raw_response": raw_str}

        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=out,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
        )
    except Exception as e:
        return InvokeResult(
            model_name=model_name,
            provider=client.__class__.__name__,
            raw_output=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            latency_s=time.monotonic() - t0,
            error=str(e),
        )


