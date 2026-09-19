---
name: crystallized_eurusd_trend
description: Crystallized institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-19T19:02:47.048537+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Core Tactical Directives
- Prioritize long entries exclusively after a verified sweep of the Asian session low during established EURUSD_TREND regimes.
- Require structural price acceptance back above the Asian low level following the sweep before triggering buy orders.
- Anchor stop-losses strictly below the extreme low of the sweep wick to protect against volatility expansion and false breakouts.
- Align the timing of the Asian low sweep setup with the London session open to capitalize on peak intraday trend momentum.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14
