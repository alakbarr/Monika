---
name: audusd_gap_fill_reversion_playbook
description: Session opening gap fill mean reversion for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.13
status: active
sharpe_ratio: 2.94
profit_factor: 1.32
max_drawdown_pct: 5.06
win_rate: 0.425
---

# AUDUSD Empirical Playbook: Session Opening Gap Fill Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.94 (Zero-Lookahead simulation)
- **Profit Factor**: 1.32 (80 verified trade executions)
- **Max Drawdown**: 5.1% (Institutional risk profile)
- **Total PnL Return**: +15.1%
- **Win Rate**: 42.5% (Normalized at minimum 1:2.13 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.2x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Detect opening price gap relative to prior bar close >= 0.35x 14-period ATR.
- Long Trigger: Downside gap opens below prior close and prints a bullish rejection candle.
- Short Trigger: Upside gap opens above prior close and prints a bearish rejection candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.13 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if gap extends beyond 1.5x ATR indicating fundamental runaway breakaway gap.
- Invalidate if gap is not filled within specified holding horizon.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
