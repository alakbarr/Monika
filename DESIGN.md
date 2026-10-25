---
name: monika-design-system
description: Authoritative design specification for the Monika Autonomous Quantitative Trading Desk featuring the original Monika Swiss Editorial & Unboxed Sculptural architecture. Reference whenever editing UI components, layouts, or stylesheets. Interactive visual specification located at docs/design_system.html.
---

# DESIGN.md — Monika Design System Specification (v4.0)
### Original Monika Visual & Typographic Grammar · Swiss Liquid Glass & Editorial Precision · Dual Mode

> "Where autonomous quantitative rigor meets optical crystal clarity — zero AI-slop neon gradients, zero fail-open fallbacks, and 100% typographic and numerical truth."

> **Interactive Reference**: Open [`docs/design_system.html`](docs/design_system.html) in any browser to inspect the live interactive Light (`#FFFFFF`) Frosted Quartz and Dark (`#121316`) Smoked Obsidian Liquid Glass surface spectrum, specular rim lighting, typographic hierarchy, sculptural equity monument, and borderless ledger primitives.

---

## 1. Design Philosophy & Original Monika Identity

Monika establishes its own original **Swiss Liquid Glass & Editorial Precision** visual architecture engineered specifically for institutional quantitative trading and autonomous multi-agent reasoning:

1. **Three-Plane Optical Material Hierarchy (Swiss Liquid Glass)**:
   - **Plane 0 — Ambient Optical Canvas**: Subtle radial luminance pools (`--glass-ambient-canvas`) beneath the workspace provide depth for floating crystal surfaces to refract.
   - **Plane 1 — Machined Crystal Wells (`.liquid-glass-panel`, `.ledger-card`, `.cockpit-bar`)**: Translucent crystal surfaces (`--color-glass-surface`) with saturated optical blur (`backdrop-filter: blur(16px) saturate(175%)`), `1px solid var(--color-glass-border)`, and physical **Specular Rim Lighting** (`inset 0 1px 0 0 var(--color-glass-specular-top)`).
   - **Plane 2 — Floating Liquid Glass Chrome (`.liquid-glass-chrome`, `.floating-dock-bar`, modals & drawers)**: High-refraction Liquid Glass (`backdrop-filter: blur(24px) saturate(200%)`), dual-edge specular bevels, and SVG optical refraction (`#monika-liquid-refraction`).
2. **Sculptural Hero Equity Monument (Strict Fail-Closed Telemetry)**: Portfolio net liquidation value is rendered at `56px–64px` (`tabular-nums`) with muted cents (`.80`) and an interactive scrubbing equity curve. If verified account equity is unavailable, the monument fails closed (`UNVERIFIED`) and never displays fabricated fallback numbers.
3. **Achromatic Discipline (90% Achromatic Crystal, 10% Signal)**: Focus rings, active buttons, and chapter tabs use pure black/white inversion (`var(--color-ink)` / `var(--color-on-inverted)`). Chromatic color is strictly reserved for financial truth and safety state: Emerald Gain (`--color-gain`), Crimson Loss/Halt (`--color-loss`), and Amber Paper/Warning (`--color-warn`).
4. **Tri-Font Editorial System**:
   - `Instrument Serif` (`--font-editorial`): Chapter titles, narrative synthesis headlines, and Bull/Bear dialectic pull-quotes.
   - `Plus Jakarta Sans` (`--font-sans`): UI labels, structural headers, and readable prose.
   - `JetBrains Mono` (`--font-mono`): Tabular financial figures (`tabular-nums`), tickets, latencies, and SHA-256 hashes.

---

## 2. Color System (WCAG 2.2 AA Verified)

### 2.1 Light Mode — Clean Pure Alabaster (`:root[data-theme="light"]`)

