---
name: smc-ict-playbook
description: "Stage 2 SMC/ICT institutional playbook, order blocks, FVG, and confluence."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [smc, ict, order_block, fvg, market_structure, liquidity, stage2, bos, choch, fair_value_gap, liquidity_sweep]
---

# SMC/ICT Playbook (smc_ict_playbook) — Stage 2 Per-Asset Analysis

> **Runtime Variable Resolution**: Placeholders like `{symbol}`, `{cot_code}`, `{effective_threshold}`, `{tool_order_guidance}` are dynamically populated at analysis runtime from the active execution cycle. When viewing raw documentation, default threshold is `7/14` (on the 0–20 rubric: 14 core + up to 6 bonus/synergy points).

## ABSOLUTE FIRST — TOOL CALL ORDER ENFORCEMENT

{tool_order_guidance}

## STEP 0: MANDATORY MARKET REGIME & SPATIAL DEALING RANGE CHECK
Evaluate market regime via D1 and H4 ADX, and inspect the 20-day D1 dealing range position $pos = (\text{Close} - \text{Low}_{20}) / (\text{High}_{20} - \text{Low}_{20})$:

- **Discount ($pos \le 0.35$)**: Institutional accumulation zone; favor `BUY` setups (or confirmed breakdown `SELL` when $pos \ge 0.15$ and `Tech == Macro == bearish`). Forbid `SELL` in extreme bottom ($pos < 0.15$) unless breaking below 20-day low.
- **Premium ($pos \ge 0.65$)**: Institutional distribution zone; favor `SELL` setups (or confirmed breakout `BUY` when $pos \le 0.85$ and `Tech == Macro == bullish`). Forbid `BUY` in extreme top ($pos > 0.85$) unless breaking above 20-day high.
- **Equilibrium ($0.35 < pos < 0.65$)**: Trend-continuation & FVG/OB retest zone. Market or limit execution is PERMITTED when `Technical == Macro` (Uncrowded Institutional Synergy) or strong structural confluence ($\ge 10$) and H4/H1 price structure aligns. Output `WAIT` in Equilibrium if `Technical` and `Macro` conflict or if ADX < 20 chop.

| Regime (D1 ADX) | Action Directive | Spatial & Synergy Requirement |
|:---|:---|:---|
| **ADX > 40 (Strong Trend)** | Threshold = `{effective_threshold}`. Trend-following preferred. Counter-trend setups require Engine 2. | Valid across Discount, Equilibrium (`Tech == Macro`), and Premium within $pos \le 0.85$ (BUY) / $pos \ge 0.15$ (SELL). |
| **ADX 25–40 (Trend)** | Threshold = `{effective_threshold}`. Prefer primary trend direction (+1 aligned bonus). | Valid in Discount/Premium or Equilibrium continuation (`Tech == Macro`, $0.15 \le pos \le 0.85$). |
| **ADX 20–25 (Moderate Trend)** | Threshold = `{effective_threshold}`. Uncrowded Institutional Synergy (`Tech == Macro != Sentiment`) or POI retest. | Valid at OB/FVG retest within $0.15 \le pos \le 0.85$ when `Tech == Macro`. |
| **ADX < 20 (Ranging / Chop)** | Threshold = `{effective_threshold} + 1`. Outer Discount ($pos \le 0.35$) or Premium ($pos \ge 0.65$) extremes only. | In Equilibrium ($0.35 < pos < 0.65$) with ADX < 20 chop $\rightarrow$ `WAIT`. |

*State explicitly in rationale*: `"D1 ADX={value}, regime={regime_label}, range_pos={pos:.2f}, threshold adjusted to {n}/14"`

## STEP 0.2: DUAL-ENGINE INSTITUTIONAL SETUP & SPECIALIST ANTI-CROWDING PROTOCOL
Before scoring, classify the setup and specialist synergy:

1. **Engine 1 (Institutional Synergy / Trend-Aligned / Neutral POI Retest)**:
   - *Condition*: `Technical == Macro` (`Uncrowded Institutional Synergy` when `Sentiment != Tech` is the highest-expectancy setup at `81.8%` 12h accuracy) or trade direction aligns with/is neutral to Stage 1 macro and D1/H4 structure.
   - *Specialist Anti-Crowding Rule*: Treat `Sentiment Specialist` as a non-blocking crowding/exhaustion gauge, NEVER as a primary directional blocker when retail positioning is moderate ($35\%\text{--}68\%$). Guard against **Crowded 3-of-3 Exhaustion** (`Tech == Macro == Sentiment` when price is already extended past Equilibrium: $pos > 0.55$ for `BUY` or $pos < 0.45$ for `SELL`).
   - *Criteria*: Reward-to-Risk $R:R \ge 1.50$ (intraday target $\approx 1.55\times\text{SL}$), spatial anti-chasing bounds $pos \le 0.85$ for `BUY` and $pos \ge 0.15$ for `SELL`. Liquidity sweep is an optional bonus (+2), NOT mandatory.
