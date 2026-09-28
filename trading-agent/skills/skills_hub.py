# ==============================================================================
# File: skills/skills_hub.py
# ==============================================================================

"""
Universal Skills Hub & Progressive Skill Runtime.
Standardized skill management, progressive disclosure, and dynamic execution engine.

Key Architectural Capabilities:
  1. Standardized Directory Format (SKILL.md):
     Skills are organized in self-contained folders containing a primary SKILL.md
     with YAML frontmatter (name, description <= 60 chars, version, platforms, conditions,
     required_environment_variables, metadata) and optional subdirectories:
       - references/ (*.md technical references)
       - templates/ (code and config templates)
       - scripts/ (ready-to-run automation scripts)
       - assets/ (static files)

  2. Two-Tier Progressive Disclosure:
     - Tier 1 (skills_list): Injects only compact index (name, description, category).
     - Tier 2 (skill_view): Reads full instructions and discovers linked files on-demand.
     - Deduplication: Computes content fingerprint to return cached stub if already loaded.

  3. Dynamic Runtime Preprocessing:
     - Template Variable Substitution: Replaces ${MONIKA_SKILL_DIR} and ${MONIKA_SESSION_ID}.
     - Inline Shell Execution: Evaluates !`command` expressions in subshell before prompt injection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from skills.skills_guard import SkillsGuard, AuditReport

logger = logging.getLogger("TradingAgent.Skills.SkillsHub")

MAX_DESCRIPTION_LENGTH = 80


@dataclass
class SkillMetadata:
    name: str
    description: str
    category: str
    path: str
    version: str = "1.0.0"
    platforms: List[str] = field(default_factory=lambda: ["windows", "linux", "macos"])
    conditions: Dict[str, Any] = field(default_factory=dict)
    required_env: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    linked_files: Dict[str, List[str]] = field(default_factory=dict)
    provenance: Optional[Dict[str, Any]] = None


class SkillsHub:
    """
    Discovers, validates, caches, and formats skills across local directories.
    """

    def __init__(self, search_directories: Optional[List[str]] = None):
        base_dir = Path(__file__).resolve().parent
        self.search_directories = search_directories or [
            str(base_dir / "trading"),
            str(base_dir / "crystallized"),
            str(base_dir / "general"),
        ]
        self._skills: Dict[str, SkillMetadata] = {}
        self._loaded_fingerprints: Set[str] = set()
        self.discover_skills()

    def discover_skills(self) -> int:
        """
        Recursively scans configured directories for SKILL.md or <name>.md skill definitions.
        """
        self._skills.clear()
        for base_dir in self.search_directories:
            p = Path(base_dir)
            if not p.exists():
                continue

            for skill_file in p.glob("**/SKILL.md"):
                if any(part.startswith(".") or part.startswith("_") for part in skill_file.parts):
                    continue
                self._load_skill_file(skill_file)

            # Also support legacy direct .md files in the root of category folders
            for skill_file in p.glob("*.md"):
                if skill_file.name != "SKILL.md" and not skill_file.name.startswith("."):
                    if any(part.startswith(".") or part.startswith("_") for part in skill_file.parts):
                        continue
                    self._load_skill_file(skill_file)

        logger.info(f"[SkillsHub] Discovered {len(self._skills)} skills across {len(self.search_directories)} paths.")
        return len(self._skills)

    def _load_skill_file(self, path: Path) -> None:
        """Parses frontmatter and inspects linked directories for a skill."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            frontmatter, body = self._parse_frontmatter(content)
            name = frontmatter.get("name", path.parent.name if path.name == "SKILL.md" else path.stem)
            desc = frontmatter.get("description", "Domain procedural skill guidance.")
            cat = path.parent.parent.name if path.name == "SKILL.md" else path.parent.name

            # Discover linked files in subdirectories
            skill_folder = path.parent if path.name == "SKILL.md" else path.parent / path.stem
            linked = {}
            if skill_folder.exists() and skill_folder.is_dir():
                for sub in ["references", "templates", "scripts", "assets"]:
                    subdir = skill_folder / sub
                    if subdir.exists() and subdir.is_dir():
                        linked[sub] = [f.name for f in subdir.glob("*") if f.is_file()]

            raw_tags = frontmatter.get("tags") or frontmatter.get("metadata", {}).get("tags") or []
            if isinstance(raw_tags, str):
                tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]
            else:
                tags_list = []

            meta = SkillMetadata(
                name=name,
                description=desc[:MAX_DESCRIPTION_LENGTH],
                category=cat.upper(),
                path=str(path.absolute()),
                version=frontmatter.get("version", "1.0.0"),
                platforms=frontmatter.get("platforms", ["windows", "linux", "macos"]),
                conditions=frontmatter.get("conditions", {}),
                required_env=frontmatter.get("required_environment_variables", []),
                tags=tags_list,
                linked_files=linked,
            )
            self._skills[name] = meta
        except Exception as exc:
            logger.debug(f"[SkillsHub] Error parsing skill file '{path}': {exc}")

    def _parse_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        """Parses YAML frontmatter delimited by ---."""
        if not text.startswith("---"):
            return {}, text

        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text

        raw_yaml = parts[1]
        body = parts[2].lstrip()

        try:
            import yaml
            meta = yaml.safe_load(raw_yaml)
            if isinstance(meta, dict):
                return meta, body
        except Exception:
            pass

        meta = {}
        for line in raw_yaml.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                meta[k] = v

        return meta, body

    def get_skill(self, name: str) -> Optional[SkillMetadata]:
        """Retrieve full SkillMetadata object by name with alias tolerance."""
        if not name:
            return None
        if name in self._skills:
            return self._skills[name]
        alt = name.replace("_", "-")
        if alt in self._skills:
            return self._skills[alt]
        alt2 = name.replace("-", "_")
        if alt2 in self._skills:
            return self._skills[alt2]
        for k, v in self._skills.items():
            if k.lower() in (name.lower(), alt.lower(), alt2.lower()):
                return v
        return None

    def list_skills(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Tier 1 Progressive Disclosure: returns compact metadata list."""
        cat_filter = category.upper() if category else None
        output = []
        for name, meta in sorted(self._skills.items()):
            if cat_filter and meta.category != cat_filter:
                continue
            output.append({
                "name": meta.name,
                "category": meta.category,
                "description": meta.description,
                "tags": meta.tags,
                "linked_files": meta.linked_files,
            })
        return output

    def view_skill(
        self, name: str, file_path: Optional[str] = None, session_id: str = "default"
    ) -> Tuple[bool, str]:
        """
        Tier 2 Progressive Disclosure: reads full content, executes inline preprocessing,
        and provides deduplication checking.
        """
        meta = self.get_skill(name)
        if not meta:
            return False, f"Skill '{name}' not found in registry."

        base_path = Path(meta.path)
        skill_dir = base_path.parent if base_path.name == "SKILL.md" else base_path.parent

        target_file = base_path
        if file_path:
            # Viewing a linked file (e.g. references/rules.md)
            candidate = skill_dir / file_path
            if not candidate.exists() or not candidate.is_file():
                return False, f"Linked file '{file_path}' not found for skill '{name}'."
            target_file = candidate

        try:
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Deduplication check on base skill
            if not file_path:
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                dedup_key = f"{session_id}:{name}:{content_hash}"
                if dedup_key in self._loaded_fingerprints:
                    return True, f"[Skill '{name}' is already active and loaded in this session - instructions unchanged]"
                self._loaded_fingerprints.add(dedup_key)

            # Preprocessing: Variable substitution
            processed = content.replace("${MONIKA_SKILL_DIR}", str(skill_dir))
            processed = processed.replace("${MONIKA_SESSION_ID}", session_id)

            # Preprocessing: Inline shell execution !`cmd`
            processed = self._evaluate_inline_shells(processed, str(skill_dir))

            header = f"# Skill: {meta.name} (Category: {meta.category})\n"
            if meta.linked_files and not file_path:
                header += f"Linked resources: {json.dumps(meta.linked_files)}\n\n"

            return True, header + processed
        except Exception as exc:
            return False, f"Error viewing skill '{name}': {exc}"

    def _evaluate_inline_shells(self, text: str, cwd: str) -> str:
        """Evaluates inline subshell blocks !`command` in the skill directory."""
        pattern = re.compile(r"!`([^`]+)`")

        def replacer(match):
            cmd = match.group(1)
            try:
                shell = ["powershell.exe", "-NoProfile", "-Command"] if sys.platform == "win32" else ["/bin/bash", "-c"]
                res = subprocess.run(
                    shell + [cmd],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                output = res.stdout.strip()
                return output[:4000] if output else match.group(0)
            except Exception:
                return match.group(0)

        return pattern.sub(replacer, text)

    def audit_skill(self, name: str) -> Optional[AuditReport]:
        """Runs static AST security audit on a registered skill."""
        meta = self._skills.get(name)
        if not meta:
            return None
        base_path = Path(meta.path)
        skill_dir = base_path.parent if base_path.name == "SKILL.md" else base_path.parent
        return SkillsGuard.audit_skill_directory(str(skill_dir), skill_name=name)

    def install_skill(
        self,
        source_dir: str,
        category: str = "general",
        enforce_security: bool = True,
    ) -> Tuple[bool, str, Optional[AuditReport]]:
        """
        Installs a new skill package from local directory into the appropriate category folder,
        subject to strict static AST security audit.
        """
        import time
        src = Path(source_dir)
        if not src.exists() or not src.is_dir():
            return False, f"Source directory '{source_dir}' does not exist.", None

        skill_name = src.name
        # Run pre-installation AST security audit
        report = SkillsGuard.audit_skill_directory(str(src), skill_name=skill_name)
        if enforce_security and not report.is_safe:
            findings_summary = "; ".join(f"{f.rule}: {f.message}" for f in report.findings[:3])
            return (
                False,
                f"Security Gate Rejected skill '{skill_name}' (Score: {report.score}/100). Violations: {findings_summary}",
                report,
            )

        target_base = Path("trading-agent/skills") / category.lower() / skill_name
        target_base.parent.mkdir(parents=True, exist_ok=True)

        try:
            if target_base.exists():
                shutil.rmtree(target_base)
            shutil.copytree(src, target_base)

            # Discover and reload
            self.discover_skills()
            meta = self._skills.get(skill_name)
            if meta:
                meta.provenance = {
                    "installed_from": str(src.resolve()),
                    "installed_at": time.time(),
                    "audit_score": report.score,
                    "is_safe": report.is_safe,
                }

            return True, f"Skill '{skill_name}' installed and verified successfully (Score: {report.score}/100).", report
        except Exception as exc:
            return False, f"Installation failed during file transfer: {exc}", report
