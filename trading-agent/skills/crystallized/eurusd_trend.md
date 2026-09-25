---
name: crystallized_eurusd_trend
description: Institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-25T12:09:21.483088+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Empirical Track Record
- Reliability Status: High-Conviction Institutional Setup
- Sample Size: 2 verified winning trades
- Baseline Conviction: 88%

## Core Tactical Directives
- **Identify Liquidity Targets:** Mark the Asian session low as the primary liquidity pool to monitor for potential long entries during bullish trend regimes.
- **Require Sweep & Rejection:** Wait for a definitive price sweep below the Asian low followed by an immediate reclaim to confirm institutional accumulation before entering.
- **Align with Macro Trend:** Ensure the liquidity sweep occurs in the direction of the dominant higher-timeframe `EURUSD_TREND` to filter out counter-trend traps.
- **Execute and Protect:** Enter long upon the structural confirmation/reclaim of the Asian low, placing stop-losses strictly below the sweep extreme to invalidate failed setups.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14

## Invalidation Scenarios
- Invalidate immediately if an opposing higher-timeframe structural break (BOS/ChoCH) occurs prior to entry trigger.
- Cancel setup if Tier-1 macroeconomic volatility event occurs within 30 minutes before or after entry window.
- Invalidate if price fails to generate immediate displacement following the initial liquidity sweep.
