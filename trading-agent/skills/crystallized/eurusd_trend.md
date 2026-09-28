---
name: crystallized_eurusd_trend
description: Institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-28T18:43:24.356901+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Empirical Track Record
- Reliability Status: High-Conviction Institutional Setup
- Sample Size: 2 verified winning trades
- Baseline Conviction: 88%

## Core Tactical Directives
- Execute long entries exclusively after a confirmed sweep and rejection of the Asian session low.
- Validate that the Asian low sweep aligns with the dominant higher-timeframe bullish bias of the 'EURUSD_TREND' regime.
- Require a localized market structure shift (MSS) or reclaim of the swept level on lower timeframes before order execution.
- Restrict entry timing strictly to the London open session window immediately following the liquidity sweep event.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14

## Invalidation Scenarios
- Invalidate immediately if an opposing higher-timeframe structural break (BOS/ChoCH) occurs prior to entry trigger.
- Cancel setup if Tier-1 macroeconomic volatility event occurs within 30 minutes before or after entry window.
- Invalidate if price fails to generate immediate displacement following the initial liquidity sweep.
