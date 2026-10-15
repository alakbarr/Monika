---
name: xbrusd_ema_retest_macd_playbook
description: EMA pullback with MACD confluence for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.57
status: active
sharpe_ratio: 2.56
profit_factor: 1.2
max_drawdown_pct: 8.13
win_rate: 0.45
---

# XBRUSD Empirical Playbook: EMA 21 Trend Retest with MACD Confluence

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.56 (Zero-Lookahead simulation)
- **Profit Factor**: 1.20 (111 verified trade executions)
- **Max Drawdown**: 8.1% (Institutional risk profile)
- **Total PnL Return**: +12.0%
- **Win Rate**: 45.0% (Normalized at minimum 1:1.57 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.2x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, Low tests EMA 21, Close > EMA 21, MACD Hist > 0.
- Short Trigger: Close < EMA 50, High tests EMA 21, Close < EMA 21, MACD Hist < 0.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.57 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes completely across EMA 50.
- Invalidate if MACD histogram turns against trend direction.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
