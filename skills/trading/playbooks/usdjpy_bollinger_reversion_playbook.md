---
name: usdjpy_bollinger_reversion_playbook
description: Bollinger Bands volatility mean reversion playbook for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 4.37
profit_factor: 1.34
max_drawdown_pct: 6.76
win_rate: 0.493
---

# USDJPY Empirical Playbook: Bollinger Bands Volatility Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.37 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (140 verified trade executions)
- **Max Drawdown**: 6.8% (Institutional risk profile)
- **Total PnL Return**: +24.8%
- **Win Rate**: 49.3% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 1.8x ATR, Max Holding = 14 bars

## Trigger Conditions & Tactical Directives
- Calculate 20-period Bollinger Bands (2.0 standard deviations) on H1.
- Long Trigger: H1 Low pierces lower band, closes back inside, Close > Open, and RSI <= 42.
- Short Trigger: H1 High pierces upper band, closes back inside, Close < Open, and RSI >= 58.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if band width contracts below 0.25% indicating volatility squeeze rather than range.
- Invalidate if price closes consecutively outside the bands.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
