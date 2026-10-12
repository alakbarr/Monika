---
name: user-chart-collaborative-analysis
description: "Interactive chart analysis: MT5 chart objects, overlays, and S/R levels."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [interactive_charting, mt5_chart_objects, collaborative_analysis, ema_cross, user_levels, top_down_synthesis]
---

# User-Chart Collaborative Analysis Playbook

> **Mission**: Seamlessly bridge the user's manual MT5 technical charting (user-drawn Support/Resistance horizontal lines, trendlines, Fibonacci retracements, and EMA 50/100/200 overlays) with Monika's institutional analytical engine (Macro fundamentals, positioning sentiment, and Smart Money Concepts).

---

## 1. Collaborative Ingestion Workflow (Addressing Q151)

When the user states that they have charted an asset in MT5:

### Step 1: Capture User Chart Elements
1. Call `get_mt5_chart_objects(symbol)`:
   - Reads user-drawn horizontal lines (S/R), trendlines, Fibonacci levels, and technical indicator handles from MT5 chart files.
2. Call `capture_mt5_chart_screenshot(symbol)`:
   - Captures high-resolution visual screenshot of the user's active MT5 chart window.

### Step 2: Top-Down Multi-Layer Synthesis
Synthesize the analysis in 4 strict consecutive layers:

1. **Layer 1: Macro & Fundamental Backdrop**:
   - Query central bank rate expectations, sovereign yield spreads, and macroeconomic drivers (e.g. Fed policy, US real yields for Gold, DXY trend).
   - Establish whether fundamental macro bias is Bullish, Bearish, or Neutral.
2. **Layer 2: Market Sentiment & Positioning**:
   - Check CFTC COT institutional positioning (Asset Manager vs Leveraged Funds net bias).
   - Check retail positioning (long/short retail sentiment contrarian indicator) and volatility regime (VIX / GVZ).
3. **Layer 3: Technical & User Chart Object Validation**:
   - **EMA 50 / 100 / 200 Analysis**:
     - Trend alignment: Price above EMA 50 > 100 > 200 = Bullish stack. Price below = Bearish stack.
     - Dynamic Support/Resistance: Is price reacting to the EMA 50 or EMA 200 pullbacks?
   - **User Support / Resistance & Fibonacci Levels**:
     - Cross-examine user's S/R lines against Monika's institutional Order Blocks and Fair Value Gaps.
     - Validate whether user's Fibonacci retracement level coincides with institutional Optimal Trade Entry (OTE 0.618 - 0.786).
     - State explicitly: *"Level support user di X terkonfirmasi bertepatan dengan Bullish Order Block H4 Monika di X."*
4. **Layer 4: Concrete Strategic Recommendation**:
   - Bias: (e.g. Bullish Continuation / Defensive Wait).
   - Optimal Entry Zone: Specific price band combining user level + institutional POI.
   - Stop Loss (SL): Invalidation point below structural swing/EMA 200.
   - Take Profit (TP): Target aligned with user resistance or liquidity pool.
   - Risk:Reward Ratio and maximum recommended lot sizing.

---

## 2. Interaction Protocol (Sparring Partner Persona)

- **Acknowledge and Validate**: Never dismiss user-drawn lines. Evaluate them critically and objectively. If a user level is high quality, praise the confluence. If a user level is vulnerable to a liquidity sweep, explain why institutional algorithms often target stops resting just beyond that level.
- **Synthesize, Don't Confuse**: Provide clear, definitive guidance so the user can make an informed, confident execution decision.
