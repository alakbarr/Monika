"""
File: analysis/tools/tool_spill.py
Tool result spillover storage and standardized Head/Tail truncation for Monika.
Saves oversized tool outputs (>3,000 chars) to disk and provides structured
<persisted-output> summaries to prevent context window bloat and protect prompt caching.
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.ToolSpill")


def truncate_head_tail(text: str, max_chars: int = 2500, head_pct: float = 0.40) -> str:
    """Standardized 40% Head / 60% Tail truncation to preserve initial setup and latest results."""
    if len(text) <= max_chars:
        return text

    head_chars = int(max_chars * head_pct)
    tail_chars = max_chars - head_chars
    omitted = len(text) - (head_chars + tail_chars)

    head = text[:head_chars]
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    return f"{head}\n\n... [OUTPUT TRUNCATED - {omitted} characters omitted out of {len(text)} total] ...\n\n{tail}"


class ToolSpillStorage:
    """Manages offloading of large tool results to disk cache."""

    def __init__(self, spill_dir: Optional[Path] = None):
        if spill_dir:
            self.spill_dir = Path(spill_dir)
        else:
            base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            self.spill_dir = base_dir / "data" / "tool_spill"
        self.spill_dir.mkdir(parents=True, exist_ok=True)

    def maybe_spill(
        self,
        tool_name: str,
        tool_call_id: str,
        output_text: str,
        threshold_chars: int = 3000,
        preview_chars: int = 800,
    ) -> Tuple[bool, str]:
        """Saves output to disk if exceeding threshold and returns formatted <persisted-output>.
        
        Returns:
            Tuple of (spilled bool, resulting output text)
        """
        if len(output_text) <= threshold_chars:
            return False, output_text

        file_id = f"{tool_name}_{tool_call_id}_{int(time.time()*1000)}"
        file_path = self.spill_dir / f"{file_id}.txt"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info(f"Spilled large output ({len(output_text)} chars) for tool '{tool_name}' to {file_path}")
        except Exception as e:
            logger.warning(f"Failed to spill tool output to disk: {e}")
            return False, truncate_head_tail(output_text, max_chars=threshold_chars)

        preview = output_text[:preview_chars]
        persisted_block = (
            f"<persisted-output>\n"
            f"This tool result was too large ({len(output_text):,} characters, {len(output_text.encode('utf-8'))/1024:.1f} KB).\n"
            f"Full output saved to: {file_path.as_posix()}\n"
            f"Use targeted analysis tools or inspect specific sections if needed.\n"
            f"Preview (first {preview_chars} chars):\n"
            f"{preview}\n"
            f"... [Remaining {len(output_text) - preview_chars:,} characters persisted on disk]\n"
            f"</persisted-output>"
        )
        return True, persisted_block

    def cleanup_old_spills(self, max_age_seconds: float = 86400.0) -> int:
        """Deletes spill files older than max_age_seconds (default: 24h)."""
        now = time.time()
        deleted = 0
        for p in self.spill_dir.glob("*.txt"):
            try:
                if now - p.stat().st_mtime > max_age_seconds:
                    p.unlink()
                    deleted += 1
            except Exception:
                pass
        return deleted
