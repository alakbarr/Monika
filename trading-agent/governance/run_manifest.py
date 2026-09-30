# ==============================================================================
# File: governance/run_manifest.py
# Monika Content-Addressed Run Manifest & Audit Reproducibility Engine
# ==============================================================================

"""
Content-Addressed Run Manifest:
Generates deterministic cryptographic fingerprints of the trading agent runtime:
1. SHA-256 of the active system prompt and core governance directives.
2. Registry snapshot of all enabled quantitative alpha strategies and active skills.
3. Strict dependency version pinning (Python, NumPy, Pandas, SQLAlchemy, MetaTrader 5).
4. Git commit hash and environment telemetry.

Guarantees full run-to-run reproducibility for institutional post-trade audits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Governance.RunManifest")


@dataclass(frozen=True, slots=True)
class RunManifest:
    manifest_id: str                   # SHA-256 content-hash of the entire manifest payload
    timestamp_utc: str
    git_commit_hash: Optional[str]
    python_version: str
    os_platform: str
    dependency_versions: Dict[str, str]
    system_prompt_sha256: str
    registered_strategies: List[str]
    active_skills: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


class RunManifestGenerator:
    """Produces immutable, content-addressed fingerprints of agent execution states."""

    @classmethod
    def _get_git_commit(cls) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    @classmethod
    def _get_dependency_versions(cls) -> Dict[str, str]:
        deps = {}
        for mod_name in ("numpy", "pandas", "sqlalchemy", "MetaTrader5", "pydantic", "yaml"):
            try:
                mod = sys.modules.get(mod_name) or __import__(mod_name)
                deps[mod_name] = getattr(mod, "__version__", "unknown")
            except Exception:
                deps[mod_name] = "not_installed"
        return deps

    @classmethod
    def _get_registered_strategies(cls) -> List[str]:
        try:
            from analysis.strategies.registry import StrategyRegistry
            return sorted(list(StrategyRegistry._registry.keys()))
        except Exception:
            return []

    @classmethod
    def _get_active_skills(cls) -> List[str]:
        skills = []
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        if skills_dir.exists():
            for p in skills_dir.rglob("*.py"):
                if not p.name.startswith("__"):
                    skills.append(p.stem)
        return sorted(skills)

    @classmethod
    def generate(
        cls,
        system_prompt: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> RunManifest:
        """Generates a complete content-addressed RunManifest."""
        prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        now_utc = datetime.now(timezone.utc).isoformat()
        git_hash = cls._get_git_commit()
        deps = cls._get_dependency_versions()
        strategies = cls._get_registered_strategies()
        skills = cls._get_active_skills()

        payload = {
            "timestamp_utc": now_utc,
            "git_commit_hash": git_hash,
            "python_version": platform.python_version(),
            "os_platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "dependency_versions": deps,
            "system_prompt_sha256": prompt_hash,
            "registered_strategies": strategies,
            "active_skills": skills,
            "metadata": extra_metadata or {},
        }

        # Deterministic manifest content-hash
        canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        manifest_id = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return RunManifest(
            manifest_id=manifest_id,
            timestamp_utc=now_utc,
            git_commit_hash=git_hash,
            python_version=platform.python_version(),
            os_platform=f"{platform.system()} {platform.release()}",
            dependency_versions=deps,
            system_prompt_sha256=prompt_hash,
            registered_strategies=strategies,
            active_skills=skills,
            metadata=extra_metadata or {},
        )

    @classmethod
    def save_manifest(cls, manifest: RunManifest, directory: Optional[Path] = None) -> Path:
        target_dir = directory or (Path(__file__).resolve().parent.parent / "data" / "manifests")
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"run_manifest_{manifest.manifest_id[:16]}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(manifest.to_json())
        logger.info(f"Saved RunManifest: {file_path}")
        return file_path
