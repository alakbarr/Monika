"""
Concrete surface specification and invariant validators for Monika.

Maps the 8 Harness^2 components to Monika's trading architecture:
c1: systemprompt.md               -> Analytical system prompts & reasoning posture
c2: guardrails.md                 -> Analytical guardrails & grounding bounds
c3: LongTermMEMORY.md             -> Epistemic ledger & regime reflections
c4: tool_guidance.md              -> Usage guidance for quant/market tools
c5: sub_agents/<name>/AGENT.md    -> Specialized analyst subagents (Macro, Micro, SMC)
c6: skills/<name>/SKILL.md        -> Reusable trading playbooks & procedural rules
c7: scripts/<name>.py             -> Deterministic quant calculation helpers
c8: plugins/<name>.py             -> Pre/post execution tool hooks

Strictly enforces the Mechanical Fortress Invariant:
No harness edit is ever allowed to touch risk gates, position sizing limits,
broker interfaces, or database migrations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from monika.domain.harness.models import (
    ComponentType,
    HarnessViolationError,
    SurfaceSpec,
)

# Immutable paths that can NEVER be touched, proposed, or modified by any harness edit.
RESERVED_IMMUTABLE_PATTERNS: frozenset[str] = frozenset(
    {
        r"^src/monika/domain/risk/.*",
        r"^src/monika/domain/trade/.*",
        r"^src/monika/infrastructure/brokers/.*",
        r"^src/monika/infrastructure/database/migrations/.*",
        r"^\.env.*",
        r".*\.pem$",
        r".*\.key$",
        r".*credentials.*\.json$",
        r"^config/settings\.yaml$",
    }
)

MONIKA_SURFACE = SurfaceSpec(
    name="monika_trading_surface",
    always_on=(
        "systemprompt.md",
        "guardrails.md",
        "LongTermMEMORY.md",
        "tool_guidance.md",
    ),
    always_on_max_chars=32_000,
    always_on_cap_reason="Tokens in always-on components directly compete with the model reasoning and market context window",
    skill_dir="skills",
    subagent_dir="sub_agents",
    script_dir="scripts",
    plugin_dir="plugins",
    reserved_paths=RESERVED_IMMUTABLE_PATTERNS,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


def normalize_rel_path(rel_path: str) -> str:
    """
    Normalizes relative paths, strictly rejecting directory traversal or absolute escapes.
    """
    cleaned = str(rel_path).strip().replace("\\", "/")
    if cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise HarnessViolationError(f"Path escapes harness surface boundary: {rel_path!r}")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.strip("/")


def is_path_reserved(rel_path: str, spec: SurfaceSpec = MONIKA_SURFACE) -> bool:
    """Checks if a path matches any reserved immutable system pattern."""
    norm = normalize_rel_path(rel_path)
    for pat in spec.reserved_paths:
        if re.search(pat, norm, re.IGNORECASE):
            return True
    return False


def classify_component(rel_path: str, spec: SurfaceSpec = MONIKA_SURFACE) -> ComponentType:
    """
    Classifies a file path into one of the 8 Harness components.
    Raises HarnessViolationError if path is off-surface or reserved.
    """
    norm = normalize_rel_path(rel_path)

    if is_path_reserved(norm, spec):
        raise HarnessViolationError(f"Attempted to access reserved immutable path: {norm!r}")

    if norm == "systemprompt.md":
        return ComponentType.SYSTEM_PROMPT
    if norm == "guardrails.md":
        return ComponentType.GUARDRAIL
    if norm == "LongTermMEMORY.md":
        return ComponentType.MEMORY
    if norm == "tool_guidance.md":
        return ComponentType.TOOL_GUIDANCE

    parts = norm.split("/")
    top_dir = parts[0]

    if top_dir == spec.skill_dir and len(parts) >= 2:
        return ComponentType.SKILL
    if top_dir == spec.subagent_dir and len(parts) >= 2:
        return ComponentType.SUBAGENT
    if top_dir == spec.script_dir and len(parts) >= 2:
        if any(norm.endswith(ext) for ext in spec.allowed_script_extensions):
            return ComponentType.SCRIPT
    if top_dir == spec.plugin_dir and len(parts) >= 2:
        if any(norm.endswith(ext) for ext in spec.allowed_plugin_extensions):
            return ComponentType.PLUGIN

    raise HarnessViolationError(f"Path is off-surface or unrecognized by harness spec: {norm!r}")


def validate_tree_invariants(tree: Mapping[str, str], spec: SurfaceSpec = MONIKA_SURFACE) -> None:
    """
    Validates a complete harness tree against surface invariants:
    1. No reserved paths modified or included.
    2. Total characters in always_on components do not exceed `always_on_max_chars`.
    3. All components belong to valid surface classifications.
    4. Guardrails and system prompt are non-empty.
    """
    total_always_on = 0

    for path, content in tree.items():
        norm = normalize_rel_path(path)
        comp_type = classify_component(norm, spec)

        if norm in spec.always_on:
            if not content.strip() and norm in ("systemprompt.md", "guardrails.md"):
                raise HarnessViolationError(f"Core always_on component '{norm}' cannot be empty.")
            total_always_on += len(content)

    if total_always_on > spec.always_on_max_chars:
        raise HarnessViolationError(
            f"Always-on harness components exceed maximum character cap: "
            f"{total_always_on} > {spec.always_on_max_chars}. ({spec.always_on_cap_reason})"
        )
