---
name: post-event-orderflow-absorption
description: "Framework for post-event orderflow absorption, sweeps, and repricing."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [news_trading, macro_events, orderflow, absorption, liquidity_sweep, cpi, nfp, fomc, stage2_execution]
---

# Post-Event Orderflow Absorption — Institutional Volatility Phases & Timing Rules

Institutional methodology for evaluating market behavior following Tier-1 macroeconomic data releases (US CPI, Core PCE, Non-Farm Payrolls, Central Bank Rate Decisions), distinguishing liquidity sweep traps from structural trend expansions.

---

## 1. Core Foundational Principle

Tier-1 economic releases do not produce instantaneous fair value pricing. Instead, they trigger a deterministic **Three-Phase Liquidity Cycle** executed by institutional high-frequency algorithms (HFAs) and market makers.

Entering trades prematurely during the initial news candle is retail gambling. Institutional execution requires observing **Orderflow Absorption** and price acceptance beyond the initial volatility range.

---

## 2. The Three Phases of Post-Event Volatility

```
[Event Released: t = 0]
      │
      ├── Phase 1: Knee-Jerk & Liquidity Sweep (0 - 15 min)
      │     • Spreads widen 2x to 4x.
      │     • High-frequency algorithms hunt stop-loss clusters above/below pre-event range.
      │     • MANDATE: Zero Market Orders. Absolute Execution Blackout.
      │
      ├── Phase 2: Institutional Absorption & Range Definition (15 - 60 min)
      │     • Establishes Event Anchor Range: [Event_High, Event_Low].
      │     • Real-money institutional flows deploy (pensions, asset managers, central bank dealers).
      │     • Check Acceptance vs. Rejection at range boundaries.
      │
      └── Phase 3: Structural Expansion vs. Mean-Reversion (1 - 4 hours)
            • Scenario A (Acceptance / Repricing): Price breaks and closes beyond Event Range ⟹ High-conviction trend continuation.
            • Scenario B (Rejection / Liquidity Sweep): Price sweeps extreme, forms H1 ChoCH/FVG back inside ⟹ Violent counter-trend reversal.
```

---

## 3. Absorption Evaluation Rules for Stage 2 SMC/ICT

1. **The 15-Minute Blackout Rule**:
   - Never execute BUY or SELL market orders within 15 minutes of a scheduled Tier-1 release (CPI, NFP, FOMC).
   - Allow the initial M15 candle to close to define the **Event Anchor Range** ($H_{event}, L_{event}$).

2. **Differentiating Institutional Repricing from Liquidity Traps**:
   - **Continuous Repricing (Trend Continuation)**:
     - Realized data deviates significantly from consensus ($Z\text{-score} > 1.5$).
     - Price breaks $H_{event}$ and forms consecutive M15/H1 closes above it, leaving unfilled bullish Fair Value Gaps (FVGs).
     - *Execution Directive*: Enter on the first retest of the M15/H1 FVG inside the upper 50% of the event expansion.
   - **Sell-The-News / Liquidity Sweep Rejection**:
     - Event was already largely priced in (Stage 1 `priced_in_score >= 6`).
     - Price spikes past a major multi-day swing high/low into an unmitigated higher-timeframe Order Block, but immediately prints long wicks and closes back inside the prior range.
     - *Execution Directive*: Treat as an institutional liquidity sweep. Look for market structure shift (ChoCH) on M15 in the opposite direction.

3. **Spread & Slippage Defense**:
   - Inspect broker spread relative to normal median before placing orders.
   - If current spread $> 1.5\times$ normal median, delay entry or enforce limit orders rather than market execution.
