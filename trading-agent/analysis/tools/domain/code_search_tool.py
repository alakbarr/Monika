# ==============================================================================
# File: analysis/tools/domain/code_search_tool.py
# ==============================================================================

"""
High-Performance Code Search & Regex Navigation Tool.
Institutional-grade software engineering developer tools for Monika.

Provides fast regex and keyword pattern search across the codebase with:
  1. Automatic exclusion of build artifacts, virtualenvs, .git, and binary files.
  2. Precision line windowing and context snippet extraction.
  3. Bounded result limits to prevent token context saturation.
  4. Integration with unified_tool_registry.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.CodeSearch")

_DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "alembic",
    ".idea",
    ".vscode",
}

_BINARY_EXTENSIONS = {
    ".pyc",
    ".pyd",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".tar",
    ".zip",
    ".gz",
    ".parquet",
    ".feather",
}


class CodeSearchInput(BaseModel):
    """Input parameters for searching code patterns."""
    pattern: str = Field(
        ...,
        description="The substring or regex pattern to search for across files."
    )
    path: str = Field(
        ".",
        description="Directory or file path to search within (default current directory)."
    )
    file_pattern: Optional[str] = Field(
        None,
        description="Optional glob pattern to filter filenames (e.g. '*.py', '*.ts', '*.yaml')."
    )
    max_results: int = Field(
        30,
        ge=1,
        le=200,
        description="Maximum number of search matches to return (default 30)."
    )
    context_lines: int = Field(
        2,
        ge=0,
        le=10,
        description="Number of context lines before and after each match (default 2)."
    )
    is_regex: bool = Field(
        True,
        description="If True, treats pattern as regular expression; if False, literal string."
    )


class CodeSearchEngine:
    """Core search engine scanning filesystem directories with safety filters."""

    @classmethod
    def is_binary_file(cls, path: Path) -> bool:
        if path.suffix.lower() in _BINARY_EXTENSIONS:
            return True
        try:
            with open(path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return True
        except Exception:
            return True
        return False

    @classmethod
    def search(
        cls,
        pattern: str,
        base_path: str = ".",
        file_pattern: Optional[str] = None,
        max_results: int = 30,
        context_lines: int = 2,
        is_regex: bool = True,
    ) -> List[Dict[str, Any]]:
        """Scans filesystem and returns structured search matches with context."""
        root = Path(base_path).resolve()
        if not root.exists():
            return []

        flags = re.IGNORECASE
        if is_regex:
            try:
                regex = re.compile(pattern, flags)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression pattern: {exc}")
        else:
            regex = re.compile(re.escape(pattern), flags)

        matches: List[Dict[str, Any]] = []

        files_to_scan: List[Path] = []
        if root.is_file():
            files_to_scan.append(root)
        else:
            for dirpath, dirnames, filenames in os.walk(root):
                # Filter out ignored directories in-place
                dirnames[:] = [d for d in dirnames if d not in _DEFAULT_IGNORE_DIRS and not d.startswith(".")]
                for fname in filenames:
                    fpath = Path(dirpath) / fname
                    if file_pattern and not fpath.match(file_pattern):
                        continue
                    if fpath.suffix.lower() in _BINARY_EXTENSIONS:
                        continue
                    files_to_scan.append(fpath)

        for fpath in files_to_scan:
            if len(matches) >= max_results:
                break

            if cls.is_binary_file(fpath):
                continue

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                if len(matches) >= max_results:
                    break

                if regex.search(line):
                    start_ctx = max(0, idx - context_lines)
                    end_ctx = min(len(lines), idx + context_lines + 1)
                    snippet = lines[start_ctx:end_ctx]

                    # Format relative path for concise output
                    try:
                        rel_path = fpath.relative_to(Path.cwd()).as_posix()
                    except ValueError:
                        rel_path = fpath.as_posix()

                    matches.append({
                        "file": rel_path,
                        "line_number": idx + 1,
                        "line_content": line.rstrip("\r\n"),
                        "snippet": "".join(snippet),
                    })

        return matches


@unified_tool_registry.register(
    name="search_files",
    category="FILESYSTEM",
    input_model=CodeSearchInput,
)
async def handle_search_files(
    params: CodeSearchInput,
    context: Optional[Any] = None,
) -> str:
    """Fast regex and keyword code search across codebase files with context windowing."""
    try:
        results = CodeSearchEngine.search(
            pattern=params.pattern,
            base_path=params.path,
            file_pattern=params.file_pattern,
            max_results=params.max_results,
            context_lines=params.context_lines,
            is_regex=params.is_regex,
        )
    except Exception as exc:
        return f"[ERROR] Code search failed: {exc}"

    if not results:
        return f"[SEARCH RESULTS] No matches found for '{params.pattern}' in '{params.path}'."

    output_lines = [f"[SEARCH RESULTS] Found {len(results)} matches for '{params.pattern}':", ""]
    for r in results:
        output_lines.append(f"File: {r['file']}:{r['line_number']}")
        output_lines.append("```")
        output_lines.append(r["snippet"].rstrip())
        output_lines.append("```")
        output_lines.append("")

    return "\n".join(output_lines)
