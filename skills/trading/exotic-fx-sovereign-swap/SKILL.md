---
name: exotic-fx-sovereign-swap
description: "Exotic FX analysis (USDZAR, USDTRY, USDMXN) and sovereign credit risk."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [fx_exotics, sovereign_risk, swap_rates, carry_trade, usdzar, usdtry, usdmxn]
---

# Exotic FX, Sovereign Risk & Swap Drag Playbook

## 1. Core Evaluation Pillars

### 1.1 Sovereign Credit Risk & CDS Spreads
- Sovereign 5-Year Credit Default Swap (CDS) spreads represent market-priced sovereign default probability.
- Rapidly widening CDS ($> +50\text{ bps}$ over 10 trading days) dictates structural depreciation pressure on the domestic currency, overriding minor technical support levels.
- Query templates for research synthesis: `"Turkey 5Y CDS spread"`, `"South Africa sovereign CDS spread"`, `"Mexico Banxico policy rate spread"`.

### 1.2 Swap / Carry Drag Ratio Calculation
Before committing to any multi-day swing setup on exotic FX pairs, calculate cumulative swap drag:

```python
import MetaTrader5 as mt5

info = mt5.symbol_info("USDTRY")
# swap_long / swap_short points per lot per day
swap_points_per_day = info.swap_long if direction == "BUY" else info.swap_short
point_value = info.point * info.trade_contract_size

daily_swap_usd = swap_points_per_day * point_value * lot_size
total_projected_swap = abs(daily_swap_usd) * projected_holding_days
swap_drag_ratio = total_projected_swap / projected_tp_usd
```

$$\text{Swap Drag Ratio} = \frac{\text{Projected Holding Days} \times \text{Daily Swap Cost}}{\text{Projected Take Profit (\$)}}$$

- **Execution Gate**: If $\text{Swap Drag Ratio} > 0.20$ (swap eats more than 20% of projected profit), the setup is disqualified.
- **Directional Invariant**: Counter-carry swing trades on high-inflation currencies (e.g. Short USDTRY) are strictly prohibited due to severe negative carry drag ($> 50\%\text{--}80\%$ annualized).

## 2. Pair-Specific Tactical Directives
- **USDTRY (Turkish Lira)**: Permanent structural depreciation and hyperinflation bias. Prohibit short USD positions entirely. Execute long USD pullbacks on D1/H4 Fair Value Gap retests only.
- **USDZAR (South African Rand)**: Commodity-linked high beta FX (sensitive to Gold/Platinum prices and China industrial demand). Highly vulnerable to power utility disruption headlines and fiscal widening.
- **USDMXN (Mexican Peso)**: Nearshoring manufacturing flows anchor medium-term strength. Carry trade is hyper-sensitive to global equity volatility; unwinds aggressively when $VIX > 22.0$.
