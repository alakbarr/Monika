# ==============================================================================
# File: domain/ports/llm.py
# ==============================================================================

"""
Domain LLM Port.

Defines pure abstract interfaces for language model generation, structured JSON
inference, and agent deliberation (Dependency Inversion Principle).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class LlmPort(Protocol):
    """Standardized pure domain protocol for LLM text and structured generation."""

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """Single-turn text generation."""
        ...

    async def generate_json(
        self,
        prompt: str,
        system: str = "",
        schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Generate validated structured JSON output."""
        ...

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Generate and classify structured JSON output."""
        ...

    async def generate_content(
        self,
        system_prompt: str = "",
        user_message: str = "",
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> Optional[Any]:
        """Generate content supporting schema enforcement and structured payloads."""
        ...


# Semantic alias
ModelProviderPort = LlmPort
