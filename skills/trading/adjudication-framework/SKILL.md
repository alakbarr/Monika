---
name: adjudication-framework
description: "Stage 2 synthesis adjudication rules for specialist conflict resolution."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [adjudication, synthesis, confluence, stage2, trade_gate]
---

# Adjudication Framework — Stage 2 Synthesis Rules

## 1. Evidence Quality Hierarchy & Specialist Anti-Crowding Rule
1. **PRICE ACTION (Technical)**: Highest baseline weight ($45\%$). Price displacement, structural breaks (BOS/ChoCH), and unmitigated institutional zones define actual entry timing and risk boundaries.
2. **MACRO BRIEF (Macro)**: Sovereign directional tailwinds ($35\%$). High weight ($< 3\text{h}$ old), Medium ($3\text{--}5\text{h}$), Low ($> 5\text{h}$).
3. **POSITIONING (Sentiment)**: Non-blocking crowding/exhaustion gauge ($20\%$).
   - **Specialist Anti-Crowding Rule**: `Technical == Macro` with `Sentiment` neutral or contrarian (`uncrowded_institutional_synergy`) is the highest-expectancy setup (`81.8%` 12h / `65.4%` 24h accuracy). Treat `Sentiment Specialist` as a non-blocking crowding/exhaustion gauge, NEVER as a primary directional blocker when retail positioning is moderate ($35\%\text{--}68\%$).
   - **Crowded Tech+Sentiment Trap vs Macro (`crowded_tech_sent_trap_vs_macro`)**: When `Technical == Sentiment != Macro` (`CROWDED_TECH_SENT_TRAP_VS_MACRO`), retail sentiment and short-term price action are chasing into institutional opposition (`71.4%` 24h reversal rate). Reject (`avoid`/`wait`) trades aligned with the retail crowd against `Macro`; approve trades aligned with the `Macro Specialist` direction when supported by structure.
   - **Crowded 3-of-3 Exhaustion Warning (`crowded_unanimous_exhaustion`)**: When `Technical == Macro == Sentiment` all agree in the same direction AND price is already extended past Equilibrium ($pos > 0.55$ for `BUY` or $pos < 0.45$ for `SELL`), beware late-stage trend exhaustion and default to `WAIT` or an outer pullback limit order.

## 2. Spatial, Regime & Institutional Synergy Protocol (3-Zone Dealing Range)

Calculate or inspect `dealing_range_pos` $pos = (\text{Close} - \text{Low}_{20}) / (\text{High}_{20} - \text{Low}_{20})$, `h4_impulse_atr`, and `regime_classification`:
1. **DISCOUNT (`DISCOUNT_ACCUMULATION_ZONE`, $pos \le 0.38$)**: Institutional accumulation zone; approve `BUY` setups when structural demand holds (even if lagging Stage 1 macro or unanimous specialists are bearish) or confirmed breakdown `SELL` when `BEARISH_IMPULSE_BREAKOUT` ($\text{h4\_impulse\_atr} \le -1.25$).
2. **PREMIUM ($pos \ge 0.65$)**: Institutional distribution or `UPPER_RANGE_TREND_CONTINUATION` zone; approve `SELL` setups at supply/rejection, or `BUY` when `BULLISH_IMPULSE_BREAKOUT` ($\text{h4\_impulse\_atr} \ge +1.25$) / `UPPER_RANGE_TREND_CONTINUATION`. Reject market-chasing `BUY` inside `OVEREXTENDED_RANGE_CEILING_PULLBACK_RISK` ($pos \ge 0.80$ without structure breakout).
3. **EQUILIBRIUM ($0.38 < pos < 0.65$)**: Reject (`WAIT` / `AVOID`) when `regime_classification == "EQUILIBRIUM_DEAD_ZONE_CHOP"` ($0.40 \le pos \le 0.60$ and $|\text{h4\_impulse\_atr}| < 0.25$). Otherwise, market or limit execution in `MID_RANGE_DIRECTIONAL_FLOW` is PERMITTED when `Technical == Macro` (`uncrowded_institutional_synergy`) or strong structural confluence ($\ge 10$) and H4/H1 price structure aligns.

