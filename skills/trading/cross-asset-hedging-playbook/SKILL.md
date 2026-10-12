---
name: cross-asset-hedging-playbook
description: "Intermarket transmission, correlation regimes, and cross-asset hedges."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [cross_asset, intermarket, gold_dxy, commodity_spread, brent_wti, yield_correlation, hedging]
---

# Cross-Asset & Intermarket Hedging Playbook

> **Core Thesis**: No asset trades in a vacuum. Sovereign bond yields, currency indices (DXY), industrial/energy commodities (Oil, Copper), and precious metals (Gold) transmit impulses through institutional asset allocation rebalancing.

---

## 1. Primary Cross-Asset Intermarket Linkages

### A. Gold (XAUUSD) vs. US Dollar (DXY) & Real Yields (TIPS 10Y)
- **Standard Correlation**: Gold has a strong negative correlation ($-0.65$ to $-0.85$) with 10Y US Real Yields (`DFII10`) and DXY.
- **Regime Decoupling**: If Gold rises *despite* a rising DXY and higher real yields, this signals **Geopolitical Flight to Safety** or **Central Bank Reserve Diversification**.
- **Action**: Never enter aggressive Gold shorts during decoupling regimes even if DXY is breaking out.

### B. Crude Oil (Brent vs WTI Spread)
- **Standard Spread**: Brent typically trades at a $\$3.00 - \$5.00$ premium over WTI due to coastal/seaborne freight logistics and sweeter light crude differentials.
- **Spread Compression ($<\$2.00$)**: Signals US domestic supply bottlenecks or strong US export demand.
- **Spread Blowout ($>\$7.00$)**: Signals geopolitical risk in the Middle East/Strait of Hormuz or European refinery stress.
- **Execution Tool**: `get_commodity_spread("BRENT_WTI")`.

### C. Sovereign Yield Spreads vs FX Pairs
- USDJPY tracks the US 10Y minus Japan 10Y yield spread ($r_{US10} - r_{JP10}$) with $>0.80$ correlation.
- EURUSD tracks the US 10Y minus German 10Y Bund yield spread ($r_{DE10} - r_{US10}$).

---

## 2. Portfolio Hedging Rules

1. **Direct Currency Beta Hedging**:
   - Long EURUSD + Long GBPUSD = High positive correlation ($+0.82$). This is NOT diversification; it is double long USD risk.
   - To hedge a Long XAUUSD position against unexpected dollar strength: Short AUDUSD or Long USDJPY (exploits dollar rally without liquidating gold core holding).
2. **Commodity Pairs Hedging**:
   - Long WTI Crude (XTIUSD) + Short Brent Crude (XBRUSD) when spread z-score $> 2.0$ (mean-reversion pair trade).
