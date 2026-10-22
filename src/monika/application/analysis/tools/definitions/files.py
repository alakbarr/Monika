# ==============================================================================
# File: application/analysis/tools/definitions/files.py
# ==============================================================================

"""
Filesystem tool schemas for general-purpose coding and workspace tasks.

Execution handlers live in ``analysis/tools/domain/file_tools.py``; these
schemas make the tools reachable from the operator catalog used by the chat
harness.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

READ_FILE = _tool(
    name="read_file",
    description="Read a file with 1-indexed line numbers and record it for stale-overwrite protection.",
    properties={
        "path": {"type": "string", "description": "Path to the file (relative to workspace or absolute)."},
        "offset": {"type": "integer", "description": "1-indexed line to start reading from.", "default": 1},
        "limit": {"type": "integer", "description": "Maximum number of lines to return.", "default": 2000},
    },
    required=["path"],
)


WRITE_FILE = _tool(
    name="write_file",
    description="Create or write a file under stale-overwrite protection and post-write syntax validation.",
    properties={
        "path": {"type": "string", "description": "Path to the file to write."},
        "content": {"type": "string", "description": "Full text content to write."},
        "allow_overwrite": {
            "type": "boolean",
            "description": "Set true to intentionally overwrite an existing file larger than 100 lines.",
            "default": False,
        },
    },
    required=["path", "content"],
)


PATCH_FILE = _tool(
    name="patch",
    description="Apply a targeted file replacement with fuzzy matching and automatic syntax validation.",
    properties={
        "path": {"type": "string", "description": "Path to the file to patch."},
        "old_string": {"type": "string", "description": "Exact or near-exact block to replace."},
        "new_string": {"type": "string", "description": "Replacement block."},
        "replace_all": {
            "type": "boolean",
            "description": "Replace every occurrence instead of only the first.",
            "default": False,
        },
    },
    required=["path", "old_string", "new_string"],
)


FILE_TOOLS = [READ_FILE, WRITE_FILE, PATCH_FILE]
