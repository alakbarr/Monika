---
name: audusd_adr_extreme_fade_playbook
description: Average Daily Range extreme stretch fade for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 1.35
profit_factor: 1.15
max_drawdown_pct: 11.49
win_rate: 0.371
---

# AUDUSD Empirical Playbook: Average Daily Range (ADR) Extreme Stretch Fade

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.35 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (194 verified trade executions)
- **Max Drawdown**: 11.5% (Institutional risk profile)
- **Total PnL Return**: +17.1%
- **Win Rate**: 37.1% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Measure 12-hour intraday displacement relative to 14-period ATR.
- Short Trigger: Intraday rise >= 1.5x ATR, Close < Open, and RSI >= 60.
- Long Trigger: Intraday drop <= -1.5x ATR, Close > Open, and RSI <= 40.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if fundamental catalyst causes expansion beyond 2.5x ATR.
- Invalidate if reversal candle shows no buying/selling volume response.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
