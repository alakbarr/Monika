"""Filesystem observation policy ensuring edit safety.

Provides ObservedStateGate:
- Tracks exact filesystem state (mtime_ns, size, sha256) upon reading.
- Forbids edits/overwrites on files that were never read or truncated during read.
- Forbids edits/overwrites on files that changed on disk since the last read.
- Auto-records post-write states to allow consecutive edits.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FsVersion:
    """Exact filesystem version snapshot."""

    mtime_ns: int
    size: int
    sha256: str


class ObservedStateGate:
    """Gate verifying files have been observed prior to mutation."""

    def __init__(self) -> None:
        self._observed: dict[str, FsVersion] = {}

    def _canonical_path(self, path: str | Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    def _compute_version(self, canonical_path: str) -> FsVersion | None:
        if not os.path.exists(canonical_path):
            return None
        st = os.stat(canonical_path)
        with open(canonical_path, "rb") as f:
            content_bytes = f.read()
        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
        return FsVersion(
            mtime_ns=st.st_mtime_ns,
            size=st.st_size,
            sha256=sha256_hash,
        )

    def record_read(self, path: str | Path, truncated: bool = False) -> FsVersion | None:
        """Record file version upon reading. Ignored if content was truncated."""
        if truncated:
            return None

        canonical = self._canonical_path(path)
        version = self._compute_version(canonical)
        if version is not None:
            self._observed[canonical] = version
        return version

    def check_write_allowed(self, path: str | Path) -> tuple[bool, str | None, str | None]:
        """Verify whether an edit or overwrite is allowed for path.

        Returns (allowed, error_code, error_message).
        """
        canonical = self._canonical_path(path)
        if not os.path.exists(canonical):
            return True, None, None

        if canonical not in self._observed:
            return False, "FS_UNREAD", f"File '{path}' must be read in full before editing or overwriting."

        recorded = self._observed[canonical]
        current = self._compute_version(canonical)
        if current is None:
            return True, None, None

        if current.mtime_ns != recorded.mtime_ns or current.size != recorded.size or current.sha256 != recorded.sha256:
            return (
                False,
                "FS_STALE",
                f"File '{path}' has changed on disk since it was last read. Read the file again before editing.",
            )

        return True, None, None

    def record_write(self, path: str | Path) -> FsVersion | None:
        """Update observed version after a successful write/edit."""
        canonical = self._canonical_path(path)
        version = self._compute_version(canonical)
        if version is not None:
            self._observed[canonical] = version
        return version
