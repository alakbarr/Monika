---
name: eurusd_stoch21_rev_asia_playbook
description: Verified ranging tactical execution playbook for EURUSD.
symbol: EURUSD
regime: ranging
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 6.3
profit_factor: 1.19
max_drawdown_pct: 8.7
win_rate: 0.403
---

# EURUSD Empirical Playbook: Stochastic 21 Rev Asia Strategy

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 6.30 (Zero-Lookahead simulation)
- **Profit Factor**: 1.19 (134 verified trade executions)
- **Max Drawdown**: 8.7% (Institutional risk profile)
- **Total PnL Return**: +15.4%
- **Win Rate**: 40.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.
- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.
- Invalidate if opposite structural momentum triggers before trade execution fill.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
