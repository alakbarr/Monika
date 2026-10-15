---
name: audusd_rsi14_rev_all_playbook
description: Verified trending tactical execution playbook for AUDUSD.
symbol: AUDUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 12.86
profit_factor: 1.41
max_drawdown_pct: 7.3
win_rate: 0.443
---

# AUDUSD Empirical Playbook: RSI 14 Rev All Strategy

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 12.86 (Zero-Lookahead simulation)
- **Profit Factor**: 1.41 (61 verified trade executions)
- **Max Drawdown**: 7.3% (Institutional risk profile)
- **Total PnL Return**: +15.7%
- **Win Rate**: 44.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.6x ATR, Take-Profit = 1.2x ATR, Max Holding = 10 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.6x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 10 bars.
