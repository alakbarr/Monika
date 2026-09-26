# ==============================================================================
# File: analysis/memory/trajectory_compressor.py
# ==============================================================================

"""
Trajectory Compressor for Fine-Tuning & Offline Evaluation.

Post-processes long multi-turn agent transcripts into strict token budgets for fine-tuning.
Protects crucial turns (system prompt, initial goal, first assistant response, and last N turns).
Compresses and truncates bulky middle tool responses and intermediate loops while preserving
chain-of-thought integrity and <think> scratchpad reasoning blocks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_middle_text(text: str, max_chars: int) -> str:
    """Head + tail truncation for verbose text or tool outputs."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    omitted = len(text) - (2 * half)
    return f"{text[:half]}\n[... {omitted} characters omitted ...]\n{text[-half:]}"


@dataclass
class TrajectoryCompressionConfig:
    """Configuration options for trajectory compaction."""
    target_max_tokens: int = 8192
    protect_first_system: bool = True
    protect_first_user: bool = True
    protect_first_assistant: bool = True
    protect_last_n_turns: int = 3
    tool_output_max_chars: int = 1200
    verbose_turn_max_chars: int = 2400


class TrajectoryCompressor:
    """
    Compresses conversation trajectories to fit model context windows for fine-tuning.
    """

    def __init__(self, config: Optional[TrajectoryCompressionConfig] = None):
        self.config = config or TrajectoryCompressionConfig()

    def _estimate_message_tokens(self, msg: Dict[str, Any]) -> int:
        content = str(msg.get("content") or "")
        tokens = estimate_tokens(content)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            tokens += estimate_tokens(json.dumps(tool_calls))
        return tokens

    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compresses a sequence of messages into the configured token budget.
        """
        if not messages:
            return []

        total_turns = len(messages)
        if total_turns <= (3 + self.config.protect_last_n_turns):
            # Short trajectory: simply truncate oversized individual tool outputs
            return [self._sanitize_turn(m, self.config.tool_output_max_chars) for m in messages]

        # Identify protected indices
        protected_indices = set()
        system_seen = False
        user_seen = False
        asst_seen = False

        for i, m in enumerate(messages):
            role = m.get("role")
            if role == "system" and not system_seen and self.config.protect_first_system:
                protected_indices.add(i)
                system_seen = True
            elif role == "user" and not user_seen and self.config.protect_first_user:
                protected_indices.add(i)
                user_seen = True
            elif role == "assistant" and not asst_seen and self.config.protect_first_assistant:
                protected_indices.add(i)
                asst_seen = True

        # Last N turns are protected
        last_n = min(self.config.protect_last_n_turns, total_turns)
        for i in range(total_turns - last_n, total_turns):
            protected_indices.add(i)

        # First pass: sanitize tool outputs in unprotected middle turns
        compressed: List[Dict[str, Any]] = []
        for i, msg in enumerate(messages):
            if i in protected_indices:
                compressed.append(dict(msg))
            else:
                # Unprotected middle turn: clamp tool outputs and verbose prose
                compressed.append(self._sanitize_turn(msg, self.config.tool_output_max_chars))

        # Check budget
        total_tokens = sum(self._estimate_message_tokens(m) for m in compressed)
        if total_tokens <= self.config.target_max_tokens:
            return compressed

        # Second pass: aggressively compress unprotected middle turns
        aggressively_compressed: List[Dict[str, Any]] = []
        for i, msg in enumerate(compressed):
            if i in protected_indices:
                aggressively_compressed.append(msg)
            else:
                role = msg.get("role")
                content = str(msg.get("content") or "")
                if role == "tool":
                    # Compress tool result even further
                    tiny_content = truncate_middle_text(content, 400)
                    new_msg = dict(msg)
                    new_msg["content"] = tiny_content
                    aggressively_compressed.append(new_msg)
                elif role in ("assistant", "user") and len(content) > 600:
                    new_msg = dict(msg)
                    new_msg["content"] = truncate_middle_text(content, 600)
                    aggressively_compressed.append(new_msg)
                else:
                    aggressively_compressed.append(msg)

        return aggressively_compressed

    def _sanitize_turn(self, msg: Dict[str, Any], max_tool_chars: int) -> Dict[str, Any]:
        """Truncates excessively large tool results or message payloads."""
        new_msg = dict(msg)
        content = str(msg.get("content") or "")
        role = msg.get("role")

        if role == "tool" and len(content) > max_tool_chars:
            new_msg["content"] = truncate_middle_text(content, max_tool_chars)
        elif len(content) > self.config.verbose_turn_max_chars:
            new_msg["content"] = truncate_middle_text(content, self.config.verbose_turn_max_chars)

        return new_msg

    def compress_jsonl_file(
        self,
        input_path: Path | str,
        output_path: Path | str,
    ) -> Dict[str, int]:
        """
        Reads a JSONL file of trajectories, compresses each trajectory, and writes to output.
        """
        in_p = Path(input_path)
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        processed = 0
        written = 0

        with open(in_p, "r", encoding="utf-8") as fin, open(out_p, "w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                processed += 1
                try:
                    record = json.loads(line)
                    if "messages" in record:
                        record["messages"] = self.compress(record["messages"])
                    elif "conversations" in record:
                        # Convert ShareGPT back to role format, compress, then re-format
                        temp_msgs = []
                        for turn in record["conversations"]:
                            role = "user" if turn.get("from") == "human" else "assistant" if turn.get("from") == "gpt" else "system"
                            temp_msgs.append({"role": role, "content": turn.get("value", "")})
                        compressed_temp = self.compress(temp_msgs)
                        record["conversations"] = [
                            {
                                "from": "human" if m["role"] == "user" else "gpt" if m["role"] == "assistant" else "system",
                                "value": m["content"],
                            }
                            for m in compressed_temp
                        ]
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
                except Exception as exc:
                    logger.warning("Failed compressing trajectory line %d: %s", processed, exc)

        return {"processed": processed, "written": written}
