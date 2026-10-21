---
name: smc-ict-playbook
description: "Stage 2 SMC/ICT institutional playbook, order blocks, FVG, and confluence."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [smc, ict, order_block, fvg, market_structure, liquidity, stage2, bos, choch, fair_value_gap, liquidity_sweep]
---

# SMC/ICT Playbook (smc_ict_playbook) — Stage 2 Per-Asset Analysis

> **Runtime Variable Resolution**: Placeholders like `{symbol}`, `{cot_code}`, `{effective_threshold}`, `{tool_order_guidance}` are dynamically populated at analysis runtime from the active execution cycle. When viewing raw documentation, default threshold is `7/14`.

## ABSOLUTE FIRST — TOOL CALL ORDER ENFORCEMENT

{tool_order_guidance}

## STEP 0: MANDATORY MARKET REGIME CHECK
Evaluate market regime via D1 and H4 ADX prior to scoring:

| Regime (D1 ADX) | Action Directive |
|:---|:---|
| **ADX > 40 (Strong Trend)** | Threshold = `{effective_threshold}`. Trend-following ONLY. Counter-trend setups penalized (-3). |
| **ADX 25–40 (Trend)** | Threshold = `{effective_threshold}`. Prefer primary trend direction (+1 aligned bonus). |
| **ADX 15–25 (Weak Trend)** | Threshold = `{effective_threshold}`. Mean-reversion valid at major S/R extremes. |
| **ADX < 15 (Ranging / Chop)** | Threshold = `{effective_threshold} + 1`. Limit orders at confirmed range extremes only. |

*State explicitly in rationale*: `"D1 ADX={value}, regime={regime_label}, threshold adjusted to {n}/14"`

## STEP 0.5: MANDATORY STRUCTURAL TP/SL LOOKUP
Call `get_optimal_intraday_levels(symbol, direction, entry_price)` before finalizing SL/TP.
- Take Profit MUST align within $\approx 0.4\times$ ATR of a genuine structural level inside the 50%–80% ADR band.
- If `entry_allowed == False` (daily range exhausted) $\rightarrow$ Submit `WAIT`.

## MANDATORY CONFLUENCE SCORECARD FORMAT
Output confluence assessment in EXACT format BEFORE calling `submit_asset_analysis`.
Choose either **REGIME A (PULLBACK / ZONE RETEST)** or **REGIME B (BREAKOUT / MOMENTUM EXPANSION)** depending on market context:

```text
CONFLUENCE SCORECARD FOR {SYMBOL}:
SETUP_TYPE: [PULLBACK_RETEST / BREAKOUT_EXPANSION]

--- CORE STRUCTURAL & MACRO FACTORS ---
[ ] F1_FUNDAMENTAL_BIAS: Macro brief supports {BUY/SELL}? YES(+2)/NO(0); Strong Conviction: YES(+3); Contra-Macro Setup (opposes Stage 1 bias when confidence >= 0.55): FORCED_PENALTY(-3) unless price breached Stage 1 invalidation level = __
[ ] F2_DXY_CONFIRMS: DXY/Contagion confirms direction? YES(+1)/NO(0) = __
[ ] F3_D1_TREND: D1 & H4 trend aligns with entry? YES(+2)/NO(0) = __
[ ] F4_RSI_NEUTRAL_OR_MOMENTUM: RSI confirmed (not overbought/oversold for retest, or strong momentum 45-65 for breakout)? YES(+1)/NO(0) = __

--- REGIME A: ZONE RETEST / SMC PULLBACK FACTORS (If entering on pullback) ---
[ ] F5_FVG_PROXIMITY: Entry within 0.5x ATR of unfilled H1/H4 FVG? YES(+2)/NO(0) = __
[ ] F6_ORDER_BLOCK: Unmitigated H1/H4 OB within 0.5x ATR of entry? YES(+2)/NO(0) = __
[ ] F7_OTE_ZONE: Entry between Fib 0.618-0.786? YES(+1)/NO(0) = __
[ ] F8_SR_ZONE: Entry at D1 or H4/H1 S/R zone (within tolerance)? YES(+1)/NO(0) = __

--- REGIME B: BREAKOUT / MOMENTUM EXPANSION FACTORS (If entering on breakout) ---
[ ] F5_BREAKOUT_EXPANSION: Breakout of Donchian channel or key structural high/low? YES(+2)/NO(0) = __
[ ] F6_VOLUME_EXPANSION: Relative volume RVOL >= 1.2 or volume spike confirmed? YES(+2)/NO(0) = __
[ ] F7_TREND_CONTINUATION: ADX > 25 and clean continuation impulse formed? YES(+2)/NO(0) = __
[ ] F8_MOMENTUM_EXPANSION: Candle closing decisively outside recent range? YES(+1)/NO(0) = __

--- SHARED CONTEXT & RISK FILTERS ---
[ ] F9_COT_ALIGNED: COT / Positioning not extreme against trade direction? YES(+1)/NO(0) = __
[ ] F10_VIX_OK: VIX < 20? YES(+1)/NO(0); VIX >= 30: BLOCKING_ISSUE = __
[ ] F11_MICROSTRUCTURE_OK: VPIN < 0.50 or Kyle Lambda low? YES(+1)/NO(0); Toxic VPIN > 0.70: FORCED_SUBTRACT(-1) = __
[ ] F12_PATTERN_CONSENSUS: Multi-timeframe pattern consensus or alpha screen aligns (win rate >= 60%)? YES(+1)/NO(0) = __

BASE STRUCTURAL SCORE: __ / 14

--- QUANT ALPHA & EXECUTION BONUSES (0 to +5) ---
[ ] SWEEP_CONFIRMED: get_liquidity_sweep_context confirms structure? YES(+2)/NO(0) = __
[ ] QUANT_STRATEGY_EDGE: StrategyRegistry confirms alpha signal? YES(+1)/NO(0) = __
[ ] RR_RATIO_BONUS: Reward-to-Risk >= min_rr_ratio? YES(+1)/NO(0) = __
[ ] ADR_TARGET_BONUS: TP inside 50-80% ADR band? YES(+1)/NO(0) = __

SESSION MODIFIER: NY-London Overlap (13:00-16:00 UTC)? +1. Off-peak (22:00-00:00 UTC)? 0.
REGIME MODIFIER: ADX < 15 (ranging)? +1 to threshold. ADX > 40? -1 to threshold.

TOTAL CONFLUENCE SCORE: __ (Base Score + Quant Bonuses + Session Modifier)
EFFECTIVE THRESHOLD: __ / 14 (Standard 7 + Dynamic Adjustments)
DECISION: __ (BUY/SELL if Total Confluence >= Effective Threshold, WAIT if sub-threshold, AVOID if structural invalidation)
```

