---
name: crystallized_eurusd_trend
description: Crystallized institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-19T19:47:45.744721+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Core Tactical Directives
- Wait for a clear sweep of the Asian session low before executing any long (buy) entries in the trend direction.
- Confirm the buy entry with a localized market structure shift (MSS) or break of structure on lower timeframes immediately following the liquidity sweep.
- Restrict long executions to high-liquidity windows (London open or early New York session) that immediately follow the Asian range sweep.
- Anchor stop-losses strictly below the swept Asian low extreme to protect against false breakouts while targeting higher timeframe liquidity pools.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14
