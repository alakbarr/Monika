---
name: gbpusd_adr_extreme_fade_playbook
description: Average Daily Range extreme stretch fade for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.03
profit_factor: 1.09
max_drawdown_pct: 14.12
win_rate: 0.383
---

# GBPUSD Empirical Playbook: Average Daily Range (ADR) Extreme Stretch Fade

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.03 (Zero-Lookahead simulation)
- **Profit Factor**: 1.09 (209 verified trade executions)
- **Max Drawdown**: 14.1% (Institutional risk profile)
- **Total PnL Return**: +10.2%
- **Win Rate**: 38.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Measure 12-hour intraday displacement relative to 14-period ATR.
- Short Trigger: Intraday rise >= 1.5x ATR, Close < Open, and RSI >= 60.
- Long Trigger: Intraday drop <= -1.5x ATR, Close > Open, and RSI <= 40.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if fundamental catalyst causes expansion beyond 2.5x ATR.
- Invalidate if reversal candle shows no buying/selling volume response.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
