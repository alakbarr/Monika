---
name: cross_asset_regime_model
description: "Cross-asset volatility transmission, correlation shifts, and regime modeling."
version: 1.0.0
category: TRADING
tags: [cross_asset, macro, regime, volatility, correlation, bonds, equities, fx]
---

# Cross-Asset Macro Regime Analysis

## Framework
Monitors inter-market transmission channels across fixed income (US 10Y/2Y Yields), commodities (Crude Oil, Gold), equity volatility (VIX, MOVE), and foreign exchange (DXY).

## Regime Classifications
1. **Risk-On Expansion**:
   - Equities advancing, Credit spreads tightening, VIX < 16, US 10Y yields stable or gently drifting up with real growth.
   - High-beta FX (AUD, NZD, CAD) favored over safe-havens (JPY, CHF, USD).

2. **Stagflationary Pressure**:
   - Commodities (Energy/Agriculture) rallying, Inflation breakevens widening, Yield curve flattening or inverting, Equities under pressure.
   - Favor defensive positioning, Commodity FX, and reduce long-duration equity exposure.

3. **Liquidity Shock / Flight to Quality**:
   - VIX > 25, MOVE index spiking, Credit spreads blowing out.
   - Rapid carry trade unwinding (JPY surges, CHF bids, USD cash scramble).
   - Mandatory RiskGate sizing reduction by 50% across all speculative strategies.
