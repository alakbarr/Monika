---
name: ai-trading-dashboard-design
description: Design guide for the Monika AI Trading Agent Web Dashboard featuring a windowed desktop workstation interface with distinct panel categories, clean outlines, tactile buttons, segmented progress bars, and crisp drop shadows. Reference whenever editing UI components, layouts, or stylesheets.
---

# DESIGN.md — Monika Web Dashboard Design Guide
### UI & Layout Specification · Windowed Workstation Interface · Dual Mode

> "A focused desktop workstation environment where every panel provides clear, real-time insight into quantitative market intelligence and system status."

---

## Table of Contents

1. [Design Philosophy & Concept](#1-design-philosophy--concept)
2. [Visual Foundation & Structure](#2-visual-foundation--structure)
3. [Color System & Titlebar Palette](#3-color-system--titlebar-palette)
4. [Typography](#4-typography)
5. [Window & Component Anatomy](#5-window--component-anatomy)
6. [Buttons & Interactive Controls](#6-buttons--interactive-controls)
7. [Status Badges & Progress Bars](#7-status-badges--progress-bars)
8. [Dual Mode (Light ⇄ Dark)](#8-dual-mode-light--dark)
9. [Anti-Patterns](#9-anti-patterns)
10. [Workspace Organization](#10-workspace-organization)
11. [Audio Feedback](#11-audio-feedback)

---

## 1. Design Philosophy & Concept

The Monika Web Dashboard transforms complex quantitative trading telemetry into a structured, windowed desktop workstation interface.

### Key Pillars:
- **Windowed Architecture**: Every panel is a self-contained window complete with a category title bar, title label, and control icons `[ _ ] [ □ ] [ × ]`.
- **Solid Outlines & Offset Shadows**: 2px solid dark borders (`var(--color-rule)`) paired with crisp, zero-blur offset shadows (`var(--shadow-card)` = `3px 3px 0 var(--color-rule)`).
- **Categorical Color Coding**: Title bars reflect the operational role of each window (Blue for market data, Yellow for overview, Salmon for macro briefs, Coral for risk limits, Green for executions).
- **Tactile Feedback**: Interactive buttons depress on click (`transform: translate(2px, 2px); box-shadow: 0 0 0 transparent;`).
- **Tabular Data Presentation**: Monospace tabular numbers prevent layout shifts during tick updates.

---

## 2. Visual Foundation & Structure

- Desktop canvas layout with structured floating panel cards.
- High-contrast titlebars with distinct functional roles.
- Window control buttons `[ _ ] [ □ ] [ × ]`.
- Segmented rectangular progress bars.
- Status indicators and warning icons `[ ✕ ]` / `[ ! ]`.
- Navigation tabs with clean accent markers.

---

## 3. Color System & Titlebar Palette

### 3.1 Light Mode — Classic Desktop (Default)

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

- **Precision Monospace**: `"Courier Prime", "SF Pro Mono", monospace` for financial values, ledger rows, timestamps, and tickets.
- **System Display**: `system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif` for window titlebars, folder names, and action buttons.
- **Tabular Numerics**: `font-variant-numeric: tabular-nums` enforced across all prices, deltas, and P&L metrics to eliminate cumulative layout shifts (CLS).

---

## 5. Window & Component Anatomy

### 5.1 The Desktop Window (`.win-window`)
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

### 6.1 Action Buttons (`.win-btn` / `.typewriter-btn`)
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

- **Status Badges (`.win-badge`)**: `1.5px solid var(--color-rule)`, `3px` radius, bold uppercase text, `1px 1px 0 var(--color-rule)` shadow.
- **Segmented Progress Bar**: Multi-segment pill block track (`8` segments) with coral/yellow block fills.
- **Status LED**: `8px x 8px` square with `1.5px solid var(--color-rule)`.

---

## 8. Dual Mode (Light ⇄ Dark)

- Desktop switch via `<ThemeToggle />` persists selection in `localStorage('monika_theme')`.
- All CSS variables dynamically update on `[data-theme="light"]` and `[data-theme="dark"]`.
- Solid borders and offset shadows persist in both modes to preserve spatial geometry.

---

## 9. Anti-Patterns

1. **NO Gaussian Blurs**: Never use `filter: blur()`, `backdrop-filter: blur()`, or soft dropshadows (`box-shadow: 0 8px 30px rgba(0,0,0,0.12)`). Use crisp offset shadows only (`box-shadow: 3px 3px 0 var(--color-rule)`).
2. **NO Hairlines (0.5px)**: Minimum border width is `1.5px` (badges) or `2px` (windows, buttons, inputs).
3. **NO Floating Pill Buttons**: Do not use `border-radius: 9999px` on action buttons. Use `border-radius: 4px` for authentic window feel.
4. **NO Neon P&L**: Use classic emerald (`#2E7D32`) and bold crimson (`#D32F2F`), never neon lime or hot pink.

---

## 10. Workspace Organization

1. `[TRD]` **Trading Desk**: Ledger Positions, Cockpit Summary, Signals & Quick Triggers.
2. `[INT]` **Intelligence Room**: LangGraph Pipeline DAG, AI Debate Studio, Fundamental Macro Brief.
3. `[LED]` **Ledger & Risk**: P&L Performance, Edge Metrics, Risk Limits, LLM Token Audit.
4. `[TEL]` **Telegraph & Chat**: AI REPL Chat Console, Session History, Dispatch Logs.
5. `[SYS]` **System Configuration**: Settings.yaml Editor, Host Diagnostics & Health Checks.

---

## 11. Audio Feedback

- Native Web Audio API synthesis without external audio files (`soundEffects.ts`).
- Subtle mechanical key clicks on button presses and tab switches.
- Solenoid shutter audio cue when collapsing or maximizing windows.
- Persistent mute toggle in the navigation header.