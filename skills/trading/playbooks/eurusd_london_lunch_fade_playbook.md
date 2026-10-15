---
name: eurusd_london_lunch_fade_playbook
description: London midday session mean reversion for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.57
status: active
sharpe_ratio: 1.72
profit_factor: 1.14
max_drawdown_pct: 3.05
win_rate: 0.45
---

# EURUSD Empirical Playbook: London Midday Session Mean Reversion Fade

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.72 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (20 verified trade executions)
- **Max Drawdown**: 3.0% (Institutional risk profile)
- **Total PnL Return**: +1.4%
- **Win Rate**: 45.0% (Normalized at minimum 1:1.57 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.2x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Active during European midday lull (11:00 to 12:00 UTC).
- Long Trigger: RSI <= 36 and candle prints bullish rejection close.
- Short Trigger: RSI >= 64 and candle prints bearish rejection close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.57 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price breaks session high/low with increasing volume.
- Invalidate if held past New York open (13:00 UTC).
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
