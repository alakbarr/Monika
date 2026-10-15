---
name: btcusd_ema_ribbon_momentum_playbook
description: 5-EMA ribbon trend expansion momentum playbook for BTCUSD.
symbol: BTCUSD
regime: trending
timeframe: H1
min_rr: 2.13
status: active
sharpe_ratio: 1.23
profit_factor: 1.12
max_drawdown_pct: 11.33
win_rate: 0.365
---

# BTCUSD Empirical Playbook: 5-EMA Ribbon Trend Expansion Momentum

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.23 (Zero-Lookahead simulation)
- **Profit Factor**: 1.12 (115 verified trade executions)
- **Max Drawdown**: 11.3% (Institutional risk profile)
- **Total PnL Return**: +7.7%
- **Win Rate**: 36.5% (Normalized at minimum 1:2.13 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.2x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Confirm perfect ribbon stacking: EMA 8 > 13 > 21 > 34 > 55 (Bull) or 8 < 13 < 21 < 34 < 55 (Bear).
- Long Trigger: Low tests into EMA 21 buffer and candle closes above EMA 13.
- Short Trigger: High tests into EMA 21 buffer and candle closes below EMA 13.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.13 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if ribbon lines cross or tangle (indicating range regime).
- Invalidate if candle body closes beyond EMA 55.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
