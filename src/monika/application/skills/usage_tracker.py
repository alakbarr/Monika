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
        from monika.core.paths import get_runtime_skills_dir, get_static_skills_dir

        target = Path(skill_path).resolve()
        static_root = get_static_skills_dir().resolve()
        try:
            is_skills_tree = ("skills" in target.parts) or target.is_relative_to(static_root)
        except Exception:
            is_skills_tree = "skills" in target.parts

        if is_skills_tree:
            name_part = target.parent.name if target.name == "SKILL.md" else target.stem
            cat_part = target.parent.parent.name if target.name == "SKILL.md" else target.parent.name
            safe_key = f"{cat_part}__{name_part}".strip("_")
            telemetry_dir = get_runtime_skills_dir() / "telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            return telemetry_dir / f"{safe_key}.usage.json"

        # Adjacent to target for hermetic isolation in tests / custom directories
        if target.is_dir():
            return target / ".usage.json"
        if target.name == "SKILL.md":
            return target.parent / ".usage.json"
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
            from monika.core.paths import atomic_write_text

            atomic_write_text(uf, json.dumps(data, indent=2), encoding="utf-8")
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
