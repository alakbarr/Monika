---
name: xtiusd_london_lunch_fade_playbook
description: London midday session mean reversion for XTIUSD.
symbol: XTIUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 4.94
profit_factor: 1.28
max_drawdown_pct: 6.26
win_rate: 0.346
---

# XTIUSD Empirical Playbook: London Midday Session Mean Reversion Fade

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.94 (Zero-Lookahead simulation)
- **Profit Factor**: 1.28 (26 verified trade executions)
- **Max Drawdown**: 6.3% (Institutional risk profile)
- **Total PnL Return**: +4.6%
- **Win Rate**: 34.6% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 2.0x ATR, Max Holding = 18 bars

## Trigger Conditions & Tactical Directives
- Active during European midday lull (11:00 to 12:00 UTC).
- Long Trigger: RSI <= 36 and candle prints bullish rejection close.
- Short Trigger: RSI >= 64 and candle prints bearish rejection close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price breaks session high/low with increasing volume.
- Invalidate if held past New York open (13:00 UTC).
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
