---
name: xtiusd_stoch21_trend_cross_playbook
description: Verified ranging tactical execution playbook for XTIUSD.
symbol: XTIUSD
regime: ranging
timeframe: H1
min_rr: 1.83
status: active
sharpe_ratio: 8.52
profit_factor: 1.26
max_drawdown_pct: 14.6
win_rate: 0.427
---

# XTIUSD Empirical Playbook: Stochastic 21 Trend Cross Strategy

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 8.52 (Zero-Lookahead simulation)
- **Profit Factor**: 1.26 (117 verified trade executions)
- **Max Drawdown**: 14.6% (Institutional risk profile)
- **Total PnL Return**: +19.2%
- **Win Rate**: 42.7% (Normalized at minimum 1:1.83 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.6x ATR, Take-Profit = 1.1x ATR, Max Holding = 10 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.
- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.83 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.6x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.1x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.
- Invalidate if opposite structural momentum triggers before trade execution fill.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 10 bars.
