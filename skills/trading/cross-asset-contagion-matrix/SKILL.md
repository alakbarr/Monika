---
name: cross-asset-contagion-matrix
description: "Cross-asset cascading liquidations, margin calls, and carry trade unwinds."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [contagion, cross_asset, margin_call, crypto_washout, carry_unwind, gold_liquidation, dollar_hoarding]
---

# Cross-Asset Contagion & Liquidity Cascades

## 1. Core Mechanics
In periods of acute financial stress, historical asset correlations break down toward $+1.0$ (cross-asset asset liquidation) and $-1.0$ (flight to cash/USD). Market distress propagates through four primary contagion channels:

```
[Crypto / High-Beta Liquidation] 
            │
            ▼ (Leverage Wipeout & Exchange Margin Deficits)
[Gold / Liquid Asset Fire-Sale] (Traders sell winners to cover margin calls elsewhere)
            │
            ▼ (Collateral Scramble & Cross-Currency Basis Widening)
[US Dollar Hoarding / Liquidity Freeze] (DXY Spikes, Real Yields surge)
            │
            ▼ (Rapid Deleveraging)
[JPY / CHF Carry Trade Unwind] (Forced short-covering of funding currencies)
```

## 2. Contagion Transmission Archetypes

### Archetype A: Crypto Cascading Washout $\rightarrow$ Commodity Margin Calls
- **Trigger**: Massive liquidation cascade in BTCUSD / ETHUSD ($\ge 10\%$ intraday drawdown).
- **Contagion Transmission**: Multi-asset hedge funds and prop desks face cross-margining margin calls. Liquid assets with unrealized profits (Gold / XAUUSD, Silver / XAGUSD) are dumped indiscriminately to meet cash margin requirements.
- **Trading Mandate**: When Crypto experiences a severe washout, **DO NOT assume Gold will act as an immediate safe haven**. Anticipate an initial 24–48 hour dip in XAUUSD before flight-to-safety bids emerge.

### Archetype B: Sovereign Yield / FX Carry Unwind (e.g. JPY Carry Crash)
- **Trigger**: Unexpected BoJ hawkish shift or massive widening in JPY yield differentials.
- **Contagion Transmission**: Rapid short-covering in USDJPY and EURJPY forces global asset sales (US tech equities, high-yielding emerging currencies, commodity longs).
- **Trading Mandate**: When USDJPY drops $>2.5\%$ in a single session, halt all speculative long positions across equities and high-beta FX (AUDUSD, NZDUSD, GBPUSD).

### Archetype C: Geopolitical Oil Spike $\rightarrow$ Stagflationary FX Divergence
- **Trigger**: Supply shock in Crude Oil (XTIUSD / XBRUSD $> +5\%$ gap).
- **Contagion Transmission**: Importers (EUR, JPY) suffer terms-of-trade shocks and currency depreciation; exporters (CAD, NOK, USD) strengthen.
- **Trading Mandate**: Short EURUSD and EURCAD; avoid long EURGBP or EURJPY.

### Archetype D: Dollar Liquidity Crunch (DXY Breakout with Widening Credit Spreads)
- **Trigger**: DXY $+1.5\%$ weekly impulse accompanied by High-Yield OAS widening $>50\text{ bps}$.
- **Contagion Transmission**: Global dollar shortage forces central bank swap line utilization; all foreign currencies weaken irrespective of local rate hikes.
- **Trading Mandate**: Cease all mean-reversion buying against USD. Only enter trend-continuation USD longs at validated H4 Order Blocks.

## 3. Specialist & RiskGate Operational Directives
- **Sentiment Specialist**: Monitor cross-asset correlation matrix ($r > 0.70$ between normally uncorrelated pairs signals systemic contagion).
- **Debate Council**: Bear Analyst must invoke Archetypes A–D whenever counter-asset dislocations are observed.
- **RiskGate / Fortress**: When Contagion flag is active, automatically cap total portfolio exposure at $1.5\%$ heat and set maximum individual trade risk multiplier to $0.50\times$.
