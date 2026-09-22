# ==============================================================================
# File: plugins/manifest.py
# ==============================================================================

"""
Plugin Manifest Definition & Schema Validation.
Defines metadata, dependencies, custom tools, and 12 lifecycle hook endpoints.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, field_validator

# 12 Core Monika v2 lifecycle hooks
SUPPORTED_HOOKS = [
    "pre_tool_call",
    "post_tool_call",
    "pre_llm_call",
    "post_llm_call",
    "on_llm_error",
    "pre_risk_gate",
    "post_cycle",
    "pre_order",
    "post_order",
    "on_startup",
    "on_shutdown",
    "on_risk_check",
]


class PluginManifest(BaseModel):
    """
    Formal schema for plugin.yaml manifests.
    Enforces semantic versioning, hook validity, and explicit dependencies.
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: Optional[str] = None
    enabled: bool = True
    entrypoint: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    hooks: Dict[str, str] = Field(default_factory=dict)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("hooks")
    @classmethod
    def validate_hooks(cls, v: Dict[str, str]) -> Dict[str, str]:
        for hook_name, target in v.items():
            if hook_name not in SUPPORTED_HOOKS:
                # Log warning or reject invalid hook
                raise ValueError(
                    f"Unsupported hook '{hook_name}'. Supported hooks: {', '.join(SUPPORTED_HOOKS)}"
                )
            if ":" not in target:
                raise ValueError(f"Hook target '{target}' must follow 'module.path:callable_name' format.")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Plugin name cannot be empty.")
        return v
