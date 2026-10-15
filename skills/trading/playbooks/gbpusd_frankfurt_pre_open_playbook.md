---
name: gbpusd_frankfurt_pre_open_playbook
description: Frankfurt pre-open liquidity breakout playbook for GBPUSD.
symbol: GBPUSD
regime: breakout
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 3.4
profit_factor: 1.24
max_drawdown_pct: 6.62
win_rate: 0.459
---

# GBPUSD Empirical Playbook: Frankfurt Pre-Open Liquidity Breakout

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.40 (Zero-Lookahead simulation)
- **Profit Factor**: 1.24 (37 verified trade executions)
- **Max Drawdown**: 6.6% (Institutional risk profile)
- **Total PnL Return**: +4.7%
- **Win Rate**: 45.9% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 1.8x ATR, Max Holding = 16 bars

## Trigger Conditions & Tactical Directives
- Active during Frankfurt opening hour (06:00 UTC) preceding London open.
- Long Trigger: Price breaks above the 6-hour Asian range high and Close > Open.
- Short Trigger: Price breaks below the 6-hour Asian range low and Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price re-enters Asian box before 07:00 UTC.
- Invalidate if spread widens abnormally during pre-market transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
