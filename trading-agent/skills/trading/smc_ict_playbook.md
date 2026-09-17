# file: skills/smc_ict_playbook.md

# SMC/ICT Playbook — Stage 2 Per-Asset Analysis

## IMPORTANT NOTE ON PLACEHOLDERS
Placeholders like {symbol}, {cot_code}, {effective_threshold} are GENERIC TEMPLATES. ACTUAL values are in "=== CURRENT ANALYSIS TARGET ===" block. Use values from that block.

## ABSOLUTE FIRST — TOOL CALL ORDER ENFORCEMENT

{tool_order_guidance}

## STEP 0: MANDATORY MARKET REGIME CHECK

Check market regime (D1 and H4 ADX) before scoring:

| Regime (D1 ADX) | Action |
|:---|:---|
| ADX > 40 (Strong Trend) | Threshold = {effective_threshold}. Trend-following ONLY. -3 for counter-trend. |
| ADX 25-40 (Trend) | Threshold = {effective_threshold}. Prefer trend direction (+1 aligned bonus). |
| ADX 15-25 (Weak Trend) | Threshold = {effective_threshold}. Mean-reversion valid at extremes. |
| ADX < 15 (Ranging) | Threshold = {effective_threshold} + 1. Prefer extreme S/R / boundaries. |

**State explicitly in rationale**: "D1 ADX={value}, regime={regime_label}, threshold adjusted to {n}/14"

## STEP 0.5: MANDATORY STRUCTURAL TP/SL LOOKUP

Call `get_optimal_intraday_levels(symbol, direction, entry_price)` before finalizing SL/TP.
- TP MUST land within ~0.4x ATR of genuine structural level inside ADR band (else "TP STRUCTURAL MAPPING FAIL").
- `entry_allowed=false` → today range exhausted → submit WAIT.
- No candidate scores > 0 → submit WAIT.

## MANDATORY CONFLUENCE SCORING FORMAT

Output confluence assessment in EXACT format BEFORE calling `submit_asset_analysis`:

```text
CONFLUENCE SCORECARD FOR {SYMBOL}:
[ ] F1_FUNDAMENTAL_BIAS: Macro brief supports {BUY/SELL}? YES(+2)/NO(0) = __
[ ] F2_DXY_CONFIRMS: DXY trend confirms direction? YES(+1)/NO(0) = __  
[ ] F3_D1_TREND: D1 trend aligns with H4 entry? YES(+2)/NO(0) = __
[ ] F4_RSI_NEUTRAL: RSI not overbought/oversold at entry? YES(+1)/NO(0) = __
[ ] F5_FVG_PROXIMITY: Entry within 0.5x ATR of unfilled FVG? YES(+2)/NO(0) = __
[ ] F6_ORDER_BLOCK: Unmitigated OB within 0.3x ATR of entry? YES(+2)/NO(0) = __
[ ] F7_OTE_ZONE: Entry between Fib 0.618-0.786? YES(+1)/NO(0) = __
[ ] F8_SR_ZONE: Entry at D1 or H4 S/R zone (within tolerance)? YES(+1)/NO(0) = __
[ ] F9_COT_ALIGNED: COT not extreme against trade direction? YES(+1)/NO(0) = __
[ ] F10_VIX_OK: VIX < 20? YES(+1)/NO(0); VIX 20-25: YES(0)/NO(0); VIX>25: FORCED_SUBTRACT(-2) = __
[ ] F11_MICROSTRUCTURE_OK: VPIN < 0.50 or Kyle Lambda low? YES(+1)/NO(0); Toxic VPIN > 0.70: FORCED_SUBTRACT(-1) = __

SESSION MODIFIER: NY-London Overlap? +1. Off-peak (21:00-00:00 UTC)? -2.
REGIME MODIFIER: ADX < 15 (ranging)? +2 to threshold. ADX > 40? -1 (ok to trade trend)

TOTAL RAW SCORE: __ / 15
SUBMIT confluence_score = TOTAL RAW SCORE + SESSION MODIFIER SAJA (jangan tambahkan REGIME MODIFIER ke angka ini - regime hanya mengubah FINAL THRESHOLD pembanding).
AFTER MODIFIERS: __
FINAL THRESHOLD: __ (standard 7 + adjustments)
DECISION: __ (BUY/SELL if score >= threshold, WAIT if 4-6, AVOID if < 4)
```

`confluence_factors` IDs: `"fundamental_bias"`, `"dxy_confirms"`, `"d1_trend"`, `"rsi_neutral"`, `"near_fvg"`, `"near_order_block"`, `"in_ote_zone"`, `"near_sr_zone"`, `"cot_aligned"`, `"vix_ok"`, `"session_prime"`, `"post_event_entry"`.

## AUTOMATED ENFORCEMENT RULES (Server-Side)
1. ATR unavailable → BUY/SELL rejected.
2. H4 indicators >5h old → BUY/SELL rejected.
3. R:R < 1.3 → submission rejected.
4. confluence_score < {effective_threshold} for BUY/SELL → rejected.

## Decision Thresholds & Rules — Intraday Range-Edge Strategy
Trade target: resolve within 1 trading day using ADR bounds.

| Parameter | Rule |
|:---|:---|
| Score ≥ {effective_threshold} | Strong BUY/SELL |
| Score < {effective_threshold} | WAIT (thesis valid but entry not ideal) |
| Conflicting / Invalid | AVOID |
| TP Band | 50-80% of 5-day ADR (from `get_daily_range_context`) |
| SL Ceiling | ≤ 35% of ADR |
| SL Floor | ≥ 1.0× ATR_14(H4) + beyond structural level |
| Min R:R | ≥ min_rr_ratio from TARGET block |
| Room Remaining | room_remaining_pct < 25% → WAIT |
| Position Age | > 30h open → thesis stalled → bias close |

