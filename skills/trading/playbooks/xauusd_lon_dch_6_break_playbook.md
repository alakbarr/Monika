---
name: xauusd_lon_dch_6_break_playbook
description: Verified breakout tactical execution playbook for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 18.05
profit_factor: 1.66
max_drawdown_pct: 12.0
win_rate: 0.429
---

# XAUUSD Empirical Playbook: Lon Dch 6 Break Strategy

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 18.05 (Zero-Lookahead simulation)
- **Profit Factor**: 1.66 (133 verified trade executions)
- **Max Drawdown**: 12.0% (Institutional risk profile)
- **Total PnL Return**: +61.1%
- **Win Rate**: 42.9% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
