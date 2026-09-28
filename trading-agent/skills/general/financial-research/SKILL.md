---
name: financial-research
description: Analyze prediction markets, DEX perps, and cross-asset correlations.
category: research
version: 1.0.0
platforms: [windows, linux, macos]
tags: [polymarket, hyperliquid, prediction-markets, funding-rates, crypto, macro]
---

# Financial Research & Quantitative Sentiment Playbook

Institutional methodology for gathering non-traditional market sentiment and high-frequency derivatives positioning.

## 1. Prediction Markets (Polymarket & Kalshi)
- **Probability Distillation**: Convert prediction market pricing (0.00 - 1.00 USDC) to implied event probability for macroeconomic binary outcomes (e.g. FOMC rate cuts, CPI prints, regulatory approvals).
- **Mispricing Identification**: Compare implied event probability against institutional consensus forecasts (e.g. Bloomberg / Reuters median survey). Where probability delta > 15%, flag an asymmetric positioning opportunity.

## 2. Decentralized Derivatives (Hyperliquid & dYdX)
- **Perp Funding Rate Analysis**:
  - Positive Extreme (> +0.03% per 8h): Overleveraged long sentiment, heightened long squeeze liquidation risk.
  - Negative Extreme (< -0.03% per 8h): Aggressive short crowding, potential violent short squeeze.
- **Open Interest (OI) Divergence**:
  - Price Rising + OI Rising: Strong trend continuation confirmed by new institutional capital inflow.
  - Price Rising + OI Falling: Short-covering rally, vulnerable to reversal once squeeze concludes.

## 3. Cross-Asset Risk-On / Risk-Off Matrix
- **Correlations to Monitor**:
  - Gold (XAUUSD) vs Real Yields (US10Y - Inflation expectations).
  - Bitcoin (BTCUSD) vs NASDAQ 100 (QQQ) beta sensitivity.
  - US Dollar Index (DXY) momentum vs commodity currencies (AUD, CAD).
