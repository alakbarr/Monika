"""
Domain models for Monika Harness surface, components, and safety invariants.

Follows the 8-component modular harness architecture (c1..c8) from Harness^2:
c1: System Prompt
c2: Guardrails
c3: Memory
c4: Tool Guidance
c5: Subagents
c6: Skills
c7: Scripts
c8: Plugins

Strictly maintains the Mechanical Fortress invariant: risk, sizing, and broker paths
are non-negotiably immutable and cannot be altered or softened by any harness mutation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class ComponentType(str, Enum):
    """The 8 modular harness components."""

    SYSTEM_PROMPT = "system_prompt"  # c1: foundational framing and persona
    GUARDRAIL = "guardrail"  # c2: hard constraints and safety bounds
    MEMORY = "memory"  # c3: long-term memory and epistemic context
    TOOL_GUIDANCE = "tool_guidance"  # c4: advice on tool parameterization and usage
    SUBAGENT = "subagent"  # c5: specialized delegated analyst agents
    SKILL = "skill"  # c6: reusable procedural trading playbooks
    SCRIPT = "script"  # c7: deterministic quant calculation scripts
    PLUGIN = "plugin"  # c8: execution hooks inside the tool loop


class HarnessViolationError(ValueError):
    """Raised when a harness proposal violates domain invariants or safety rules."""


@dataclass(frozen=True)
class HarnessComponent:
    """An individual file-mounted component on the harness surface."""

    rel_path: str
    component_type: ComponentType
    content: str
    checksum: str = field(default="")

    def __post_init__(self) -> None:
        if not self.checksum:
            digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            object.__setattr__(self, "checksum", digest)


@dataclass(frozen=True)
class SurfaceSpec:
    """
    Specification of the editable agent harness surface.
    Defines component directories, size limits, and strictly reserved immutable paths.
    """

    name: str
    always_on: tuple[str, ...]
    always_on_max_chars: int
    always_on_cap_reason: str
    skill_dir: str
    subagent_dir: str
    script_dir: str
    plugin_dir: str
    reserved_paths: frozenset[str] = field(default_factory=frozenset)
    allowed_script_extensions: tuple[str, ...] = (".py",)
    allowed_plugin_extensions: tuple[str, ...] = (".py", ".ts")


@dataclass(frozen=True)
class HarnessDiff:
    """Represents changes proposed between two harness trees."""

    added: Mapping[str, str] = field(default_factory=dict)
    modified: Mapping[str, str] = field(default_factory=dict)
    removed: Sequence[str] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.modified or self.removed)

    def summary(self) -> dict[str, int]:
        return {
            "added_count": len(self.added),
            "modified_count": len(self.modified),
            "removed_count": len(self.removed),
        }
