---
name: options-volatility-hedging
description: "Options volatility smiles, 25D risk reversal skews, and delta-neutral hedges."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [options, implied_volatility, iv_surface, greeks, delta_hedging, risk_reversal, butterfly]
---

# Options Implied Volatility Surface & Spot Delta-Hedging Playbook

> **Scope**: Analytical calculation of options pricing, Greeks (Delta, Gamma, Vega, Theta), IV surface smile, and spot market delta rebalancing. Does not require direct broker option order submission.

---

## 1. Implied Volatility Surface Decomposition

FX options trade on volatility quotes rather than cash dollar premiums:
- **ATM Volatility ($\sigma_{atm}$)**: The baseline pricing of market uncertainty for a given expiry.
- **25-Delta Risk Reversal ($RR_{25}$)**:
  $$RR_{25} = \sigma_{25D, \text{Call}} - \sigma_{25D, \text{Put}}$$
  - $RR_{25} > 0$: **Call Skew**. Market paying premium for upside protection (Bullish sentiment).
  - $RR_{25} < 0$: **Put Skew**. Market paying premium for downside protection (Bearish sentiment).
- **25-Delta Butterfly ($BF_{25}$)**:
  $$BF_{25} = \frac{\sigma_{25D, \text{Call}} + \sigma_{25D, \text{Put}}}{2} - \sigma_{atm}$$
  - Measures the "fatness" of tail-risk distributions (Kurtosis / black swan pricing).

---

## 2. Spot Delta-Hedging Workflow

To neutralize directional market exposure on an option or synthetic position:
1. **Compute Portfolio Delta**:
   $$\Delta_{\text{net}} = \sum_i Q_i \cdot \Delta_i \times \text{Contract Size}$$
2. **Determine Spot Hedge Order**:
   $$\text{Hedge Lots} = -\frac{\Delta_{\text{net}}}{\text{Standard Lot Size}}$$
3. **Rebalancing Frequency**:
   - Rebalance dynamically when $|\Delta_{\text{net}}| > 0.10$ standard lots or when market spot moves $> 1.0\times$ ATR.