| Scenario | Specialist / Regime Alignment | Synthesized Action | Sizing & Invariants |
|:---|:---|:---|:---|
| **Uncrowded Institutional Synergy** | `Tech == Macro` (BULL/BEAR), `Sent != Tech` (`uncrowded_institutional_synergy`) | **BUY / SELL** | Highest-expectancy alpha. Standard risk sizing ($1.0\times$). Net $R:R \ge 1.50$. |
| **Discount Accumulation Zone** | `DISCOUNT_ACCUMULATION_ZONE` ($pos \le 0.38$) with structural demand | **BUY** | Approve `BUY` even if lagging Stage 1 macro or unanimous specialists are bearish ($0.65\times\text{--}0.85\times$). |
| **Crowded Tech+Sent Trap vs Macro** | `Tech == Sent != Macro` (`CROWDED_TECH_SENT_TRAP_VS_MACRO`) | **Follow Macro / AVOID Trap** | Approve trade aligned with `Macro` direction; reject (`avoid`/`wait`) trade chasing `Tech+Sent` against `Macro`. |
| **Impulse Breakout** | `BULLISH_IMPULSE_BREAKOUT` / `BEARISH_IMPULSE_BREAKOUT` ($|\text{h4\_impulse\_atr}| \ge 1.25$) | **BUY / SELL** (Trend Continuation) | Follow active H4 displacement; never counter-trend fade an active impulse breakout. |
| **Overextended Range Ceiling** | `OVEREXTENDED_RANGE_CEILING_PULLBACK_RISK` ($pos \ge 0.80$, no breakout) | **WAIT / AVOID Chase** | Do not market-chase at range ceiling without a structure breakout. |
| **Equilibrium Dead-Zone Chop** | `EQUILIBRIUM_DEAD_ZONE_CHOP` ($0.40 \le pos \le 0.60$, $\|\text{h4\_impulse\_atr}\| < 0.25$) | **WAIT / AVOID** | Directionless mid-range chop; preserve capital. |

## 3. Zero-Arithmetic Bracket Adoption (`adopted_bracket`) & Intraday ADR R:R Compliance
- **Zero-Arithmetic Bracket Adoption (`adopted_bracket`)**: When submitting `BUY` or `SELL` via `submit_asset_analysis`, pass `adopted_bracket="LONG_OPTION_A"` (for `BUY`) or `adopted_bracket="SHORT_OPTION_B"` (for `SELL`) from the pre-computed `DETERMINISTIC INVARIANT ENGINE` block so verified `entry_condition`, `stop_loss`, and `take_profit` are populated without mental floating-point arithmetic errors.
- **Harmonized Intraday R:R Rule (`net R:R >= 1.50`)**: Any bracket with **net $R:R \ge 1.50$** and **$\text{SL} \ge 1.0\times\text{H4 ATR}$** (or ADR-harmonized floor $\ge 0.95\times\text{ATR}$ / $\le 0.50\times\text{ADR}$) is **100% compliant** with Monika's intraday ADR geometry (`TP = min(1.50x ATR, 0.68x ADR)`, `SL = TP / 1.50`). Never reject or downgrade a trade in Stage 2 or Stage 3 Investment Judge solely because $R:R$ is $1.50\text{--}1.70$ instead of $1.75 / 2.00$.
- **Score Sub-Threshold**: If `confluence_score < effective_threshold` $\rightarrow$ Decision MUST be `WAIT`.
- **Priced-In Exhaustion**: If `priced_in_score >= 8` $\rightarrow$ Prohibit trend-following market chase in direction of priced-in narrative. Stance is `WAIT` for pullback or re-evaluation at outer structural discount/premium.
- **RiskGate Invalidation**: If RiskGate returns an active blocking issue (drawdown, spread, news window) $\rightarrow$ Decision MUST be `WAIT` or `AVOID`.
- Output structured analysis strictly via `submit_asset_analysis`.

## 4. Structural Stop Loss Anchoring Invariant
- **Major H4 Swing Anchoring**: Stop Loss MUST be placed beyond the major H4 swing level or order block boundary, NOT minor M15 intraday noise.
- **Mandatory Structural Buffer & Floor**: Minimum SL distance MUST be $\ge 1.0\times\text{ ATR}(14, \text{H4})$ (or ADR-harmonized floor $\ge 0.95\times\text{ATR}$ / $\le 0.50\times\text{ADR}$) with harmonized intraday ceiling $\le \max(\text{ADR cap}, 1.35\times\text{H4 ATR})$ and net $R:R \ge 1.50$.

## 5. Sovereign Dollar Regime & Anti-Falling-Knife Invariants
- **Dynamic Dollar Momentum**: Prohibit commodity/crypto longs only when DXY has active upward momentum (DXY > 20 EMA and positive daily change > +0.3%). Static price levels alone (e.g. 101.00) do not invalidate technical setups if DXY is consolidating or pulling back.
- **Anti-Falling-Knife Rule**: When macro direction strongly opposes technical direction (e.g., strong macro bearish on BTC/Gold), touching a discount POI alone is INSUFFICIENT. A confirmed liquidity sweep of prior swing low (Turtle Soup) followed by displacement back above the sweep level is MANDATORY before any BUY is authorized. Never buy an untethered falling knife into an un-swept level.
