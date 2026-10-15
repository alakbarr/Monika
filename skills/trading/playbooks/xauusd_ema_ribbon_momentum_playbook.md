---
name: xauusd_ema_ribbon_momentum_playbook
description: 5-EMA ribbon trend expansion momentum playbook for XAUUSD.
symbol: XAUUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.85
profit_factor: 1.32
max_drawdown_pct: 11.63
win_rate: 0.406
---

# XAUUSD Empirical Playbook: 5-EMA Ribbon Trend Expansion Momentum

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.85 (Zero-Lookahead simulation)
- **Profit Factor**: 1.32 (96 verified trade executions)
- **Max Drawdown**: 11.6% (Institutional risk profile)
- **Total PnL Return**: +19.2%
- **Win Rate**: 40.6% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Confirm perfect ribbon stacking: EMA 8 > 13 > 21 > 34 > 55 (Bull) or 8 < 13 < 21 < 34 < 55 (Bear).
- Long Trigger: Low tests into EMA 21 buffer and candle closes above EMA 13.
- Short Trigger: High tests into EMA 21 buffer and candle closes below EMA 13.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if ribbon lines cross or tangle (indicating range regime).
- Invalidate if candle body closes beyond EMA 55.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
