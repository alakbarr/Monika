# ==============================================================================
# File: plugins/manifest.py
# ==============================================================================

"""
Plugin Manifest Definition & Schema Validation.
Defines metadata, dependencies, custom tools, and 12 lifecycle hook endpoints.
"""

from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator

# Core Monika lifecycle hooks
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
    # Extended session and pipeline stage hooks
    "on_session_start",
    "on_session_end",
    "pre_stage1",
    "post_stage1",
    "pre_stage2",
    "post_stage2",
]


class PluginManifest(BaseModel):
    """
    Formal schema for plugin.yaml manifests.
    Enforces semantic versioning, hook validity, explicit dependencies, and capabilities.
    Supports both dictionary-mapped hooks and list-declared hooks.
    """
    id: Optional[str] = None
    name: str
    version: str = "1.0.0"
    category: str = "middleware"
    description: str = ""
    author: Optional[str] = None
    enabled: bool = True
    entrypoint: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    hooks: Union[Dict[str, str], List[str]] = Field(default_factory=dict)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("hooks")
    @classmethod
    def validate_hooks(cls, v: Union[Dict[str, str], List[str]]) -> Union[Dict[str, str], List[str]]:
        if isinstance(v, dict):
            for hook_name, target in v.items():
                if hook_name not in SUPPORTED_HOOKS:
                    raise ValueError(
                        f"Unsupported hook '{hook_name}'. Supported hooks: {', '.join(SUPPORTED_HOOKS)}"
                    )
                if ":" not in target:
                    raise ValueError(f"Hook target '{target}' must follow 'module.path:callable_name' format.")
            return v
        elif isinstance(v, list):
            for hook_name in v:
                if hook_name not in SUPPORTED_HOOKS:
                    raise ValueError(
                        f"Unsupported hook '{hook_name}'. Supported hooks: {', '.join(SUPPORTED_HOOKS)}"
                    )
            return v
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Plugin name cannot be empty.")
        return v
