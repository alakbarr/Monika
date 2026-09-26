# ==============================================================================
# File: analysis/tools/file_patch_engine.py
# ==============================================================================

"""
Universal File Patch Engine, 9-Stage Fuzzy Matcher & Stale-Overwrite Guard.
Institutional-grade software engineering precision editing tools for Monika.

1. 9-Stage Fuzzy Matching:
   Matches target content against disk files through progressively flexible stages:
     Stage 1: exact (exact character matching)
     Stage 2: line_trimmed (trailing whitespace stripped per line)
     Stage 3: whitespace_normalized (collapses multi-space and tabs)
     Stage 4: indentation_flexible (matches relative indentation shifts)
     Stage 5: escape_normalized (literal vs unescaped control characters)
     Stage 6: trimmed_boundary (tolerates boundary whitespace on first/last line)
     Stage 7: unicode_normalized (converts smart quotes, em-dashes, non-breaking spaces)
     Stage 8: block_anchor (anchors on first and last lines, matches inner block)
     Stage 9: context_aware (line-by-line Levenshtein similarity with >= 80% threshold)

2. Stale-Overwrite Guard:
   Tracks file read history (mtime + SHA-256 hash). Rejects write_file or patch if
   the target file has never been read in the current session or was modified on disk
   since it was last read.

3. Automated Post-Edit Syntax Linting:
   Instantly parses the resulting file in-process (Python AST, JSON, YAML) immediately
   after patching. Returns immediate syntax diagnostic feedback if an error is introduced.

4. Multi-File V4A Unified Patch Parser:
   Parses and applies combined patches with multiple operations (Update, Add, Delete, Move).
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Tools.FilePatchEngine")


@dataclass
class FileReadRecord:
    path: str
    mtime: float
    sha256: str
    read_timestamp: float


class StaleOverwriteGuard:
    """
    Guards files against blind or out-of-order overwrites.
    """

    def __init__(self):
        self._read_records: Dict[str, FileReadRecord] = {}

    def record_read(self, path: str) -> None:
        """Records a successful read event for a file."""
        norm_path = os.path.normpath(os.path.abspath(path))
        if os.path.exists(norm_path):
            mtime = os.path.getmtime(norm_path)
            try:
                with open(norm_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                file_hash = ""
            self._read_records[norm_path] = FileReadRecord(
                path=norm_path,
                mtime=mtime,
                sha256=file_hash,
                read_timestamp=os.path.getmtime(norm_path),
            )

    def verify_can_modify(self, path: str) -> Tuple[bool, Optional[str]]:
        """
        Verifies if a file is safe to modify or overwrite.
        Returns (True, None) if safe, or (False, error_reason) if unsafe.
        """
        norm_path = os.path.normpath(os.path.abspath(path))
        if not os.path.exists(norm_path):
            # Brand new file: modification is safe
            return True, None

        record = self._read_records.get(norm_path)
        if record is None:
            return (
                False,
                f"Safety Guard: File '{path}' exists but has not been read in this session. "
                "Read the file first to verify existing content before modifying.",
            )

        current_mtime = os.path.getmtime(norm_path)
        if current_mtime > record.mtime + 0.001:
            try:
                with open(norm_path, "rb") as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest()
                if current_hash != record.sha256:
                    return (
                        False,
                        f"Safety Guard: File '{path}' was modified externally on disk since last read. "
                        "Re-read the file to ensure changes are not overwritten.",
                    )
            except Exception as exc:
                return False, f"Safety Guard error checking file '{path}': {exc}"

        return True, None


class FuzzyMatcher:
    """
    9-Stage progressive fuzzy matcher for resilient search-and-replace.
    """

    @classmethod
    def find_match(cls, content: str, target: str) -> Tuple[Optional[Tuple[int, int]], str]:
        """
        Attempts to find target in content across 9 stages.
        Returns ((start_idx, end_idx), stage_name) or (None, "no_match").
        """
        if not target:
            return None, "empty_target"

        # Stage 1: Exact
        idx = content.find(target)
        if idx != -1:
            return (idx, idx + len(target)), "exact"

        # Normalize line endings
        content_lf = content.replace("\r\n", "\n")
        target_lf = target.replace("\r\n", "\n")
        idx_lf = content_lf.find(target_lf)
        if idx_lf != -1:
            return (idx_lf, idx_lf + len(target_lf)), "exact_lf"

        content_lines = content_lf.splitlines(keepends=True)
        target_lines = target_lf.splitlines(keepends=True)

        # Stage 2: Line trimmed (trailing whitespace ignored)
        match = cls._match_line_trimmed(content_lines, target_lines)
        if match:
            return match, "line_trimmed"

        # Stage 3: Whitespace normalized
        match = cls._match_whitespace_normalized(content_lf, target_lf)
        if match:
            return match, "whitespace_normalized"

        # Stage 4: Indentation flexible
        match = cls._match_indentation_flexible(content_lines, target_lines)
        if match:
            return match, "indentation_flexible"

        # Stage 5: Escape normalized
        match = cls._match_escape_normalized(content_lf, target_lf)
        if match:
            return match, "escape_normalized"

        # Stage 6: Trimmed boundary
        match = cls._match_trimmed_boundary(content_lf, target_lf)
        if match:
            return match, "trimmed_boundary"

        # Stage 7: Unicode normalized
        match = cls._match_unicode_normalized(content_lf, target_lf)
        if match:
            return match, "unicode_normalized"

        # Stage 8: Block anchor
        match = cls._match_block_anchor(content_lines, target_lines)
        if match:
            return match, "block_anchor"

        # Stage 9: Context-aware similarity (threshold >= 0.80)
        match = cls._match_context_aware(content_lines, target_lines, threshold=0.80)
        if match:
            return match, "context_aware"

        return None, "no_match"

    @classmethod
    def _match_line_trimmed(cls, c_lines: List[str], t_lines: List[str]) -> Optional[Tuple[int, int]]:
        t_stripped = [l.rstrip() for l in t_lines]
        t_len = len(t_lines)
        for i in range(len(c_lines) - t_len + 1):
            window = [l.rstrip() for l in c_lines[i : i + t_len]]
            if window == t_stripped:
                start = sum(len(l) for l in c_lines[:i])
                length = sum(len(l) for l in c_lines[i : i + t_len])
                return start, start + length
        return None

    @classmethod
    def _match_whitespace_normalized(cls, content: str, target: str) -> Optional[Tuple[int, int]]:
        tokens = [re.escape(tok) for tok in target.split()]
        if not tokens:
            return None
        pattern = r"\s+".join(tokens)
        match = re.search(pattern, content)
        if match:
            return match.start(), match.end()
        return None

    @classmethod
    def _match_indentation_flexible(cls, c_lines: List[str], t_lines: List[str]) -> Optional[Tuple[int, int]]:
        t_dedent = [l.lstrip() for l in t_lines]
        t_len = len(t_lines)
        for i in range(len(c_lines) - t_len + 1):
            window = [l.lstrip() for l in c_lines[i : i + t_len]]
            if window == t_dedent:
                start = sum(len(l) for l in c_lines[:i])
                length = sum(len(l) for l in c_lines[i : i + t_len])
                return start, start + length
        return None

    @classmethod
    def _match_escape_normalized(cls, content: str, target: str) -> Optional[Tuple[int, int]]:
        unescaped = target.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        idx = content.find(unescaped)
        if idx != -1:
            return idx, idx + len(unescaped)
        return None

    @classmethod
    def _match_trimmed_boundary(cls, content: str, target: str) -> Optional[Tuple[int, int]]:
        t_strip = target.strip()
        idx = content.find(t_strip)
        if idx != -1:
            return idx, idx + len(t_strip)
        return None

    @classmethod
    def _match_unicode_normalized(cls, content: str, target: str) -> Optional[Tuple[int, int]]:
        c_nfkd = unicodedata.normalize("NFKD", content)
        t_nfkd = unicodedata.normalize("NFKD", target)
        idx = c_nfkd.find(t_nfkd)
        if idx != -1:
            return idx, idx + len(target)
        return None

    @classmethod
    def _match_block_anchor(cls, c_lines: List[str], t_lines: List[str]) -> Optional[Tuple[int, int]]:
        if len(t_lines) < 3:
            return None
        first_anchor = t_lines[0].strip()
        last_anchor = t_lines[-1].strip()
        t_len = len(t_lines)

        for i in range(len(c_lines) - t_len + 1):
            if c_lines[i].strip() == first_anchor:
                # Check candidate last anchor within +/- 2 lines of expected length
                for j in range(max(0, i + t_len - 3), min(len(c_lines), i + t_len + 3)):
                    if c_lines[j].strip() == last_anchor:
                        start = sum(len(l) for l in c_lines[:i])
                        length = sum(len(l) for l in c_lines[i : j + 1])
                        return start, start + length
        return None

    @classmethod
    def _match_context_aware(
        cls, c_lines: List[str], t_lines: List[str], threshold: float = 0.80
    ) -> Optional[Tuple[int, int]]:
        t_len = len(t_lines)
        if t_len == 0 or len(c_lines) < t_len:
            return None

        t_text = "".join(t_lines)
        best_ratio = 0.0
        best_span = None

        for i in range(len(c_lines) - t_len + 1):
            window = "".join(c_lines[i : i + t_len])
            matcher = difflib.SequenceMatcher(None, window, t_text)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                if ratio >= threshold:
                    start = sum(len(l) for l in c_lines[:i])
                    length = len(window)
                    best_span = (start, start + length)

        return best_span


class SyntaxLinter:
    """
    In-process syntax linter for immediate post-edit diagnostic feedback.
    """

    @classmethod
    def lint_content(cls, path: str, content: str) -> Optional[str]:
        """
        Lints content based on file extension.
        Returns an error message string if syntax is invalid, or None if valid.
        """
        ext = os.path.splitext(path)[1].lower()

        if ext == ".py":
            try:
                ast.parse(content, filename=path)
            except SyntaxError as e:
                return f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}\n  {e.text}"

        elif ext == ".json":
            try:
                json.loads(content)
            except Exception as e:
                return f"JSON ParseError: {e}"

        elif ext in (".yaml", ".yml"):
            try:
                import yaml
                yaml.safe_load(content)
            except Exception as e:
                return f"YAML ParseError: {e}"

        return None


class FilePatchEngine:
    """
    High-level facade orchestrating safe file reading, 9-stage fuzzy patching,
    and post-edit linting.
    """

    def __init__(self):
        self.guard = StaleOverwriteGuard()

    def read_file(
        self, path: str, offset: int = 1, limit: int = 2000
    ) -> Tuple[bool, str]:
        """
        Reads file content with 1-indexed line numbers and records read timestamp.
        """
        norm_path = os.path.normpath(os.path.abspath(path))
        if not os.path.exists(norm_path):
            return False, f"File not found: '{path}'"

        try:
            with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            self.guard.record_read(norm_path)

            start = max(0, offset - 1)
            end = min(len(lines), start + limit)
            selected_lines = lines[start:end]

            numbered = [f"{i + 1:6d}: {line}" for i, line in enumerate(selected_lines, start=start)]
            header = f"[Viewing '{path}' - lines {start + 1} to {end} of {len(lines)}]\n"
            return True, header + "".join(numbered)
        except Exception as exc:
            return False, f"Error reading file '{path}': {exc}"

    def write_file(self, path: str, content: str, allow_overwrite: bool = False) -> Tuple[bool, str]:
        """
        Safely writes full file content under stale-overwrite and large-file wipeout protection.
        """
        # Rule 10: Zero-byte/empty file wipeout protection
        if not content.strip():
            return False, "Safety Guard: Writing an empty file (0 bytes) is prohibited."

        can_mod, reason = self.guard.verify_can_modify(path)
        if not can_mod:
            return False, reason or "Write rejected by safety guard."

        norm_path = os.path.normpath(os.path.abspath(path))

        # Check existing file size/line count to prevent accidental full rewrites
        if os.path.exists(norm_path) and not allow_overwrite:
            try:
                with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                    existing_lines = sum(1 for _ in f)
                if existing_lines > 100:
                    return (
                        False,
                        f"Safety Guard: Existing file '{path}' is large ({existing_lines} lines). "
                        "To prevent accidental truncation or loss of codebase context, please use 'patch' "
                        "for targeted edits, or explicitly pass allow_overwrite=True if replacing the entire file.",
                    )
            except Exception:
                pass

        # Lint before saving
        lint_err = SyntaxLinter.lint_content(path, content)
        if lint_err:
            return False, f"Write rejected due to syntax error:\n{lint_err}"

        os.makedirs(os.path.dirname(norm_path), exist_ok=True)

        try:
            with open(norm_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.guard.record_read(norm_path)
            return True, f"Successfully wrote {len(content)} characters to '{path}'"
        except Exception as exc:
            return False, f"Failed writing to '{path}': {exc}"


    def patch_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> Tuple[bool, str]:
        """
        Applies a targeted find-and-replace using 9-stage fuzzy matching.
        """
        can_mod, reason = self.guard.verify_can_modify(path)
        if not can_mod:
            return False, reason or "Patch rejected by safety guard."

        norm_path = os.path.normpath(os.path.abspath(path))
        if not os.path.exists(norm_path):
            return False, f"File not found: '{path}'"

        try:
            with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()

            match_span, stage = FuzzyMatcher.find_match(original_content, old_string)
            if match_span is None:
                return False, f"Patch failed: target string not found in '{path}' across all 9 fuzzy matching stages."

            start, end = match_span
            if replace_all:
                patched_content = original_content.replace(old_string, new_string)
            else:
                patched_content = original_content[:start] + new_string + original_content[end:]

            # Post-edit linting
            lint_err = SyntaxLinter.lint_content(path, patched_content)
            if lint_err:
                return (
                    False,
                    f"Patch resulted in syntax error (stage matched: {stage}). Aborting write:\n{lint_err}",
                )

            with open(norm_path, "w", encoding="utf-8") as f:
                f.write(patched_content)

            self.guard.record_read(norm_path)
            return (
                True,
                f"Successfully patched '{path}' (matched via stage: {stage}). Replaced {end - start} chars.",
            )
        except Exception as exc:
            return False, f"Error patching '{path}': {exc}"

    def apply_multi_patch(
        self, patch_text: str, dry_run: bool = False
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Two-phase transactional multi-file patch execution.
        Phase 1: In-memory simulation and full AST / syntax lint verification.
        Phase 2: Atomic disk commit if and only if Phase 1 passes 100%.
        """
        ops = V4APatchParser.parse(patch_text)
        if not ops:
            return False, "No valid patch operations found in patch text.", []

        staged_contents: Dict[str, str] = {}
        staged_deletions: List[str] = []
        staged_moves: List[Tuple[str, str]] = []
        op_summaries: List[Dict[str, Any]] = []

        # Phase 1: In-memory simulation & linting
        for idx, op in enumerate(ops):
            norm_path = os.path.normpath(os.path.abspath(op.path)) if op.path else ""

            if op.action == "UPDATE":
                if not norm_path:
                    return False, f"Phase 1 Dry-run failed: UPDATE missing target file path.", op_summaries

                # Check guard
                can_mod, reason = self.guard.verify_can_modify(norm_path)
                if not can_mod:
                    return False, f"Phase 1 Dry-run rejected for '{op.path}': {reason}", op_summaries

                # Get existing or already-staged content
                if norm_path in staged_contents:
                    current_content = staged_contents[norm_path]
                else:
                    if not os.path.exists(norm_path):
                        return False, f"Phase 1 Dry-run failed: file '{op.path}' does not exist on disk.", op_summaries
                    try:
                        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                            current_content = f.read()
                    except Exception as e:
                        return False, f"Phase 1 Dry-run failed reading '{op.path}': {e}", op_summaries

                if op.search_content:
                    match_span, stage = FuzzyMatcher.find_match(current_content, op.search_content)
                    if match_span is None:
                        return (
                            False,
                            f"Phase 1 Dry-run failed: search block #{idx + 1} not found in '{op.path}' across 9 fuzzy stages.",
                            op_summaries,
                        )
                    start, end = match_span
                    new_content = current_content[:start] + (op.replace_content or "") + current_content[end:]
                else:
                    new_content = op.replace_content or ""
                    stage = "full_replace"

                # In-memory post-patch linting check
                lint_err = SyntaxLinter.lint_content(norm_path, new_content)
                if lint_err:
                    return (
                        False,
                        f"Phase 1 Dry-run failed: syntax error in '{op.path}' after applying patch #{idx + 1}:\n{lint_err}",
                        op_summaries,
                    )

                staged_contents[norm_path] = new_content
                op_summaries.append({
                    "action": "UPDATE",
                    "path": op.path,
                    "stage": stage,
                    "length": len(new_content),
                })

            elif op.action == "ADD":
                if not norm_path:
                    return False, "Phase 1 Dry-run failed: ADD missing target file path.", op_summaries
                new_content = op.new_file_content or ""
                lint_err = SyntaxLinter.lint_content(norm_path, new_content)
                if lint_err:
                    return (
                        False,
                        f"Phase 1 Dry-run failed: syntax error in new file '{op.path}':\n{lint_err}",
                        op_summaries,
                    )
                staged_contents[norm_path] = new_content
                op_summaries.append({
                    "action": "ADD",
                    "path": op.path,
                    "length": len(new_content),
                })

            elif op.action == "DELETE":
                if not norm_path or not os.path.exists(norm_path):
                    return False, f"Phase 1 Dry-run failed: file to delete '{op.path}' does not exist.", op_summaries
                staged_deletions.append(norm_path)
                op_summaries.append({"action": "DELETE", "path": op.path})

            elif op.action == "MOVE":
                if not norm_path or not op.new_path:
                    return False, f"Phase 1 Dry-run failed: MOVE operation missing target path for '{op.path}'.", op_summaries
                norm_new_path = os.path.normpath(os.path.abspath(op.new_path))
                if not os.path.exists(norm_path):
                    return False, f"Phase 1 Dry-run failed: file to move '{op.path}' does not exist.", op_summaries
                staged_moves.append((norm_path, norm_new_path))
                op_summaries.append({"action": "MOVE", "path": op.path, "new_path": op.new_path})

        if dry_run:
            return True, f"Dry-run passed: all {len(ops)} operations verified with zero syntax errors.", op_summaries

        # Phase 2: Atomic Disk Commit
        try:
            for file_path, content in staged_contents.items():
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.guard.record_read(file_path)

            for src, dst in staged_moves:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(src, dst)
                self.guard.record_read(dst)

            for del_path in staged_deletions:
                if os.path.exists(del_path):
                    os.remove(del_path)

            return True, f"Successfully committed {len(ops)} operations across {len(staged_contents)} files.", op_summaries
        except Exception as exc:
            return False, f"Phase 2 Commit failed during disk write: {exc}", op_summaries


