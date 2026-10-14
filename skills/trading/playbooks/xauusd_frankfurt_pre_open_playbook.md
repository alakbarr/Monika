---
name: xauusd_frankfurt_pre_open_playbook
description: Frankfurt pre-open liquidity breakout playbook for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 9.12
profit_factor: 2.49
max_drawdown_pct: 3.95
win_rate: 0.594
---

# XAUUSD Empirical Playbook: Frankfurt Pre-Open Liquidity Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 9.12 (Zero-Lookahead simulation)
- **Profit Factor**: 2.49 (32 verified trade executions)
- **Max Drawdown**: 4.0% (Institutional risk profile)
- **Total PnL Return**: +21.0%
- **Win Rate**: 59.4% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Active during Frankfurt opening hour (06:00 UTC) preceding London open.
- Long Trigger: Price breaks above the 6-hour Asian range high and Close > Open.
- Short Trigger: Price breaks below the 6-hour Asian range low and Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price re-enters Asian box before 07:00 UTC.
- Invalidate if spread widens abnormally during pre-market transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
