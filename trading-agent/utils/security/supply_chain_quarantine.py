# ==============================================================================
# File: utils/security/supply_chain_quarantine.py
# ==============================================================================

"""
14-Day Supply-Chain Quarantine & Dependency Verification Sentinel.

Protects agent execution, plugins, and third-party skills from zero-day package poisoning,
dependency confusion, and typosquatting attacks by enforcing:
1. 14-day quarantine delay on newly released packages/versions (Institutional supply-chain invariant).
2. Typosquatting distance analysis against critical institutional libraries.
3. Cryptographic digest / SHA-256 integrity verification.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Institutional core libraries protected from typosquatting
CRITICAL_CORE_LIBRARIES: Set[str] = {
    "metatrader5",
    "anthropic",
    "openai",
    "google-genai",
    "deepseek",
    "numpy",
    "pandas",
    "scipy",
    "sqlalchemy",
    "asyncpg",
    "pydantic",
    "fastapi",
    "uvicorn",
    "alembic",
    "pytest",
    "pyyaml",
    "requests",
    "aiohttp",
}

DEFAULT_QUARANTINE_DAYS: int = 14


@dataclass
class QuarantineVerdict:
    """Outcome of supply chain dependency quarantine assessment."""
    package_name: str
    version: str
    allowed: bool
    status: str  # "CLEAN", "QUARANTINED", "TYPOSQUAT_SUSPECT", "HASH_MISMATCH", "ALLOWLISTED"
    reason: str
    release_age_days: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


class SupplyChainQuarantine:
    """
    Enforces supply chain security and quarantine rules for plugins and dynamically loaded modules.
    """

    def __init__(
        self,
        quarantine_days: int = DEFAULT_QUARANTINE_DAYS,
        allowlist: Optional[Set[str]] = None,
        critical_libraries: Optional[Set[str]] = None,
    ):
        self.quarantine_days = quarantine_days
        self.allowlist = {pkg.lower() for pkg in (allowlist or set())}
        self.critical_libraries = {
            pkg.lower() for pkg in (critical_libraries or CRITICAL_CORE_LIBRARIES)
        }

    def check_typosquatting(self, package_name: str) -> Optional[Tuple[str, float]]:
        """
        Calculates string similarity against core libraries.
        Returns (target_library, similarity_ratio) if suspicious typosquat is detected.
        """
        pkg = package_name.lower().replace("-", "_")
        for target in self.critical_libraries:
            tgt = target.lower().replace("-", "_")
            if pkg == tgt:
                continue
            ratio = difflib.SequenceMatcher(None, pkg, tgt).ratio()
            # If similarity is >= 0.82 and not identical, flag as potential typosquat
            if ratio >= 0.82 and abs(len(pkg) - len(tgt)) <= 3:
                return target, ratio
        return None

    def evaluate_package(
        self,
        package_name: str,
        version: str,
        release_date: Optional[datetime | str] = None,
        package_bytes: Optional[bytes] = None,
        expected_sha256: Optional[str] = None,
    ) -> QuarantineVerdict:
        """
        Evaluates a package against quarantine rules, hash integrity, and typosquatting.
        """
        pkg_lower = package_name.lower()

        # 1. Allowlist override
        if pkg_lower in self.allowlist or f"{pkg_lower}=={version}" in self.allowlist:
            return QuarantineVerdict(
                package_name=package_name,
                version=version,
                allowed=True,
                status="ALLOWLISTED",
                reason=f"Package {package_name} explicitly allowlisted by operator.",
            )

        # 2. Check typosquatting against critical core libraries
        typo_match = self.check_typosquatting(package_name)
        if typo_match:
            target_lib, score = typo_match
            reason = (
                f"Typosquatting risk: '{package_name}' is {score:.2%} similar to "
                f"institutional core library '{target_lib}'."
            )
            return QuarantineVerdict(
                package_name=package_name,
                version=version,
                allowed=False,
                status="TYPOSQUAT_SUSPECT",
                reason=reason,
                details={"target_library": target_lib, "similarity_score": score},
            )

        # 3. Check cryptographic hash mismatch if provided
        if package_bytes is not None and expected_sha256:
            actual_sha256 = hashlib.sha256(package_bytes).hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                return QuarantineVerdict(
                    package_name=package_name,
                    version=version,
                    allowed=False,
                    status="HASH_MISMATCH",
                    reason=f"SHA-256 hash mismatch! Expected {expected_sha256}, got {actual_sha256}.",
                    details={"expected_sha256": expected_sha256, "actual_sha256": actual_sha256},
                )

        # 4. Check 14-day release quarantine
        if release_date is not None:
            if isinstance(release_date, str):
                try:
                    rel_dt = datetime.fromisoformat(release_date.replace("Z", "+00:00"))
                except ValueError:
                    rel_dt = None
            else:
                rel_dt = release_date

            if rel_dt is not None:
                if rel_dt.tzinfo is None:
                    rel_dt = rel_dt.replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                age_delta = now_dt - rel_dt
                age_days = max(0.0, age_delta.total_seconds() / 86400.0)

                if age_days < self.quarantine_days:
                    quarantine_remaining = self.quarantine_days - age_days
                    reason = (
                        f"Package '{package_name}=={version}' was released {age_days:.1f} days ago. "
                        f"Subject to {self.quarantine_days}-day quarantine ({quarantine_remaining:.1f} days remaining)."
                    )
                    return QuarantineVerdict(
                        package_name=package_name,
                        version=version,
                        allowed=False,
                        status="QUARANTINED",
                        reason=reason,
                        release_age_days=age_days,
                        details={"quarantine_remaining_days": quarantine_remaining},
                    )

        return QuarantineVerdict(
            package_name=package_name,
            version=version,
            allowed=True,
            status="CLEAN",
            reason=f"Package {package_name}=={version} passed all supply chain quarantine gates.",
        )
