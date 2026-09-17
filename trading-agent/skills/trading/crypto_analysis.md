# file: skills/crypto_analysis.md

# Crypto Analysis Framework — BTCUSD

## Driver Hierarchy
1. **Spot ETF Net Flows**: Large inflows (+$500M+) = institutional accumulation (bullish). Net outflows = distribution.
2. **Macro Risk-On/Off**: NASDAQ/SPX correlation 0.6-0.8. VIX > 25 → BTC sells off 5-15% quickly (AVOID new entries).
3. **Fear & Greed Index**: Tool `get_fear_greed_index`. <25 = Extreme Fear (contrarian long if macro aligned); >75 = Extreme Greed (elevated correction risk).
4. **Funding Rate**: >+0.05% = crowded long (reversal risk); <-0.05% = crowded short (short squeeze risk).

## Technical & Entry Rules
- Major levels: $50k, $60k, $70k, $80k, $90k, $100k.
- 24/7 market: 7-day ADR lookback (see `get_daily_range_context`).
- Peak volume: 12:00-20:00 UTC. Weekends = lower liquidity & stop hunt risk.
- Position sizing: reduce lot size by 40-50% vs FX pairs due to high volatility.
- Threshold: {effective_threshold}/14.