2. **Engine 2 (Contra-Macro Liquidity Sweep / Turtle Soup)**:
   - *Condition*: Trade direction opposes strong Stage 1 macro ($conf \ge 0.55$).
   - *Requirement*: Touching a POI alone is INSUFFICIENT. MANDATORY: Confirmed liquidity sweep of recent key swing high/low (Turtle Soup) followed by displacement back above/below the swept level (MSS) in Discount ($pos \le 0.35$ for `BUY`) or Premium ($pos \ge 0.65$ for `SELL`). Downscale risk sizing to $0.65\times\text{--}0.75\times$.

## STEP 0.5: ZERO-ARITHMETIC BRACKET ADOPTION (`adopted_bracket`) & INTRADAY LEVELS
- **Zero-Arithmetic Bracket Adoption**: When calling `submit_asset_analysis` for `BUY` or `SELL`, pass `adopted_bracket="LONG_OPTION_A"` (for `BUY`) or `adopted_bracket="SHORT_OPTION_B"` (for `SELL`) from the pre-computed `DETERMINISTIC INVARIANT ENGINE` block so verified `entry_condition`, `stop_loss`, and `take_profit` are populated automatically without mental floating-point arithmetic errors.
- If `entry_allowed == False` (daily range exhausted) $\rightarrow$ Submit `WAIT`.

## MANDATORY CONFLUENCE SCORECARD FORMAT
Output confluence assessment before calling `submit_asset_analysis`. Choose either **REGIME A (PULLBACK / ZONE RETEST)** or **REGIME B (BREAKOUT / MOMENTUM EXPANSION)**:

```text
CONFLUENCE SCORECARD FOR {symbol}:
SETUP_TYPE: [PULLBACK_RETEST / BREAKOUT_EXPANSION]
EXECUTION_ENGINE: [ENGINE_1_POI_RETEST / ENGINE_2_LIQUIDITY_SWEEP]

--- CORE STRUCTURAL & MACRO FACTORS ---
[ ] F1_FUNDAMENTAL_BIAS: Macro brief supports {BUY/SELL}? YES(+2)/NO(0); Strong Conviction: YES(+3); Contra-Macro Setup (opposes Stage 1 bias when confidence >= 0.55): FORCED_PENALTY(-3) unless Engine 2 confirmed sweep exists = __
[ ] F2_DXY_CONFIRMS: DXY momentum confirms direction? YES(+1)/NO(0) = __
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

--- QUANT ALPHA, SYNERGY & EXECUTION BONUSES (0 to +6, Total Scale 0-20) ---
[ ] UNCROWDED_SYNERGY_BONUS: Technical == Macro with Sentiment uncrowded? YES(+2)/NO(0) = __
[ ] SWEEP_CONFIRMED: get_liquidity_sweep_context confirms structure? YES(+2)/NO(0) = __
[ ] QUANT_STRATEGY_EDGE: StrategyRegistry confirms alpha signal? YES(+1)/NO(0) = __
[ ] RR_RATIO_BONUS: Reward-to-Risk >= min_rr_ratio? YES(+1)/NO(0) = __
[ ] ADR_TARGET_BONUS: TP inside 50-80% ADR band? YES(+1)/NO(0) = __

SESSION MODIFIER: NY-London Overlap (13:00-16:00 UTC)? +1. Off-peak (22:00-00:00 UTC)? 0.
REGIME MODIFIER: ADX < 20 (ranging)? +1 to threshold. ADX > 40? -1 to threshold.

TOTAL CONFLUENCE SCORE: __ / 20 (Base Score + Synergy/Quant Bonuses + Session Modifier)
EFFECTIVE THRESHOLD: __ / 14 (Standard 7 + Dynamic Adjustments)
DECISION: __ (BUY/SELL if Total Confluence >= Effective Threshold within valid Spatial & Synergy bounds [pos <= 0.85 BUY, pos >= 0.15 SELL] using adopted_bracket="LONG_OPTION_A" or "SHORT_OPTION_B"; WAIT if sub-threshold, Tech != Macro conflict in Equilibrium, or ADX < 20 chop)
```

