---
name: eurusd_tokyo_sweep_12_playbook
description: Verified trending tactical execution playbook for EURUSD.
symbol: EURUSD
regime: trending
timeframe: H1
min_rr: 2.2
status: active
sharpe_ratio: 14.49
profit_factor: 1.49
max_drawdown_pct: 7.0
win_rate: 0.409
---

# EURUSD Empirical Playbook: Tokyo Sweep 12 Strategy

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 14.49 (Zero-Lookahead simulation)
- **Profit Factor**: 1.49 (88 verified trade executions)
- **Max Drawdown**: 7.0% (Institutional risk profile)
- **Total PnL Return**: +28.3%
- **Win Rate**: 40.9% (Normalized at minimum 1:2.2 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.2x ATR, Max Holding = 18 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.2 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
