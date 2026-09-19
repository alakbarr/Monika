"""
Model-family gated execution discipline and verification prompts.
"""

from typing import Optional

TOOL_USE_ENFORCEMENT_MODELS = ("gpt", "codex", "gemini", "gemma", "deepseek", "qwen", "glm")
TRADING_VERIFICATION_MODELS = ("gpt", "deepseek", "qwen", "glm")

TOOL_USE_ENFORCEMENT_GUIDANCE = """# Mandatory Tool Execution Discipline
You MUST use your tools to query real market quotes, news, and indicators — NEVER estimate or answer from memory.
When you announce an action (e.g. 'checking ATR', 'reading current quote', 'retrieving market structure'), you MUST immediately invoke the corresponding tool call in the same response.
Never end your turn with a promise of future action without executing it now."""

TRADING_VERIFICATION_GUIDANCE = """# Verification & Mathematical Grounding
Before submitting any trading recommendation or concluding analysis:
1. Verify SL and TP distances are mathematically grounded in ATR and structure, not arbitrary guesses.
2. Confirm R:R ratio meets minimum policy requirements (>= 1.3:1).
3. If tool calls returned errors or empty sets, label data unavailable — NEVER fabricate indicator values.
4. If confluences are below threshold (min 5/14), conclude with WAIT immediately."""


def get_model_discipline(model_name: Optional[str]) -> str:
    """
    Returns targeted operational guidance based on model family traits.
    Returns empty string if model already adheres to discipline or is unknown.
    """
    if not model_name:
        return ""

    model_lower = model_name.lower()
    sections = []

    if any(m in model_lower for m in TOOL_USE_ENFORCEMENT_MODELS):
        sections.append(TOOL_USE_ENFORCEMENT_GUIDANCE)

    if any(m in model_lower for m in TRADING_VERIFICATION_MODELS):
        sections.append(TRADING_VERIFICATION_GUIDANCE)

    return "\n\n".join(sections)
