"""
Physical Deliverables & State Verification Gate.
Probes physical filesystem and execution state before allowing an agent to claim
completion on file modification, code generation, or deliverable artifacts.
Eliminates narrative hallucination where an LLM asserts work is complete without actual disk presence.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Set

logger = logging.getLogger("TradingAgent.Harness.PhysicalDeliverableGate")


@dataclass
class DeliverableVerdict:
    is_valid: bool
    status: str  # "verified", "missing_deliverable", "empty_file", "unverified_test"
    message: Optional[str] = None
    verified_paths: List[str] = field(default_factory=list)
    missing_paths: List[str] = field(default_factory=list)
    git_confirmed_paths: List[str] = field(default_factory=list)


class PhysicalDeliverableGate:
    """
    Physical Ground-Truth Probing Gate for Agent Harness Deliverables.
    Verifies that files claimed to be created or modified exist on disk, are non-empty,
    and match declared deliverable criteria using both OS filesystem probes and Git working tree snapshots.
    """

    FILE_MENTION_PATTERN = re.compile(
        r"(?:created|written|modified|edited|saved|generated|wrote\s+to|file)\s+[`'\"]([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[`'\"]",
        re.IGNORECASE,
    )

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self._initial_git_snapshot: Optional[Set[str]] = None

    def capture_git_snapshot(self) -> Optional[Set[str]]:
        """Captures working tree porcelain status at turn start."""
        try:
            import subprocess

            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                snapshot = set()
                for line in res.stdout.splitlines():
                    if len(line) > 3:
                        snapshot.add(line[3:].strip().replace("/", os.sep))
                self._initial_git_snapshot = snapshot
                return snapshot
        except Exception as e:
            logger.debug(f"[PhysicalDeliverableGate] Git snapshot capture skipped: {e}")
        self._initial_git_snapshot = None
        return None

    def get_git_diff_changes(self) -> Set[str]:
        """Returns set of relative paths changed/created since start of turn."""
        try:
            import subprocess

            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                current_lines = set()
                for line in res.stdout.splitlines():
                    if len(line) > 3:
                        current_lines.add(line[3:].strip().replace("/", os.sep))
                if self._initial_git_snapshot is not None:
                    return current_lines - self._initial_git_snapshot
                return current_lines
        except Exception as e:
            logger.debug(f"[PhysicalDeliverableGate] Git diff detection skipped: {e}")
        return set()

    def resolve_path(self, path_str: str) -> Path:
        """Resolves path safely against workspace root."""
        clean = path_str.strip().strip("`'\"")
        p = Path(clean)
        if p.is_absolute():
            return p
        return Path(self.workspace_root) / p

    def verify_file_deliverable(self, path_str: str, min_bytes: int = 1) -> DeliverableVerdict:
        """Probes a single file deliverable for existence and minimum size."""
        resolved = self.resolve_path(path_str)
        try:
            if not resolved.exists():
                return DeliverableVerdict(
                    is_valid=False,
                    status="missing_deliverable",
                    message=f"Claimed deliverable '{path_str}' does not exist on disk at {resolved}.",
                    missing_paths=[str(resolved)],
                )

            if not resolved.is_file():
                return DeliverableVerdict(
                    is_valid=False,
                    status="missing_deliverable",
                    message=f"Claimed deliverable '{path_str}' is a directory, not a regular file.",
                    missing_paths=[str(resolved)],
                )

            file_size = resolved.stat().st_size
            if file_size < min_bytes:
                return DeliverableVerdict(
                    is_valid=False,
                    status="empty_file",
                    message=f"Claimed deliverable '{path_str}' exists but is empty (0 bytes).",
                    missing_paths=[str(resolved)],
                )

            return DeliverableVerdict(
                is_valid=True,
                status="verified",
                message=f"Deliverable '{path_str}' verified ({file_size} bytes).",
                verified_paths=[str(resolved)],
            )
        except Exception as e:
            logger.warning(f"Error checking deliverable path {resolved}: {e}")
            return DeliverableVerdict(
                is_valid=False,
                status="missing_deliverable",
                message=f"Error checking deliverable '{path_str}': {e}",
                missing_paths=[str(resolved)],
            )

    def verify_deliverables_batch(self, paths: List[str], min_bytes: int = 1) -> DeliverableVerdict:
        """Probes multiple deliverables, collecting verified and missing paths."""
        verified: List[str] = []
        missing: List[str] = []

        for p in paths:
            res = self.verify_file_deliverable(p, min_bytes=min_bytes)
            if res.is_valid:
                verified.extend(res.verified_paths)
            else:
                missing.extend(res.missing_paths)

        if missing:
            return DeliverableVerdict(
                is_valid=False,
                status="missing_deliverable",
                message=f"{len(missing)} deliverable(s) missing or empty on disk: {', '.join(missing)}",
                verified_paths=verified,
                missing_paths=missing,
            )

        return DeliverableVerdict(
            is_valid=True,
            status="verified",
            message=f"All {len(verified)} deliverable(s) verified on disk.",
            verified_paths=verified,
        )

    def audit_claimed_completion(
        self,
        response_text: str,
        touched_files: Optional[List[str]] = None,
        ledger: Optional[Any] = None,
    ) -> DeliverableVerdict:
        """
        Audits model response text for claimed file operations.
        Validates that any file stated as created or modified actually exists on disk.
        """
        paths_to_check = set(touched_files or [])

        # Extract file mentions from response text if declaring completion
        if response_text:
            matches = self.FILE_MENTION_PATTERN.findall(response_text)
            for m in matches:
                # Filter out obvious false positives like URLs or package imports
                if not m.startswith(("http://", "https://", "venv", "site-packages")) and "." in m:
                    paths_to_check.add(m)

        if not paths_to_check:
            return DeliverableVerdict(is_valid=True, status="verified", message="No file deliverables claimed.")

        verdict = self.verify_deliverables_batch(list(paths_to_check))
        if not verdict.is_valid:
            logger.warning(f"[PhysicalDeliverableGate] Falsification detected: {verdict.message}")
            verdict.message = (
                f"[PHYSICAL DELIVERABLE GATE]: You asserted completion on deliverable(s), but the following "
                f"file(s) are missing or empty on disk: {', '.join(verdict.missing_paths)}. "
                f"Inspect the workspace and physically create or write the files before claiming task completion."
            )
        else:
            # Check git changes to confirm files modified in working tree
            git_changes = self.get_git_diff_changes()
            git_confirmed = []
            for p in verdict.verified_paths:
                try:
                    rel = os.path.relpath(p, self.workspace_root).replace("/", os.sep)
                    if rel in git_changes or any(rel.endswith(gc) for gc in git_changes):
                        git_confirmed.append(p)
                except Exception:
                    pass
            verdict.git_confirmed_paths = git_confirmed
        return verdict
