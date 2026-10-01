---
name: financial-research
description: "Cross-asset research, prediction market analysis, derivatives positioning, and sentiment distillation."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [polymarket, funding_rates, crypto, macro, cot, sentiment, cross_asset]
---

# Financial Research & Quantitative Sentiment Playbook

## 1. Tool-Mapped Research Architecture

| Research Domain | Primary Tool / Channel | Metric & Interpretation |
|:---|:---|:---|
| **Institutional Futures Positioning** | `get_cot_report` | Leveraged Funds / Non-Commercial net positioning percentile ($> 90\text{th}$ percentile = crowded). |
| **Broad Market Risk Sentiment** | `get_fear_greed_index` | $< 20$ (Extreme Fear), $> 80$ (Extreme Greed). |
| **Crypto Perpetual Derivatives** | `get_funding_rate` | Funding rate $> +0.03\%$ per 8h indicates high long squeeze liquidation risk. |
| **Fixed Income & Real Rates** | `get_treasury_yields` | US 10Y/2Y yield curve slope and nominal sovereign spreads. |
| **Macro Volatility & Dollar** | `get_vix`, `get_dxy` | VIX $> 25.0$ indicates global liquidity contraction. |

## 2. Binary Prediction Markets (Polymarket / Kalshi) SOP
- **Probability Distillation**: Convert share prices ($0.00\text{--}1.00\text{ USD}$) directly into implied market probabilities.
- **Asymmetric Delta Arbitrage**: Compare prediction market odds with official economic consensus surveys (e.g. CME FedWatch vs Polymarket FOMC contract). Where divergence $> 15\%$, flag an asymmetric repricing risk.
- **Search Query Templates via `web_search`**:
  - `"Polymarket Fed interest rate decision odds"`
  - `"Polymarket US CPI release prediction"`
  - `"Kalshi Treasury yield forecast"`

## 3. Perpetual Open Interest & Funding Mechanics (Binance / Bybit / Hyperliquid)
- **Cross-Venue Positioning**: Monitor aggregate Open Interest and Funding Rates across major liquidity venues (Binance, Bybit, Hyperliquid).
- **Price Rising + Open Interest Rising**: Strong institutional capital inflow confirming trend expansion.
- **Price Rising + Open Interest Falling**: Short-covering squeeze; vulnerable to abrupt exhaustion once liquidations taper.
- **Extreme Negative Funding ($< -0.02\%$ per 8h)**: Aggressive retail short chasing; prime setup for short squeeze rally.
