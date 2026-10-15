---
name: btcusd_volatility_squeeze_playbook
description: Carter volatility squeeze expansion breakout for BTCUSD.
symbol: BTCUSD
regime: breakout
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 2.04
profit_factor: 1.23
max_drawdown_pct: 6.9
win_rate: 0.345
---

# BTCUSD Empirical Playbook: Carter Volatility Squeeze Expansion Breakout

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.04 (Zero-Lookahead simulation)
- **Profit Factor**: 1.23 (29 verified trade executions)
- **Max Drawdown**: 6.9% (Institutional risk profile)
- **Total PnL Return**: +4.1%
- **Win Rate**: 34.5% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Detect squeeze condition: Bollinger Bands compress strictly inside Keltner Channels.
- Long Trigger: Squeeze fires long as Upper BB expands above Keltner and Close > EMA 50.
- Short Trigger: Squeeze fires short as Lower BB expands below Keltner and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if squeeze fires and immediately reverses inside prior 2-bar low/high.
- Invalidate if ATR contracts by more than 30% during the breakout candle.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
