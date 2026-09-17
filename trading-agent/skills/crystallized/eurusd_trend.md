---
name: crystallized_eurusd_trend
description: Crystallized institutional playbook for EURUSD verified across 2 winning cycles.
symbol: EURUSD
win_count: 2
avg_confidence: 0.88
total_pnl_usd: 360.00
status: active
last_crystallized_at: 2026-09-17T01:21:46.355527+00:00
---

# Crystallized Strategy: EURUSD (EURUSD_TREND)

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on 2 profitable trading resolutions.

## Core Tactical Directives
- Execute buy entries strictly after a liquidity sweep of the Asian session low.
- Confirm the post-sweep bullish reversal with a lower-timeframe market structure shift (MSS) that aligns with the broader `EURUSD_TREND`.
- Place stop-losses immediately below the swept Asian low extreme to invalidate failed sweep setups.
- Target opposing liquidity pools, such as previous session highs or key structural resistance, for profit extraction.

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14
