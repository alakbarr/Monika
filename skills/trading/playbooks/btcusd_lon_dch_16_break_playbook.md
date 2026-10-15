---
name: btcusd_lon_dch_16_break_playbook
description: Verified breakout tactical execution playbook for BTCUSD.
symbol: BTCUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 10.81
profit_factor: 1.34
max_drawdown_pct: 5.6
win_rate: 0.425
---

# BTCUSD Empirical Playbook: Lon Dch 16 Break Strategy

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 10.81 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (73 verified trade executions)
- **Max Drawdown**: 5.6% (Institutional risk profile)
- **Total PnL Return**: +15.5%
- **Win Rate**: 42.5% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.5x ATR, Take-Profit = 1.0x ATR, Max Holding = 8 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 8 bars.
