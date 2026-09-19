# ==============================================================================
# File: analysis/tools/kernel/output_spiller.py
# Description: Head/Tail Split Truncation (40/60) & Disk Spilling Subsystem
# ==============================================================================

"""
Intelligent output bounding and disk spilling for oversized tool observations.
Instead of blind end-truncation which destroys essential recent rows or error traces,
implements deterministic 40% Head / 60% Tail partitioning and persists the full payload
to local disk cache for reference.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("TradingAgent.Tools.OutputSpiller")

DEFAULT_MAX_CHARS = 10000


def truncate_and_spill_output(
    content: str,
    tool_name: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    cache_dir: str = None,
) -> Tuple[str, bool]:
    """
    Truncate oversized output with 40/60 head/tail split and spill to disk.

    Args:
        content: Raw output string from tool.
        tool_name: Name of tool that generated the output.
        max_chars: Maximum characters to retain in inline context.
        cache_dir: Optional custom spill directory.

    Returns:
        (processed_content, was_truncated)
    """
    if not content or len(content) <= max_chars:
        return content, False

    total_len = len(content)
    head_len = int(max_chars * 0.40)
    tail_len = int(max_chars * 0.60)

    head_part = content[:head_len]
    tail_part = content[total_len - tail_len :]

    # Persist full output to disk
    if not cache_dir:
        base = Path(__file__).resolve().parent.parent.parent.parent
        cache_dir = base / "data" / "cache" / "spillover"
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_path = cache_dir / f"spill_{tool_name}_{digest}.txt"

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        spill_notice = f" [Full output ({total_len} chars) spilled to disk: {file_path}] "
    except Exception as e:
        logger.warning(f"Failed to spill tool output to disk: {e}")
        spill_notice = f" [Full output had {total_len} chars] "

    omitted = total_len - (head_len + tail_len)
    truncated_text = (
        f"{head_part}\n\n"
        f"--- [OUTPUT TRUNCATED: {omitted} characters omitted out of {total_len}.{spill_notice}] ---\n\n"
        f"{tail_part}"
    )

    return truncated_text, True
