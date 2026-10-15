---
name: eurusd_turtle_soup_sweep_playbook
description: Turtle soup false breakout sweep for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.0
profit_factor: 1.12
max_drawdown_pct: 10.49
win_rate: 0.414
---

# EURUSD Empirical Playbook: Turtle Soup 20-Bar False Breakout Reversal

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.00 (Zero-Lookahead simulation)
- **Profit Factor**: 1.12 (157 verified trade executions)
- **Max Drawdown**: 10.5% (Institutional risk profile)
- **Total PnL Return**: +9.9%
- **Win Rate**: 41.4% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Map 20-period swing high and swing low boundaries.
- Long Trigger: Low pierces 20-bar low but closes back above with bullish bar.
- Short Trigger: High pierces 20-bar high but closes back below with bearish bar.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if subsequent candle breaks the extreme wick tip.
- Invalidate if volume exceeds 2.0x 20-period volume MA.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
