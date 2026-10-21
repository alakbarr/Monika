---
name: xauusd_donchian_16_breakout_playbook
description: Verified breakout tactical execution playbook for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: null
legacy_t_statistic: 10.6
profit_factor: 1.33
max_drawdown_pct: 10.5
win_rate: 0.448
---

# XAUUSD Empirical Playbook: Donchian 16 Breakout Strategy

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 10.60 (Zero-Lookahead simulation)
- **Profit Factor**: 1.33 (241 verified trade executions)
- **Max Drawdown**: 10.5% (Institutional risk profile)
- **Total PnL Return**: +50.3%
- **Win Rate**: 44.8% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.0x ATR, Max Holding = 18 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
