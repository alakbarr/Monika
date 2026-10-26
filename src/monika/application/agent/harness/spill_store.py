"""Creation-time output spill store and spill policy.

Provides creation-time output spill storage and truncation policy:
- Safe path segment encoding preventing directory traversal.
- Exclusive file creation and session isolation.
- Token-budgeted 50/50 head/tail truncation with gap markers and omission notices.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import time
from typing import Any
import uuid


def encode_safe_segment(name: str) -> str:
    """Encode string for safe filesystem usage.

    Keeps [A-Za-z0-9._-] (except ~) literal. Encodes any other character
    as ~XXXX uppercase 4-digit hex. Encodes '.' as ~002E and '..' as ~002E~002E.
    """
    if name == ".":
        return "~002E"
    if name == "..":
        return "~002E~002E"

    out: list[str] = []
    for char in name:
        code = ord(char)
        if (
            ("A" <= char <= "Z") or ("a" <= char <= "z") or ("0" <= char <= "9") or char in (".", "_", "-")
        ) and char != "~":
            out.append(char)
        else:
            out.append(f"~{code:04X}")
    return "".join(out)


@dataclass(frozen=True, slots=True)
class SpillRef:
    """Reference to spilled output stored on disk."""

    locator: str
    bytes_total: int
    omitted_bytes: int
    retrieval_hint: str


class SpillStore:
    """Stores spilled outputs under root_dir / session-<sha256(session_id)[:12]>."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def get_session_dir(self, session_id: str) -> Path:
        session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
        return self.root_dir / f"session-{session_hash}"

    def save_text(self, session_id: str, tool_name: str, content: str) -> SpillRef:
        session_dir = self.get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        safe_tool = encode_safe_segment(tool_name)
        timestamp_ns = time.time_ns()
        random_suffix = uuid.uuid4().hex[:8]
        filename = f"{safe_tool}_{timestamp_ns}_{random_suffix}.txt"
        file_path = session_dir / filename

        content_bytes = content.encode("utf-8")
        fd = os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, content_bytes)
        finally:
            os.close(fd)

        locator = str(file_path)
        return SpillRef(
            locator=locator,
            bytes_total=len(content_bytes),
            omitted_bytes=0,
            retrieval_hint=f"Use read_file with offset/limit or grep_search to inspect {locator}",
        )


class SpillPolicy:
    """Enforces token budgets by spilling oversized tool outputs and generating head/tail excerpts."""

    GAP = "\n\n[...]\n\n"

    def __init__(
        self,
        store: SpillStore,
        max_inline_tokens: int = 8000,
        exempt_tools: frozenset[str] | None = None,
    ) -> None:
        self.store = store
        self.max_inline_tokens = max_inline_tokens
        if exempt_tools is None:
            self.exempt_tools = frozenset({"read_file", "read", "view_file_outline", "read_spill"})
        else:
            self.exempt_tools = exempt_tools

    def estimate_tokens(self, content: str) -> int:
        return math.ceil(len(content) / 4) + 4

    def apply(self, session_id: str, tool_name: str, content: str) -> tuple[str, SpillRef | None]:
        est_tokens = self.estimate_tokens(content)
        if est_tokens <= self.max_inline_tokens or tool_name in self.exempt_tools:
            return content, None

        spill_ref = self.store.save_text(session_id, tool_name, content)
        content_bytes = content.encode("utf-8")
        bytes_total = len(content_bytes)

        # Budget calculation: approx 4 chars per token
        total_char_budget = self.max_inline_tokens * 4
        # Reserve room for GAP and footer notice
        sample_notice = (
            f"\n\n(Omitted {bytes_total} bytes. Full formatted result stored at: {spill_ref.locator}. "
            f"Use read_file with offset/limit or grep_search to search within it.)"
        )
        reserved_overhead = len(self.GAP) + len(sample_notice)
        remaining_budget = max(0, total_char_budget - reserved_overhead)
        half_budget = remaining_budget // 2

        # 50% head budget without splitting high surrogate
        head_chars = min(half_budget, len(content))
        if head_chars > 0 and 0xD800 <= ord(content[head_chars - 1]) <= 0xDBFF:
            head_chars -= 1
        head_text = content[:head_chars]

        # 50% tail budget without splitting low surrogate
        tail_chars = min(half_budget, len(content) - head_chars)
        tail_start = len(content) - tail_chars
        if tail_start < len(content) and 0xDC00 <= ord(content[tail_start]) <= 0xDFFF:
            tail_start += 1
        tail_text = content[tail_start:]

        head_bytes_len = len(head_text.encode("utf-8"))
        tail_bytes_len = len(tail_text.encode("utf-8"))
        omitted_bytes = max(0, bytes_total - head_bytes_len - tail_bytes_len)

        footer = (
            f"\n\n(Omitted {omitted_bytes} bytes. Full formatted result stored at: {spill_ref.locator}. "
            f"Use read_file with offset/limit or grep_search to search within it.)"
        )
        combined_text = f"{head_text}{self.GAP}{tail_text}{footer}"

        final_ref = SpillRef(
            locator=spill_ref.locator,
            bytes_total=bytes_total,
            omitted_bytes=omitted_bytes,
            retrieval_hint=spill_ref.retrieval_hint,
        )
        return combined_text, final_ref
