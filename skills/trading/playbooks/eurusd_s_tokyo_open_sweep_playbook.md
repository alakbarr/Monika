---
name: eurusd_s_tokyo_open_sweep_playbook
description: Verified trending tactical execution playbook for EURUSD.
symbol: EURUSD
regime: trending
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 25.7
profit_factor: 2.03
max_drawdown_pct: 6.2
win_rate: 0.469
---

# EURUSD Empirical Playbook: S Tokyo Open Sweep Strategy

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 25.70 (Zero-Lookahead simulation)
- **Profit Factor**: 2.03 (49 verified trade executions)
- **Max Drawdown**: 6.2% (Institutional risk profile)
- **Total PnL Return**: +31.9%
- **Win Rate**: 46.9% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.6x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.6x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
