---
name: usdjpy_gap_fill_reversion_playbook
description: Session opening gap fill mean reversion for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.4
status: active
sharpe_ratio: null
legacy_t_statistic: 18.21
profit_factor: 1.65
max_drawdown_pct: 11.6
win_rate: 0.422
---

# USDJPY Empirical Playbook: Session Opening Gap Fill Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 18.21 (Zero-Lookahead simulation)
- **Profit Factor**: 1.65 (83 verified trade executions)
- **Max Drawdown**: 11.6% (Institutional risk profile)
- **Total PnL Return**: +37.6%
- **Win Rate**: 42.2% (Normalized at minimum 1:2.4 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.5x ATR, Take-Profit = 1.2x ATR, Max Holding = 10 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Detect opening price gap relative to prior bar close >= 0.35x 14-period ATR.
- Long Trigger: Downside gap opens below prior close and prints a bullish rejection candle.
- Short Trigger: Upside gap opens above prior close and prints a bearish rejection candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.4 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if gap extends beyond 1.5x ATR indicating fundamental runaway breakaway gap.
- Invalidate if gap is not filled within specified holding horizon.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 10 bars.
