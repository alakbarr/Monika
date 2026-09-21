"""
Three-tier system prompt architecture for prompt cache stability.
Optimized for provider prompt prefix caching across Anthropic, Gemini, and OpenAI.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any, Tuple


@dataclass
class PromptTier:
    """Represents a tier of system prompt content with cache stability metadata."""
    content: str
    cache_control: Optional[dict] = None  # e.g., {"type": "ephemeral"} for Anthropic


@dataclass
class TieredSystemPrompt:
    """Three-tier system prompt optimized for provider prompt caching.

    Tier 1 STABLE: Never changes within a session (identity, behavioral rules, tool schemas).
    Tier 2 CONTEXT: Changes only when workspace/project changes (skills catalog, instrument list).
    Tier 3 VOLATILE: Frozen snapshot at session/cycle start (chronicle, macro reality, timestamps).
    """
    tier1_stable: str = ""       # Agent identity, behavioral rules, core tool guidelines
    tier2_context: str = ""      # Skills catalog, instrument list, project context
    tier3_volatile: str = ""     # Chronicle, macro reality snapshot, session state

    def assemble(self, provider: str = "default", quarantine_volatile: bool = False) -> Union[str, List[dict]]:
        """Assemble prompt for the specific provider's caching capabilities.
        
        When quarantine_volatile is True, tier3_volatile is excluded from the system prompt
        and should be placed into the trailing user message to keep the system prompt KV-cache invariant.
        """
        if provider == "anthropic":
            blocks: List[dict] = []
            if self.tier1_stable:
                blocks.append({
                    "type": "text",
                    "text": self.tier1_stable,
                    "cache_control": {"type": "ephemeral"},
                })
            if self.tier2_context:
                blocks.append({
                    "type": "text",
                    "text": self.tier2_context,
                    "cache_control": {"type": "ephemeral"},
                })
            if self.tier3_volatile and not quarantine_volatile:
                blocks.append({
                    "type": "text",
                    "text": self.tier3_volatile,
                })
            return blocks

        # Default (OpenAI, Gemini, Ollama, Groq):
        if quarantine_volatile:
            parts = [p.strip() for p in (self.tier1_stable, self.tier2_context) if p and p.strip()]
        else:
            parts = [p.strip() for p in (self.tier1_stable, self.tier2_context, self.tier3_volatile) if p and p.strip()]
        return "\n\n".join(parts)

    def compile_stable_system(self) -> str:
        """Returns 100% cache-invariant system prompt (Tier 1 + Tier 2 only)."""
        parts = [p.strip() for p in (self.tier1_stable, self.tier2_context) if p and p.strip()]
        return "\n\n".join(parts)

    def compile_tuple(self) -> Tuple[str, str]:
        """Returns (cacheable_prefix, dynamic_suffix) tuple compatible with PromptCacheManager."""
        prefix_parts = [p.strip() for p in (self.tier1_stable, self.tier2_context) if p and p.strip()]
        prefix = "\n\n".join(prefix_parts)
        suffix = self.tier3_volatile.strip() if self.tier3_volatile else ""
        return (prefix, suffix)

    def get_ephemeral_overlay(self, context: dict) -> str:
        """Build turn-specific overlays injected into USER message, NOT system prompt.

        This preserves cache hits by keeping system prompt byte-stable.
        """
        parts = []
        if context.get("budget_warning"):
            parts.append(f"[System: {context['budget_warning']}]")
        if context.get("context_pressure"):
            parts.append(f"[System: Context at {context['context_pressure']}% capacity]")
        if context.get("session_hint"):
            parts.append(str(context["session_hint"]))
        return "\n".join(parts)


# Re-export and factory support
from utils.llm.prompt_tiering import TieredPrompt, build_tiered_prompt