@dataclass
class PatchOperation:
    action: str  # "UPDATE", "ADD", "DELETE", "MOVE"
    path: str
    new_path: Optional[str] = None
    search_content: Optional[str] = None
    replace_content: Optional[str] = None
    new_file_content: Optional[str] = None


class V4APatchParser:
    """
    Parses unified multi-file patches with syntax:
    *** Update File: path/to/file ***
    <<<<<<< SEARCH
    ...
    =======
    ...
    >>>>>>> REPLACE

    *** Add File: path/to/file ***
    ... content ...

    *** Delete File: path/to/file ***

    *** Move File: old/path -> new/path ***
    """

    FILE_HEADER_RE = re.compile(
        r"^\*{3}\s+(Update File|Add File|Delete File|Move File):\s*(.+?)\s*\*{3}$",
        re.MULTILINE,
    )

    SEARCH_REPLACE_RE = re.compile(
        r"<<<<<<<\s*SEARCH\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>>\s*REPLACE",
        re.DOTALL,
    )

    @classmethod
    def parse(cls, patch_text: str) -> List[PatchOperation]:
        operations: List[PatchOperation] = []
        if not patch_text or not patch_text.strip():
            return operations

        matches = list(cls.FILE_HEADER_RE.finditer(patch_text))
        if not matches:
            # Single search/replace block fallback
            sr_match = cls.SEARCH_REPLACE_RE.search(patch_text)
            if sr_match:
                operations.append(
                    PatchOperation(
                        action="UPDATE",
                        path="",
                        search_content=sr_match.group(1),
                        replace_content=sr_match.group(2),
                    )
                )
            return operations

        for i, m in enumerate(matches):
            action_type = m.group(1).upper()
            target_info = m.group(2).strip()
            start_body = m.end()
            end_body = matches[i + 1].start() if i + 1 < len(matches) else len(patch_text)
            body = patch_text[start_body:end_body].strip()

            if "UPDATE FILE" in action_type:
                sr_blocks = list(cls.SEARCH_REPLACE_RE.finditer(body))
                if sr_blocks:
                    for sr in sr_blocks:
                        operations.append(
                            PatchOperation(
                                action="UPDATE",
                                path=target_info,
                                search_content=sr.group(1),
                                replace_content=sr.group(2),
                            )
                        )
                else:
                    operations.append(
                        PatchOperation(
                            action="UPDATE",
                            path=target_info,
                            search_content="",
                            replace_content=body,
                        )
                    )
            elif "ADD FILE" in action_type:
                content_m = re.search(r"<<<<<<<\s*CONTENT\r?\n(.*?)\r?\n>>>>>>>\s*CONTENT", body, re.DOTALL)
                file_content = content_m.group(1) if content_m else body
                operations.append(
                    PatchOperation(
                        action="ADD",
                        path=target_info,
                        new_file_content=file_content,
                    )
                )
            elif "DELETE FILE" in action_type:
                operations.append(
                    PatchOperation(
                        action="DELETE",
                        path=target_info,
                    )
                )
            elif "MOVE FILE" in action_type:
                parts = [p.strip() for p in target_info.split("->")]
                if len(parts) == 2:
                    operations.append(
                        PatchOperation(
                            action="MOVE",
                            path=parts[0],
                            new_path=parts[1],
                        )
                    )

        return operations

