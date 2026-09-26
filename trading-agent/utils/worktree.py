# ==============================================================================
# File: utils/worktree.py
# ==============================================================================

"""
Subagent Worktree Isolation Manager.
Provides isolated, dedicated git worktrees and temporary workspaces for subagents.
Prevents subagent file modifications, git operations, or concurrent tool runs
from colliding with or corrupting the main working tree.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("TradingAgent.Utils.Worktree")


class SubagentWorktree:
    """
    Context manager for creating and automatically cleaning up an isolated
    git worktree or fallback isolated workspace for subagent execution.
    """

    def __init__(
        self,
        subagent_id: Optional[str] = None,
        base_dir: Optional[Path] = None,
        use_git: bool = True,
        auto_cleanup: bool = True,
    ):
        self.subagent_id = subagent_id or f"sub_{uuid.uuid4().hex[:8]}"
        self.base_dir = Path(base_dir or Path.cwd()).resolve()
        self.use_git = use_git
        self.auto_cleanup = auto_cleanup
        self.worktree_dir = self.base_dir / ".worktrees" / f"subagent-{self.subagent_id}"
        self.branch_name = f"subagent/{self.subagent_id}"
        self._is_git_worktree = False
        self._created = False

    def _is_in_git_repo(self) -> bool:
        """Check if base_dir is inside a valid git repository."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode == 0 and "true" in res.stdout.strip().lower()
        except Exception:
            return False

    def setup(self) -> Path:
        """Create the worktree directory and branch."""
        if self._created:
            return self.worktree_dir

        self.worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        if self.use_git and self._is_in_git_repo():
            try:
                # Add git worktree on a dedicated branch
                cmd = ["git", "worktree", "add", "-b", self.branch_name, str(self.worktree_dir)]
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0:
                    self._is_git_worktree = True
                    self._created = True
                    logger.info(
                        f"[SubagentWorktree] Created git worktree at {self.worktree_dir} (branch: {self.branch_name})"
                    )
                    return self.worktree_dir
                else:
                    logger.warning(
                        f"[SubagentWorktree] Git worktree add failed ({proc.stderr.strip()}), falling back to directory copy."
                    )
            except Exception as e:
                logger.warning(f"[SubagentWorktree] Failed creating git worktree: {e}, falling back.")

        # Fallback: create plain isolated scratch directory
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        self._is_git_worktree = False
        self._created = True
        logger.info(f"[SubagentWorktree] Created isolated scratch workspace at {self.worktree_dir}")
        return self.worktree_dir

    def get_diff(self) -> str:
        """Return the git diff of changes made inside the worktree against HEAD."""
        if not self._is_git_worktree or not self.worktree_dir.exists():
            return ""
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(self.worktree_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            return res.stdout if res.returncode == 0 else ""
        except Exception:
            return ""

    def cleanup(self) -> None:
        """Prune and safely delete the worktree and temporary branch."""
        if not self._created or not self.worktree_dir.exists():
            return

        if self._is_git_worktree:
            try:
                # Remove git worktree
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(self.worktree_dir)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                # Delete temporary branch
                subprocess.run(
                    ["git", "branch", "-D", self.branch_name],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                logger.info(f"[SubagentWorktree] Pruned git worktree and branch {self.branch_name}")
            except Exception as e:
                logger.warning(f"[SubagentWorktree] Error pruning git worktree: {e}")

        # Ensure directory is fully removed
        if self.worktree_dir.exists():
            try:
                shutil.rmtree(self.worktree_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"[SubagentWorktree] Error deleting directory {self.worktree_dir}: {e}")

        self._created = False

    def __enter__(self) -> Path:
        return self.setup()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.auto_cleanup:
            self.cleanup()
