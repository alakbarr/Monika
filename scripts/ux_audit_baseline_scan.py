#!/usr/bin/env python3
"""Monika UI/UX Audit Baseline Scanner.

Performs deterministic G1 (Token Integrity), G2 (WCAG Contrast),
G3 (Type Floor <11px), and G4 (Affordances & Targets) scans.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(h: str) -> float:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = lum(fg), lum(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def run_g1_scan():
    print("=== G1: FORBIDDEN EFFECTS & TOKEN INTEGRITY ===")
    forbidden_pat = re.compile(r"(backdrop-filter|filter:\s*blur|blur\(|rounded-full|from-purple|to-indigo)")
    sub_1px_pat = re.compile(r"(border[^:]*:\s*0\.\d+px|border-\[0\.\d+px\])")

    forbidden_matches = []
    sub_1px_matches = []
    raw_hex_matches = []

    hex_pat = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

    for root, _, files in os.walk(FRONTEND_SRC):
        for f in files:
            if not f.endswith((".tsx", ".ts", ".css")):
                continue
            path = Path(root) / f
            rel = path.relative_to(REPO_ROOT)
            is_token_file = "theme" in str(rel) or f in ("index.css", "tokens.ts")

            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                for idx, line in enumerate(fp, 1):
                    # Forbidden effects
                    m_forbid = forbidden_pat.search(line)
                    if m_forbid:
                        forbidden_matches.append(f"{rel}:{idx}: {line.strip()}")
                    # Sub 1px borders
                    m_sub = sub_1px_pat.search(line)
                    if m_sub:
                        sub_1px_matches.append(f"{rel}:{idx}: {line.strip()}")
                    # Raw hex outside token definitions
                    if not is_token_file:
                        for m_hex in hex_pat.findall(line):
                            raw_hex_matches.append((str(rel), idx, m_hex, line.strip()))

    print(f"Forbidden effects found: {len(forbidden_matches)}")
    for item in forbidden_matches[:10]:
        print(f"  - {item}")
    print(f"Sub-1px borders found: {len(sub_1px_matches)}")
    for item in sub_1px_matches[:10]:
        print(f"  - {item}")
    print(f"Raw hex occurrences outside token files: {len(raw_hex_matches)}")
    for rel, idx, hx, l in raw_hex_matches[:15]:
        print(f"  - {rel}:{idx} [{hx}]: {l[:80]}")


def run_g2_contrast_check():
    print("\n=== G2: WCAG 2.2 AA CONTRAST RATIOS ===")
    # Pairs from tokens.ts / index.css light and dark modes
    pairs = [
        # Light mode (desktop: #8E867C, paper: #EFE9DF, paperRaised: #FAF7F2, ink: #1C1917, inkSoft: #5C544C)
        ("Light Ink on PaperRaised", "#1C1917", "#FAF7F2", 4.5),
        ("Light Ink on Paper (canvas/table)", "#1C1917", "#EFE9DF", 4.5),
        ("Light InkSoft on PaperRaised", "#5C544C", "#FAF7F2", 4.5),
        ("Light InkSoft on Paper", "#5C544C", "#EFE9DF", 4.5),
        ("Light Ink on Desktop Canvas (#8E867C)", "#1C1917", "#8E867C", 4.5),
        # Titlebars Light Mode (text #1C1917)
        ("Light Titlebar Blue", "#1C1917", "#3BA4C4", 4.5),
        ("Light Titlebar Yellow", "#1C1917", "#F5BD38", 4.5),
        ("Light Titlebar Salmon", "#1C1917", "#E86C53", 4.5),
        ("Light Titlebar Coral", "#1C1917", "#E25B45", 4.5),
        ("Light Titlebar Green", "#1C1917", "#48A9A6", 4.5),
        ("Light Titlebar Gray", "#1C1917", "#C4BCB1", 4.5),
        # Dark mode (desktop: #1A1715, paper: #24201D, paperRaised: #2D2824, ink: #F6F1EA, inkSoft: #ADA296)
        ("Dark Ink on PaperRaised", "#F6F1EA", "#2D2824", 4.5),
        ("Dark Ink on Paper", "#F6F1EA", "#24201D", 4.5),
        ("Dark InkSoft on PaperRaised", "#ADA296", "#2D2824", 4.5),
        ("Dark InkSoft on Paper", "#ADA296", "#24201D", 4.5),
        ("Dark Edge Outline on Desktop (#7E7469)", "#7E7469", "#1A1715", 3.0),
        # Profit / Loss in Light Mode (profit: #1B5E20, loss: #B71C1C)
        ("Light Profit (#1B5E20) on PaperRaised", "#1B5E20", "#FAF7F2", 4.5),
        ("Light Loss (#B71C1C) on PaperRaised", "#B71C1C", "#FAF7F2", 4.5),
        ("Light Profit (#1B5E20) on Sunken (#E2DBD0)", "#1B5E20", "#E2DBD0", 4.5),
        ("Light Loss (#B71C1C) on Sunken (#E2DBD0)", "#B71C1C", "#E2DBD0", 4.5),
        # Profit / Loss in Dark Mode (profit: #4CAF50, loss: #F46A6A)
        ("Dark Profit (#4CAF50) on PaperRaised (#2D2824)", "#4CAF50", "#2D2824", 4.5),
        ("Dark Loss (#F46A6A) on PaperRaised (#2D2824)", "#F46A6A", "#2D2824", 4.5),
    ]

    fails = 0
    for name, fg, bg, req in pairs:
        r = contrast_ratio(fg, bg)
        passed = r >= req
        status = "PASS" if passed else "FAIL"
        if not passed:
            fails += 1
        print(f"  [{status}] {r:5.2f}:1 (req >= {req}:1) - {name} ({fg} on {bg})")
    print(f"Total Contrast Failures: {fails}")


def run_g3_type_floor_scan():
    print("\n=== G3: TYPE FLOOR SCAN (<11px) ===")
    # Look for font-size < 11px, e.g. 8px, 9px, 10px, or text-[8px], text-[9px], text-[10px], or rem < 0.6875rem
    tiny_type_pat = re.compile(
        r"(font-size:\s*([1-9]|10)(\.\d+)?px|text-\[([1-9]|10)(\.\d+)?px\]|fontSize:\s*['\"]?([1-9]|10)px)"
    )
    tiny_matches = []
    for root, _, files in os.walk(FRONTEND_SRC):
        for f in files:
            if not f.endswith((".tsx", ".ts", ".css")):
                continue
            path = Path(root) / f
            rel = path.relative_to(REPO_ROOT)
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                for idx, line in enumerate(fp, 1):
                    m = tiny_type_pat.search(line)
                    if m:
                        tiny_matches.append((str(rel), idx, m.group(0), line.strip()))

    print(f"Type floor violations (<11px) found: {len(tiny_matches)}")
    for rel, idx, matched, line in tiny_matches[:20]:
        print(f"  - {rel}:{idx} [{matched}]: {line[:80]}")


def run_g4_affordance_scan():
    print("\n=== G4: AFFORDANCES & DEAD CONTROLS ===")
    window_ctrl_pat = re.compile(
        r"(win-control-btn|aria-label=['\"]?(Minimize|Maximize|Close)['\"]?|['\"]_['\"]|['\"]□['\"]|['\"]×['\"])"
    )
    dead_ctrls = []
    for root, _, files in os.walk(FRONTEND_SRC):
        for f in files:
            if not f.endswith((".tsx", ".ts")):
                continue
            path = Path(root) / f
            rel = path.relative_to(REPO_ROOT)
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
                # Check for win-control-btn without onClick
                for m in re.finditer(
                    r'<span[^>]*className=["\'][^"\']*win-control-btn[^"\']*["\'][^>]*>([_□×])</span>', content
                ):
                    dead_ctrls.append((str(rel), m.group(0)))

    print(f"Dead window controls found (span without onClick): {len(dead_ctrls)}")
    for rel, tag in dead_ctrls[:10]:
        print(f"  - {rel}: {tag}")
    return dead_ctrls


if __name__ == "__main__":
    out_dir = REPO_ROOT / "docs" / "ux-audit" / "iterations" / "01"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_g1_scan()
    run_g2_contrast_check()
    run_g3_type_floor_scan()
    dead = run_g4_affordance_scan()
    print("\nScan completed successfully.")
