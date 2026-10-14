---
name: xauusd_london_expansion_playbook
description: London open volume expansion breakout playbook for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 7.65
profit_factor: 2.29
max_drawdown_pct: 2.84
win_rate: 0.552
---

# XAUUSD Empirical Playbook: London Open Volume Expansion Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 7.65 (Zero-Lookahead simulation)
- **Profit Factor**: 2.29 (29 verified trade executions)
- **Max Drawdown**: 2.8% (Institutional risk profile)
- **Total PnL Return**: +16.2%
- **Win Rate**: 55.2% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Monitor market hours 07:00, 08:00, and 09:00 UTC during European liquidity surge.
- Identify the 7-hour pre-London session high and low boundaries.
- Long Trigger: H1 Close strictly exceeds the 7-hour high with tick volume >= 1.1x 20-MA.
- Short Trigger: H1 Close strictly breaks below the 7-hour low with tick volume >= 1.1x 20-MA.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout bar closes with a rejection wick > 50% of total candle range.
- Invalidate setup if macroeconomic news event occurs within 30 minutes of open.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
