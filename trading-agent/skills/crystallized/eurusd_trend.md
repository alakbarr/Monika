---
name: crystallized_eurusd_trend
description: Crystallized institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-19T20:37:49.752696+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Core Tactical Directives
- Execute long entries exclusively after a verified sweep of the Asian session low.
- Require an immediate price reclaim or structural shift back inside the Asian range following the sweep to confirm institutional participation.
- Filter all Asian low sweep buy signals to strictly align with the prevailing higher-timeframe 'EURUSD_TREND' direction.
- Place stop-loss orders strictly beneath the extreme wick of the swept Asian low to invalidate failed liquidity grabs.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14
