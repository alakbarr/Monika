---
name: macro-yield-curve-regimes
description: "Institutional framework for 4-quadrant yield curve dynamics, spread steepening/flattening, and FX/asset transmission."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [yield_curve, 2s10s, steepener, flattener, bonds, treasury, macro, interest_rates, fx_transmission]
---

# Macro Yield Curve Regimes — 4-Quadrant Dynamics, Term Premia & Cross-Asset Transmission

Institutional framework for evaluating government bond yield curve shifts (US 2Y, 10Y, 30Y), slope dynamics (2s10s, 3m10s), and deterministic transmission mechanisms to Foreign Exchange (FX), Equities, and Commodities.

---

## 1. Core Foundational Principle

The yield curve is the bond market's collective pricing of the future path of monetary policy, inflation risk, and sovereign term premium.

A naive observer looks only at the nominal level of 10-year yields. An institutional macro trader analyzes **the slope (spread)** and **the shift direction** across maturities:
$$\text{Spread}_{2s10s} = Y_{10Y} - Y_{2Y}$$

The direction of spread change (Steepening vs. Flattening) combined with the direction of outright yields (Bull vs. Bear) defines **Four Distinct Economic & Market Regimes**.

---

## 2. The 4-Quadrant Yield Curve Matrix

| Yield Curve Regime | Short Yield ($Y_{2Y}$) | Long Yield ($Y_{10Y}$) | Spread Slope ($\Delta \text{Spread}$) | Primary Economic Driver | FX & Cross-Asset Transmission Mechanics |
|:---|:---:|:---:|:---:|:---|:---|
| **Bull Steepener** | $\Downarrow\Downarrow$ (Drops fast) | $\Downarrow$ (Drops slower) | **Steepening** ($\uparrow$) | **Monetary Easing / Recessionary Shock**.<br>Central bank cuts rates aggressively or market prices emergency cuts due to growth collapse or banking stress. | • **USD**: Strongly Bearish (short rates plummet, yield advantage vanishes).<br>• **Carry Trades**: Violent Unwind. High-yielding currencies plummet against low-yielding funding currencies (e.g., massive USDJPY plunge, EURJPY sell-off).<br>• **Gold (XAU)**: Strongly Bullish (real rates collapse, safe haven demand).<br>• **Equities**: Volatile initial sell-off, then aggressive recovery once easing takes hold. |
| **Bear Steepener** | $\leftrightarrow / \uparrow$ (Stable or slow up) | $\Uparrow\Uparrow$ (Surges fast) | **Steepening** ($\uparrow$) | **Fiscal Expansion / Debt Supply / Sticky Inflation**.<br>Heavy government bond issuance (Treasury supply shock), rising inflation expectations, or higher sovereign term premium. | • **USD**: Mixed to Bullish (liquidity strain and capital attracted by high nominal long yields, unless sovereign credit risk dominates).<br>• **Carry Trades**: Strained. Rising global discount rate tightens financial conditions.<br>• **Gold (XAU)**: Dependent on Real Yields. If driven by inflation breakevens $\implies$ Bullish; if driven by real yield surge $\implies$ Bearish headwind.<br>• **Equities**: Multiple compression, tech/growth stocks sell off. |
| **Bull Flattener** | $\leftrightarrow / \Downarrow$ (Stable or drops slow) | $\Downarrow\Downarrow$ (Drops fast) | **Flattening** ($\downarrow$) | **Disinflation / Structural Slowdown**.<br>Inflation cooling rapidly, market prices long-term growth plateau without immediate panic rate cuts. | • **USD**: Mild Bearish to Range-bound.<br>• **Bonds**: Aggressive duration rally (long-end Treasuries surge).<br>• **Growth Stocks**: Strongly Bullish (lower discount rates boost long-duration cash flows).<br>• **Commodities**: Deflationary headwind (oil and industrial metals struggle). |
| **Bear Flattener** | $\Uparrow\Uparrow$ (Surges fast) | $\Uparrow$ (Surges slower) | **Flattening** ($\downarrow$) | **Central Bank Hawkish Shock / Inversion Pressure**.<br>Central bank hikes aggressively or delays cuts to crush sticky inflation. Precursor to curve inversion. | • **USD**: Strongly Bullish (short rate yield differential widens sharply in favor of USD).<br>• **Carry Trades**: Favors USD against low-yielding currencies (e.g. USDJPY rally, AUDUSD sell-off).<br>• **Gold (XAU)**: Bearish (rising real yields and opportunity cost of holding non-yielding bullion).<br>• **Equities**: Broad sell-off across all sectors due to liquidity drain. |

