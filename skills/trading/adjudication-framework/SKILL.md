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
   - **Specialist Anti-Crowding Rule**: `Technical == Macro` with `Sentiment` neutral or contrarian (`Uncrowded Institutional Synergy`) is the highest-expectancy setup (`81.8%` 12h accuracy). Treat `Sentiment Specialist` as a non-blocking crowding/exhaustion gauge, NEVER as a primary directional blocker when retail positioning is moderate ($35\%\text{--}68\%$).
   - **Crowded 3-of-3 Exhaustion Warning**: When `Technical == Macro == Sentiment` all agree in the same direction AND price is already extended past Equilibrium ($pos > 0.55$ for `BUY` or $pos < 0.45$ for `SELL`), beware late-stage trend exhaustion and default to `WAIT` or an outer pullback limit order.

## 2. Spatial & Institutional Synergy Protocol (3-Zone Dealing Range)

Calculate or inspect the 20-day D1 dealing range position $pos = (\text{Close} - \text{Low}_{20}) / (\text{High}_{20} - \text{Low}_{20})$:
1. **DISCOUNT ($pos \le 0.35$)**: Institutional accumulation zone; favor `BUY` setups (or confirmed breakdown `SELL` when $pos \ge 0.15$ and `Tech == Macro == bearish`). Forbid `SELL` in extreme bottom ($pos < 0.15$) unless breaking decisively below the 20-day low.
2. **PREMIUM ($pos \ge 0.65$)**: Institutional distribution zone; favor `SELL` setups (or confirmed breakout `BUY` when $pos \le 0.85$ and `Tech == Macro == bullish`). Forbid `BUY` in extreme top ($pos > 0.85$) unless breaking decisively above the 20-day high.
3. **EQUILIBRIUM ($0.35 < pos < 0.65$)**: Trend-continuation & FVG/OB retest zone. Market or limit execution is PERMITTED when `Technical == Macro` (Uncrowded Institutional Synergy) or strong structural confluence ($\ge 10$) and H4/H1 price structure aligns. Output `WAIT` in Equilibrium if `Technical` and `Macro` conflict or if structure is directionless chop ($\text{ADX} < 20$).

| Scenario | Specialist Alignment | Synthesized Action | Sizing & Invariants |
|:---|:---|:---|:---|
| **Uncrowded Institutional Synergy** | `Tech == Macro` (BULL/BEAR), `Sent != Tech` (NEUT/CONTRARIAN) | **BUY / SELL** | Highest-expectancy alpha (`81.8%` 12h accuracy). Standard risk sizing ($1.0\times$). Valid across Discount, Equilibrium, and Premium within spatial bounds ($pos \le 0.85$ BUY, $pos \ge 0.15$ SELL). |
| **Early-Stage 3-of-3 Alignment** | `Tech == Macro == Sentiment` at early zone ($pos \le 0.55$ BUY / $pos \ge 0.45$ SELL) | **BUY / SELL** | Standard risk sizing ($1.0\times$). Execute only before trend becomes extended. |
| **Crowded 3-of-3 Exhaustion** | `Tech == Macro == Sentiment` extended ($pos > 0.55$ BUY / $pos < 0.45$ SELL) | **WAIT** | Late-stage exhaustion trap; avoid chasing crowded consensus at extended range levels. |
| **Trend-Pullback OTE** | Tech=PULLBACK, D1=BULL/BEAR (Trend), Sent=ALIGNED/NEUT | **BUY / SELL** (Follow D1 Trend) | Standard risk sizing ($1.0\times$). H4 counter-trend retracement into unmitigated key level is an institutional entry, not a conflict. |
| **Technical vs Macro Conflict** | Tech=BULL, Macro=BEAR (or vice-versa) | **BUY / SELL at Extremes; WAIT in Equilibrium** | In Discount ($pos \le 0.35$ for BUY) or Premium ($pos \ge 0.65$ for SELL) with confirmed Liquidity Sweep + MSS, downscale risk to $0.65\times\text{--}0.75\times$. In Equilibrium ($0.35 < pos < 0.65$) when `Technical != Macro` $\rightarrow$ `WAIT`. |
| **Tech Neutral + Strong Macro** | Tech=NEUT (Mid-range), Macro=STRONG ($\text{Conf} \ge 0.80$) | **WAIT for Pullback** | Do not chase. Place pending limit order at structural OTE / Order Block level. |
| **Macro Neutral + Strong Tech** | Tech=STRONG ($\text{Score} \ge 8$), Macro=NEUT | **BUY / SELL** | Standard risk sizing ($1.0\times$) within spatial anti-chasing bounds ($pos \le 0.85$ BUY, $pos \ge 0.15$ SELL). |
| **Ambiguous / Chop** | Mixed signals or ADX < 20 directionless chop | **WAIT** | Submit `WAIT` with explicit re-evaluation price trigger. |

## 3. Zero-Arithmetic Bracket Adoption (`adopted_bracket`) & Mechanical Risk Gate
- **Zero-Arithmetic Bracket Adoption (`adopted_bracket`)**: When submitting `BUY` or `SELL` via `submit_asset_analysis`, pass `adopted_bracket="LONG_OPTION_A"` (for `BUY`) or `adopted_bracket="SHORT_OPTION_B"` (for `SELL`) from the pre-computed `DETERMINISTIC INVARIANT ENGINE` block so verified `entry_condition`, `stop_loss`, and `take_profit` are populated without mental floating-point arithmetic errors.
- **Score Sub-Threshold**: If `confluence_score < effective_threshold` $\rightarrow$ Decision MUST be `WAIT`.
- **Priced-In Exhaustion**: If `priced_in_score >= 8` $\rightarrow$ Prohibit trend-following market chase in direction of priced-in narrative. Stance is `WAIT` for pullback or re-evaluation at outer structural discount/premium.
- **RiskGate Invalidation**: If RiskGate returns an active blocking issue (drawdown, spread, news window) $\rightarrow$ Decision MUST be `WAIT` or `AVOID`.
- Output structured analysis strictly via `submit_asset_analysis`.

## 4. Structural Stop Loss Anchoring Invariant
- **Major H4 Swing Anchoring**: Stop Loss MUST be placed beyond the major H4 swing level or order block boundary, NOT minor M15 intraday noise.
- **Mandatory Structural Buffer & Floor**: Minimum SL distance MUST be $\ge 1.0\times\text{ ATR}(14, \text{H4})$ for Forex ($\ge 1.2\times\text{ ATR}(14, \text{H4})$ for Gold/Crypto/Oil) with harmonized intraday ceiling $\le \max(\text{ADR cap}, 1.35\times\text{H4 ATR})$ and $R:R \ge 1.50$ (intraday target $\approx 1.55\times\text{SL}$).

## 5. Sovereign Dollar Regime & Anti-Falling-Knife Invariants
- **Dynamic Dollar Momentum**: Prohibit commodity/crypto longs only when DXY has active upward momentum (DXY > 20 EMA and positive daily change > +0.3%). Static price levels alone (e.g. 101.00) do not invalidate technical setups if DXY is consolidating or pulling back.
- **Anti-Falling-Knife Rule**: When macro direction strongly opposes technical direction (e.g., strong macro bearish on BTC/Gold), touching a discount POI alone is INSUFFICIENT. A confirmed liquidity sweep of prior swing low (Turtle Soup) followed by displacement back above the sweep level is MANDATORY before any BUY is authorized. Never buy an untethered falling knife into an un-swept level.
