#!/usr/bin/env python3
"""
UX Audit Baseline Scanner for Monika Web Dashboard.
Performs automated verification across G1 (Tokens), G2 (WCAG 2.2 AA Contrast),
G3 (11px Type Floor), and G4 (Affordances & Zero Dead Controls).
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
INDEX_CSS = FRONTEND_SRC / "index.css"


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel_lum(c: int) -> float:
        srgb = c / 255.0
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex_to_rgb(hex1))
    l2 = relative_luminance(hex_to_rgb(hex2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def scan_g1_forbidden_effects():
    print("=== G1: FORBIDDEN EFFECTS & TOKEN INTEGRITY ===")
    forbidden_patterns = [
        (r"backdrop-filter", "Gaussian blur backdrop-filter"),
        (r"filter:\s*blur", "CSS filter blur"),
        (r"blur\(", "Blur function"),
        (r"rounded-full", "Tailwind rounded-full pill"),
        (r"from-purple", "AI Slop purple gradient"),
        (r"to-indigo", "AI Slop indigo gradient"),
    ]
    sub_1px_pattern = re.compile(r"border[^:;]*:\s*0\.5px")
    hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")

    forbidden_hits = []
    sub_1px_hits = []
    raw_hex_hits = []

    for p in sorted(FRONTEND_SRC.rglob("*")):
        if p.suffix not in (".tsx", ".ts", ".css"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel_path = p.relative_to(REPO_ROOT)

        for idx, line in enumerate(text.splitlines(), 1):
            for pat, desc in forbidden_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    forbidden_hits.append((rel_path, idx, desc, line.strip()))
            if sub_1px_pattern.search(line):
                sub_1px_hits.append((rel_path, idx, line.strip()))

            # Check raw hex outside index.css and tokens.ts
            if p.name not in ("index.css", "tokens.ts") and "theme" not in str(p):
                if p.suffix in (".tsx", ".css"):
                    for m in hex_pattern.finditer(line):
                        raw_hex_hits.append((rel_path, idx, m.group(0), line.strip()))

    print(f"Forbidden effects found: {len(forbidden_hits)}")
    for hit in forbidden_hits:
        print(f"  - {hit[0]}:{hit[1]} [{hit[2]}]: {hit[3]}")

    print(f"Sub-1px borders found: {len(sub_1px_hits)}")
    for hit in sub_1px_hits:
        print(f"  - {hit[0]}:{hit[1]}: {hit[2]}")

    print(f"Raw hex occurrences outside token files: {len(raw_hex_hits)}")
    for hit in raw_hex_hits[:15]:
        print(f"  - {hit[0]}:{hit[1]} [{hit[2]}]: {hit[3]}")
    print()


def scan_g2_contrast():
    print("=== G2: WCAG 2.2 AA CONTRAST RATIOS ===")
    # Swiss Editorial & Unboxed Sculptural Token Pairs (DESIGN.md v3.0)
    contrast_pairs = [
        # Light Mode (#FFFFFF Canvas & #F7F8FA Well)
        ("Light Ink on Canvas (#FFFFFF)", "#111215", "#FFFFFF", 4.5),
        ("Light Ink on Well (#F7F8FA)", "#111215", "#F7F8FA", 4.5),
        ("Light InkSecondary on Canvas (#FFFFFF)", "#525660", "#FFFFFF", 4.5),
        ("Light InkSecondary on Well (#F7F8FA)", "#525660", "#F7F8FA", 4.5),
        ("Light InkMuted on Canvas (#FFFFFF)", "#686D78", "#FFFFFF", 4.5),
        ("Light InkMuted on Well (#F7F8FA)", "#686D78", "#F7F8FA", 4.5),
        ("Light Gain (#0D7A52) on Canvas (#FFFFFF)", "#0D7A52", "#FFFFFF", 4.5),
        ("Light Gain (#0D7A52) on Well (#F7F8FA)", "#0D7A52", "#F7F8FA", 4.5),
        ("Light Loss (#C82838) on Canvas (#FFFFFF)", "#C82838", "#FFFFFF", 4.5),
        ("Light Loss (#C82838) on Well (#F7F8FA)", "#C82838", "#F7F8FA", 4.5),
        ("Light Warn (#9A5B00) on Canvas (#FFFFFF)", "#9A5B00", "#FFFFFF", 4.5),
        ("Light Warn (#9A5B00) on Well (#F7F8FA)", "#9A5B00", "#F7F8FA", 4.5),
        ("Light Edge Outline on Canvas (#FFFFFF)", "#686D78", "#FFFFFF", 3.0),
        # Dark Mode (#121316 Canvas & #17191D Well)
        ("Dark Ink on Canvas (#121316)", "#F3F4F6", "#121316", 4.5),
        ("Dark Ink on Well (#17191D)", "#F3F4F6", "#17191D", 4.5),
        ("Dark InkSecondary on Canvas (#121316)", "#9CA3AF", "#121316", 4.5),
        ("Dark InkSecondary on Well (#17191D)", "#9CA3AF", "#17191D", 4.5),
        ("Dark InkMuted on Canvas (#121316)", "#848B98", "#121316", 4.5),
        ("Dark InkMuted on Well (#17191D)", "#848B98", "#17191D", 4.5),
        ("Dark Gain (#10B981) on Canvas (#121316)", "#10B981", "#121316", 4.5),
        ("Dark Gain (#10B981) on Well (#17191D)", "#10B981", "#17191D", 4.5),
        ("Dark Loss (#F43F5E) on Canvas (#121316)", "#F43F5E", "#121316", 4.5),
        ("Dark Loss (#F43F5E) on Well (#17191D)", "#F43F5E", "#17191D", 4.5),
        ("Dark Warn (#F59E0B) on Canvas (#121316)", "#F59E0B", "#121316", 4.5),
        ("Dark Warn (#F59E0B) on Well (#17191D)", "#F59E0B", "#17191D", 4.5),
        ("Dark Edge Outline on Canvas (#121316)", "#6E7685", "#121316", 3.0),
    ]

    failures = 0
    for label, fg, bg, min_req in contrast_pairs:
        ratio = contrast_ratio(fg, bg)
        status = "PASS" if ratio >= min_req else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"  [{status}] {ratio:5.2f}:1 (req >= {min_req}:1) - {label} ({fg} on {bg})")

    print(f"Total Contrast Failures: {failures}\n")


def scan_g3_type_floor():
    print("=== G3: TYPE FLOOR SCAN (<11px) ===")
    small_font_pat = re.compile(r"(?:font-size|fontSize)\s*:\s*['\"]?([0-9]+(?:\.[0-9]+)?)px")
    hits = []
    for p in sorted(FRONTEND_SRC.rglob("*")):
        if p.suffix not in (".tsx", ".ts", ".css"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel_path = p.relative_to(REPO_ROOT)
        for idx, line in enumerate(text.splitlines(), 1):
            for m in small_font_pat.finditer(line):
                val = float(m.group(1))
                if val < 11.0:
                    hits.append((rel_path, idx, f"{val}px", line.strip()))

    print(f"Type floor violations (<11px) found: {len(hits)}")
    for hit in hits:
        print(f"  - {hit[0]}:{hit[1]} [{hit[2]}]: {hit[3]}")
    print()


def scan_g4_affordances():
    print("=== G4: AFFORDANCES & DEAD CONTROLS ===")
    dead_ctrl_pat = re.compile(r"<span[^>]*win-control-btn[^>]*>")
    hits = []
    for p in sorted(FRONTEND_SRC.rglob("*.tsx")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel_path = p.relative_to(REPO_ROOT)
        for idx, line in enumerate(text.splitlines(), 1):
            if dead_ctrl_pat.search(line) and "onClick" not in line:
                hits.append((rel_path, idx, line.strip()))
    print(f"Dead window controls found (span without onClick): {len(hits)}")
    for hit in hits:
        print(f"  - {hit[0]}:{hit[1]}: {hit[2]}")
    print()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    scan_g1_forbidden_effects()
    scan_g2_contrast()
    scan_g3_type_floor()
    scan_g4_affordances()
    print("Scan completed successfully.")
