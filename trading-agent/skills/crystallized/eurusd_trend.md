---
name: crystallized_eurusd_trend
description: Institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-25T12:15:29.946462+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Empirical Track Record
- Reliability Status: High-Conviction Institutional Setup
- Sample Size: 2 verified winning trades
- Baseline Conviction: 88%

## Core Tactical Directives
- **Liquidity Mapping:** Identify and monitor the Asian session low as the primary liquidity pool prior to London or New York session execution.
- **Trigger Condition:** Execute buy orders strictly after a confirmed price sweep and rapid reclamation of the Asian low.
- **Trend Alignment:** Filter all sweep-based long entries to ensure they strictly align with the broader upward directional bias of the `EURUSD_TREND` regime.
- **Risk Parameters:** Place initial stop-loss orders immediately below the structural extreme of the sweep wick to invalidate failed setups efficiently.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14

## Invalidation Scenarios
- Invalidate immediately if an opposing higher-timeframe structural break (BOS/ChoCH) occurs prior to entry trigger.
- Cancel setup if Tier-1 macroeconomic volatility event occurs within 30 minutes before or after entry window.
- Invalidate if price fails to generate immediate displacement following the initial liquidity sweep.
