---
name: macro-asset-transmission-matrix
description: "Macro transmission framework mapping drivers to FX, commodities, and crypto."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [macro, transmission, fx, gold, xauusd, oil, xtiusd, btc, crypto, per_asset_matrix]
---

# Macro-Asset Transmission Matrix — Institutional Multi-Asset Driver Mapping

Institutional framework for translating macro indicators, policy differentials, and systemic liquidity flows into deterministic, actionable biases for specific tradable assets.

---

## 1. Core Foundational Principle

Macro fundamentals do not impact all assets uniformly. Each asset class operates under a unique **Dominant Transmission Channel**:
- **FX Pairs**: Driven by Real Yield Differentials, Central Bank Mandates, and Terms of Trade.
- **Gold (XAUUSD)**: Driven by Real Yields (10Y TIPS), Sovereign Debasement Hedging, and Physical Central Bank Accumulation.
- **Crude Oil (XTIUSD)**: Driven by Physical Balances (EIA Draws/Builds), Geopolitical Chokepoints (Hormuz), and Refining Crack Spreads.
- **Bitcoin (BTCUSD)**: Driven by Global M2 Liquidity, Fed Net Liquidity ($WALCL - TGA - RRP$), and Spot ETF Flows.

---

## 2. Granular Asset Transmission Playbooks

### A. Foreign Exchange Majors (EURUSD, GBPUSD, USDJPY, AUDUSD)

1. **EURUSD (Euro / US Dollar)**:
   - **Primary Driver**: US-German 10Y sovereign yield spread ($Y_{US10Y} - Y_{DE10Y}$) and ECB-Fed policy divergence.
   - **Transmission Rule**:
     - Spread $> +140$ bps $\implies$ Structural advantage favors USD.
     - Look out for Eurozone imported energy price shocks (pressuring EUR via Terms of Trade deterioration).
   - **Directional Bias Anchor**:
     - Fed more hawkish than ECB $\implies$ EURUSD Bearish.
     - Fed dovish pivot + narrowing spread $\implies$ EURUSD Bullish.

2. **GBPUSD (British Pound / US Dollar)**:
   - **Primary Driver**: UK Gilt yields vs US Treasuries ($Y_{UK10Y} - Y_{US10Y}$) and Bank of England (BoE) MPC vote splits.
   - **Transmission Rule**:
     - High nominal rates can depress GBP if driven by fiscal/sovereign twin deficit stress.
     - BoE split (e.g. 6-3 with persistent wage growth) provides temporary carry support against dovish Fed expectations.

3. **USDJPY (US Dollar / Japanese Yen)**:
   - **Primary Driver**: US-Japan 10Y sovereign yield spread ($Y_{US10Y} - Y_{JP10Y}$) and global risk sentiment (VIX).
   - **Transmission Rule**:
     - **Normal / Low VIX ($<20$)**: JPY acts as the premier global funding currency. Wide spread $> +250$ bps $\implies$ USDJPY Bullish (carry accumulation).
     - **High VIX ($>25$) / Acute Shock**: Violent Carry Trade Unwind $\implies$ USDJPY Bearish (aggressive JPY appreciation regardless of nominal yield gap).
     - **Warning on Bias Mapping**: A *bearish* JPY means JPY weakens, which transmits as a **BULLISH** bias for USDJPY!

4. **AUDUSD (Australian Dollar / US Dollar)**:
   - **Primary Driver**: China cyclical growth/industrial demand, bulk commodity export prices (Iron Ore, Coal), and RBA Trimmed Mean CPI.
   - **Transmission Rule**:
     - AUD has an $r \approx 0.88$ correlation with Iron Ore and Chinese industrial momentum.
     - RBA rate hikes can be neutralized if Chinese industrial profits are decelerating.

---

### B. Precious Metals: Gold (XAUUSD)

- **Primary Driver**: US 10-Year Real Yield (TIPS), Central Bank Reserve Accumulation, and Fiat Debasement Hedging.
- **Transmission Mechanics**:
  1. **Linear Yield Channel**: Falling 10Y real yields reduce the opportunity cost of holding non-yielding bullion $\implies$ Gold Bullish.
  2. **Non-Linear Decoupling Channel**: If Gold rallies while real yields are *rising*, central bank physical accumulation (PBOC, RBI) or sovereign debt sustainability fears dominate.
  3. **Priced-In Rule**: When CFTC COT Net Long is near record highs ($>200,000$ contracts) at all-time highs, sell-the-news risk is elevated on diplomatic de-escalation.

---

### C. Energy: WTI Crude Oil (XTIUSD)

- **Primary Driver**: Physical Supply-Demand Balances (EIA Weekly Petroleum Status Report), Geopolitical Chokepoints, and Refining Margins.
- **Transmission Mechanics**:
  1. **Physical Inventory Balance**:
     - Commercial crude draw $> 3.0$M barrels + gasoline draw $\implies$ Strong physical demand / Bullish.
     - Crude build $+4.0$M barrels $\implies$ Domestic supply glut / Bearish.
  2. **Geopolitical Risk Premium**:
     - Disruptions in the Strait of Hormuz ($>14$M b/d transit) or Red Sea add an asymmetric $+5\text{--}+15\%$ risk premium.
     - G7 strategic reserve releases (SPR / diesel stockpiles) act as counter-trend ceilings.
  3. **Brent-WTI Spread**:
     - If Brent-WTI spread blows out $(>\$8/bbl)$, supply disruption is foreign/seaborne, leaving US domestic WTI relatively insulated.

---

### D. Digital Assets: Bitcoin (BTCUSD)

- **Primary Driver**: Global M2 Money Supply, US Dollar Net Liquidity ($WALCL - TGA - RRP$), and Institutional Spot ETF Flows.
- **Transmission Mechanics**:
  1. **Fed Net Liquidity Direct Impact**:
     - Net Liquidity expanding $\implies$ Surplus cash flows into highest-beta monetary assets $\implies$ BTCUSD Bullish.
     - TGA refilling or aggressive QT drain $\implies$ Liquidity headwind / BTCUSD consolidation or correction.
  2. **Institutional Spot ETF Flows**:
     - Weekly net inflows $> +\$200$M $\implies$ Structural floor, absorbs miner distribution.
     - Perpetual Funding Rates $> +0.03\%$ denote retail leverage froth (long squeeze risk).

---

## 3. Mandatory Requirements for `per_asset_macro_matrix`

In `SubmitFundamentalBriefSchema`, Stage 1 MUST generate a distinct entry for all 7 active assets:
`["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD"]`.

Each asset block MUST contain:
- `directional_bias`: `strong_bullish`, `bullish`, `neutral`, `bearish`, or `strong_bearish`.
- `time_horizon`: `intraday_tactical`, `swing_structural`, or `multi_week`.
- `structural_driver`: Concrete multi-week macroeconomic force.
- `tactical_catalyst`: Session-specific data release or flow catalyst.
- `invalidation_level`: Concrete price level with numerical anchor (e.g. "D1 close < 1.1220").
- `confidence`: Calibrated float $0.0 \text{--} 1.0$.
