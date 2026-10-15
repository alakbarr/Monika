---
name: xbrusd_london_lunch_fade_playbook
description: London midday session mean reversion for XBRUSD.
symbol: XBRUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 5.59
profit_factor: 1.32
max_drawdown_pct: 4.23
win_rate: 0.407
---

# XBRUSD Empirical Playbook: London Midday Session Mean Reversion Fade

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.59 (Zero-Lookahead simulation)
- **Profit Factor**: 1.32 (27 verified trade executions)
- **Max Drawdown**: 4.2% (Institutional risk profile)
- **Total PnL Return**: +5.1%
- **Win Rate**: 40.7% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.6x ATR, Max Holding = 14 bars

## Trigger Conditions & Tactical Directives
- Active during European midday lull (11:00 to 12:00 UTC).
- Long Trigger: RSI <= 36 and candle prints bullish rejection close.
- Short Trigger: RSI >= 64 and candle prints bearish rejection close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price breaks session high/low with increasing volume.
- Invalidate if held past New York open (13:00 UTC).
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
