---
name: monika-design-system
description: Authoritative design specification for the Monika Autonomous Quantitative Trading Desk featuring the original Monika Swiss Editorial & Unboxed Sculptural architecture. Reference whenever editing UI components, layouts, or stylesheets. Interactive visual specification located at docs/design_system.html.
---

# DESIGN.md — Monika Design System Specification (v3.0)
### Original Monika Visual & Typographic Grammar · Swiss Editorial & Unboxed Sculptural · Dual Mode

> "Where autonomous quantitative rigor meets editorial calm — zero boxy cards, zero decorative noise, and 100% typographic and numerical truth."

> **Interactive Reference**: Open [`docs/design_system.html`](docs/design_system.html) in any browser to inspect the live interactive Light (`#FFFFFF`) and Dark (`#121316`) surface spectrum, typographic hierarchy, sculptural equity monument, and borderless ledger primitives.

---

## 1. Design Philosophy & Original Monika Identity

Monika establishes its own original **Swiss Editorial & Unboxed Sculptural** visual architecture engineered specifically for institutional quantitative trading and autonomous multi-agent reasoning:

1. **Unboxed Open Canvas (High Data-Ink Ratio)**: Data sits directly on the architectural canvas separated by exposed `1px solid var(--color-rule)` hairlines, generous whitespace, and subtle Swiss crosshair (`+`) intersections. Nested card containers, thick outer borders, and ornamental shadows are strictly prohibited.
2. **Sculptural Hero Equity Monument**: Portfolio net liquidation value is rendered at `64px` (`Plus Jakarta Sans` 700, `tabular-nums`) with muted cents (`.50`) and an interactive scrubbing equity curve that updates the monument and return delta live on cursor scrub.
3. **Achromatic Discipline (90% Achromatic, 10% Signal)**: Focus rings, active buttons, and chapter tabs use pure black/white inversion (`var(--color-ink)` / `var(--color-on-inverted)`). Chromatic color is strictly reserved for financial truth and safety state: Emerald Gain (`--color-gain`), Crimson Loss/Halt (`--color-loss`), and Amber Paper/Warning (`--color-warn`).
4. **Tri-Font Editorial System**:
   - `Instrument Serif` (`--font-editorial`): Chapter titles, narrative synthesis headlines, and Bull/Bear dialectic pull-quotes.
   - `Plus Jakarta Sans` (`--font-sans`): Sculptural equity monuments, UI labels, and readable prose.
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
