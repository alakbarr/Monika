---
name: xbrusd_triple_ema_pullback_playbook
description: Triple EMA alignment pullback continuation for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 2.21
profit_factor: 1.2
max_drawdown_pct: 12.73
win_rate: 0.432
---

# XBRUSD Empirical Playbook: Triple EMA Alignment Pullback Continuation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.21 (Zero-Lookahead simulation)
- **Profit Factor**: 1.20 (146 verified trade executions)
- **Max Drawdown**: 12.7% (Institutional risk profile)
- **Total PnL Return**: +15.9%
- **Win Rate**: 43.2% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Bullish alignment: EMA 9 > EMA 21 > EMA 50.
- Bearish alignment: EMA 9 < EMA 21 < EMA 50.
- Long Trigger: Low tests EMA 21, candle closes higher than open and above EMA 21.
- Short Trigger: High tests EMA 21, candle closes lower than open and below EMA 21.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50.
- Invalidate if ribbon order flips prior to entry.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
