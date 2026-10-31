---
name: adjudication-framework
description: "Stage 2 synthesis adjudication rules for specialist conflict resolution."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [adjudication, synthesis, confluence, stage2, trade_gate]
---

# Adjudication Framework — Stage 2 Synthesis Rules

## 1. Evidence Quality Hierarchy
1. **PRICE ACTION (Technical)**: Highest baseline weight ($45\%$). Price displacement, structural breaks (BOS/ChoCH), and unmitigated institutional zones define actual entry timing and risk boundaries.
2. **MACRO BRIEF (Macro)**: Sovereign directional tailwinds ($35\%$). High weight ($< 3\text{h}$ old), Medium ($3\text{--}5\text{h}$), Low ($> 5\text{h}$).
3. **POSITIONING (Sentiment)**: Contrarian positioning filter ($20\%$). CFTC COT multi-week extremes + Retail crowding sentiment ($> 70\%$ retail skew = contrarian signal).

## 2. Directional Synthesis Decision Matrix & 3-Zone Dealing Range

### 3-Zone Spatial Dealing Range Rules
Calculate or inspect the 20-day dealing range position $pos = (\text{Close} - \text{Low}_{20}) / (\text{High}_{20} - \text{Low}_{20})$:
1. **DEEP DISCOUNT ($pos \le 0.35$)**: Institutional accumulation zone. BUY is authorized via Dual-Engine:
   - *Engine 1 (Macro-Aligned / Neutral POI Retest)*: Unmitigated Demand OB / FVG retest with $R:R \ge 1.75$.
   - *Engine 2 (Contra-Macro Liquidity Sweep)*: Requires confirmed Liquidity Sweep of swing low + MSS displacement back above sweep level with $R:R \ge 2.00$. Downscale sizing to $0.65\times\text{--}0.75\times$.
2. **DEEP PREMIUM ($pos \ge 0.65$)**: Institutional distribution zone. SELL is authorized via Dual-Engine:
   - *Engine 1 (Macro-Aligned / Neutral POI Retest)*: Unmitigated Supply OB / FVG retest with $R:R \ge 1.75$.
   - *Engine 2 (Contra-Macro Liquidity Sweep)*: Requires confirmed Liquidity Sweep of swing high + MSS displacement back below sweep level with $R:R \ge 2.00$. Downscale sizing to $0.65\times\text{--}0.75\times$.
3. **EQUILIBRIUM DEAD ZONE ($0.35 < pos < 0.65$)**: Middle-range chop. Market order execution is STRICTLY PROHIBITED. Stance MUST be `WAIT` (or pending limit order placed strictly at outer discount/premium POI boundaries).

| Scenario | Specialist Alignment | Synthesized Action | Sizing & Invariants |
|:---|:---|:---|:---|
| **Full Alignment** | Tech=BULL/BEAR, Macro=BULL/BEAR, Sent=ALIGNED/NEUT | **BUY / SELL** | Standard risk sizing ($1.0\times$). Execute at structural zone ($pos \le 0.35$ or $pos \ge 0.65$) with score $\ge \text{threshold}$. |
| **Contrarian Sentiment** | Tech=BULL, Macro=BULL, Retail=BEARISH ($> 70\%$) | **BUY** | Standard risk sizing ($1.0\times$). Retail trap amplifies institutional move. |
| **Contrarian Sentiment** | Tech=BEAR, Macro=BEAR, Retail=BULLISH ($> 70\%$) | **SELL** | Standard risk sizing ($1.0\times$). |
| **Trend-Pullback OTE** | Tech=PULLBACK, D1=BULL/BEAR (Trend), Sent=ALIGNED/NEUT | **BUY / SELL** (Follow D1 Trend) | Standard risk sizing ($1.0\times$). H4 counter-trend retracement into unmitigated key level is an institutional discount entry, not a conflict. |
| **Technical vs Macro Conflict** | Tech=BULL, Macro=BEAR (or vice-versa) | **BUY / SELL** (Follow Tech at Extremes) | Downscale risk to $0.65\times\text{--}0.75\times$. MUST be in Deep Discount ($pos \le 0.35$) for BUY or Deep Premium ($pos \ge 0.65$) for SELL with confirmed Liquidity Sweep + MSS. In Equilibrium ($0.35 < pos < 0.65$) $\rightarrow$ `WAIT`. |
| **Tech Neutral + Strong Macro** | Tech=NEUT (Mid-range), Macro=STRONG ($\text{Conf} \ge 0.80$) | **WAIT for Pullback** | Do not chase. Place pending limit order at structural OTE / Order Block level. |
| **Macro Neutral + Strong Tech** | Tech=STRONG ($\text{Score} \ge 8$), Macro=NEUT | **BUY / SELL** | Standard risk sizing ($1.0\times$). Technical edge independently verifiable at range extremes. |
| **Ambiguous / Mixed** | Mixed signals with zero high-conviction anchors | **WAIT** | Submit `WAIT` with explicit re-evaluation price trigger. |

## 3. Mechanical Risk Gate Enforcement (Non-Negotiable)
- **Score Sub-Threshold**: If `confluence_score < effective_threshold` $\rightarrow$ Decision MUST be `WAIT`.
- **Priced-In Exhaustion**: If `priced_in_score >= 8` $\rightarrow$ Prohibit trend-following market chase in direction of priced-in narrative. Stance is `WAIT` for pullback or re-evaluation at extreme structural discount/premium.
- **RiskGate Invalidation**: If RiskGate returns an active blocking issue (drawdown, spread, news window) $\rightarrow$ Decision MUST be `WAIT` or `AVOID`.
- Output structured analysis strictly via `submit_asset_analysis`.

## 4. Structural Stop Loss Anchoring Invariant
- **Major H4 Swing Anchoring**: Stop Loss MUST be placed beyond the major H4 swing level, NOT minor M15 intraday noise.
- **Mandatory Structural Buffer & Floor**: Always inject a noise buffer beyond the structural swing high/low (+0.35x ATR for Forex, +1.20x ATR for Commodities/Gold). Minimum SL distance MUST be $\ge 1.0\times\text{ ATR}(14, \text{H4})$ across all assets to prevent liquidity wick stop-outs.

## 5. Sovereign Dollar Regime & Anti-Falling-Knife Invariants
- **Dynamic Dollar Momentum**: Prohibit commodity/crypto longs only when DXY has active upward momentum (DXY > 20 EMA and positive daily change > +0.3%). Static price levels alone (e.g. 101.00) do not invalidate technical setups if DXY is consolidating or pulling back.
- **Anti-Falling-Knife Rule**: When macro direction strongly opposes technical direction (e.g., strong macro bearish on BTC/Gold), touching a discount POI alone is INSUFFICIENT. A confirmed liquidity sweep of prior swing low (Turtle Soup) followed by displacement back above the sweep level is MANDATORY before any BUY is authorized. Never buy an untethered falling knife into an un-swept level.