`confluence_factors` IDs: `"fundamental_bias"`, `"dxy_confirms"`, `"d1_trend"`, `"rsi_neutral"`, `"near_fvg"`, `"near_order_block"`, `"in_ote_zone"`, `"near_sr_zone"`, `"breakout_expansion"`, `"volume_expansion"`, `"trend_continuation"`, `"momentum_expansion"`, `"cot_aligned"`, `"vix_ok"`, `"post_event_entry"`, `"session_prime"`, `"liquidity_sweep_confirmed"`, `"microstructure_ok"`, `"historical_pattern_consensus"`, `"quant_strategy_edge"`, `"rr_ratio_bonus"`, `"adr_target_bonus"`.

## AUTOMATED SERVER-SIDE RISK ENFORCEMENT RULES
1. **ATR Missing**: BUY/SELL rejected.
2. **Stale H4 Indicators (> 5h)**: BUY/SELL rejected.
3. **Reward-to-Risk < 1.30**: Submission rejected.
4. **Confluence Score < `{effective_threshold}` for BUY/SELL**: Submission rejected.
5. **Priced-In Score $\ge 8$**: Mandatory `WAIT`. Hard block in RiskGate.
6. **Contra-Macro Setup without Adjudication**: When currency confidence $\ge 0.70$, submitting BUY/SELL directly opposing the macro brief without explicit `specialist_adjudication` (with conflict_detected=true, resolution_path in ('override_macro', 'cancel_setup', 'hedged_entry', 'scale_out'), and $\ge 40$ chars justification citing structural level breach) is **HARD REJECTED** by the server.

## Decision Thresholds & Intraday Range Rules
- **Take Profit Target Band**: 40%–85% of 5-day ADR (via `get_daily_range_context`), placed at a verified structural target.
- **Stop Loss Sizing & Placement**:
  - SL MUST be anchored to verified structural invalidation (swing high/low, order block boundary) with a 0.15–0.25x ATR buffer.
  - SL Floor: $\ge 0.5\times\text{ ATR}(14, \text{H4})$ to ensure the position is not stopped out by spread or micro-noise.
  - SL Ceiling: Adaptive ceiling $\le \max(0.40\times\text{ADR}, 1.25\times\text{ATR}(14, \text{H4}))$. Never squeeze SL smaller than structural protection.
- **Room Remaining**: `room_remaining_pct < 15%` $\rightarrow$ Submit `WAIT` (insufficient range left for the session).

## CRITICAL: Anti-Over-Conservative Directive

**WAIT is NOT the safe default. Excessive WAIT on qualified setups is a system failure.**

Before defaulting to WAIT, complete this Active Opportunity Scan:
1. **D1 Structure**: Is the macro trend clear? (ADX > 20, price aligned with moving averages)
2. **H4 Zone**: Is price resting inside a valid unmitigated Order Block, FVG, or S/R zone?
3. **Directional Alignment**: Does D1 trend match the proposed H4 entry direction? (Counter-trend H4 pullbacks into D1 trend support/resistance are prime institutional discount entries, NOT conflicts).
4. **Safety Filter**: Is VIX $< 30.0$ AND no high-impact economic news within 15 minutes?
5. **Regime B Momentum Expansion**: If a confirmed Donchian or structural breakout occurs with volume (RVOL $\ge$ 1.2), do NOT reject on lack of older FVG proximity — enter on the expansion impulse with SL behind the breakout base.

**If $\ge 3/5$ criteria are YES $\rightarrow$ An active institutional setup exists. Score and submit BUY/SELL decisively if confluence $\ge$ threshold.**
