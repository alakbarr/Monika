# ==============================================================================
# Package: monika.infrastructure.data_ingestion.scrapers
# File: profile_reaper.py
# Description: Automated Browser Profile Cache Reaper & Disk Bloat Sanitizer
# ==============================================================================

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import time
from typing import Optional

from monika.core.paths import DATA_DIR

logger = logging.getLogger("TradingAgent.Scrapers.ProfileReaper")

DISPOSABLE_CACHE_SUBDIRS = [
    ("Default", "Cache"),
    ("Default", "Code Cache"),
    ("Default", "GPUCache"),
    ("Default", "Service Worker", "CacheStorage"),
    ("Default", "Service Worker", "ScriptCache"),
    ("GrShaderCache",),
    ("ShaderCache",),
]


class BrowserProfileReaper:
    """
    Automated Browser Profile Cache Reaper & Disk Hygiene Sanitizer.

    Prevents unbounded disk bloat and slow Chromium launch times by:
    1. Pruning disposable HTTP caches, shader caches, and GPU caches across all scraper profiles.
    2. Purging stale temporary/test profile directories (test_*, debug_*, bench_*) older than 7 days.
    """

    @classmethod
    def get_profiles_dir(cls) -> Path:
        p = DATA_DIR / "sessions" / "browser_profile"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def prune_profile_caches(cls, max_cache_size_mb: float = 50.0) -> int:
        """
        Scans all profile directories and prunes disposable cache subdirectories
        if their cumulative size exceeds max_cache_size_mb.

        Returns:
            Total bytes freed.
        """
        profiles_dir = cls.get_profiles_dir()
        if not profiles_dir.exists():
            return 0

        total_freed_bytes = 0
        threshold_bytes = int(max_cache_size_mb * 1024 * 1024)

        for profile in profiles_dir.iterdir():
            if not profile.is_dir():
                continue

            # Calculate total disposable cache size in this profile
            profile_cache_bytes = 0
            paths_to_prune: list[Path] = []

            for sub_parts in DISPOSABLE_CACHE_SUBDIRS:
                target = profile
                for part in sub_parts:
                    target = target / part
                if target.exists() and target.is_dir():
                    paths_to_prune.append(target)
                    for root, _, files in os.walk(str(target)):
                        for f in files:
                            try:
                                profile_cache_bytes += os.path.getsize(os.path.join(root, f))
                            except OSError, PermissionError:
                                pass

            if profile_cache_bytes > threshold_bytes:
                logger.info(
                    f"[ProfileReaper] Pruning {profile_cache_bytes / (1024 * 1024):.1f}MB from profile '{profile.name}'..."
                )
                for path in paths_to_prune:
                    try:
                        shutil.rmtree(str(path), ignore_errors=True)
                        total_freed_bytes += profile_cache_bytes
                    except Exception as err:
                        logger.debug(f"[ProfileReaper] Error removing {path}: {err}")

        # Also purge stale test/debug/bench directories older than 7 days
        cls.prune_stale_test_profiles(max_age_days=7.0)

        if total_freed_bytes > 0:
            logger.info(f"[ProfileReaper] Total disk space reclaimed: {total_freed_bytes / (1024 * 1024):.1f} MB.")
        return total_freed_bytes

    @classmethod
    def prune_stale_test_profiles(cls, max_age_days: float = 7.0) -> int:
        """Purges test_*, debug_*, bench_*, and trace_* directories older than max_age_days."""
        profiles_dir = cls.get_profiles_dir()
        if not profiles_dir.exists():
            return 0

        cutoff = time.time() - (max_age_days * 86400.0)
        removed_count = 0

        test_prefixes = ("test_", "debug_", "bench_", "trace_", "check_")
        for profile in profiles_dir.iterdir():
            if not profile.is_dir():
                continue
            name_lower = profile.name.lower()
            if any(name_lower.startswith(prefix) for prefix in test_prefixes):
                try:
                    mtime = profile.stat().st_mtime
                    if mtime < cutoff:
                        shutil.rmtree(str(profile), ignore_errors=True)
                        removed_count += 1
                        logger.info(f"[ProfileReaper] Removed stale test profile '{profile.name}'.")
                except Exception as err:
                    logger.debug(f"[ProfileReaper] Could not prune {profile.name}: {err}")

        return removed_count


__all__ = ["BrowserProfileReaper"]
