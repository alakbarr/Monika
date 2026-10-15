---
name: btcusd_ema50_trend_bounce_playbook
description: Institutional 50-EMA trend boundary bounce for BTCUSD.
symbol: BTCUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.27
profit_factor: 1.16
max_drawdown_pct: 11.63
win_rate: 0.389
---

# BTCUSD Empirical Playbook: Institutional 50-EMA Trend Boundary Bounce

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.27 (Zero-Lookahead simulation)
- **Profit Factor**: 1.16 (108 verified trade executions)
- **Max Drawdown**: 11.6% (Institutional risk profile)
- **Total PnL Return**: +9.7%
- **Win Rate**: 38.9% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Macro trend filter: Close > EMA 200 (Bull) or Close < EMA 200 (Bear).
- Long Trigger: Low touches EMA 50, rejects, and candle closes bullish above EMA 50.
- Short Trigger: High touches EMA 50, rejects, and candle closes bearish below EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully across EMA 50.
- Invalidate if 200 EMA slope turns flat or opposing.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
