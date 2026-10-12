---
name: liquidity-and-macro-edge
description: "Liquidity sweeps, macro bias alignment, and volatility regime edge layer."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [liquidity_sweep, macro_bias, volatility_regime, edge_layer, confluence]
---

# Quantitative Edge Layer: Liquidity Sweep, Macro Bias & Volatility

## 1. Edge Tool Suite & Interpretation SOP

### 1.1 `get_liquidity_sweep_context`
- **Workflow Position**: Call during Stage 2 per-asset evaluation before finalizing confluence scorecard.
- **Return Fields**: `{"sweep_detected": bool, "structure_confirmed": bool, "sweep_side": "high"|"low", "sweep_timeframe": str}`
- **Scoring & Interpretation**:
  - If `structure_confirmed == True` AND `sweep_side` aligns with intended trade direction (sweep of low for BUY, sweep of high for SELL):
    - Award $+2$ points bonus to Confluence Score (`liquidity_sweep_confirmed`).
  - **Absence is Non-Disqualifying**: Lack of a liquidity sweep does NOT invalidate a valid Fair Value Gap or Order Block setup.

### 1.2 `get_macro_bias_score`
- **Workflow Position**: Call to verify currency sovereign direction from Stage 1.
- **Return Fields**: `{"base_currency_score": float, "quote_currency_score": float, "net_differential": float, "macro_bias": str}`
- **Server Enforcement**: If Stage 2 trade direction directly contradicts strong macro bias ($|\text{net_differential}| > 2.0$), RiskGate rejects the execution. Verify macro harmony before order submission.

### 1.3 `get_volatility_regime`
- **Workflow Position**: Mandatory check prior to executing breakout strategies.
- **Return Fields**: `{"regime": "trending"|"ranging"|"squeezed"|"turbulent", "chop_block": bool, "atr_percentile": float}`
- **Enforcement Rule**:
  - If `chop_block == True`: Market is compressed in noise. Submit `WAIT` unless a 20-period Donchian channel breakout with volume expansion is confirmed. Server-side RiskGate blocks range breakouts when chop block is active.

### 1.4 `get_volume_profile_context`
- **Workflow Position**: Structural level identification (Point of Control, Value Area High/Low).
- **Return Fields**: `{"poc_price": float, "vah_price": float, "val_price": float, "regime": "balanced"|"imbalanced"}`
- **Tactical Directives**:
  - **Balanced Regime**: Price oscillating inside Value Area. Trade mean-reversion entries from VAH/VAL boundaries back toward POC.
  - **Imbalanced Regime**: Price expanding outside Value Area. Trade trend-continuation pullbacks to the outer value boundary.

## 2. Robust Error Handling Protocol
If any edge tool returns a temporary execution error or empty dictionary:
- Fall back to primary SMC price action (H4 Market Structure + Fair Value Gaps).
- Do not stall analysis or default to WAIT purely due to secondary tool downtime if primary technical confluence meets or exceeds the required threshold.
