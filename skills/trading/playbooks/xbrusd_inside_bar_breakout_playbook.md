---
name: xbrusd_inside_bar_breakout_playbook
description: Inside bar compression volatility breakout for XBRUSD.
symbol: XBRUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.42
profit_factor: 1.16
max_drawdown_pct: 12.35
win_rate: 0.413
---

# XBRUSD Empirical Playbook: Inside Bar Compression Volatility Breakout

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.42 (Zero-Lookahead simulation)
- **Profit Factor**: 1.16 (150 verified trade executions)
- **Max Drawdown**: 12.3% (Institutional risk profile)
- **Total PnL Return**: +13.6%
- **Win Rate**: 41.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Identify Inside Bar: High[i-1] <= High[i-2] and Low[i-1] >= Low[i-2].
- Long Trigger: H1 Close breaks strictly above inside bar high and Close > EMA 50.
- Short Trigger: H1 Close breaks strictly below inside bar low and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout bar fails to close beyond the mother bar boundary.
- Invalidate if price chops inside the range for more than 4 bars after signal.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
