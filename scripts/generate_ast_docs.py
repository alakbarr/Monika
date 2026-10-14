#!/usr/bin/env python3
# ==============================================================================
# File: scripts/generate_ast_docs.py
# Description: Automated AST-based Documentation Generator for INDEX.md & STRUCTURE.md
# ==============================================================================

"""
Automated AST documentation generator for Monika trading codebase.

Generates:
1. STRUCTURE.md: Full repository directory tree layout and file catalog.
2. INDEX.md: 100% synthetic Python AST dump of classes, functions, and module
   docstrings across all architectural layers with an auto-generated Table of Contents.

Supports --check flag for zero-drift CI pipeline verification.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src" / "monika"
INDEX_PATH = ROOT_DIR / "INDEX.md"
STRUCTURE_PATH = ROOT_DIR / "STRUCTURE.md"

IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "temp_test_dir",
    ".runtime",
    ".agents",
    ".cache",
    "moa-traces",
    ".hypothesis",
    "synthesized",
    "mt5_slippage_defense",
}

IGNORED_FILES: Set[str] = {
    "AGENTS.md",
    "GEMINI.md",
    "settings.yaml",
}

IGNORED_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".db",
    ".sqlite",
    ".wal",
    ".shm",
}


# ==============================================================================
# 1. STRUCTURE.md Tree Generator
# ==============================================================================


def generate_structure_tree(root: Path) -> str:
    """Generate an ASCII tree of the repository structure."""
    lines: List[str] = [
        "# Project Structure & Directory Layout",
        "",
        "> **Auto-Generated File**: Generated via `python scripts/generate_ast_docs.py`.",
        "> Do not edit manually.",
        "",
        "```text",
        f"{root.name}/",
    ]

    total_files = 0
    total_dirs = 0

    def walk_dir(current_dir: Path, prefix: str = ""):
        nonlocal total_files, total_dirs
        try:
            entries = sorted(
                [e for e in current_dir.iterdir() if e.name not in IGNORED_DIRS and e.name not in IGNORED_FILES],
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return

        for index, entry in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if entry.is_dir():
                total_dirs += 1
                lines.append(f"{prefix}{connector}{entry.name}/")
                walk_dir(entry, prefix + child_prefix)
            else:
                if entry.suffix.lower() not in IGNORED_EXTENSIONS:
                    total_files += 1
                    lines.append(f"{prefix}{connector}{entry.name}")

    # Walk primary project folders
    for top_folder in ("src", "frontend", "tests", "scripts", "deploy", "docs", "config"):
        p = root / top_folder
        if p.exists():
            walk_dir(p, "│   ")

    # Add top-level files
    top_files = sorted(
        [
            f
            for f in root.iterdir()
            if f.is_file()
            and f.suffix.lower() not in IGNORED_EXTENSIONS
            and not f.name.startswith(".")
            and f.name not in IGNORED_FILES
        ],
        key=lambda f: f.name.lower(),
    )
    for f in top_files:
        lines.append(f"├── {f.name}")

    lines.append("```")
    lines.append("")
    lines.append(f"**Total Tracked Directories**: {total_dirs} | **Total Tracked Files**: {total_files}")
    lines.append("")
    return "\n".join(lines)


# ==============================================================================
# 2. INDEX.md AST Extractor & Generator
# ==============================================================================


@dataclass
class FunctionInfo:
    name: str
    docstring: Optional[str]
    args: List[str]
    return_type: Optional[str]
    is_async: bool


@dataclass
class ClassInfo:
    name: str
    bases: List[str]
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)


@dataclass
class ModuleInfo:
    rel_path: str
    docstring: Optional[str]
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)


def format_type_annotation(node: Optional[ast.AST]) -> Optional[str]:
    """Format an AST type annotation node to string."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    """Extract metadata from an AST function definition."""
    doc = ast.get_docstring(node)
    first_line_doc = doc.strip().split("\n")[0] if doc else None

    args: List[str] = []
    for a in node.args.args:
        if a.arg in ("self", "cls"):
            continue
        arg_str = a.arg
        if a.annotation:
            ann = format_type_annotation(a.annotation)
            if ann:
                arg_str += f": {ann}"
        args.append(arg_str)

    ret_type = format_type_annotation(node.returns)
    return FunctionInfo(
        name=node.name,
        docstring=first_line_doc,
        args=args,
        return_type=ret_type,
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def parse_module(py_file: Path) -> Optional[ModuleInfo]:
    """Parse a single Python file using AST."""
    try:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
    except Exception:
        return None

    rel_path = py_file.relative_to(ROOT_DIR).as_posix()
    mod_doc = ast.get_docstring(tree)
    first_line_mod_doc = mod_doc.strip().split("\n")[0] if mod_doc else None

    classes: List[ClassInfo] = []
    functions: List[FunctionInfo] = []

    for item in tree.body:
        if isinstance(item, ast.ClassDef):
            if item.name.startswith("_") and not item.name.startswith("__"):
                continue  # skip private classes
            bases = [ast.unparse(b) for b in item.bases]
            cdoc = ast.get_docstring(item)
            first_cdoc = cdoc.strip().split("\n")[0] if cdoc else None

            methods: List[FunctionInfo] = []
            for sub in item.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not sub.name.startswith("_") or sub.name == "__init__":
                        methods.append(parse_function(sub))

            classes.append(ClassInfo(name=item.name, bases=bases, docstring=first_cdoc, methods=methods))
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not item.name.startswith("_"):
                functions.append(parse_function(item))

    return ModuleInfo(
        rel_path=rel_path,
        docstring=first_line_mod_doc,
        classes=classes,
        functions=functions,
    )


def generate_index_content() -> str:
    """Scan src/monika and generate complete synthetic AST INDEX.md."""
    modules_by_package: Dict[str, List[ModuleInfo]] = defaultdict(list)

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if any(ignored in py_file.parts for ignored in IGNORED_DIRS):
            continue
        if py_file.name in IGNORED_FILES:
            continue
        if py_file.name == "__init__.py" and py_file.stat().st_size == 0:
            continue
        mod_info = parse_module(py_file)
        if mod_info:
            parent_pkg = py_file.parent.relative_to(ROOT_DIR).as_posix()
            modules_by_package[parent_pkg].append(mod_info)

    # Sort packages hierarchically: core, domain, application, infrastructure, interfaces
    layer_order = ["core", "domain", "application", "infrastructure", "interfaces"]

    def package_sort_key(pkg: str) -> Tuple[int, str]:
        for idx, layer in enumerate(layer_order):
            if f"src/monika/{layer}" in pkg:
                return (idx, pkg)
        return (len(layer_order), pkg)

    sorted_packages = sorted(modules_by_package.keys(), key=package_sort_key)

    lines: List[str] = [
        "# Monika Codebase Index & Architecture Map",
        "",
        "> **Auto-Generated Synthetic AST Dump**: Generated via `python scripts/generate_ast_docs.py`.",
        "> SOTA Algorithmic Trading Platform & General-Purpose Agent Harness (Version 1.0.0).",
        "> Strict Clean Architecture: Interfaces → Application → Domain → Core (Inward Dependencies Only).",
        "",
        "## Table of Contents",
        "",
    ]

    # Generate ToC
    for pkg in sorted_packages:
        anchor = pkg.replace("/", "").replace("_", "").replace(".", "").replace("-", "")
        lines.append(f"- [`{pkg}`](#folder-{anchor})")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Generate Package & Module Details
    for pkg in sorted_packages:
        anchor = pkg.replace("/", "").replace("_", "").replace(".", "").replace("-", "")
        lines.append(f'### Folder: `{pkg}` <a id="folder-{anchor}"></a>')
        lines.append("")

        for mod in modules_by_package[pkg]:
            file_name = Path(mod.rel_path).name
            doc_str = f" - *{mod.docstring}*" if mod.docstring else ""
            lines.append(f"#### `{file_name}`{doc_str}")
            lines.append(f"- **Path**: [`{mod.rel_path}`]({mod.rel_path})")

            if mod.classes:
                lines.append("- **Classes**:")
                for c in mod.classes:
                    base_str = f"({', '.join(c.bases)})" if c.bases else ""
                    doc_c = f": {c.docstring}" if c.docstring else ""
                    lines.append(f"  - `class {c.name}{base_str}`{doc_c}")
                    for m in c.methods:
                        async_prefix = "async " if m.is_async else ""
                        ret_str = f" -> {m.return_type}" if m.return_type else ""
                        args_str = ", ".join(m.args[:3]) + (", ..." if len(m.args) > 3 else "")
                        m_doc = f" - *{m.docstring}*" if m.docstring else ""
                        lines.append(f"    - `{async_prefix}{m.name}({args_str}){ret_str}`{m_doc}")

            if mod.functions:
                lines.append("- **Top-Level Functions**:")
                for f in mod.functions:
                    async_prefix = "async " if f.is_async else ""
                    ret_str = f" -> {f.return_type}" if f.return_type else ""
                    args_str = ", ".join(f.args[:3]) + (", ..." if len(f.args) > 3 else "")
                    f_doc = f": {f.docstring}" if f.docstring else ""
                    lines.append(f"  - `{async_prefix}{f.name}({args_str}){ret_str}`{f_doc}")

            lines.append("")

    return "\n".join(lines)


# ==============================================================================
# 3. CLI & Entrypoint
# ==============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic AST documentation for Monika.")
    parser.add_argument("--check", action="store_true", help="Check for documentation drift in CI.")
    args = parser.parse_args()

    structure_content = generate_structure_tree(ROOT_DIR)
    index_content = generate_index_content()

    if args.check:
        drift = False
        if STRUCTURE_PATH.exists():
            if STRUCTURE_PATH.read_text(encoding="utf-8") != structure_content:
                print(f"[DRIFT DETECTED] {STRUCTURE_PATH} is out of sync with filesystem.")
                drift = True
        else:
            print(f"[DRIFT DETECTED] {STRUCTURE_PATH} does not exist.")
            drift = True

        if INDEX_PATH.exists():
            if INDEX_PATH.read_text(encoding="utf-8") != index_content:
                print(f"[DRIFT DETECTED] {INDEX_PATH} is out of sync with Python AST.")
                drift = True
        else:
            print(f"[DRIFT DETECTED] {INDEX_PATH} does not exist.")
            drift = True

        if drift:
            print("Run `python scripts/generate_ast_docs.py` to synchronize documentation.")
            return 1

        print("[OK] AST documentation (INDEX.md & STRUCTURE.md) is 100% in sync.")
        return 0

    STRUCTURE_PATH.write_text(structure_content, encoding="utf-8")
    print(f"Generated: {STRUCTURE_PATH}")

    INDEX_PATH.write_text(index_content, encoding="utf-8")
    print(f"Generated: {INDEX_PATH}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
