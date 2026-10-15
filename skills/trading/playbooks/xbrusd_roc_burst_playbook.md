---
name: xbrusd_roc_burst_playbook
description: Rate of change momentum velocity surge for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 2.13
status: active
sharpe_ratio: 1.13
profit_factor: 1.11
max_drawdown_pct: 13.55
win_rate: 0.372
---

# XBRUSD Empirical Playbook: Rate of Change Momentum Velocity Surge

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.13 (Zero-Lookahead simulation)
- **Profit Factor**: 1.11 (239 verified trade executions)
- **Max Drawdown**: 13.6% (Institutional risk profile)
- **Total PnL Return**: +14.8%
- **Win Rate**: 37.2% (Normalized at minimum 1:2.13 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.2x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Monitor 6-period Rate of Change (ROC) and 20-period volume moving average.
- Long Trigger: ROC expands above surge threshold with Volume >= 1.25x 20-MA and Close > EMA 20.
- Short Trigger: ROC drops below negative threshold with Volume >= 1.25x 20-MA and Close < EMA 20.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.13 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body retraces more than 50% on following bar.
- Invalidate if volume fails to maintain institutional expansion.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
