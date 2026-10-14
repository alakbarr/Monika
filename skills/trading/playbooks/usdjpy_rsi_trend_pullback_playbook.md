---
name: usdjpy_rsi_trend_pullback_playbook
description: RSI midpoint trend retest continuation for USDJPY.
symbol: USDJPY
regime: trending
timeframe: H1
min_rr: 1.8
status: active
sharpe_ratio: 1.63
profit_factor: 1.12
max_drawdown_pct: 12.04
win_rate: 0.423
---

# USDJPY Empirical Playbook: RSI Midpoint Trend Retest Continuation

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.63 (Zero-Lookahead simulation)
- **Profit Factor**: 1.12 (104 verified trade executions)
- **Max Drawdown**: 12.0% (Institutional risk profile)
- **Total PnL Return**: +6.2%
- **Win Rate**: 42.3% (Normalized at minimum 1:1.8 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.8x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Trend filter: Close > EMA 50 (Bull) or Close < EMA 50 (Bear).
- Long Trigger: RSI pulls back into 40-50 zone and candle closes higher than open.
- Short Trigger: RSI pulls back into 50-60 zone and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.8 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if RSI drops below 35 in bull trend or rises above 65 in bear trend.
- Invalidate if price prints structural lower low.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
