"""
Output Spill Store for Large Artifacts (Phase 7.4).
Offloads oversized tool outputs, news transcripts, and raw order book data to disk,
returning bounded head/tail previews to context to preserve LLM token budgets.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("TradingAgent.SpillStore")

DEFAULT_SPILL_DIR = Path("data/spill_store")


class SpillStore:
    """Local artifact store for offloading bulky contextual data with preview generation."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None, max_preview_chars: int = 1200):
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_SPILL_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_preview_chars = max_preview_chars

    @staticmethod
    def generate_preview(text: str, max_chars: int = 1200, head_ratio: float = 0.7) -> str:
        """Generate bounded head/tail preview of large text content."""
        if not text or len(text) <= max_chars:
            return text

        head_len = int(max_chars * head_ratio)
        tail_len = max_chars - head_len
        omitted = len(text) - (head_len + tail_len)

        head = text[:head_len]
        tail = text[-tail_len:] if tail_len > 0 else ""
        return (
            f"{head}\n\n"
            f"[... {omitted:,} characters spilled to disk for context budget ...]\n\n"
            f"{tail}"
        )

    def spill_artifact(
        self,
        content: Union[str, dict, list],
        artifact_type: str = "generic",
        artifact_id: Optional[str] = None,
        preview_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Save large artifact payload to disk and return metadata with bounded preview."""
        if isinstance(content, (dict, list)):
            serialized = json.dumps(content, indent=2, default=str)
            is_json = True
        else:
            serialized = str(content)
            is_json = False

        size_bytes = len(serialized.encode("utf-8"))
        if not artifact_id:
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
            artifact_id = f"{artifact_type}_{digest}"

        ext = ".json" if is_json else ".txt"
        file_path = self.base_dir / f"{artifact_id}{ext}"

        try:
            file_path.write_text(serialized, encoding="utf-8")
        except Exception as e:
            logger.error(f"[SpillStore] Failed to write artifact {artifact_id}: {e}")
            return {
                "spilled": False,
                "error": str(e),
                "preview": serialized[:(preview_chars or self.max_preview_chars)],
            }

        preview_limit = preview_chars or self.max_preview_chars
        preview = self.generate_preview(serialized, max_chars=preview_limit)

        return {
            "spilled": True,
            "artifact_id": artifact_id,
            "file_path": str(file_path),
            "size_bytes": size_bytes,
            "total_chars": len(serialized),
            "preview": preview,
            "type": artifact_type,
        }

    def load_artifact(self, artifact_id_or_path: str) -> Optional[Union[str, dict, list]]:
        """Retrieve full artifact from disk by ID or direct path."""
        target_path = Path(artifact_id_or_path)
        if not target_path.exists():
            # Check within base_dir
            for ext in (".json", ".txt"):
                candidate = self.base_dir / f"{artifact_id_or_path}{ext}"
                if candidate.exists():
                    target_path = candidate
                    break

        if not target_path.exists() or not target_path.is_file():
            logger.warning(f"[SpillStore] Artifact '{artifact_id_or_path}' not found")
            return None

        raw = target_path.read_text(encoding="utf-8")
        if target_path.suffix.lower() == ".json":
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw


# Default singleton instance
_default_spill_store: Optional[SpillStore] = None


def get_spill_store() -> SpillStore:
    """Get or instantiate default SpillStore singleton."""
    global _default_spill_store
    if _default_spill_store is None:
        _default_spill_store = SpillStore()
    return _default_spill_store
