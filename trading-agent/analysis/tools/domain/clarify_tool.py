# ==============================================================================
# File: analysis/tools/domain/clarify_tool.py
# ==============================================================================

"""
Interactive Clarification Tool.
Institutional-grade engine turn protection architecture.

Enables Monika to ask structured, multi-choice clarification questions to the user
whenever high ambiguity or significant trading risks are encountered.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.Clarify")


class ClarifyInput(BaseModel):
    """Schema for asking the user clarifying questions."""
    question: str = Field(
        ...,
        description="The primary question or ambiguity that requires user confirmation."
    )
    options: List[str] = Field(
        default_factory=list,
        description="List of suggested options or choices for the user to pick from."
    )
    default_choice: Optional[str] = Field(
        None,
        description="Recommended or default choice if the user confirms without specifying."
    )
    urgency: str = Field(
        "medium",
        description="Urgency level: 'low', 'medium', 'high', or 'critical'."
    )


@unified_tool_registry.register(
    name="clarify_with_user",
    category="INTERACTIVE",
    input_model=ClarifyInput,
)
async def handle_clarify_with_user(
    params: ClarifyInput,
    context: Optional[Any] = None,
) -> str:
    """
    Format and emit clarification request to user interface (Telegram/CLI).
    """
    output = {
        "type": "clarification_request",
        "question": params.question,
        "options": params.options,
        "default_choice": params.default_choice,
        "urgency": params.urgency,
        "status": "awaiting_user_response",
    }
    logger.info(f"[ClarifyTool] Emitted clarification request: {params.question}")
    return json.dumps(output, indent=2)
