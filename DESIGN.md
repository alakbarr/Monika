---
name: ai-trading-dashboard-design
description: Design guide for the Monika AI Trading Agent dashboard featuring a Retro Vintage OS (90s / Windows 95-98) vector aesthetic with colorful window frames, thick outlines, chunky buttons, segmented progress bars, and zero-blur hard drop shadows. Reference whenever editing UI components, layouts, or stylesheets.
---

# DESIGN.md — Monika AI Trading Agent Dashboard
### Design Specification · Retro Vintage OS · 90s Desktop Aesthetic · Dual Mode

> "A 1990s vintage operating system workstation, where every window is a portal into real-time quantitative market intelligence and autonomous AI cognition."

---

## Table of Contents

1. [Design Philosophy & Concept](#1-design-philosophy--concept)
2. [Visual Anchors & Reference](#2-visual-anchors--reference)
3. [Color System & Titlebar Palette](#3-color-system--titlebar-palette)
4. [Typography](#4-typography)
5. [Window & Component Anatomy](#5-window--component-anatomy)
6. [Buttons & Interactive Controls](#6-buttons--interactive-controls)
7. [Status Badges & Progress Bars](#7-status-badges--progress-bars)
8. [Dual Mode (Light ⇄ Dark)](#8-dual-mode-light--dark)
9. [Anti-Patterns](#9-anti-patterns)

---

## 1. Design Philosophy & Concept

The Monika dashboard transforms traditional quantitative trading telemetry into a playful yet rigorously organized **Retro Vintage OS** desktop environment inspired by 90s system software (Windows 95/98, classic Mac OS, and neo-vintage vector GUI design).

### Key Pillars:
- **Windowed Architecture**: Every panel is a self-contained OS window complete with a bold, colorful title bar, window title, and control icons `[ _ ] [ □ ] [ × ]`.
- **Thick Outlines & Hard Shadows**: 2px solid dark borders (`var(--color-rule)`) paired with crisp, zero-blur drop shadows (`var(--shadow-card)` = `3px 3px 0 var(--color-rule)`). No fuzzy modern gaussian blur.
- **Categorical Color Coding**: Title bars reflect the operational category of the window (Blue for market data, Yellow for system/overview, Salmon for documents/macro, Coral for risk/error, Green for execution/profit).
- **Physical Feedback**: Buttons depress on click (`transform: translate(2px, 2px); box-shadow: 0 0 0 transparent;`), emulating mechanical plastic keys.
- **Tactile Data Presentation**: Segmented progress bars, pixel indicators, and monospace tabular data prevent layout shifts.

---

## 2. Visual Anchors & Reference

Design anchors derived from `vintage-ui.jpg`:
- Windows 95/98 desktop canvas (warm taupe slate desktop `#877F75` with floating cream window cards)
- Colorful high-contrast titlebars with distinct functional roles
- Chunky window control buttons `[ _ ] [ □ ] [ × ]`
- Segmented rectangular progress bars with rounded pill blocks
- Circular warning and error icons `[ ✕ ]` / `[ ! ]`
- Explorer folder tabs with yellow accent markers

---

## 3. Color System & Titlebar Palette

### 3.1 Light Mode — Vintage Desktop (Default)

| Token | Hex | Role |
|---|---|---|
| `--color-desktop` | `#877F75` | Desktop canvas background (warm taupe/slate) |
| `--color-paper` | `#EFE9DF` | Secondary surface / table headers / track backgrounds |
| `--color-paper-raised` | `#FAF7F2` | Window face / card content surface |
| `--color-ink` | `#1C1917` | Primary text and 2px border strokes |
| `--color-ink-soft` | `#5C544C` | Secondary labels, captions, and muted timestamps |
| `--color-rule` | `#1C1917` | Primary 2px structural outline color |

#### Window Titlebar Palette:
| Token | Hex | Category / Application |
|---|---|---|
| `--color-win-blue` | `#3BA4C4` | Market Data, General Overview, System Explorers |
| `--color-win-yellow` | `#F5BD38` | Agent Status, Live Ticker, Navigation Folders |
| `--color-win-salmon` | `#E86C53` | Macro Briefs, AI Analysis, Research Reports |
| `--color-win-coral` | `#E25B45` | Risk Management, Errors, Emergency Halts |
| `--color-win-green` | `#48A9A6` | Performance, Order Executions, Verified Gains |
| `--color-win-gray` | `#C4BCB1` | Inactive windows, Dialog footers |

### 3.2 Dark Mode — Night Station

| Token | Hex | Role |
|---|---|---|
| `--color-desktop` | `#1A1715` | Deep obsidian desk canvas |
| `--color-paper` | `#24201D` | Secondary dark background |
| `--color-paper-raised` | `#2D2824` | Raised dark window face |
| `--color-ink` | `#F6F1EA` | Light parchment text |
| `--color-ink-soft` | `#ADA296` | Muted captions |
| `--color-rule` | `#0F0D0C` | Deep dark border outlines |

---

## 4. Typography

- **Precision Monospace**: `"Courier Prime", "SF Pro Mono", monospace` for deterministic financial values, ledger rows, timestamps, and tickets.
- **System Display**: `system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif` for window titlebars, folder names, and action buttons.
- **Tabular Numerics**: `font-variant-numeric: tabular-nums` enforced across all prices, deltas, and P&L metrics to eliminate cumulative layout shifts (CLS).

---

## 5. Window & Component Anatomy

### 5.1 The Retro Window (`.win-window`)
```css
.win-window {
  background: var(--color-paper-raised);
  border: 2px solid var(--color-rule);
  border-radius: 6px;
  box-shadow: 3px 3px 0 var(--color-rule);
  overflow: hidden;
}
```

### 5.2 Window Title Bar (`.win-titlebar`)
- Height: ~30px
- Padding: `6px 10px`
- Border-bottom: `2px solid var(--color-rule)`
- Left: Window icon (16x16) + Bold window title
- Right: Window control buttons `[ _ ] [ □ ] [ × ]`

---

## 6. Buttons & Interactive Controls

### 6.1 Retro Buttons (`.win-btn` / `.typewriter-btn`)
```css
.win-btn {
  font-family: var(--font-precision);
  font-size: var(--text-body-sm);
  font-weight: 700;
  text-transform: uppercase;
  padding: 6px 14px;
  background: var(--color-paper-raised);
  color: var(--color-ink);
  border: 2px solid var(--color-rule);
  border-radius: 4px;
  box-shadow: 2px 2px 0 var(--color-rule);
  cursor: pointer;
}

.win-btn:active {
  transform: translate(2px, 2px);
  box-shadow: 0 0 0 transparent;
}
```

---

## 7. Status Badges & Progress Bars

- **Retro Badges (`.win-badge`)**: `1.5px solid var(--color-rule)`, `3px` radius, bold uppercase text, `1px 1px 0 var(--color-rule)` shadow.
- **Segmented Progress Bar**: Multi-segment pill block track (`8` segments) with coral/yellow block fills to evoke 90s downloading dialogs.
- **Pixel Status LED**: `8px x 8px` square with `1.5px solid var(--color-rule)`.

---

## 8. Dual Mode (Light ⇄ Dark)

- Desktop switch via `<ThemeToggle />` persists selection in `localStorage('monika_theme')`.
- All CSS variables dynamically update on `[data-theme="light"]` and `[data-theme="dark"]`.
- Thick borders and hard shadows persist in both modes to preserve spatial geometry.

---

## 9. Anti-Patterns

1. **NO Gaussian Blurs**: Never use `filter: blur()`, `backdrop-filter: blur()`, or soft dropshadows (`box-shadow: 0 8px 30px rgba(0,0,0,0.12)`). Use hard offset shadows only (`box-shadow: 3px 3px 0 var(--color-rule)`).
2. **NO Hairlines (0.5px)**: Minimum border width is `1.5px` (badges) or `2px` (windows, buttons, inputs).
3. **NO Floating Pill Buttons**: Do not use `border-radius: 9999px` on action buttons. Use `border-radius: 4px` for authentic OS feel.
4. **NO Neon P&L**: Use classic emerald (`#2E7D32`) and bold crimson (`#D32F2F`), never neon lime or hot pink.

---

## 10. 5 Themed Workspace Folders

1. `[TRD]` **Meja Trading**: Posisi Buku Besar, Ringkasan Kokpit, Sinyal & Pemicu Cepat.
2. `[INT]` **Ruang Intelijen**: LangGraph Pipeline DAG, Studio Debat AI, Brief Makro Fundamental.
3. `[LED]` **Buku Besar & Risiko**: Kinerja P&L, Metrik Edge, Batas Risiko, Audit Token LLM.
4. `[TEL]` **Telegraph & Chat**: Konsol Obrolan AI REPL, Riwayat Sesi, Log Dispatch.
5. `[SYS]` **Konfigurasi Sistem**: Editor Settings.yaml, Diagnostik Host & Sistem.

---

## 11. Tactile Audio Feedback

- Sintesis Web Audio API tanpa aset eksternal (`soundEffects.ts`).
- Suara klik tuts mesin tik mekanikal pada setiap penekanan tombol dan pergantian tab.
- Suara rana mekanikal (*solenoid shutter*) saat melipat atau memaksimalkan jendela.
- Tombol bisu (*mute switch*) di bilah menu taskbar atas dengan persistensi `localStorage`.