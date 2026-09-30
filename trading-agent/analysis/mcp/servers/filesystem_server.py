# ==============================================================================
# File: analysis/mcp/servers/filesystem_server.py
# Description: Global Workspace & Playbook Filesystem MCP Server
# Provides read/write access to user notes (Obsidian), markdown docs, and playbooks.
# ==============================================================================

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class FilesystemMcpServer:
    """Safe high-performance MCP Server for Obsidian vaults, documents, and playbooks."""

    def __init__(self):
        self.name = "workspace-filesystem-server"
        self.version = "2.0.0"
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "fs_read_file",
                "description": "Read the text content of a file (e.g. Obsidian markdown note, text document, config).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Full path or relative path to the file.",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to read (default: 50000).",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "fs_write_file",
                "description": "Create, overwrite, or append content to a file (creates parent folders automatically).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the target file.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content to write or append.",
                        },
                        "append": {
                            "type": "boolean",
                            "description": "If true, append to existing file instead of overwriting (default: false).",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "fs_list_directory",
                "description": "List files and subdirectories in a folder (e.g. Obsidian vault or project folder).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the directory.",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "If true, scan subdirectories recursively (default: false).",
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Maximum number of items to return (default: 100).",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "fs_search_files",
                "description": "Search for files by name pattern or text content within a directory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Directory path to search in.",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Filename pattern (e.g. '*.md') or substring to match.",
                        },
                        "containing_text": {
                            "type": "string",
                            "description": "Optional text to search inside file contents.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum search matches to return (default: 30).",
                        },
                    },
                    "required": ["directory"],
                },
            },
            {
                "name": "fs_list_playbooks",
                "description": "List all markdown playbook files in skills/trading directory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "fs_read_playbook",
                "description": "Read the text of a specific playbook or markdown document safely.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the markdown file (e.g. 'central_banks_framework.md', 'smc_ict_playbook.md').",
                        }
                    },
                    "required": ["filename"],
                },
            },
        ]

    def _resolve_path(self, raw_path: str) -> Path:
        p = Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()
        return p

    def _resolve_safe_path(self, filename: str) -> Path:
        clean = Path(filename).name
        target = self.root_dir / "skills" / "trading" / clean
        if not target.exists():
            clean_stem = Path(filename).stem
            variants = [clean_stem, clean_stem.replace("_", "-"), clean_stem.replace("-", "_")]
            for v in variants:
                t_skill = self.root_dir / "skills" / "trading" / v / "SKILL.md"
                if t_skill.exists():
                    return t_skill
            target_pb = self.root_dir / "skills" / "trading" / "playbooks" / clean
            if target_pb.exists():
                return target_pb
            for v in variants:
                pb_skill = self.root_dir / "skills" / "trading" / "playbooks" / v / "SKILL.md"
                if pb_skill.exists():
                    return pb_skill
            target_cr = self.root_dir / "skills" / "crystallized" / clean
            if target_cr.exists():
                return target_cr
            for v in variants:
                cr_skill = self.root_dir / "skills" / "crystallized" / v / "SKILL.md"
                if cr_skill.exists():
                    return cr_skill
            raise FileNotFoundError(f"File '{clean}' not found in skills directory.")
        return target

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "fs_read_file":
            raw_path = arguments.get("path", "").strip()
            if not raw_path:
                raise ValueError("'path' is required")
            p = self._resolve_path(raw_path)
            if not p.exists():
                raise FileNotFoundError(f"File not found: {p}")
            if p.is_dir():
                raise IsADirectoryError(f"Target is a directory: {p}")
            max_chars = int(arguments.get("max_chars", 50000))
            content = p.read_text(encoding="utf-8", errors="replace")
            return {
                "path": str(p),
                "total_chars": len(content),
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }

        elif tool_name == "fs_write_file":
            raw_path = arguments.get("path", "").strip()
            if not raw_path:
                raise ValueError("'path' is required")
            content = arguments.get("content", "")
            append = bool(arguments.get("append", False))
            p = self._resolve_path(raw_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode, encoding="utf-8") as f:
                f.write(content)
            return {
                "status": "success",
                "path": str(p),
                "mode": "appended" if append else "written",
                "bytes_written": len(content.encode("utf-8")),
            }

        elif tool_name == "fs_list_directory":
            raw_path = arguments.get("path", "").strip()
            if not raw_path:
                raise ValueError("'path' is required")
            p = self._resolve_path(raw_path)
            if not p.exists():
                raise FileNotFoundError(f"Directory not found: {p}")
            if not p.is_dir():
                raise NotADirectoryError(f"Target is not a directory: {p}")
            recursive = bool(arguments.get("recursive", False))
            max_items = min(int(arguments.get("max_items", 100)), 500)
            items = []
            iterator = p.rglob("*") if recursive else p.iterdir()
            for child in iterator:
                try:
                    is_dir = child.is_dir()
                    items.append({
                        "name": child.name,
                        "path": str(child),
                        "type": "directory" if is_dir else "file",
                        "size": child.stat().st_size if not is_dir else 0,
                    })
                    if len(items) >= max_items:
                        break
                except Exception:
                    continue
            return {"directory": str(p), "count": len(items), "items": items}

        elif tool_name == "fs_search_files":
            raw_dir = arguments.get("directory", "").strip()
            if not raw_dir:
                raise ValueError("'directory' is required")
            p = self._resolve_path(raw_dir)
            if not p.exists() or not p.is_dir():
                raise NotADirectoryError(f"Invalid directory: {p}")
            pattern = arguments.get("pattern", "*") or "*"
            containing = arguments.get("containing_text", "")
            max_results = min(int(arguments.get("max_results", 30)), 100)
            matches = []
            for child in p.rglob(pattern):
                if not child.is_file():
                    continue
                if containing:
                    try:
                        text = child.read_text(encoding="utf-8", errors="ignore")
                        if containing.lower() not in text.lower():
                            continue
                    except Exception:
                        continue
                matches.append({"name": child.name, "path": str(child), "size": child.stat().st_size})
                if len(matches) >= max_results:
                    break
            return {"directory": str(p), "match_count": len(matches), "matches": matches}

        elif tool_name == "fs_list_playbooks":
            skills_dir = self.root_dir / "skills" / "trading"
            files = []
            for d in skills_dir.glob("*/SKILL.md"):
                files.append(f"{d.parent.name}/SKILL.md")
            for f in skills_dir.glob("*.md"):
                if f.name != "SKILL.md":
                    files.append(f.name)
            pb_dir = skills_dir / "playbooks"
            if pb_dir.exists():
                for d in pb_dir.glob("*/SKILL.md"):
                    files.append(f"playbooks/{d.parent.name}/SKILL.md")
                for f in pb_dir.glob("*.md"):
                    if f.name != "SKILL.md":
                        files.append(f"playbooks/{f.name}")
            return {"files": sorted(files)}

        elif tool_name == "fs_read_playbook":
            fname = arguments.get("filename", "")
            safe_path = self._resolve_safe_path(fname)
            content = safe_path.read_text(encoding="utf-8")
            return {"filename": safe_path.name, "content": content}

        raise ValueError(f"Unknown tool: '{tool_name}'")

    async def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if method == "initialize":
            return make_result_response(
                req_id,
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            )
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            return make_result_response(req_id, {})
        elif method == "tools/list":
            return make_result_response(req_id, {"tools": self.get_tool_definitions()})
        elif method == "tools/call":
            t_name = params.get("name")
            args = params.get("arguments", {}) or {}
            if not isinstance(t_name, str):
                return make_error_response(req_id, -32602, "Invalid params: 'name' must be a string")
            try:
                res = self.handle_tool_call(t_name, args)
                return make_result_response(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(res, indent=2, default=str)}]},
                )
            except Exception as e:
                return make_result_response(
                    req_id,
                    {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]},
                )
        return make_error_response(req_id, METHOD_NOT_FOUND, f"Unknown method: '{method}'")

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
                resp = await self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err = make_error_response(None, PARSE_ERROR, str(e))
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = FilesystemMcpServer()
    asyncio.run(server.run())
