---
name: cot-positioning-playbook
description: "COT institutional positioning, smart money vs commercial flows, and bias."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [cot, cftc, macro, positioning, sentiment, currencies, gold, oil]
---

# CFTC Commitments of Traders (COT) Institutional Positioning Playbook

## 1. Overview & Institutional Market Structure
The CFTC Commitments of Traders (COT) report provides weekly transparency into the collective net positioning of major market participants in futures markets. Released every Friday at 15:30 EST (reflecting Tuesday cutoff positions).

Participant Categorization:
1. **Non-Commercial (Large Speculators / Hedge Funds)**:
   - Trend followers and momentum players.
   - Typically correct during strong multi-month trends, but vulnerable to violent squeezes at historical extremes.
2. **Commercial (Hedgers / Producers / Exporters)**:
   - Natural counter-trend participants locking in future prices.
   - Smart money with deep fundamental knowledge of supply/demand constraints.
3. **Non-Reportable (Small Retail Traders)**:
   - Often laggards entering trends near completion.

## 2. Institutional Quant Metrics

### 1. COT Net Positioning Index (Percentile Metric)
Calculates where current Non-Commercial net positioning stands relative to a 3-year (156-week) historical lookback:
$$\text{COT Index} = \frac{\text{Net Pos}_{\text{current}} - \text{Net Pos}_{\text{min}(3\text{y})}}{\text{Net Pos}_{\text{max}(3\text{y})} - \text{Net Pos}_{\text{min}(3\text{y})}} \times 100$$

- **Overcrowded Long (> 85% / Overbought Extreme)**:
  - Smart money long positioning is saturated. High vulnerability to long liquidation cascades on negative fundamental catalysts.
- **Overcrowded Short (< 15% / Oversold Extreme)**:
  - Speculative shorts are heavily crowded. Asymmetric risk profile favoring massive short squeeze rallies on neutral-to-positive surprises.

### 2. Multi-Week Flow Velocity & Turning Points
- **Acceleration Signatures**: Consecutive weeks of $> 10,000$ net contract accumulation indicate strong institutional macro re-allocation.
- **Divergence with Price**: Price makes higher highs while COT Non-Commercial net longs decrease (smart money taking profit into retail buying). Strong early warning of trend exhaustion.

## 3. Integration with Monika Analysis Tools
- `get_cot_report(symbol)`: Fetches current and historical COT net positions, commercial vs non-commercial contracts, and weekly changes.
- `get_macro_priced_in_score(symbol)`: Evaluates whether market consensus has already fully priced in macro direction.
- `get_retail_sentiment(symbol)`: Compare institutional COT positioning against retail sentiment (FXSSI / retail broker long/short ratio) to uncover retail-vs-smart-money divergence.
