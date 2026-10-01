---
name: cross-asset-regime-model
description: "Cross-asset volatility transmission, correlation shifts, and regime modeling."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [cross_asset, macro, regime, volatility, correlation, bonds, equities, fx]
---

# Cross-Asset Macro Regime Analysis & Volatility Modeling

## 1. Transmission Mechanism
Monitors inter-market transmission channels across fixed income (US 2Y/10Y yield curve, real yields), commodities (Crude Oil, Gold), equity volatility (VIX), credit spreads (HY OAS), and sovereign foreign exchange (DXY).

## 2. Quantitative 5-Regime Matrix

| Macro Regime | VIX Level | 2s10s Curve | Credit Spreads | DXY Trend | Favored Asset Allocation | Prohibited Setups |
|:---|:---|:---|:---|:---|:---|:---|
| **1. Risk-On Expansion** | $< 16.0$ | Normal ($> 0\text{ bps}$) | Tightening | Neutral / Bearish | AUD, GBP, NZD, BTCUSD | JPY carry shorts, Long USD |
| **2. Disinflationary Boom** | $< 18.0$ | Bull Steepening | Tight | Bearish | EUR, Equities, High-Beta FX | Defensive CHF, Long USD |
| **3. Stagflationary Pressure** | $18.0\text{--}24.0$ | Flat / Inverting | Widening | Bullish | XAUUSD, XTIUSD, Commodity FX | High-PE equities, Long EUR |
| **4. Liquidity Crunch** | $25.0\text{--}35.0$ | Inverting / Distorted | Blowing Out | Very Bullish | USD Cash, JPY, CHF | BTCUSD, High-Beta FX |
| **5. Systemic Shock** | $> 35.0$ | Extreme Inversion | Severe Panic | Extreme Flight | USD Cash, US Treasuries | ALL new speculative risk entries |

## 3. Operational Risk Rules Per Regime
- **Regime 1 & 2 (Expansionary)**: Full standard position sizing ($1.0\%$ risk per setup). Pro-cyclical momentum and trend-continuation strategies active.
- **Regime 3 (Stagflationary)**: Prioritize commodities (Gold, Crude Oil). FX sizing capped at $0.75\times$ standard risk.
- **Regime 4 (Liquidity Crunch)**: Mandatory RiskGate sizing reduction by $50\%$ ($0.50\%$ risk). Prohibit crypto and high-beta FX long entries. JPY carry unwinds active.
- **Regime 5 (Systemic Shock)**: RiskGate triggers defensive pause. Zero new market orders permitted until VIX closes below 30.0 for 2 consecutive 4-hour candles.
