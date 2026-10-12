# ==============================================================================
# File: utils/content_distiller.py
# ==============================================================================

"""
Content Distiller & Token Budget Optimization Pipeline.
Institutional-grade web content extraction and context defense architecture.

Capabilities:
  1. Base64 & Binary Defuse:
     Detects and neutralizes massive data URLs and inline base64 blobs that bloat token consumption.
  2. 75/25 Context Partitioning:
     Allocates 75% of character budget to narrative body content and 25% to structured tables/code.
  3. Automatic Disk Spill & Pointer Reference:
     When raw text exceeds max threshold (e.g. 16k chars), writes full content to data/spill/<hash>.txt
     and returns distilled excerpt with a retrieve_spilled_context pointer.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.Utils.ContentDistiller")

DEFAULT_SPILL_DIR = Path("data/spill")

# Regex to strip inline base64 blobs
_BASE64_DATA_URL_REGEX = re.compile(r"data:[a-zA-Z0-9/+-]+;base64,[A-Za-z0-9+/=]{100,}")
_INLINE_BINARY_REGEX = re.compile(r"(?:[A-Za-z0-9+/]{80,}\s*){3,}")


class ContentDistiller:
    """
    Distills HTML or markdown web content into token-efficient text.
    """

    def __init__(
        self,
        max_chars: int = 16000,
        spill_dir: Optional[Path] = None,
    ):
        self.max_chars = max_chars
        self.spill_dir = spill_dir or DEFAULT_SPILL_DIR

    def defuse_binaries(self, text: str) -> str:
        """Strips base64 image urls and large binary blocks."""
        if not text:
            return ""
        # Defuse data URLs
        defused = _BASE64_DATA_URL_REGEX.sub("[INLINE_IMAGE_BLOB_DEFUSED]", text)
        # Defuse standalone large base64 chunks
        defused = _INLINE_BINARY_REGEX.sub("[BINARY_DATA_BLOB_DEFUSED]", defused)
        return defused

    def distill(
        self,
        raw_text: str,
        title: str = "",
        url: str = "",
        budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Processes and compresses content using 75/25 partitioning and disk spill.
        """
        budget_limit = budget or self.max_chars
        cleaned = self.defuse_binaries(raw_text)

        raw_len = len(cleaned)
        if raw_len <= budget_limit:
            return {
                "distilled_text": cleaned,
                "spilled": False,
                "storage_key": None,
                "original_length": raw_len,
                "distilled_length": raw_len,
            }

        # Content exceeds budget: write to disk spill
        content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        spill_key = f"web_{content_hash[:16]}"
        self.spill_dir.mkdir(parents=True, exist_ok=True)
        spill_file = self.spill_dir / f"{spill_key}.txt"

        try:
            with open(spill_file, "w", encoding="utf-8") as f:
                f.write(cleaned)
            logger.info(f"[ContentDistiller] Spilled {raw_len} chars to {spill_file} (key: {spill_key}).")
        except Exception as exc:
            logger.warning(f"[ContentDistiller] Failed writing spill file: {exc}")

        # 75/25 split extraction
        narrative_budget = int(budget_limit * 0.75)
        structured_budget = budget_limit - narrative_budget

        # Extract structured elements (tables, code blocks, lists)
        structured_blocks = []
        for match in re.finditer(r"(?:```.*?```|\|.*?\|(?:\n\|.*?\|)+)", cleaned, re.DOTALL):
            structured_blocks.append(match.group(0))

        structured_text = "\n\n".join(structured_blocks)[:structured_budget]

        # Extract narrative text
        non_structured = re.sub(r"(?:```.*?```|\|.*?\|(?:\n\|.*?\|)+)", "", cleaned, flags=re.DOTALL)
        narrative_text = non_structured[:narrative_budget].strip()

        notice = (
            f"\n\n---\n"
            f"[Notice: Document '{title or url}' exceeded token budget ({raw_len:,} chars). "
            f"Spilled complete text to disk with key '{spill_key}'. "
            f"Use tool 'retrieve_spilled_context(storage_key=\"{spill_key}\")' to view additional pages.]"
        )

        final_distilled = narrative_text
        if structured_text:
            final_distilled += "\n\n### Key Structured Data:\n" + structured_text
        final_distilled += notice

        return {
            "distilled_text": final_distilled,
            "spilled": True,
            "storage_key": spill_key,
            "original_length": raw_len,
            "distilled_length": len(final_distilled),
        }
