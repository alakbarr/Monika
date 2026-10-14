---
name: eurusd_bollinger_reversion_playbook
description: Bollinger Bands volatility mean reversion playbook for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.31
profit_factor: 1.29
max_drawdown_pct: 12.34
win_rate: 0.453
---

# EURUSD Empirical Playbook: Bollinger Bands Volatility Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.31 (Zero-Lookahead simulation)
- **Profit Factor**: 1.29 (137 verified trade executions)
- **Max Drawdown**: 12.3% (Institutional risk profile)
- **Total PnL Return**: +22.3%
- **Win Rate**: 45.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Calculate 20-period Bollinger Bands (2.0 standard deviations) on H1.
- Long Trigger: H1 Low pierces lower band, closes back inside, Close > Open, and RSI <= 42.
- Short Trigger: H1 High pierces upper band, closes back inside, Close < Open, and RSI >= 58.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if band width contracts below 0.25% indicating volatility squeeze rather than range.
- Invalidate if price closes consecutively outside the bands.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
