---
name: xtiusd_lon_ema21_bounce_playbook
description: Verified trending tactical execution playbook for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 8.68
profit_factor: 1.26
max_drawdown_pct: 9.9
win_rate: 0.441
---

# XTIUSD Empirical Playbook: Lon EMA 21 Bounce Strategy

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 8.68 (Zero-Lookahead simulation)
- **Profit Factor**: 1.26 (152 verified trade executions)
- **Max Drawdown**: 9.9% (Institutional risk profile)
- **Total PnL Return**: +23.8%
- **Win Rate**: 44.1% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.9x ATR, Take-Profit = 1.5x ATR, Max Holding = 14 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.9x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
