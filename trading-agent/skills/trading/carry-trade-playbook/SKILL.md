---
name: carry-trade-playbook
description: "Currency carry trade selection, rate differentials, and funding risk."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [carry_trade, interest_rates, central_banks, swap_rates, sofr, funding_stress, g10_divergence]
---

# Systematic Carry Trade & Interest Rate Differential Playbook

> **Core Thesis**: In low-volatility macro regimes, capital flows from low-yielding funding currencies (JPY, CHF, EUR) into higher-yielding investment currencies (USD, GBP, AUD, NZD, MXN). However, carry trades suffer violent unwind risks during volatility shocks.

---

## 1. The Carry-to-Risk Metric

Never rank carry trades on raw nominal interest rate spread alone. High yield is useless if currency volatility wipes out the carry.

$$\text{Carry-to-Risk Ratio} = \frac{\text{Rate Differential (\%)}}{\text{Annualized FX Volatility (\%)}}$$

- **Target Carry-to-Risk $\ge 0.40$**: High quality, institutional-grade carry.
- **Carry-to-Risk $0.25 - 0.40$**: Moderate; requires strict trailing stops.
- **Carry-to-Risk $< 0.25$**: Unattractive; carry return does not compensate for exchange rate variance.

---

## 2. Market Regime & Liquidity Filter (Mandatory Pre-Check)

Carry trades must be filtered against systemic funding stress:
1. **ICE BofA High Yield OAS**:
   - $< 380$ bps: **BENIGN**. Carry trades favorable.
   - $380 - 450$ bps: **ELEVATED RISK**. Reduce carry allocation by 50%.
   - $> 450$ bps: **LIQUIDATION REGIME**. Prohibit new carry longs; close or hedge existing carry.
2. **VIX Filter**:
   - $\text{VIX} < 18$: Optimal carry environment.
   - $\text{VIX} \ge 25$: High risk of carry unwind (flight to safe havens USD/CHF/JPY).
3. **Central Bank Reaction Trajectory**:
   - Favor carry where high-rate central bank is maintaining higher-for-longer (or hiking) while low-rate central bank is cutting.

---

## 3. Execution Protocol

When a user inquires about carry trades:
1. Call `get_carry_trade_rankings(top_n=5)`.
2. Call `get_fed_net_liquidity_and_stress()` to verify funding conditions (SOFR & HY OAS).
3. Present:
   - Ranked pairs with net rate differentials.
   - Daily swap credit / debit impact.
   - Systemic stress verdict (Safe vs Warning).
   - Invalidation level (e.g. key daily support level where technical breakdown triggers emergency unwind).