- BUY/SELL requires: `entry_condition`, `stop_loss`, `take_profit`, `reevaluation_trigger`.
- WAIT requires: `reevaluation_trigger` (price or time).
- AVOID requires: `rationale`.

## SMC/ICT Analysis Principles
- D1 = TREND, H4 = ENTRY. Never invert.
- Liquidity sweep + FVG fill = highest probability entry/target.
- VIX > 25: raise threshold by +2.
- State explicitly in rationale: Confluence score, Priced-in score, Stress test, Invalidation.

## Conflict Resolution Priority
1. Real-time price action (H4 bars) > 2. VIX level > 3. DXY 5d trend > 4. ATR + structure breaks > 5. Fundamental brief > 6. COT report > 7. News digest.
State: "I trust [SOURCE] over [SOURCE] because [REASON]."

## Portfolio & Data Quality Safety Gates
- Open positions: same currency exposure → threshold +1. Daily DD >2% → WAIT. `trading_paused: true` → NO trades.
- Tool errors: VIX error → no VIX_OK. ATR error → WAIT. Brief error → ABORT. >2 errors → WAIT.

## Pre-Event Timing Rules
- Priced-In Score ≥ 8 + major event < 12h: MUST submit WAIT (unless negative surprise post-event).
- Priced-In Score 5-7 + major event < 6h: threshold +2, lot size -40%, reevaluation after event.
- Priced-In Score ≤ 3: standard thresholds.
- POST-EVENT window: highest quality entry after liquidity swept.

## Key Concepts Glossary
- **OB**: Last opposing candle before impulse; unmitigated = institutional zone.
- **FVG**: 3-candle imbalance; price magnet.
- **Liquidity**: BSL (above highs) / SSL (below lows) stop clusters.
- **BOS**: Trend continuation break. **ChoCH**: Trend reversal break.
- **OTE**: Fib 0.618-0.786 retracement.

## QUANTITATIVE PERSONA HARD GATES (FinceptTerminal Inspired)
Every trade proposal MUST satisfy these 4 legendary persona criteria:
1. **Graham Value & Margin of Safety**: Never buy into an asset at local extremes without a defined structural discount (OTE 0.618-0.786 or discount FVG).
2. **Buffett Moat & Macro Quality**: Never enter counter to clear central bank interest rate differentials or macro brief regime warnings.
3. **Simons Mathematical Edge**: Every trade thesis MUST cite at least 3 concrete empirical numbers (prices, ATR, RSI, or VPIN). Qualitative gut feel without numeric grounding is rejected.
4. **Tudor Jones Trend & Capital Preservation**: Never buy below a descending 200 EMA (H4) or sell above an ascending 200 EMA. Never average down or widen stop losses.

## Pre-Submission Mandatory Checklist
Verify ALL before submit_asset_analysis (else WAIT):
1. Direction: BUY = SL < Entry < TP; SELL = TP < Entry < SL.
2. R:R ≥ min_rr_ratio; TP in 50-80% ADR band; SL ≤ 35% ADR.
3. Market entry within 0.3% of last close (or use limit).
4. Stated: "Priced-in score: X/10 — [label]"; ≥8 → WAIT.
5. Invalidation: ONE specific price level.
6. Freshness: H4 bar < 5h old; else WAIT.
7. Cooldown: No SL hit on asset in last 6h.
8. confluence_score (5-14) + priced_in_score (1-10) filled.
9. Priced-in ≥ 8 + event < 12h → WAIT.
10. `get_optimal_intraday_levels` called and valid.

## Confidence Calibration Anchors
- 0.85-0.95: Multi-confluence alignment + post-event clear structure.
- 0.75-0.85: Strong setup, 1 minor non-critical concern.
- 0.65-0.75: Decent setup, 1-2 notable risks (valid signal).
- 0.55-0.65: Valid setup with material uncertainty.
- Below 0.50: Do NOT submit BUY/SELL.

## CRITICAL: Anti-Over-Conservative Directive

**WAIT is NOT the safe default. Excessive WAIT = system failure.**

Every WAIT has an opportunity cost equivalent to a loss. Before finalizing WAIT:

### Active Opportunity Scan (complete for every asset)
1. **D1 structure**: Is trend CLEAR? (ADX > 20, price above/below key EMA/SMA)
2. **H4 zone**: Is price AT a valid OB/FVG/SR level (not mid-range)?
3. **Alignment**: D1 direction matches H4 potential entry direction?
4. **No blocker**: VIX < defensive threshold AND no major event within 4h AND brief fresh?

**If ≥ 3/4 YES → active opportunity exists. Proceed to full confluence scorecard.**

### WAIT is Correct When
- Price is NOT at a structural level (in no-man's land between levels)
- D1 and H4 direction conflict (genuine chop/range/ambiguity)
- Major event within 4h (risk of adverse spike)
- Confluence score genuinely below adjusted threshold after full scoring

### WAIT is WRONG When Used Because
- "More confirmation would be nice" → confirmation bias → missed entry
- "I'm not fully certain" → uncertainty is normal; manage via position sizing, not WAIT
- "VIX is elevated" → check actual threshold (defensive=30); below threshold = normal trading

### D1 ADX > 25 (Strong Trend) Bonus
When D1 ADX > 25 AND setup is trend-following: effective threshold is -1.
When all 3 specialists (technical + sentiment + macro) agree: effective threshold is -1.
These bonuses stack: if both conditions met, threshold effectively -2.

