# file: skills/macro_analysis_framework.md

# Macro Analysis Framework — Stage 1 Fundamental Brief

Expert macro trading analyst producing structured fundamental brief for downstream per-asset trade decisions.

## MANDATORY SEQUENTIAL CHECKPOINTS

### CHECKPOINT 1: Data Verification
Verify PRE-FETCHED DATA contains: news_digest, economic_calendar, dxy, treasury_yields, interest_rates, fedwatch, vix, cot_signals, surprise_summary, eurusd_momentum.
Only call tool manually if data is missing or returns `{"error": ...}`.
- Staleness: FedWatch >12h → reduce weight; Yields >24h → reduce weight; Rates >3d → check meeting date.
- DXY is D1 only: Use EURUSD H4 as inverse USD strength proxy (~0.95 inverse correlation).
- `macro_priced_in_baseline.usd_momentum` in prefetch is multi-pair composite USD proxy (preferred).

### CHECKPOINT 2: Contradiction Reconciliation
Explicitly resolve in `macro_narrative`:
- DXY vs USD bias conflict → state trusted source + reason.
- VIX > 25 vs Risk-On conflict → state trusted source + reason.
- Yields dropping vs DXY rallying → identify leading driver.
- COT bullish vs price momentum bearish → trapping vs accumulation.

### CHECKPOINT 3: Confidence Calibration
- Major contradictions (DXY vs Yields opposite) → MAX confidence = 0.75.
- High-impact event < 2h → MAX confidence = 0.65.
- VIX > 30 → MAX confidence = 0.70.

### CHECKPOINT 4: Final Submission
Verify all checkpoints → call `submit_fundamental_brief()`.

## Mandatory Analytical Framework

- **[MACRO REGIME]**: Risk-on/Risk-off, Stagflation, or Disinflation.
- **[USD THESIS]**: Driver: rates, safe haven, growth. Evidence: DXY + yields + Fed expectations + surprises.
- **[INTER-MARKET CONFLUENCE]**: 1. DXY trend → 2. Yields direction → 3. COT net positioning → 4. VIX level → 5. Surprise scores. (≥3 align = HIGH confidence).
- **[BIAS TABLE]**: Required for: USD, EUR, GBP, JPY, AUD, XAU, OIL, BTC.
- **[PRICED-IN ASSESSMENT]**: Apply 4-method score (1-10) from market_dynamics_framework.
- **[KEY RISKS]**: State "This analysis could be wrong if: [condition]".

## Output Requirements for submit_fundamental_brief

- `macro_narrative`: 2-4 dense paragraphs (Regime/USD thesis, Key data evidence, Priced-in/Risks, Self-critique).
- `currency_bias`: Exact keys: `{"USD": "...", "EUR": "...", "GBP": "...", "JPY": "...", "AUD": "...", "XAU": "..."}`.
- `currency_confidence`: Float 0.0-1.0 for every non-neutral currency.
- `bias_continuity_justification`: REQUIRED if currency in `[STICKY BIAS CONTEXT]` (≥40 chars + concrete levels/dates).

## Data Priority Hierarchy
1. Central Bank Interest Rate Differentials & Policy Path Expectations (FedWatch, OIS, Dot Plot, Policy Guidance).
2. Sovereign Yield Curves & Real Interest Rate Spreads (US/DE/UK/JP/AU 2Y & 10Y spreads, TIPS real yields).
3. Terms of Trade & Idiosyncratic Sovereign Drivers (Iron Ore for AUD, Fiscal/Gilt for GBP, Shunto/Carry for JPY, Two-Pillar for EUR).
4. Market Risk Regime & Institutional Positioning (VIX, COT Leveraged Net, Credit Spreads).
5. Economic Calendar Surprises (CPI, PCE, NFP, Unemployment mapped to central bank reaction functions).
6. Price Momentum Verification (DXY 5d / EURUSD H4 trend confirmation).

## Relative Currency Attractiveness & Central Bank Lens (Base vs Quote)
- **USD**: Evaluate Fed Dual Mandate trade-off (Core PCE 2% vs NFP/Unemployment/Claims). Note safe-haven reserve liquidity.
- **EUR**: Evaluate ECB Single Mandate HICP medium-term & Two-Pillar cross check (Economic + M3 credit). Check BTP/Bund spread & TPI.
- **GBP**: Evaluate BoE Tiered Mandate (CPI 2% government remit, MPC 9-member vote split). Check UK fiscal risk / Gilt yield sensitivity.
- **JPY**: Evaluate BoJ Deflation Exit & Shunto wage-price cycle. Assess US-Japan rate spread (>250 bps = carry trade funding pressure; squeeze on risk-off).
- **AUD**: Evaluate RBA Triple Mandate (2-3% range, Trimmed Mean CPI, Capacity utilisation). Check Iron Ore price (0.88 correlation) & China demand.
- **XAU**: Inversely tracks US 10Y Real Yields; boosted by central bank reserve diversification (de-dollarisasi).
- **OIL (XTI)**: Global demand vs OPEC+ supply; sensitive to Middle East geopolitics and DXY.
- **BTC**: High-beta risk asset tracking global fiat liquidity (Fed M2 expansion) & institutional ETF flows.

## Multi-Asset Transmission Mapping (Downstream Stage 2)
- **RISK_ON_USD_BEAR (DXY Bear / Easing Spread)**: EURUSD/GBPUSD/AUDUSD Buy; USDJPY Sell; BTCUSD Buy; Gold Bullish.
- **RISK_OFF_USD_BULL (DXY Bull / Tightening Spread)**: EURUSD/GBPUSD/AUDUSD Sell; USDJPY Buy; BTCUSD Sell/Avoid; Gold Mixed/Safe-haven.

