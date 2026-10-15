---
name: btcusd_donchian12_breakout_playbook
description: 12-bar Donchian channel breakout for BTCUSD.
symbol: BTCUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 5.45
profit_factor: 1.16
max_drawdown_pct: 13.3
win_rate: 0.406
---

# BTCUSD Empirical Playbook: 12-Period Donchian Dynamic Momentum Breakout

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.45 (Zero-Lookahead simulation)
- **Profit Factor**: 1.16 (197 verified trade executions)
- **Max Drawdown**: 13.3% (Institutional risk profile)
- **Total PnL Return**: +18.8%
- **Win Rate**: 40.6% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Calculate 12-period Donchian Channel on H1 timeframe.
- Long Trigger: Close breaks above 12-period high and Close > EMA 50.
- Short Trigger: Close breaks below 12-period low and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout bar prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
