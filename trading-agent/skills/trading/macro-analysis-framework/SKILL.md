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

### CHECKPOINT 1: Data Verification & Time-to-Live (TTL) Hierarchy
Verify PRE-FETCHED DATA contains: news_digest, economic_calendar, dxy, treasury_yields, interest_rates, fedwatch, vix, cot_signals, surprise_summary, eurusd_momentum.

| Data Source | Maximum Acceptable TTL | Action if Stale / Missing |
|:---|:---|:---|
| **CME FedWatch Probabilities** | 12 hours | Discount weight by 50%; check for breaking FOMC speaker commentary. |
| **Sovereign Treasury Yields (10Y/2Y)** | 24 hours | Call `get_treasury_yields` manually. |
| **Central Bank Policy Rates** | 72 hours | Check economic calendar for recent rate decisions. |
| **CFTC COT Report** | 7 days (released Fridays) | Use latest published release; check for mid-week extreme momentum. |
| **Equity Volatility (VIX Index)** | 4 hours | Call `get_vix` manually to verify live risk environment. |

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
- `macro_narrative`: 2–4 dense paragraphs covering Macro Regime/USD thesis, Empirical data evidence, Priced-in calibration, and Falsification conditions.
- `currency_bias`: Exact keys: `{"USD": "...", "EUR": "...", "GBP": "...", "JPY": "...", "AUD": "...", "XAU": "..."}`.
- `currency_confidence`: Float 0.0–1.0 for every active directional currency bias.
- `bias_continuity_justification`: Required if currency is in `[STICKY BIAS CONTEXT]` ($\ge 40$ chars citing concrete fundamental levels/dates).
