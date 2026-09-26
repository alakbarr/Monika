# ==============================================================================
# File: analysis/memory/sharegpt_exporter.py
# ==============================================================================

"""
ShareGPT and OpenAI Fine-Tuning Trajectory Exporter.

Converts multi-turn agent conversations, quantitative debates, and tool-interaction trajectories
into standardized ShareGPT and OpenAI JSON Lines formats for model fine-tuning and evaluation.
Includes cross-platform file locking (msvcrt on Windows, fcntl on POSIX) for safe concurrent appends.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def convert_scratchpad_to_think(content: str) -> str:
    """
    Normalizes internal scratchpad and reasoning tags to standard <think> tags
    compatible with DeepSeek-R1/V4, Qwen, and modern reasoning evaluators.
    """
    if not content:
        return ""
    text = content.replace("<REASONING_SCRATCHPAD>", "<think>").replace("</REASONING_SCRATCHPAD>", "</think>")
    text = text.replace("<scratchpad>", "<think>").replace("</scratchpad>", "</think>")
    return text


def _lock_append_handle(f: Any, acquire: bool) -> None:
    """
    Cross-platform append file locking:
    msvcrt.locking on Windows NT, fcntl.flock on POSIX.
    """
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if acquire else msvcrt.LK_UNLCK, 1)
        f.seek(0, os.SEEK_END)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if acquire else fcntl.LOCK_UN)


class ShareGptExporter:
    """
    Formats and exports agent trajectory logs for fine-tuning.
    """

    @staticmethod
    def to_sharegpt_format(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Converts role-based messages to ShareGPT format:
        system -> system
        user -> human
        assistant -> gpt
        tool -> gpt (tool output context)
        """
        conversations: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = convert_scratchpad_to_think(str(msg.get("content") or ""))

            # Append tool calls if present in assistant message
            tool_calls = msg.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                tool_lines = []
                for tc in tool_calls:
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    name = fn.get("name") or tc.get("name", "tool")
                    args = fn.get("arguments") or tc.get("arguments", "")
                    tool_lines.append(f"<tool_call>{name}({args})</tool_call>")
                if tool_lines:
                    content = f"{content}\n" + "\n".join(tool_lines) if content else "\n".join(tool_lines)

            if role == "system":
                conversations.append({"from": "system", "value": content})
            elif role == "user":
                conversations.append({"from": "human", "value": content})
            elif role == "assistant":
                conversations.append({"from": "gpt", "value": content})
            elif role == "tool":
                conversations.append({"from": "gpt", "value": f"<tool_response>{content}</tool_response>"})

        return conversations

    @staticmethod
    def to_openai_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converts messages into standard OpenAI fine-tuning message structure.
        """
        formatted: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = convert_scratchpad_to_think(str(msg.get("content") or ""))
            entry: Dict[str, Any] = {"role": role, "content": content}
            if msg.get("tool_calls"):
                entry["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                entry["tool_call_id"] = msg["tool_call_id"]
            formatted.append(entry)
        return formatted

    @classmethod
    def save_trajectory(
        cls,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        completed: bool,
        output_file: Optional[str | Path] = None,
        schema: str = "sharegpt",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """
        Appends formatted trajectory to a JSONL file with exclusive write lock.
        """
        if not messages:
            return None

        if schema == "openai":
            record_payload = {"messages": cls.to_openai_format(messages)}
        else:
            record_payload = {"conversations": cls.to_sharegpt_format(messages)}

        record = {
            **record_payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "completed": completed,
            "metadata": metadata or {},
        }

        if output_file is None:
            filename = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
            target_path = Path(filename)
        else:
            target_path = Path(output_file)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"

        try:
            with open(target_path, "a", encoding="utf-8") as f:
                _lock_append_handle(f, True)
                try:
                    f.write(line)
                    f.flush()
                finally:
                    _lock_append_handle(f, False)
            logger.info("Trajectory successfully saved to %s", target_path)
            return target_path
        except Exception as exc:
            logger.warning("Failed to save trajectory to %s: %s", target_path, exc)
            return None
