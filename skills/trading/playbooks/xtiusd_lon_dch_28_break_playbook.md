---
name: xtiusd_lon_dch_28_break_playbook
description: Verified breakout tactical execution playbook for XTIUSD.
symbol: XTIUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 13.85
profit_factor: 1.46
max_drawdown_pct: 10.3
win_rate: 0.429
---

# XTIUSD Empirical Playbook: Lon Dch 28 Break Strategy

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 13.85 (Zero-Lookahead simulation)
- **Profit Factor**: 1.46 (70 verified trade executions)
- **Max Drawdown**: 10.3% (Institutional risk profile)
- **Total PnL Return**: +19.0%
- **Win Rate**: 42.9% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
