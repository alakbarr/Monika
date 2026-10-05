---
name: crystallized_eurusd_trend
description: Playbook for EURUSD verified across 5 winning cycles.
symbol: EURUSD
win_count: 5
avg_confidence: 0.88
total_pnl_usd: 900.00
status: active
last_crystallized_at: 2026-10-05T01:40:13.260063+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 5 profitable trading resolutions.

## Empirical Track Record
- Reliability Status: Early-Stage Pattern (Low Sample Size)
- Sample Size: 5 verified winning trades
- Baseline Conviction: 88% (n=5)

## Core Tactical Directives
- <MagicMock name='mock.chat.completions.create().choices.__getitem__().message.content' id='3116466569296'>

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14

## Invalidation Scenarios
- Invalidate immediately if an opposing higher-timeframe structural break (BOS/ChoCH) occurs prior to entry trigger.
- Cancel setup if Tier-1 macroeconomic volatility event occurs within 30 minutes before or after entry window.
- Invalidate if price fails to generate immediate displacement following the initial liquidity sweep.
