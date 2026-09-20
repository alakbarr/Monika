"""
Tool Result Storage & Spillover Manager.
Saves large tool outputs (> 16KB) to local disk storage and replaces the inline payload
with a structured summary and file reference, preventing context bloat and JSON corruption.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.ToolResultStorage")


class ToolResultStorage:
    """Manages disk-based spillover for large analytical tool execution outputs."""

    DEFAULT_SPILL_THRESHOLD_BYTES = 16 * 1024  # 16 KB
    DEFAULT_STORAGE_DIR = Path("data/tool_results")

    def __init__(self, storage_dir: Optional[Path] = None, threshold_bytes: int = DEFAULT_SPILL_THRESHOLD_BYTES):
        self.storage_dir = storage_dir or self.DEFAULT_STORAGE_DIR
        self.threshold_bytes = threshold_bytes
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"[ToolResultStorage] Failed to create storage dir '{self.storage_dir}': {e}")

    def maybe_persist(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        raw_result: Any,
    ) -> Tuple[Any, bool]:
        """
        If raw_result exceeds threshold_bytes, persists full payload to disk
        and returns (summary_payload, True). Otherwise returns (raw_result, False).
        """
        try:
            if isinstance(raw_result, (dict, list)):
                content_str = json.dumps(raw_result, ensure_ascii=False, default=str)
            else:
                content_str = str(raw_result)

            content_bytes = content_str.encode("utf-8")
            if len(content_bytes) <= self.threshold_bytes:
                return raw_result, False

            digest = hashlib.sha256(content_bytes).hexdigest()[:16]
            file_name = f"{tool_name}_{digest}.json"
            file_path = self.storage_dir / file_name

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_str)

            preview = content_str[:1200]
            summary_payload = {
                "status": "spilled_to_disk",
                "notice": (
                    f"Full result for '{tool_name}' was large ({len(content_bytes):,} bytes) and stored to disk. "
                    f"Use specific parameters or slice ranges if detailed subset is required."
                ),
                "file_path": str(file_path.as_posix()),
                "bytes": len(content_bytes),
                "preview": preview,
            }
            logger.info(
                f"[ToolResultStorage] Spilled {len(content_bytes):,} bytes for '{tool_name}' -> {file_path}"
            )
            return summary_payload, True
        except Exception as e:
            logger.warning(f"[ToolResultStorage] Spillover error for '{tool_name}': {e}")
            return raw_result, False


_global_storage: Optional[ToolResultStorage] = None


def get_tool_result_storage() -> ToolResultStorage:
    global _global_storage
    if _global_storage is None:
        _global_storage = ToolResultStorage()
    return _global_storage
