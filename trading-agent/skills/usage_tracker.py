"""
Skill usage telemetry tracking (.usage.json ledger).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("TradingAgent.Skills.UsageTracker")


class SkillUsageTracker:
    """Maintains lightweight execution and inspection telemetry alongside skill files."""

    @staticmethod
    def _get_usage_file(skill_path: Union[str, Path]) -> Path:
        target = Path(skill_path).resolve()
        if target.is_dir():
            return target / ".usage.json"
        return target.parent / f"{target.stem}.usage.json"

    @classmethod
    def load(cls, skill_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads usage telemetry from .usage.json file."""
        uf = cls._get_usage_file(skill_path)
        if uf.exists():
            try:
                return json.loads(uf.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"Failed to read usage json {uf}: {e}")
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "use_count": 0,
            "view_count": 0,
            "last_used_at": None,
        }

    @classmethod
    def save(cls, skill_path: Union[str, Path], data: Dict[str, Any]) -> None:
        """Saves usage telemetry to .usage.json file."""
        uf = cls._get_usage_file(skill_path)
        try:
            uf.parent.mkdir(parents=True, exist_ok=True)
            uf.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to write usage json {uf}: {e}")

    @classmethod
    def record_use(cls, skill_path: Union[str, Path]) -> None:
        """Records an active execution/invocation of a skill."""
        data = cls.load(skill_path)
        data["use_count"] = int(data.get("use_count", 0)) + 1
        data["last_used_at"] = datetime.now(timezone.utc).isoformat()
        cls.save(skill_path, data)

    @classmethod
    def record_view(cls, skill_path: Union[str, Path]) -> None:
        """Records an inspection/load of a skill into context."""
        data = cls.load(skill_path)
        data["view_count"] = int(data.get("view_count", 0)) + 1
        cls.save(skill_path, data)