---

## 3. Spread Thresholds & Inversion Mechanics

1. **The Inversion Line ($0.0$ bps)**:
   - When $Y_{10Y} - Y_{2Y} < 0$, the curve is **Inverted** (classic recession warning, historical lead time 12–18 months).
   - Inversion itself does *not* trigger the recession; the **Un-inversion** (transition from inverted back to positive via Bull Steepener) marks the immediate onset of the crisis window.
2. **Current Cycle Slope Boundaries**:
   - Deeply Inverted: $\text{Spread} < -25$ bps (Maximum policy restriction).
   - Flat / Near-Zero: $-10 \text{ bps} \le \text{Spread} \le +15 \text{ bps}$ (Regime pivot / transitional ambiguity).
   - Normalized Slope: $+20 \text{ bps} \le \text{Spread} \le +60 \text{ bps}$ (Mid-cycle expansion or disinflationary normalization).
   - Steep Slope: $\text{Spread} > +80$ bps (Late-stage easing recovery or severe fiscal term premium expansion).

---

## 4. Multi-Channel FX Transmission Protocol

When synthesizing Stage 1 Fundamental Brief, evaluate the yield curve state through this decision tree:

```
[Is 2s10s Spread Steepening or Flattening?]
    ├── STEEPENING:
    │     ├── Are 2Y yields dropping faster than 10Y?
    │     │     └── YES ⟹ BULL STEEPENER:
    │     │           • USD Bias: BEARISH
    │     │           • JPY Bias: BULLISH (Carry unwind)
    │     │           • XAU Bias: BULLISH
    │     └── Are 10Y yields surging faster than 2Y?
    │           └── YES ⟹ BEAR STEEPENER:
    │                 • USD Bias: BULLISH (Term premium squeeze)
    │                 • Equities/Tech: BEARISH
    │                 • XTI/Oil: Check demand vs. inflation
    └── FLATTENING:
          ├── Are 10Y yields dropping while 2Y stays firm?
          │     └── YES ⟹ BULL FLATTENER:
          │           • USD Bias: NEUTRAL / MILD BEARISH
          │           • High-Beta Risk Assets: BULLISH
          └── Are 2Y yields surging faster than 10Y?
                └── YES ⟹ BEAR FLATTENER:
                      • USD Bias: STRONG BULLISH
                      • High-Beta Risk Assets: BEARISH
                      • XAU Bias: BEARISH
```

---

## 5. Synthesis Directives for Stage 1 Model

1. **State Explicit Regime**:
   In `SubmitFundamentalBriefSchema`, assign `yield_curve_regime` to one of:
   `"bull_steepener"`, `"bear_steepener"`, `"bull_flattener"`, `"bear_flattener"`, or `"neutral"`.
2. **Cite Actual Spread & Shift**:
   State numerical 2Y, 10Y yields and the 2s10s spread in basis points (e.g. `US10Y 4.25% - US02Y 3.95% = +30 bps (Bull Steepener)`).
3. **Guard Against Superficial Yield Analysis**:
   Never write "Yields rose so USD is bullish" without checking whether the rise was driven by short rates (hawkish Fed = USD bullish) or long-end sovereign risk premium (fiscal worry = USD vulnerable).
