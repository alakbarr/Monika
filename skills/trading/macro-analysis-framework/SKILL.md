---
name: macro-analysis-framework
description: "Stage 1 fundamental brief macro framework, data TTLs, and check sequence."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [macro, fundamental_brief, stage1, dxy, yields, cot, fedwatch]
---

# Macro Analysis Framework — Stage 1 Fundamental Brief

## Data Priority Hierarchy
1. Sovereign Real Yield Differentials & Central Bank Reaction Functions
2. DXY Trend & Currency Index Intraday Momentum
3. Institutional Positioning (CFTC COT Percentiles)
4. Macro Volatility Transmission (VIX Regimes)
5. Economic Data Surprise Deltas

## Relative Currency Attractiveness
Rank currency attractiveness across G10/major pairs based on policy rate differentials, terms-of-trade shifts, and growth surprise divergences.

## MANDATORY SEQUENTIAL CHECKPOINTS

### CHECKPOINT 1: Data Verification & Pre-Fetch Synthesis Mandate
All core macro indicators are pre-fetched directly into your prompt under `[PRE-FETCHED DATA]`: news_digest, economic_calendar, dxy, treasury_yields, interest_rates, fedwatch, vix, cot_signals, surprise_summary, eurusd_momentum.

> [!IMPORTANT]
> **PRE-FETCH SYNTHESIS MANDATE (Zero Redundant Tool Calls)**:
> If pre-fetched data is present in your context, DO NOT invoke redundant read tools (`get_treasury_yields`, `get_vix`, `get_dxy`, `get_economic_calendar`, etc.).
> Immediately synthesize the pre-fetched indicators in your reasoning and call `submit_fundamental_brief()` directly.
> Manual tool calls are STRICTLY reserved as an emergency fallback if a critical indicator is completely absent or returned an error during pre-fetch.

| Data Source | Maximum Acceptable TTL | Action if Stale / Missing |
|:---|:---|:---|
| **CME FedWatch Probabilities** | 12 hours | Discount weight by 50%; check for breaking FOMC speaker commentary in pre-fetch news. |
| **Sovereign Treasury Yields (10Y/2Y)** | 24 hours | If completely absent from pre-fetch, call `get_treasury_yields`. |
| **Central Bank Policy Rates** | 72 hours | Check economic calendar in pre-fetch for recent rate decisions. |
| **CFTC COT Report** | 7 days (released Fridays) | Use latest published release from pre-fetch; check for mid-week extreme momentum. |
| **Equity Volatility (VIX Index)** | 4 hours | If completely absent from pre-fetch, call `get_vix`. |

*DXY Proxy Note*: DXY is daily (D1) only. Use EURUSD H4 momentum as high-fidelity intraday inverse USD strength proxy (~0.95 inverse correlation).

### CHECKPOINT 2: Contradiction Reconciliation Protocol
Explicitly resolve inter-market divergences in `macro_narrative`:
- **Yields Dropping vs DXY Rallying**: Identify dominant channel. If driven by European sovereign fiscal stress or global flight-to-cash, USD rallies despite sliding yields (Liquidity Scramble). State: *"I trust USD liquidity demand over nominal yield spread because European credit risk is widening."*
- **COT Bullish vs Price Momentum Bearish**: Differentiate institutional accumulation from aggressive trap. If price broke H4 market structure to downside despite net-long COT, treat as speculative distribution/liquidation.
- **VIX Spiking (> 25) vs Risk-On Macro Data**: Volatility transmission supersedes growth optimism. Prioritize capital preservation over cyclical narrative.

### CHECKPOINT 3: Confidence Calibration
- Major unresolved contradictions (DXY vs Yields opposite) $\rightarrow$ Cap MAX confidence at `0.75`.
- High-impact Tier-1 release scheduled within 2 hours $\rightarrow$ Cap MAX confidence at `0.65`.
- VIX $> 30.0$ $\rightarrow$ Cap MAX confidence at `0.70`.

### CHECKPOINT 4: Final Submission
Verify all checkpoints $\rightarrow$ Call `submit_fundamental_brief()`.

---

## Mandatory Analytical Framework
- **[MACRO REGIME]**: Risk-On Expansion, Disinflationary Boom, Stagflation, Liquidity Crunch, or Systemic Shock.
- **[USD THESIS]**: Primary driver (Yield differential, Safe-haven scramble, or Growth divergence). Evidence: DXY + 10Y/2Y spreads + FedWatch expectations + Surprise indices.
- **[INTER-MARKET CONFLUENCE]**: 1. DXY trend $\rightarrow$ 2. Real yields $\rightarrow$ 3. COT positioning $\rightarrow$ 4. VIX regime $\rightarrow$ 5. Data surprises. ($\ge 3$ aligned = HIGH confidence).
- **[BIAS TABLE]**: Required for: USD, EUR, GBP, JPY, AUD, XAU, OIL, BTC.
- **[PRICED-IN ASSESSMENT]**: Apply canonical 4-method score (1–10) from `market-dynamics-framework`. Score $\ge 8$ mandates `WAIT` downstream.
- **[KEY RISKS]**: State *"This analysis could be wrong if: [falsifiable macro condition]"*.

## Output Requirements for submit_fundamental_brief
- `macro_narrative`: Institutional Macro Research Memo (Professional English, Bloomberg Intelligence / Goldman Sachs GIR style). Explain economic causality, transmission mechanisms, and cross-market dynamics clearly and articulately.
  - **Structure with Clear Thematic Sub-Sections**:
    * `### 1. Macro Regime & Cross-Asset Sentiment`: Define prevailing regime (e.g. Stagflation, Expansion, Disinflationary Boom) and volatility transmission (VIX, equity vs credit stress).
    * `### 2. Inflation & Labor Transmission to Central Bank Mandates`: Differentiate transitory noise from persistent structural core pressures (shelter, supercore). Analyze labor quality/revisions and how they transmit into central bank reaction functions (Fed, ECB, BoE, BoJ, RBA).
    * `### 3. Monetary Trajectory, Rates & Systemic Liquidity`: Quantify FedWatch repricing shifts, Treasury yield movements, 10Y real yields, yield curve regime (e.g. bear steepener), and systemic net liquidity (WALCL - TGA - RRP).
    * `### 4. Cross-Market Dynamics & Institutional Positioning`: Reconcile divergences between yields, DXY, and commodities. Explain safe-haven decoupling (e.g. Gold rallying despite high real yields due to geopolitical premia) and institutional COT positioning vulnerabilities.
    * `### 5. Primary Risks & Falsification Conditions`: Explicitly state falsifiable conditions and numerical levels (DXY, yields, VIX) that would disprove this thesis.
  - **Style Directives (Strict Anti-AI Slop & Anti-Machine Shorthand)**:
    * Do NOT write telegraphic machine shorthand (e.g. avoid run-on formulas like `Pipeline A -> B -> C classified XYZ`). Write natural, articulate, professional economic prose.
    * Do NOT use generic AI filler, cliché openers, forced triads, or dramatic sales rhetoric. Maintain rigorous, objective, quantitative institutional tone.
- `currency_bias`: Exact keys: `{"USD": "...", "EUR": "...", "GBP": "...", "JPY": "...", "AUD": "...", "XAU": "..."}`.
- `currency_confidence`: Float 0.0–1.0 for every active directional currency bias.
- `bias_continuity_justification`: Required if currency is in `[STICKY BIAS CONTEXT]` ($\ge 40$ chars citing concrete fundamental levels/dates).
