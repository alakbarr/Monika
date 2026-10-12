---
name: commodity-analysis
description: "Institutional analysis framework for Gold (XAUUSD) and Crude Oil (XTIUSD)."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [commodity, oil, xtiusd, xauusd, eia, opec, energy, inventory, gold]
---

# Commodity Analysis Framework — XAUUSD & Energy (XTIUSD / XBRUSD)

## Part 1: Gold (XAUUSD) Institutional Mechanics

### Primary Macro Valuation Drivers
1. **US 10Y Real Yields (TIPS)**: Gold operates as a zero-yielding monetary reserve asset. Real yield correlation is intensely negative ($-0.75$ to $-0.90$).
   - Real Yields rising ($> +2.00\%$) $\rightarrow$ Heavy structural headwind on spot gold.
   - Real Yields falling or negative $\rightarrow$ Multi-week institutional accumulation.
2. **Central Bank Net Purchases**: Track sovereign reserve diversification flows (PBoC, RBI, CBR). Structural physical floor.
3. **Geopolitical Flight-to-Safety**: Immediate spike driver upon escalation; fades once military theater stabilizes unless real yields compress simultaneously.

### Technical & Execution Rules for XAUUSD
- **Spread & Volatility Calibration**: Normal spread is 1.5–3.5 pips. During London/NY overlap, normal M1 ATR is \$1.50–\$3.00.
- **Mandatory Stop Loss Sizing**: Stop Loss distance MUST be $\ge 1.1\times$ verified H4 ATR(14). Never place tighter stops on gold due to deep stop-hunting sweeps.
- **Key Liquidity Pools**: Asian session high/low sweep during early London (07:00–09:00 UTC) is the primary intraday setup.

---

## Part 2: WTI & Brent Crude Oil (XTIUSD / XBRUSD)

### Energy Driver Hierarchy
1. **EIA Weekly Petroleum Status Report (Wednesdays 14:30 UTC)**:
   - Tool: `get_eia_oil_inventory`
   - Crude inventory draw $> -2.5\text{M}$ bbl vs consensus $\rightarrow$ Decisive bullish impulse ($+1.5\%$ to $+3.0\%$).
   - Crude inventory build $> +2.5\text{M}$ bbl vs consensus $\rightarrow$ Decisive bearish liquidation.
   - Cross-verify Cushing, Oklahoma hub stocks and Strategic Petroleum Reserve (SPR) transfers.
2. **OPEC+ Production Quotas & Ministerial Meetings**:
   - Classify OPEC+ announcements as Tier-1 macroeconomic volatility hurdles.
   - Pre-meeting whisper leaks emerge 24–48 hours in advance; reduce trade sizing by $50\%$ within 48h of scheduled ministerial conferences.
3. **Seasonal Demand & Refinery Cycles**:
   - **Summer Driving Season (May–August)**: Peak gasoline demand, bullish baseline crack spreads.
   - **Refinery Turnaround Window (February–April & September–October)**: Scheduled maintenance reduces crude intake at Gulf Coast refiners; creates temporary physical surplus.
   - **Winter Heating Season (November–February)**: Distillate and heating oil drawdowns support sweet crude benchmarks.

### Cross-Asset Correlation Reference
| Asset Pair | Expected Correlation | Interpretation & Regime |
|:---|:---|:---|
| XTIUSD vs DXY | $-0.60\text{ to }-0.80$ | Dollar strength exerts downward pricing pressure on USD-denominated commodities. |
| XTIUSD vs S&P 500 | $+0.30\text{ to }+0.50$ | Positive during growth-driven risk-on expansions; breaks down during supply shocks. |
| XAUUSD vs DXY | $-0.70\text{ to }-0.85$ | Standard dollar denominator effect. |
| XAUUSD vs US 10Y TIPS | $-0.80\text{ to }-0.95$ | Sovereign real interest rate opportunity cost anchor. |

### Technical & Risk Invariants for Energy
- Institutional round psychological numbers (\$65.00, \$70.00, \$75.00, \$80.00, \$85.00) serve as dominant order block magnets.
- Mandatory Stop Loss Buffer: $\ge 1.2\times$ H4 ATR(14).
- Friday Execution Rule: Prohibit opening new energy positions within 3 hours of Friday market close to eliminate geopolitical weekend gap exposure.
