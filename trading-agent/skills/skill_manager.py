# ==============================================================================
# File: skills/skill_manager.py
# ==============================================================================

"""
Dynamic Skill Lifecycle Manager & Hot-Reload Engine.
Institutional-grade agent extensibility and runtime management.

Provides programmatic and interactive management of skills:
  - Creation with frontmatter validation and AST security auditing
  - In-place editing with exact and fuzzy line block patching
  - Safe archival / deletion with protected core skill immunity
  - Deep inspection (AST audit score, usage telemetry, linked files)
  - Seamless hot-reloading across SkillsHub and UnifiedSkillsRuntime
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from skills.curator import SkillCurator
from skills.skills_guard import SkillsGuard, AuditReport
from skills.skills_hub import SkillsHub, SkillMetadata

logger = logging.getLogger("TradingAgent.Skills.SkillManager")


class SkillManager:
    """
    Coordinates creation, modification, validation, archival, and hot-reload of skills.
    """

    def __init__(
        self,
        base_dir: Optional[Union[str, Path]] = None,
        skills_hub: Optional[SkillsHub] = None,
    ):
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            self.base_dir = Path(__file__).resolve().parent

        self.skills_hub = skills_hub

    def _get_hub(self) -> SkillsHub:
        if self.skills_hub:
            return self.skills_hub
        from analysis.tools.domain.skill_tools import get_skills_hub
        return get_skills_hub()

    def create_skill(
        self,
        name: str,
        content: str,
        category: str = "general",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        overwrite: bool = False,
    ) -> Tuple[bool, str]:
        """
        Creates a new domain skill with standardized frontmatter and AST security check.
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name.strip().lower().replace(" ", "_"))
        if not clean_name:
            return False, "Invalid skill name. Must contain alphanumeric characters, underscores, or hyphens."

        clean_cat = category.strip().lower()
        target_dir = self.base_dir / clean_cat / clean_name
        target_file = target_dir / "SKILL.md"

        if target_file.exists() and not overwrite:
            return False, f"Skill '{clean_name}' already exists at {target_file}. Set overwrite=True to replace."

        # If content doesn't have frontmatter, synthesize one
        if not content.startswith("---"):
            desc_val = description or f"Specialized {clean_cat} execution skill for {clean_name}."
            desc_val = desc_val[:80]
            tags_list = tags or [clean_cat, clean_name]
            tags_str = ", ".join(tags_list)
            frontmatter = (
                f"---\n"
                f"name: {clean_name}\n"
                f"description: \"{desc_val}\"\n"
                f"version: 1.0.0\n"
                f"category: {clean_cat.upper()}\n"
                f"tags: [{tags_str}]\n"
                f"---\n\n"
            )
            full_content = frontmatter + content
        else:
            full_content = content

        # Run temporary AST security validation in isolated OS temp dir
        with tempfile.TemporaryDirectory(prefix=f"monika_audit_{clean_name}_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            tmp_file = tmp_dir / "SKILL.md"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(full_content)

            report = SkillsGuard.audit_skill_directory(str(tmp_dir), skill_name=clean_name)
            if not report.is_safe:
                violations = "; ".join(f"{f.rule}: {f.message}" for f in report.findings[:3])
                return False, f"Security Gate Rejected skill '{clean_name}' (Score: {report.score}/100): {violations}"

        # Deploy to final target
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(full_content)

        self.hot_reload()
        logger.info(f"[SkillManager] Successfully created skill '{clean_name}' in category '{clean_cat}'.")
        return True, f"Skill '{clean_name}' created successfully at {target_file}."

    def edit_skill(
        self,
        name: str,
        new_content: Optional[str] = None,
        old_text: Optional[str] = None,
        replacement_text: Optional[str] = None,
        fuzzy_match: bool = True,
    ) -> Tuple[bool, str]:
        """
        Edits an existing skill in-place with exact or fuzzy line replacement.
        """
        hub = self._get_hub()
        meta = hub.get_skill(name)
        if not meta:
            # Try searching directly by file stem
            candidates = list(self.base_dir.glob(f"**/{name}/SKILL.md")) + list(self.base_dir.glob(f"**/{name}.md"))
            if not candidates:
                return False, f"Skill '{name}' not found."
            file_path = candidates[0]
        else:
            file_path = Path(meta.path)

        if not file_path.exists():
            return False, f"Skill file for '{name}' does not exist at {file_path}."

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            existing = f.read()

        if new_content is not None:
            updated = new_content
        elif old_text is not None and replacement_text is not None:
            if old_text in existing:
                updated = existing.replace(old_text, replacement_text, 1)
            elif fuzzy_match:
                # Fuzzy line matching: normalize trailing spaces and line breaks
                matched_slice = self._find_fuzzy_slice(existing, old_text)
                if matched_slice is None:
                    return False, f"Could not find matching target block for replacement in skill '{name}'."
                start_idx, end_idx = matched_slice
                updated = existing[:start_idx] + replacement_text + existing[end_idx:]
            else:
                return False, f"Exact match for target text not found in skill '{name}'."
        else:
            return False, "Either 'new_content' or both 'old_text' and 'replacement_text' must be provided."

        # Security check on updated content in isolated OS temp dir
        with tempfile.TemporaryDirectory(prefix=f"monika_audit_edit_{name}_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            tmp_file = tmp_dir / file_path.name
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(updated)

            report = SkillsGuard.audit_skill_directory(str(tmp_dir), skill_name=name)
            if not report.is_safe:
                violations = "; ".join(f"{f.rule}: {f.message}" for f in report.findings[:3])
                return False, f"Security Gate Rejected edits for skill '{name}' (Score: {report.score}/100): {violations}"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(updated)

        self.hot_reload()
        logger.info(f"[SkillManager] Successfully updated skill '{name}'.")
        return True, f"Skill '{name}' updated successfully."

    def _find_fuzzy_slice(self, full_text: str, target: str) -> Optional[Tuple[int, int]]:
        """
        Locates the character slice [start, end] in full_text that matches target with high similarity.
        """
        full_lines = full_text.splitlines(keepends=True)
        target_lines = target.splitlines(keepends=True)
        n_target = len(target_lines)

        if n_target == 0 or len(full_lines) < n_target:
            return None

        clean_target = [l.strip() for l in target_lines if l.strip()]
        if not clean_target:
            return None
        target_str = "\n".join(clean_target)

        best_ratio = 0.0
        best_slice = None

        for i in range(len(full_lines) - n_target + 1):
            window = full_lines[i : i + n_target]
            clean_window = [l.strip() for l in window if l.strip()]
            window_str = "\n".join(clean_window)
            matcher = difflib.SequenceMatcher(None, window_str, target_str)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                start_char = sum(len(l) for l in full_lines[:i])
                end_char = start_char + sum(len(l) for l in window)
                best_slice = (start_char, end_char)

        if best_ratio >= 0.70:
            return best_slice
        return None

    def delete_skill(
        self,
        name: str,
        force: bool = False,
        archive_instead: bool = True,
    ) -> Tuple[bool, str]:
        """
        Removes or archives a skill. Protected core skills cannot be deleted.
        """
        clean_name = name.strip().lower()
        if clean_name in SkillCurator.PROTECTED_SKILLS and not force:
            return False, f"Skill '{name}' is a protected core playbook and cannot be removed."

        hub = self._get_hub()
        meta = hub.get_skill(name)
        if not meta:
            candidates = list(self.base_dir.glob(f"**/{name}/SKILL.md")) + list(self.base_dir.glob(f"**/{name}.md"))
            if not candidates:
                return False, f"Skill '{name}' not found."
            file_path = candidates[0]
        else:
            file_path = Path(meta.path)

        skill_dir = file_path.parent if file_path.name == "SKILL.md" else file_path

        if archive_instead:
            archive_target = self.base_dir / ".archive" / (clean_name + f"_{int(time.time())}")
            archive_target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if skill_dir.is_dir():
                    shutil.move(str(skill_dir), str(archive_target))
                else:
                    shutil.move(str(file_path), str(archive_target))
                self.hot_reload()
                logger.info(f"[SkillManager] Archived skill '{name}' to {archive_target}.")
                return True, f"Skill '{name}' archived successfully to {archive_target.name}."
            except Exception as exc:
                return False, f"Failed to archive skill '{name}': {exc}"
        else:
            try:
                if skill_dir.is_dir():
                    shutil.rmtree(skill_dir)
                else:
                    file_path.unlink()
                self.hot_reload()
                logger.info(f"[SkillManager] Permanently deleted skill '{name}'.")
                return True, f"Skill '{name}' permanently deleted."
            except Exception as exc:
                return False, f"Failed to delete skill '{name}': {exc}"

    def get_skill_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed metadata, security status, and telemetry for a skill.
        """
        hub = self._get_hub()
        meta = hub.get_skill(name)
        if not meta:
            return None

        p = Path(meta.path)
        file_size = p.stat().st_size if p.exists() else 0
        line_count = 0
        if p.exists():
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                line_count = sum(1 for _ in f)

        audit_report = hub.audit_skill(name)
        is_protected = name.lower() in SkillCurator.PROTECTED_SKILLS

        return {
            "name": meta.name,
            "category": meta.category,
            "version": meta.version,
            "description": meta.description,
            "path": meta.path,
            "size_bytes": file_size,
            "line_count": line_count,
            "tags": meta.tags,
            "linked_files": meta.linked_files,
            "platforms": meta.platforms,
            "is_protected": is_protected,
            "audit_score": audit_report.score if audit_report else None,
            "audit_safe": audit_report.is_safe if audit_report else None,
        }

    def hot_reload(self) -> Dict[str, Any]:
        """
        Forces immediate rediscovery and LRU cache invalidation across all skill engines.
        """
        hub = self._get_hub()
        count = hub.discover_skills()

        # Invalidate loader cache if present
        try:
            from skills.loader import invalidate_cache
            invalidate_cache()
        except ImportError:
            pass

        return {
            "status": "reloaded",
            "skills_count": count,
            "timestamp": time.time(),
        }
