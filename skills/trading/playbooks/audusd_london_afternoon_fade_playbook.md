---
name: audusd_london_afternoon_fade_playbook
description: London afternoon liquidity exhaustion fade for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 0.69
profit_factor: 1.07
max_drawdown_pct: 9.36
win_rate: 0.339
---

# AUDUSD Empirical Playbook: London Afternoon Liquidity Exhaustion Fade

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.69 (Zero-Lookahead simulation)
- **Profit Factor**: 1.07 (62 verified trade executions)
- **Max Drawdown**: 9.4% (Institutional risk profile)
- **Total PnL Return**: +2.3%
- **Win Rate**: 33.9% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Active during London afternoon session (15:00 to 17:00 UTC).
- Map the 8-hour London session high and low boundaries.
- Short Trigger: High touches or exceeds 8-hour high and candle closes lower than open.
- Long Trigger: Low touches or drops below 8-hour low and candle closes higher than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body expands beyond session high/low indicating trend run.
- Invalidate during US macroeconomic news announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
