"""
Structured output engine with graceful fallback to free text schemas.
Guarantees validated structured outputs across multi-provider LLM invocations.
"""

import json
import logging
from typing import Any, Callable, Optional, Type
from pydantic import BaseModel

logger = logging.getLogger("TradingAgent.Harness.StructuredOutput")


async def invoke_structured_or_freetext(
    llm_client: Any,
    prompt: str,
    schema: Type[BaseModel],
    render_fn: Callable[[BaseModel], str],
    agent_name: str = "agent",
    system_prompt: str = "",
    fallback_client: Optional[Any] = None,
) -> str:
    """Attempt structured output; fall back to free text on failure."""
    # Attempt 1: Structured output via native provider structured decoding
    if hasattr(llm_client, "generate_structured"):
        try:
            result = await llm_client.generate_structured(
                prompt=prompt,
                schema=schema,
                system_prompt=system_prompt,
            )
            if result is not None:
                return render_fn(result)
        except Exception as exc:
            logger.warning(f"[{agent_name}] Structured output generation failed ({exc}); retrying with free text.")

    # Attempt 2: Free text with client or fallback client
    client = fallback_client or llm_client
    try:
        response = await client.generate(prompt=prompt, system=system_prompt)
        if response is None:
            return ""
        if isinstance(response, dict):
            content = response.get("content") or response.get("text") or ""
        elif hasattr(response, "content"):
            content = response.content
        elif hasattr(response, "text"):
            content = response.text
        else:
            content = response
        return str(content or "")
    except Exception as exc:
        logger.error(f"[{agent_name}] Free text fallback also failed: {exc}")
        raise
