---
name: crystallized_eurusd_trend
description: Institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-27T00:48:48.484147+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Empirical Track Record
- Reliability Status: High-Conviction Institutional Setup
- Sample Size: 2 verified winning trades
- Baseline Conviction: 88%

## Core Tactical Directives
- Map and monitor the Asian session price range to identify the daily Asian low as the primary liquidity pool for potential long setups.
- Patiently wait for a sweep or stop-hunt below the Asian low during the London open session before executing buy orders.
- Require a lower-timeframe market structure shift (MSS) or structural reclaim of the Asian low level as strict confirmation before entry.
- Align all long executions with the broader `EURUSD_TREND` bias, setting stop losses below the swept low and targeting continuation levels.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14

## Invalidation Scenarios
- Invalidate immediately if an opposing higher-timeframe structural break (BOS/ChoCH) occurs prior to entry trigger.
- Cancel setup if Tier-1 macroeconomic volatility event occurs within 30 minutes before or after entry window.
- Invalidate if price fails to generate immediate displacement following the initial liquidity sweep.