| Token | Hex | Contrast vs `#FFFFFF` | Role |
|---|---|---|---|
| `--color-canvas` | `#FFFFFF` | — | Open architectural canvas |
| `--color-well` | `#F7F8FA` | — | Subtle secondary well / hover row |
| `--color-ink` | `#111215` | `18.8:1` | Primary carbon ink & active inversion |
| `--color-ink-secondary` | `#525660` | `7.3:1` | Secondary labels & prose |
| `--color-ink-muted` | `#686D78` | `5.1:1` | Captions, kickers, & timestamps |
| `--color-rule` | `#E5E7EB` | — | 1px structural hairline divider |
| `--color-gain` | `#0D7A52` | `5.4:1` | Verified profit, long/buy, nominal status |
| `--color-loss` | `#C82838` | `5.6:1` | Loss, short/sell, circuit breaker halt |
| `--color-warn` | `#9A5B00` | `5.3:1` | Paper trading mode, caution thresholds |

### 2.2 Dark Mode — Neutral Graphite Obsidian (`:root[data-theme="dark"]`)

| Token | Hex | Contrast vs `#121316` | Role |
|---|---|---|---|
| `--color-canvas` | `#121316` | — | Neutral graphite obsidian canvas |
| `--color-well` | `#17191D` | — | Subtle recessed well / hover row |
| `--color-ink` | `#F3F4F6` | `16.4:1` | Primary alabaster ink |
| `--color-ink-secondary` | `#9CA3AF` | `7.4:1` | Secondary labels & prose |
| `--color-ink-muted` | `#848B98` | `5.2:1` | Captions, kickers, & timestamps |
| `--color-rule` | `#23262D` | — | 1px structural hairline divider |
| `--color-gain` | `#10B981` | `7.6:1` | Verified profit, long/buy, nominal status |
| `--color-loss` | `#F43F5E` | `5.1:1` | Loss, short/sell, circuit breaker halt |
| `--color-warn` | `#F59E0B` | `8.9:1` | Paper trading mode, caution thresholds |

---

## 3. Spatial Architecture & 5 Editorial Chapters

1. **L0 Whisper Horizon Safety Bar (`48px` top)**:
   - Displays Monika emblem, unmistakable `PAPER` / `LIVE` mode badge with Graduation Gate progress (`32/50`), MT5/DB/WS telemetry dots, UTC clock, Theme switch, `+ NEW ORDER` drawer trigger, and guarded `#emergency-halt-btn` (`EMERGENCY HALT` / `RESUME TRADING`).
2. **Open Canvas Chapters (Navigated via Unified Bottom Floating Dock)**:
   - **I. Capital**: Sculptural 64px Equity Monument, interactive scrubbing equity curve, Multi-Asset SMC Candlestick chart, 6-cell continuous telemetry ribbon, and Asymmetric 7:5 Position Ledger + Editorial Investment Dispatch.
   - **II. Journal**: Bull vs Bear Dialectics, Market Dispatches & Macro Brief, Interactive 5-Stage LangGraph DAG + Live Cycle Steering, Autonomous Memory Vault (with Playbook rollback), and Crystallized Skills.
   - **III. Risk**: Mechanical Fortress & Circuit Breakers, Swiss linear exposure gauges, 8-Factor Risk Scorecard, Correlation Matrix, 50-Trade Graduation Gate, and Rolling Expectancy (`7d`/`14d`/`30d`).
   - **IV. Lab**: Point-in-Time Historical Backtest Engine, Multi-Model LLM Benchmark Lab, and Token Consumption & Cost Ledger.
   - **V. Atelier**: Configuration & YAML Diff Editor, OpenTelemetry Trace Waterfall & SHA-256 Lineage, Plugin Marketplace, Host Diagnostics, and PTY OS Terminal + Session Transcripts.
3. **Unified Bottom Floating Dock & Expandable Agent Dialogue Sheet**:
   - Persistent bottom dock switching Chapters `I–V` (`1–5` keys) and expanding the live `/ws/agent-chat` dialogue sheet (`Ask or Steer Monika… ⌘K`).
