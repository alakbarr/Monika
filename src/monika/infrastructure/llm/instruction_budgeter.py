"""
Instruction File Byte-Budgeting & UTF-8 Slicing Engine.
Prevents context window saturation from unbounded workspace guidelines, AGENTS.md,
or system prompts by enforcing deterministic byte budgets with multibyte-safe UTF-8 slicing
and hierarchical ancestor pruning.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.LLM.InstructionBudgeter")

DEFAULT_INSTRUCTION_BYTE_BUDGET = 24_576  # ~6,000 tokens max for full instruction scaffold


@dataclass
class BudgetedInstructionFile:
    path: str
    content: str
    original_bytes: int
    retained_bytes: int
    is_truncated: bool = False
    is_omitted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class InstructionBudgeter:
    """
    Enforces deterministic byte budgets on instruction and context files.
    Applies hierarchical prioritization (specific child directory rules take precedence over broader ancestors)
    and binary-search UTF-8 truncation.
    """

    @staticmethod
    def truncate_to_byte_budget_utf8(text: str, max_bytes: int) -> Tuple[str, bool]:
        """
        Safely truncates string to fit within max_bytes without splitting UTF-8 multibyte characters.
        Returns: (truncated_text, was_truncated)
        """
        if not text:
            return "", False

        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text, False

        # Truncate at exact byte boundary, decoding with ignore to discard any partial trailing code point
        truncated_bytes = encoded[:max_bytes]
        safe_text = truncated_bytes.decode("utf-8", errors="ignore")

        # Trim trailing incomplete word/line if practical to avoid dangling tokens
        last_nl = safe_text.rfind("\n")
        if last_nl > int(len(safe_text) * 0.75):
            safe_text = safe_text[:last_nl]

        notice = f"\n\n[... Remaining {len(encoded) - max_bytes} bytes omitted by instruction budget ...]"
        return safe_text + notice, True

    @classmethod
    def budget_instruction_files(
        cls,
        files: List[Dict[str, str]],
        max_bytes: int = DEFAULT_INSTRUCTION_BYTE_BUDGET,
    ) -> List[BudgetedInstructionFile]:
        """
        Budgets a list of instruction files (ordered from broadest ancestor to most specific child).
        Prioritizes the most specific files (tail), pruning or omitting broader ancestors (head) if budget is tight.
        """
        if not files:
            return []

        # Analyze initial sizes
        parsed: List[BudgetedInstructionFile] = []
        for f in files:
            p = f.get("path", "instruction.md")
            c = f.get("content", "")
            b = len(c.encode("utf-8"))
            parsed.append(
                BudgetedInstructionFile(
                    path=p,
                    content=c,
                    original_bytes=b,
                    retained_bytes=b,
                )
            )

        total_bytes = sum(item.original_bytes for item in parsed)
        if total_bytes <= max_bytes:
            return parsed

        logger.info(
            f"[InstructionBudgeter] Instruction set ({total_bytes} bytes) exceeds budget ({max_bytes} bytes). "
            f"Applying hierarchical budgeting..."
        )

        # Reverse walk: allocate budget starting from the most specific file (last) backwards
        allocated: List[BudgetedInstructionFile] = []
        remaining_budget = max_bytes

        for item in reversed(parsed):
            if remaining_budget <= 0:
                # Budget exhausted: omit broader ancestor completely
                allocated.append(
                    BudgetedInstructionFile(
                        path=item.path,
                        content="",
                        original_bytes=item.original_bytes,
                        retained_bytes=0,
                        is_truncated=False,
                        is_omitted=True,
                    )
                )
                continue

            if item.original_bytes <= remaining_budget:
                allocated.append(item)
                remaining_budget -= item.original_bytes
            else:
                # Partially allocate remaining budget to this file
                trunc_text, was_trunc = cls.truncate_to_byte_budget_utf8(item.content, remaining_budget)
                allocated_bytes = len(trunc_text.encode("utf-8"))
                allocated.append(
                    BudgetedInstructionFile(
                        path=item.path,
                        content=trunc_text,
                        original_bytes=item.original_bytes,
                        retained_bytes=allocated_bytes,
                        is_truncated=was_trunc,
                        is_omitted=False,
                    )
                )
                remaining_budget = 0

        # Restore original order (broadest to specific)
        allocated.reverse()
        return allocated

    @classmethod
    def render_budgeted_instructions(
        cls,
        files: List[Dict[str, str]],
        max_bytes: int = DEFAULT_INSTRUCTION_BYTE_BUDGET,
    ) -> str:
        """Renders budgeted instruction files into structured XML blocks."""
        budgeted = cls.budget_instruction_files(files, max_bytes=max_bytes)
        sections = []
        for b in budgeted:
            if b.is_omitted:
                sections.append(
                    f'<project_instructions path="{b.path}" status="omitted_for_budget">\n'
                    f"[Ancestor instructions omitted to preserve context budget for specific project instructions]\n"
                    f"</project_instructions>"
                )
            elif b.content:
                status_attr = ' status="truncated"' if b.is_truncated else ""
                sections.append(
                    f'<project_instructions path="{b.path}"{status_attr}>\n{b.content}\n</project_instructions>'
                )

        return "\n\n".join(sections)
