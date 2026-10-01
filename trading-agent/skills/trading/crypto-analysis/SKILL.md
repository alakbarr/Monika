---
name: crypto-analysis
description: "Cryptocurrency framework for BTCUSD: on-chain, funding, and ETF flows."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [crypto, btcusd, etf_flows, funding_rate, fear_greed, digital_assets]
---

# Cryptocurrency Analysis Framework — BTCUSD

> **Runtime Variable Resolution**: Placeholders like `{effective_threshold}` are dynamically injected by the skill loader at execution time from active settings. Default confluence threshold: `7/14`.

## Institutional Driver Hierarchy
1. **US Spot ETF Net Inflow Dynamics**:
   - Institutional spot ETF flows represent the dominant marginal spot price setter.
   - Aggregate daily net inflow $> +\$300\text{M}$ $\rightarrow$ High-probability continuation of macro bullish trend.
   - Consecutive net outflows $> 3$ consecutive days $\rightarrow$ Institutional distribution regime; prohibit breakout longs.
2. **Perpetual Futures Funding Rate & Open Interest (Microstructure)**:
   - Tool: `get_funding_rate`
   - **Extreme Positive Funding ($> +0.03\%$ per 8h / $+30\%$ annualized)**: Retail overleveraged long; high liquidation cascade vulnerability to downside.
   - **Extreme Negative Funding ($< -0.02\%$ per 8h)**: Aggressive short chasing; prime conditions for violent short squeeze to upside.
   - Rapid OI expansion alongside flat spot price $\rightarrow$ Impending volatility breakout.
3. **Macro Liquidity & US Equities Beta**:
   - High positive correlation ($0.65$ to $0.85$) with NASDAQ 100 during monetary expansion cycles.
   - Risk-Off Flash Trigger: When VIX spikes $> 25.0$, crypto assets experience immediate liquidity drainage ($5\%\text{--}12\%$ intraday drawdowns). Prohibit entering new long setups during active VIX expansion.
4. **Sentiment & On-Chain Positioning Indicators**:
   - Tool: `get_fear_greed_index`
   - Extreme Fear ($< 20$): Contrarian accumulation bias ONLY when higher-timeframe weekly structure remains intact.
   - Extreme Greed ($> 80$): Strict trailing stop management; take-profit targets tightened to 50% ADR.

## Technical & Execution Rules for BTCUSD
- **24/7 Market Structure**: Use 7-day lookback for Average Daily Range calculation (via `get_daily_range_context`).
- **Optimal Liquidity Hours**: Highest execution quality occurs during London/NY overlap (12:00–20:00 UTC).
- **Weekend Liquidity Caveat**: Saturday–Sunday spreads widen by $40\%\text{--}80\%$ and trading volume drops $> 50\%$. Do not trade lower-timeframe breakouts during weekend hours; expect range-bound chop and false liquidity sweeps.
- **Mandatory Position Sizing & SL Buffer**:
  - Reduce risk sizing to $0.60\%$ equity (down $40\%$ from FX baseline).
  - Stop Loss distance MUST maintain $\ge 1.2\times$ verified H4 ATR(14) to survive crypto stop sweeps.
  - Confluence threshold: `{effective_threshold}/14`.