`confluence_factors` IDs: `"fundamental_bias"`, `"dxy_confirms"`, `"d1_trend"`, `"rsi_neutral"`, `"near_fvg"`, `"near_order_block"`, `"in_ote_zone"`, `"near_sr_zone"`, `"breakout_expansion"`, `"volume_expansion"`, `"trend_continuation"`, `"momentum_expansion"`, `"cot_aligned"`, `"vix_ok"`, `"post_event_entry"`, `"session_prime"`, `"liquidity_sweep_confirmed"`, `"microstructure_ok"`, `"historical_pattern_consensus"`, `"quant_strategy_edge"`, `"rr_ratio_bonus"`, `"adr_target_bonus"`.

## AUTOMATED SERVER-SIDE RISK ENFORCEMENT RULES
1. **ATR Missing**: BUY/SELL rejected.
2. **Stale H4 Indicators (> 5h)**: BUY/SELL rejected.
3. **Reward-to-Risk < 1.50**: Submission rejected. Adopt `adopted_bracket="LONG_OPTION_A"` or `"SHORT_OPTION_B"` for pre-verified intraday geometry ($R:R \approx 1.55$).
4. **Confluence Score < `{effective_threshold}` for BUY/SELL**: Submission rejected.
5. **Priced-In Score $\ge 8$**: Prohibit trend-following market chase in direction of priced-in narrative. Stance is `WAIT` for pullback or re-evaluation at extreme structural discount/premium.
6. **Contra-Macro Setup Adjudication**: When trading against Stage 1 macro ($conf \ge 0.55$), verify Engine 2 (Liquidity Sweep confirmed) and document structural invalidation in `specialist_adjudication` or rationale. High-confluence setups will be automatically routed to the Dialectical Debate Council for investment adjudication.

## Decision Thresholds & Intraday Range Rules
- **Take Profit Target Band**: 50%–80% of 5-day ADR (or $\le 1.65\times\text{effective SL max}$), placed at a verified structural target ($R:R \ge 1.50$, target $\approx 1.55\times\text{SL}$).
- **Stop Loss Sizing & Placement**:
  - SL MUST be anchored to verified structural invalidation (swing high/low, order block boundary) or adopted directly via `adopted_bracket="LONG_OPTION_A"` / `"SHORT_OPTION_B"`.
  - SL Floor: $\ge 1.0\times\text{ ATR}(14, \text{H4})$ for Forex ($\ge 1.2\times\text{ ATR}(14, \text{H4})$ for Gold/Crypto/Oil) to prevent spread or micro-noise stop-outs.
  - SL Ceiling: Harmonized adaptive ceiling $\le \max(\text{ADR cap}, 1.35\times\text{ATR}(14, \text{H4}))$. Never squeeze SL smaller than the H4 ATR noise floor.
- **Room Remaining**: `room_remaining_pct < 15%` $\rightarrow$ Submit `WAIT` (insufficient range left for the session).

## CRITICAL: Anti-Over-Conservative Directive

**WAIT is NOT the safe default. Excessive WAIT on qualified setups is a system failure.**

Before defaulting to WAIT, complete this Active Opportunity Scan:
1. **Uncrowded Institutional Synergy (`Tech == Macro != Sentiment`)**: Do Technical and Macro specialists agree while Sentiment is uncrowded (neutral or contrarian)?
2. **Spatial & Structural Zone**: Is price in Discount ($pos \le 0.35$ for BUY), Premium ($pos \ge 0.65$ for SELL), or Equilibrium continuation ($0.35 < pos < 0.65$ with `Tech == Macro` and H4/H1 alignment), within anti-chasing bounds ($pos \le 0.85$ BUY, $pos \ge 0.15$ SELL)?
3. **Directional Alignment**: Does D1/H4 trend or Order Block/FVG structure support the entry direction?
4. **Safety Filter**: Is VIX $< 30.0$ AND no high-impact economic news within 15 minutes?
5. **Zero-Arithmetic Execution**: Select `adopted_bracket="LONG_OPTION_A"` (for BUY) or `adopted_bracket="SHORT_OPTION_B"` (for SELL) from the pre-computed invariant engine.

**If $\ge 3/5$ criteria are YES and `Tech == Macro` within valid spatial bounds ($0.15 \le pos \le 0.85$) $\rightarrow$ An active institutional setup exists. Score and submit BUY/SELL decisively using `adopted_bracket` if confluence $\ge$ threshold.**
