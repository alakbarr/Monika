# ==============================================================================
# File: analysis/tools/domain/file_tools.py
# ==============================================================================

"""
Universal Filesystem Domain Tools.
Institutional-grade precision file inspection, safe writing, and fuzzy patching.

Tools registered:
  - read_file: Reads file content with 1-indexed line numbers and records read hash.
  - write_file: Writes file under stale-overwrite protection and AST/syntax validation.
  - patch: Applies targeted replacement using 9-stage fuzzy matching and syntax linting.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from analysis.tools.file_patch_engine import FilePatchEngine
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.FileTools")

# Global singleton engine instance maintaining session read records
_FILE_PATCH_ENGINE = FilePatchEngine()


def get_file_patch_engine() -> FilePatchEngine:
    """Return the global FilePatchEngine singleton."""
    return _FILE_PATCH_ENGINE


class ReadFileInput(BaseModel):
    """Input parameters for reading file content."""
    path: str = Field(
        ...,
        description="Path to the file to read (relative to workspace or absolute)."
    )
    offset: int = Field(
        1,
        ge=1,
        description="1-indexed line number to start reading from (default 1)."
    )
    limit: int = Field(
        2000,
        ge=1,
        le=10000,
        description="Maximum number of lines to return (default 2000)."
    )


class WriteFileInput(BaseModel):
    """Input parameters for writing or creating a file."""
    path: str = Field(
        ...,
        description="Path to the file to write. Will be created along with parent directories if not existing."
    )
    content: str = Field(
        ...,
        description="Full text content to write into the file."
    )


class PatchFileInput(BaseModel):
    """Input parameters for fuzzy patching a file."""
    path: str = Field(
        ...,
        description="Path to the file to patch."
    )
    old_string: str = Field(
        ...,
        description="The exact or near-exact string/block to be replaced in the target file."
    )
    new_string: str = Field(
        ...,
        description="The replacement string/block to insert."
    )
    replace_all: bool = Field(
        False,
        description="If True, replaces all occurrences of old_string. If False, replaces only the first match."
    )


@unified_tool_registry.register(
    name="read_file",
    category="FILESYSTEM",
    input_model=ReadFileInput,
)
async def handle_read_file(
    params: ReadFileInput,
    context: Optional[Any] = None,
) -> str:
    """Read file content with line numbers under stale-overwrite tracking."""
    success, result = _FILE_PATCH_ENGINE.read_file(
        path=params.path,
        offset=params.offset,
        limit=params.limit,
    )
    return result


@unified_tool_registry.register(
    name="write_file",
    category="FILESYSTEM",
    input_model=WriteFileInput,
)
async def handle_write_file(
    params: WriteFileInput,
    context: Optional[Any] = None,
) -> str:
    """Write file under stale-overwrite protection and post-write syntax linting."""
    success, result = _FILE_PATCH_ENGINE.write_file(
        path=params.path,
        content=params.content,
    )
    status_tag = "[SUCCESS]" if success else "[REJECTED/ERROR]"
    return f"{status_tag} {result}"


@unified_tool_registry.register(
    name="patch",
    category="FILESYSTEM",
    input_model=PatchFileInput,
)
async def handle_patch(
    params: PatchFileInput,
    context: Optional[Any] = None,
) -> str:
    """Apply targeted replacement via 9-stage fuzzy matching with automatic syntax validation."""
    success, result = _FILE_PATCH_ENGINE.patch_file(
        path=params.path,
        old_string=params.old_string,
        new_string=params.new_string,
        replace_all=params.replace_all,
    )
    status_tag = "[SUCCESS]" if success else "[REJECTED/ERROR]"
    return f"{status_tag} {result}"
