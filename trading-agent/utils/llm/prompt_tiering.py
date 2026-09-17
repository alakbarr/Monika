# ==============================================================================
# File: utils/llm/prompt_tiering.py
# ==============================================================================

"""
Three-Tier Prompt Architecture.
Separates prompt construction into:
- Tier 1: Core identity, persona, tool instructions (stable, cacheable)
- Tier 2: Domain rules, reference guides, instrument constants (stable, cacheable)
- Tier 3: Volatile runtime context, timestamps, market snapshot, ephemeral state (dynamic)
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class TieredPrompt:
    """Represents a structured 3-tier prompt."""
    tier1_identity: str = ""
    tier2_domain: str = ""
    tier3_runtime: str = ""

    def get_cacheable_prefix(self) -> str:
        """Combines Tier 1 and Tier 2 into a single stable, cacheable prefix."""
        parts = []
        if self.tier1_identity and self.tier1_identity.strip():
            parts.append(self.tier1_identity.strip())
        if self.tier2_domain and self.tier2_domain.strip():
            parts.append(self.tier2_domain.strip())
        return "\n\n".join(parts)

    def get_dynamic_suffix(self) -> str:
        """Returns Tier 3 dynamic/volatile runtime context."""
        return self.tier3_runtime.strip() if self.tier3_runtime else ""

    def compile_tuple(self) -> Tuple[str, str]:
        """
        Returns (cacheable_prefix, dynamic_suffix) tuple
        compatible with PromptCacheManager and AgentHarness.
        """
        return (self.get_cacheable_prefix(), self.get_dynamic_suffix())

    def compile_full(self) -> str:
        """Returns the full monolithic prompt string."""
        prefix = self.get_cacheable_prefix()
        suffix = self.get_dynamic_suffix()
        if prefix and suffix:
            return f"{prefix}\n\n{suffix}"
        return prefix or suffix


def build_tiered_prompt(
    tier1_identity: str,
    tier2_domain: str = "",
    tier3_runtime: str = "",
) -> TieredPrompt:
    """Helper factory for creating a TieredPrompt."""
    return TieredPrompt(
        tier1_identity=tier1_identity,
        tier2_domain=tier2_domain,
        tier3_runtime=tier3_runtime,
    )


# Re-export classes from prompt_tiers for cross-compatibility
from utils.llm.prompt_tiers import TieredSystemPrompt, PromptTier

