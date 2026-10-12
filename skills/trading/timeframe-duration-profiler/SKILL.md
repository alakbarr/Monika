---
name: timeframe-duration-profiler
description: "Cross-timeframe alignment, execution horizon, and holding duration."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [timeframe, scalping, day_trading, swing_trading, holding_duration, multi_timeframe, mtf]
---

# Timeframe & Trade Duration Profiling Playbook

> **Core Principle**: Strategy rules, stop distances, and trade management must strictly correspond to the chosen operational timeframe horizon. Mixing scalping stops with swing targets (or vice versa) is the leading cause of retail failure.

---

## 1. Institutional Timeframe Profiles

| Horizon Profile | Anchor HTF | Setup MTF | Trigger LTF | Typical Holding Period | Target ATR Multiple | Stop Loss Sizing |
|:---|:---|:---|:---|:---|:---|:---|
| **Scalping** | H1 / H4 | M15 | M1 / M5 | 15 mins – 2 hours | $0.2 - 0.5 \times$ D1 ATR (10–25 pips) | Tight swing high/low (5–12 pips) |
| **Day Trading** | D1 | H4 / H1 | M15 | 2 hours – 12 hours | $0.5 - 1.0 \times$ D1 ATR (35–80 pips) | Structural Order Block / FVG (15–30 pips) |
| **Swing Trading** | W1 | D1 | H4 | 2 days – 2 weeks | $1.5 - 3.5 \times$ D1 ATR (100–350 pips) | Major D1/W1 Swing Point (50–120 pips) |
| **Macro Position** | MN1 | W1 | D1 | 2 weeks – 3 months | $4.0 - 10.0 \times$ D1 ATR (400–1000+ pips) | Macro regime invalidation |

---

## 2. Multi-Timeframe Alignment Protocol (Top-Down)

1. **Step 1: Anchor Timeframe (Macro & HTF Structure)**:
   - Identify primary directional flow (Bullish/Bearish BOS) on Anchor TF.
   - Never take trades directly counter to Anchor TF unless HTF has tapped a major liquidity pool and created a confirmed CHoCH.
2. **Step 2: Setup Timeframe (POI Identification)**:
   - Identify unmitigated Order Blocks, Fair Value Gaps, or Discount/Premium OTE zones ($0.618 - 0.786$).
3. **Step 3: Trigger Timeframe (Execution Confirmation)**:
   - Wait for LTF liquidity sweep + displacement (MSS) into the HTF POI.
   - Set SL just beyond the LTF displacement origin.
