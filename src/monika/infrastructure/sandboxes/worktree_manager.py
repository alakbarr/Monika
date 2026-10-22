# ==============================================================================
# Package: monika.infrastructure.sandboxes
# File: worktree_manager.py
# ==============================================================================

"""
Git Worktree Isolation & Sandboxed Branch Management.
Institutional-grade execution sandbox architecture.

Enables autonomous subagents to safely check out isolated git worktrees for:
  1. Isolated branch modifications without dirtying main working directory.
  2. Concurrent multi-branch code generation and testing.
  3. Safe worktree tear-down and pruning upon task completion.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


class WorktreeManager:
    """
    Manages isolated Git worktrees for agent task sandboxing.
    """

    def __init__(self, repo_path: str | Path | None = None):
        self.repo_path = Path(repo_path or Path.cwd()).resolve()

    def _run_git(self, args: list[str]) -> tuple[int, str, str]:
        """Runs a git command within the target repository."""
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=False,
                timeout=30.0,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as exc:
            return -1, "", str(exc)

    def is_git_repo(self) -> bool:
        code, out, _ = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and out == "true"

    def list_worktrees(self) -> list[dict[str, Any]]:
        """Lists active git worktrees."""
        code, out, _ = self._run_git(["worktree", "list", "--porcelain"])
        if code != 0:
            return []

        worktrees = []
        current: dict[str, Any] = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
                continue
            if line.startswith("worktree "):
                current["path"] = line[len("worktree ") :].strip()
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD ") :].strip()
            elif line.startswith("branch "):
                current["branch"] = line[len("branch ") :].strip()
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True

        if current:
            worktrees.append(current)
        return worktrees

    def create_worktree(
        self,
        branch_or_commit: str = "HEAD",
        worktree_path: str | Path | None = None,
        detach: bool = True,
    ) -> Path:
        """
        Creates a new git worktree. If worktree_path is omitted, creates a temporary directory.
        """
        if not self.is_git_repo():
            raise RuntimeError(f"Path '{self.repo_path}' is not a valid git repository.")

        if worktree_path is None:
            target_dir = Path(tempfile.mkdtemp(prefix="monika_worktree_"))
        else:
            target_dir = Path(worktree_path).resolve()
            if target_dir == self.repo_path or target_dir.parent == target_dir:
                raise ValueError(f"Invalid worktree path: cannot be repository root or system root: {target_dir}")
            target_dir.parent.mkdir(parents=True, exist_ok=True)

        args = ["worktree", "add"]
        if detach:
            args.append("--detach")
        args.extend([str(target_dir), branch_or_commit])

        code, out, err = self._run_git(args)
        if code != 0:
            if worktree_path is None and target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to create git worktree: {err or out}")

        logger.info(f"[WorktreeManager] Created worktree at '{target_dir}' from '{branch_or_commit}'.")
        return target_dir

    def remove_worktree(self, worktree_path: str | Path, force: bool = True) -> bool:
        """Removes a worktree and cleans up disk directory with safety checks."""
        target = Path(worktree_path).resolve()
        # Security Guard: never delete repo root, system root, or anything outside sandboxed worktrees
        if target == self.repo_path or target.parent == target:
            raise ValueError(f"Refusing to delete repository root or drive root: {target}")

        temp_dir = Path(tempfile.gettempdir()).resolve()
        is_in_temp = temp_dir in target.parents
        is_in_worktrees = (self.repo_path / ".worktrees").resolve() in target.parents

        active_worktrees = self.list_worktrees()
        is_known_worktree = any(Path(w.get("path", "")).resolve() == target for w in active_worktrees if w.get("path"))

        # Main worktree check: the first worktree in `worktree list` is always the main worktree
        if active_worktrees and Path(active_worktrees[0].get("path", "")).resolve() == target:
            raise ValueError(f"Refusing to remove main worktree: {target}")

        if not (is_in_temp or is_in_worktrees or is_known_worktree):
            raise ValueError(
                f"Refusing to remove worktree at '{target}': not an active worktree or inside allowed temporary sandbox."
            )

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(target))

        code, out, err = self._run_git(args)
        if code != 0:
            logger.warning(f"[WorktreeManager] Git worktree remove error: {err}. Attempting manual prune.")

        if target.exists() and (is_in_temp or is_in_worktrees or is_known_worktree):
            shutil.rmtree(target, ignore_errors=True)

        self.prune()
        return True

    def prune(self) -> None:
        """Prunes stale git worktree metadata."""
        self._run_git(["worktree", "prune"])
